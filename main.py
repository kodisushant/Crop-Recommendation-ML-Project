"""Crop Advisor - FastAPI backend. Serves the API (/docs) AND the website (templates + static)."""
import os, time, logging, requests, numpy as np, pandas as pd
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Dict, Literal
import re
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sklearn.tree import DecisionTreeClassifier, export_text
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import predictor as P
import crop_data as C

BASE = Path(__file__).parent
log = logging.getLogger("crop-advisor")
app = FastAPI(title="Crop Advisor API", version="1.0",
              description="AI crop recommendation with confidence, out-of-range detection and planning tools.")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
FEATURES = P.FEATURES
DF = P.DF
API_KEY = os.getenv("DATA_GOV_API_KEY", "")
RESOURCE = os.getenv("DATA_GOV_RESOURCE_ID", "9ef84268-d588-465a-a308-a864a43d0070")
REQ_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# ---------- dataset-derived ranges ----------
RANGES = {}
for crop, g in DF.groupby("label"):
    RANGES[crop] = {f: {"ideal": [round(float(g[f].quantile(.10)), 2), round(float(g[f].quantile(.90)), 2)],
                        "acceptable": [round(float(g[f].quantile(.025)), 2), round(float(g[f].quantile(.975)), 2)]}
                    for f in FEATURES}


# ---------- schemas ----------
class Conditions(BaseModel):
    N: float = Field(..., ge=0, le=300, description="Nitrogen (dataset units)")
    P: float = Field(..., ge=0, le=300, description="Phosphorus")
    K: float = Field(..., ge=0, le=400, description="Potassium")
    temperature: float = Field(..., ge=-5, le=55, description="°C")
    humidity: float = Field(..., ge=0, le=100, description="%")
    ph: float = Field(..., ge=0, le=14)
    rainfall: float = Field(..., ge=0, le=1000, description="mm")
    state: Optional[str] = Field(None, description="Location only - NOT an ML input")

class DistrictLocation(BaseModel):
    state: str = Field(..., min_length=2, max_length=80)
    district: str = Field(..., min_length=2, max_length=120)

class RecommendationRequest(BaseModel):
    N: float = Field(..., ge=0, le=300)
    P: float = Field(..., ge=0, le=300)
    K: float = Field(..., ge=0, le=400)
    ph: float = Field(..., ge=0, le=14)
    location: DistrictLocation

class Change(BaseModel):
    mode: Literal["set", "add", "pct"] = "set"
    value: float

class WhatIf(BaseModel):
    base: Conditions
    changes: Dict[str, Change]

class Sweep(BaseModel):
    base: Conditions
    feature: str
    start: float
    end: float
    steps: int = Field(15, ge=3, le=60)

class LandCheck(BaseModel):
    crop: str
    conditions: Conditions

class Fertilizer(BaseModel):
    crop: str
    N: float = Field(..., ge=0, le=300); P: float = Field(..., ge=0, le=300); K: float = Field(..., ge=0, le=400)
    area_ha: float = Field(1.0, gt=0, le=10000)

class Profit(BaseModel):
    crop: str
    area_ha: float = Field(1.0, gt=0, le=10000)
    yield_q_ha: Optional[float] = Field(None, gt=0)
    price_per_q: Optional[float] = Field(None, gt=0)
    cost_per_ha: Optional[float] = Field(None, ge=0)
    duration_days: Optional[int] = Field(None, gt=0, le=1500)
    state: Optional[str] = None

class Rotation(BaseModel):
    previous_crop: str
    next_season: Optional[Literal["Kharif", "Rabi", "Zaid"]] = None
    conditions: Optional[Conditions] = None


def vals(c: Conditions): return {f: getattr(c, f) for f in FEATURES}
def need_crop(c):
    c = c.lower().strip()
    if c not in C.CROPS: raise HTTPException(404, f"Unknown crop '{c}'. See /crops")
    return c

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    if isinstance(exc, HTTPException): raise exc
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

def run_predict(v):
    try: return P.predict(v)
    except ValueError as e: raise HTTPException(422, str(e))


# ---------- pages ----------
PAGES = {"": "index", "dashboard": "dashboard", "recommendation": "recommendation", "ideal-conditions": "ideal_conditions",
         "land-check": "land_check", "fertilizer": "fertilizer", "market": "market", "profit": "profit",
         "what-if": "what_if", "rotation": "rotation", "model-performance": "model_performance"}
def _page(name):
    def h(request: Request): return templates.TemplateResponse(request, f"{name}.html", {"page": name})
    return h
for path, name in PAGES.items():
    app.add_api_route("/" + path, _page(name), methods=["GET"], include_in_schema=False)

@app.get("/health", include_in_schema=False)
def health(): return {"status": "ok"}


# ---------- general ----------
@app.get("/meta", tags=["General"])
def meta():
    m = P.METRICS
    return {"app": "Crop Advisor", "n_crops": len(P.CLASSES), "features": FEATURES, "best_model": m["best_model"],
            "selected_by_rule": m.get("selected_by_rule"), "tied_models": m.get("tied_models"),
            "test_accuracy": m["test"]["accuracy"], "macro_f1": m["test"]["macro_f1"], "rows": m["dataset"]["rows"],
            "market_api_configured": bool(API_KEY),
            "note": "State, season and soil type are NOT model inputs (not in the dataset)."}

_states = {"t": 0, "data": None}
_weather_cache = {}
RAINFALL_PERIOD_DAYS = 365
MODEL_RAINFALL_MIN = float(P.ood["min"]["rainfall"])
MODEL_RAINFALL_MAX = float(P.ood["max"]["rainfall"])
_districts_cache = {"t": 0, "data": None}
DISTRICTS_DATA_URL = "https://raw.githubusercontent.com/codingmation/indian-states-districts/main/data/india_states_districts.min.json"
@app.get("/states", tags=["General"])
def states():
    """Indian states/UTs. Tries the data.gov.in Agmarknet dataset (needs key); falls back to a local list."""
    if _states["data"] and time.time() - _states["t"] < 86400: return _states["data"]
    out = {"source": "local fallback list", "states": C.STATES}
    if API_KEY:
        try:
            r = requests.get(f"https://api.data.gov.in/resource/{RESOURCE}", headers=REQ_HEADERS, timeout=15,
                params={"api-key": API_KEY, "format": "json", "limit": 1000, "fields": "state"})
            r.raise_for_status()
            live = {x["state"].strip() for x in r.json().get("records", []) if x.get("state")}
            names = sorted(s for s in C.STATES if s in live or s.replace("&", "and") in live)
            if len(names) >= 5: out = {"source": "data.gov.in (live) merged with official list", "states": C.STATES}
        except Exception as e:
            log.warning("states API failed: %s", e)
    _states.update(t=time.time(), data=out)
    return out

def normalized_place_name(value: str):
    return re.sub(r"[^a-z]", "", value.lower().replace("&", "and").replace("unionterritory", "").replace("ut", ""))

def district_data():
    """Load the complete India state/district catalog and cache it for one day."""
    if _districts_cache["data"] and time.time() - _districts_cache["t"] < 86400:
        return _districts_cache["data"]
    try:
        response = requests.get(DISTRICTS_DATA_URL, timeout=15)
        response.raise_for_status()
        catalog = response.json()
        if isinstance(catalog, dict):
            catalog = catalog.get("states", [])
        data = {
            normalized_place_name(row["name"]): sorted(
                district["name"] if isinstance(district, dict) else district
                for district in row["districts"]
            )
            for row in catalog
        }
    except (requests.RequestException, KeyError, TypeError, ValueError):
        raise HTTPException(503, "District list is temporarily unavailable. Please try again.")
    _districts_cache.update(t=time.time(), data=data)
    return data

@app.get("/districts", tags=["General"])
def districts(state: str):
    """Return all districts for the selected State / UT."""
    state = state.strip()
    if state not in C.STATES:
        raise HTTPException(422, "Choose a valid State / UT")
    requested = normalized_place_name(state)
    catalog = district_data()
    match = next((districts for name, districts in catalog.items() if name == requested or requested in name or name in requested), None)
    if match is None:
        raise HTTPException(404, "No district list is available for that State / UT")
    return match

def district_coordinates(location: DistrictLocation):
    """Resolve a selected Indian district to coordinates for the weather API."""
    try:
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location.district, "count": 20, "language": "en", "format": "json", "countryCode": "IN"},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException:
        raise HTTPException(503, "District location lookup is temporarily unavailable. Please try again.")

    wanted = normalized_place_name(location.state)
    for place in response.json().get("results", []):
        admin1 = normalized_place_name(place.get("admin1") or "")
        if place.get("country_code") == "IN" and (admin1 == wanted or wanted in admin1 or admin1 in wanted):
            return float(place["latitude"]), float(place["longitude"])
    raise HTTPException(422, "Could not locate that district. Please choose another district from the list.")

def current_weather(latitude: float, longitude: float):
    """Fetch current weather and a 365-day precipitation total for a district."""
    key = (round(latitude, 3), round(longitude, 3))
    hit = _weather_cache.get(key)
    if hit and time.time() - hit["t"] < 15 * 60:
        return hit["data"]
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": latitude, "longitude": longitude,
                    "current": "temperature_2m,relative_humidity_2m,precipitation", "timezone": "auto"},
            timeout=10,
        )
        response.raise_for_status()
        current = response.json()["current"]
        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=RAINFALL_PERIOD_DAYS - 1)
        rainfall_response = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={"latitude": latitude, "longitude": longitude, "daily": "precipitation_sum",
                    "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "timezone": "auto"},
            timeout=20,
        )
        rainfall_response.raise_for_status()
        daily_rainfall = rainfall_response.json()["daily"]["precipitation_sum"]
        annual_rainfall = round(sum(float(value or 0) for value in daily_rainfall), 1)
        monthly_rainfall = annual_rainfall / 12
        # The trained rainfall feature is on a monthly-scale (20.2–298.6 mm),
        # while the weather API returns a 365-day total. Convert before model use
        # and use the model's supported maximum whenever the normalized value is
        # outside its learned range, so rainfall alone cannot reject a request.
        rainfall_outside_model_range = not MODEL_RAINFALL_MIN <= monthly_rainfall <= MODEL_RAINFALL_MAX
        model_rainfall = MODEL_RAINFALL_MAX if rainfall_outside_model_range else monthly_rainfall
        data = {"temperature": float(current["temperature_2m"]),
                "humidity": float(current["relative_humidity_2m"]),
                "rainfall": round(model_rainfall, 1), "annual_rainfall": annual_rainfall,
                "monthly_rainfall": round(monthly_rainfall, 1),
                "rainfall_capped": rainfall_outside_model_range,
                "rainfall_maximum": round(MODEL_RAINFALL_MAX, 1),
                "rainfall_period_days": RAINFALL_PERIOD_DAYS, "observed_at": current["time"], "source": "Open-Meteo"}
    except (requests.RequestException, KeyError, TypeError, ValueError):
        raise HTTPException(503, "Current weather is temporarily unavailable. Please try again.")
    _weather_cache[key] = {"t": time.time(), "data": data}
    return data

@app.get("/crops", tags=["General"])
def crops():
    return [{"crop": c, "family": d["family"], "seasons": d["seasons"], "duration_days": d["duration_days"],
             "reference_price": d["ref_price"]} for c, d in C.CROPS.items()]

@app.get("/crops/{crop}", tags=["General"])
def crop_detail(crop: str):
    crop = need_crop(crop)
    return {"crop": crop, **C.CROPS[crop], "ranges": RANGES[crop], "ranges_source": "10th–90th (ideal) and 2.5th–97.5th (acceptable) percentiles of the uploaded dataset - not verified agronomic recommendations",
            "reference_note": "Seasons, duration, price, yield, cost and soil are indicative reference values; confirm with ICAR / state agricultural university."}


# ---------- prediction ----------
@app.post("/predict", tags=["Prediction"])
def predict(r: RecommendationRequest):
    latitude, longitude = district_coordinates(r.location)
    weather = current_weather(latitude, longitude)
    conditions = Conditions(N=r.N, P=r.P, K=r.K, ph=r.ph, state=r.location.state,
                            temperature=weather["temperature"], humidity=weather["humidity"], rainfall=weather["rainfall"])
    return {**run_predict(vals(conditions)), "location": {"state": r.location.state, "district": r.location.district},
            "weather": weather}

def apply_changes(base, changes):
    new = dict(base)
    for f, ch in changes.items():
        if f not in FEATURES: raise HTTPException(422, f"Unknown feature '{f}'")
        new[f] = ch.value if ch.mode == "set" else base[f] + ch.value if ch.mode == "add" else base[f] * (1 + ch.value / 100)
    return new

@app.post("/what-if", tags=["What-if"])
def what_if(w: WhatIf):
    b = vals(w.base); n = apply_changes(b, w.changes)
    try: b, n = P.validate(b), P.validate(n)
    except ValueError as e: raise HTTPException(422, str(e))
    pb, pn = P.probabilities(b), P.probabilities(n)
    delta = sorted([{"crop": c, "before": round(float(x), 4), "after": round(float(y), 4), "change": round(float(y - x), 4)}
                    for c, x, y in zip(P.CLASSES, pb, pn)], key=lambda r: -abs(r["change"]))[:8]
    ob, on = P.predict(b), P.predict(n)
    return {"original": {"input": b, "status": ob["status"], "crop": ob["crop"], "top_k": ob["top_k"]},
            "modified": {"input": n, "status": on["status"], "crop": on["crop"], "top_k": on["top_k"]},
            "top_crop_changed": ob["crop"] != on["crop"], "probability_changes": delta,
            "influential_changes": [{"feature": f, "from": b[f], "to": round(n[f], 3)} for f in w.changes],
            "explanation_modified": on["explanation"],
            "note": "Shows how the MODEL responds, not agronomic cause and effect."}

@app.post("/what-if/sweep", tags=["What-if"])
def sweep(s: Sweep):
    if s.feature not in FEATURES: raise HTTPException(422, f"Unknown feature '{s.feature}'")
    if s.start >= s.end: raise HTTPException(422, "start must be below end")
    base = vals(s.base); rows, prev = [], None; tips = []
    for x in np.linspace(s.start, s.end, s.steps):
        v = dict(base); v[s.feature] = float(x)
        try: v = P.validate(v)
        except ValueError as e: raise HTTPException(422, str(e))
        p = P.probabilities(v); tk = P.top_k(p, 3); chk = P.check_range(v)
        rows.append({"value": round(float(x), 3), "top_crop": tk[0]["crop"], "top_probability": tk[0]["probability"],
                     "out_of_range": chk["out_of_range"], "probabilities": {c: round(float(q), 4) for c, q in zip(P.CLASSES, p)}})
        if prev and prev != tk[0]["crop"]: tips.append({"between": [rows[-2]["value"], rows[-1]["value"]], "from": prev, "to": tk[0]["crop"]})
        prev = tk[0]["crop"]
    return {"feature": s.feature, "points": rows, "tipping_points": tips}


# ---------- land suitability ----------
@app.post("/land-check", tags=["Land"])
def land_check(r: LandCheck):
    crop = need_crop(r.crop); v = vals(r.conditions); rows, score = [], 0
    tips = {"N": "nitrogen", "P": "phosphorus", "K": "potassium", "temperature": "temperature", "humidity": "humidity",
            "ph": "soil pH", "rainfall": "rainfall / irrigation"}
    for f in FEATURES:
        rg = RANGES[crop][f]; x = v[f]
        if rg["ideal"][0] <= x <= rg["ideal"][1]: st, pts = "IDEAL", 1.0
        elif rg["acceptable"][0] <= x <= rg["acceptable"][1]: st, pts = "BORDERLINE", 0.5
        else: st, pts = "OUTSIDE", 0.0
        score += pts
        adv = None
        if st != "IDEAL":
            tgt = rg["ideal"]; adv = f"{'Increase' if x < tgt[0] else 'Reduce'} {tips[f]} towards {tgt[0]}–{tgt[1]}"
        rows.append({"feature": f, "value": x, "status": st, "ideal": rg["ideal"], "acceptable": rg["acceptable"], "advice": adv})
    score = round(score / len(FEATURES) * 100)
    outside = sum(r_["status"] == "OUTSIDE" for r_ in rows)
    verdict = "SUITABLE" if score >= 80 and outside == 0 else "MARGINAL" if score >= 50 and outside <= 2 else "NOT_SUITABLE"
    ml = run_predict(v)
    p_crop = ml["all_probabilities"].get(crop) if ml.get("all_probabilities") else None
    return {"crop": crop, "score": score, "verdict": verdict, "features": rows,
            "improvements": [x["advice"] for x in rows if x["advice"]],
            "ml": {"status": ml["status"], "predicted_crop": ml["crop"], "probability_for_selected_crop": p_crop, "top_k": ml["top_k"]},
            "note": "Ranges are dataset percentiles, not verified agronomic limits."}


# ---------- fertilizer ----------
@app.post("/fertilizer", tags=["Fertilizer"])
def fertilizer(r: Fertilizer):
    crop = need_crop(r.crop); d = C.CROPS[crop]; soil = {"N": r.N, "P": r.P, "K": r.K}
    cls, factor = {}, {"LOW": 1.25, "MEDIUM": 1.0, "HIGH": 0.75}
    for f in "NPK":
        lo, hi = RANGES[crop][f]["ideal"]
        cls[f] = "LOW" if soil[f] < lo else "HIGH" if soil[f] > hi else "MEDIUM"
    need = {"N": d["N"] * factor[cls["N"]], "P2O5": d["P2O5"] * factor[cls["P"]], "K2O": d["K2O"] * factor[cls["K"]]}
    dap = need["P2O5"] / 0.46; urea = max(need["N"] - 0.18 * dap, 0) / 0.46; mop = need["K2O"] / 0.60
    a = r.area_ha; q = {"urea_kg": urea * a, "dap_kg": dap * a, "mop_kg": mop * a}
    cost = q["urea_kg"] * C.FERT_PRICE["urea"] + q["dap_kg"] * C.FERT_PRICE["dap"] + q["mop_kg"] * C.FERT_PRICE["mop"]
    dur = d["duration_days"]; perennial = d["seasons"] == "Perennial"
    top = [{"when": f"~{int(dur*.25)} days after planting" if not perennial else "start of growth flush", "urea_kg": round(urea * a * .25, 1)},
           {"when": f"~{int(dur*.5)} days after planting" if not perennial else "mid-season", "urea_kg": round(urea * a * .25, 1)}]
    return {"crop": crop, "area_ha": a, "soil_class": cls, "adjustment": {k: f"x{factor[v]}" for k, v in cls.items()},
            "nutrient_need_kg_ha": {k: round(v, 1) for k, v in need.items()}, "recommended_dose_kg_ha": {k: d[k] for k in ("N", "P2O5", "K2O")},
            "quantity": {k: round(v, 1) for k, v in q.items()}, "estimated_cost_inr": round(cost),
            "basal": {"urea_kg": round(urea * a * .5, 1), "dap_kg": round(q["dap_kg"], 1), "mop_kg": round(q["mop_kg"], 1)},
            "top_dressing": top, "prices_inr_per_kg": C.FERT_PRICE,
            "sponsored": {"label": "SPONSORED", "items": C.SPONSORS, "note": "Sponsored products never change the quantities above."},
            "assumptions": ["Urea 46% N, DAP 18-46-0, MOP 60% K2O; N from DAP is deducted from urea.",
                            "Soil class compares your N/P/K with the crop's dataset range (dataset units, not lab kg/ha).",
                            "Doses and prices are indicative - confirm with ICAR / your state agricultural university or a soil test report."]}


# ---------- market ----------
_mcache = {}
def ref_row(crop):
    return {"crop": crop, "price_unit": "Rs/quintal", "reference_price": C.CROPS[crop]["ref_price"]}

@app.get("/market/{crop}", tags=["Market"])
def market(crop: str, state: Optional[str] = None):
    crop = need_crop(crop); key = (crop, state or "")
    hit = _mcache.get(key)
    if hit and time.time() - hit["t"] < 6 * 3600:
        return {**hit["data"], "cached": True}
    data = {"crop": crop, "state": state, "type": "reference", "records": [], **ref_row(crop),
            "message": "Reference price (MSP / indicative) - NOT live market data.",
            "retrieved_on": time.strftime("%Y-%m-%d")}
    if API_KEY:
        try:
            params = {"api-key": API_KEY, "format": "json", "limit": 50, "filters[commodity]": C.AGMARK[crop]}
            if state: params["filters[state]"] = state
            r = requests.get(f"https://api.data.gov.in/resource/{RESOURCE}", headers=REQ_HEADERS, params=params, timeout=15)
            r.raise_for_status()
            recs = [{"state": x.get("state"), "market": x.get("market"), "date": x.get("arrival_date"),
                     "min": float(x["min_price"]), "max": float(x["max_price"]), "modal": float(x["modal_price"])}
                    for x in r.json().get("records", []) if x.get("modal_price") not in (None, "", "NA")]
            if recs:
                data.update(type="live", records=recs, message="Live mandi prices (Agmarknet via data.gov.in), Rs/quintal.",
                            latest_market_date=max(x["date"] for x in recs if x["date"]))
            else: data["message"] += " (No live records found for this crop/state.)"
        except Exception as e:
            log.warning("market API failed: %s", e); data["message"] += " (Live API unavailable.)"
    elif not API_KEY: data["message"] += " (Set DATA_GOV_API_KEY to enable live prices.)"
    _mcache[key] = {"t": time.time(), "data": data}
    return {**data, "cached": False}


# ---------- profit ----------
@app.post("/profit", tags=["Profit"])
def profit(r: Profit):
    crop = need_crop(r.crop); d = C.CROPS[crop]
    price = r.price_per_q; src = "user"
    if price is None:
        m = market(crop, r.state); src = m["type"]
        price = float(np.mean([x["modal"] for x in m["records"]])) if m["type"] == "live" else d["ref_price"]
        src = "live market average" if m["type"] == "live" else "reference price"
    y = r.yield_q_ha or d["yield_q_ha"]; cost = (r.cost_per_ha or d["cost_ha"]) * r.area_ha
    dur = r.duration_days or d["duration_days"]; months = dur / 30
    sc = {}
    for k, f in C.YIELD_FACTORS.items():
        tot = y * f * r.area_ha; rev = tot * price
        sc[k] = {"yield_q_ha": round(y * f, 2), "total_yield_q": round(tot, 1), "revenue": round(rev), "profit": round(rev - cost),
                 "profit_per_month": round((rev - cost) / months)}
    return {"crop": crop, "area_ha": r.area_ha, "price_per_q": round(price, 2), "price_source": src, "total_cost": round(cost),
            "duration_days": dur, "scenarios": sc, "break_even_yield_q_ha": round(cost / price / r.area_ha, 2),
            "break_even_price_per_q": round(cost / (y * r.area_ha), 2),
            "note": "Estimates only, not guaranteed earnings. Perennial crops: cost/yield shown per year, establishment cost ignored."}


# ---------- rotation ----------
@app.post("/rotation", tags=["Rotation"])
def rotation(r: Rotation):
    prev = need_crop(r.previous_crop); pd_ = C.CROPS[prev]; ml = None
    if r.conditions:
        pr = P.probabilities(P.validate(vals(r.conditions))); ml = dict(zip(P.CLASSES, pr))
    out = []
    for c, d in C.CROPS.items():
        if c == prev: continue
        if r.next_season and r.next_season not in d["seasons"] and d["seasons"] != "Perennial": continue
        if d["seasons"] == "Perennial" and pd_["seasons"] != "Perennial" and not r.next_season is None: continue
        s, why = 0, []
        if d["family"] != pd_["family"]: s += 3; why.append("different crop family (breaks pest/disease cycle)")
        else: s -= 4; why.append("same family as previous crop")
        if d["legume"] and not pd_["legume"]: s += 3; why.append("legume after non-legume (fixes nitrogen)")
        if pd_["legume"] and not d["legume"]: s += 2; why.append("non-legume uses the nitrogen left by the legume")
        if pd_["heavy"] and d["heavy"]: s -= 3; why.append("two heavy feeders back-to-back")
        if pd_["heavy"] and not d["heavy"]: s += 1; why.append("lighter feeder after a heavy feeder")
        if c in C.SEQUENCES.get(prev, []): s += 3; why.append("commonly practised sequence")
        if ml: s += 4 * float(ml[c]); why.append(f"model suitability for stated climate: {ml[c]:.0%}")
        out.append({"crop": c, "score": round(s, 2), "reasons": why, "seasons": d["seasons"], "duration_days": d["duration_days"]})
    out.sort(key=lambda x: -x["score"])
    return {"previous_crop": prev, "suggestions": out[:5], "disclaimer": "Simplified rules - not a substitute for professional agronomic advice."}


# ---------- metrics ----------
@app.get("/metrics", tags=["Model performance"])
def metrics():
    m = P.METRICS
    return {k: m[k] for k in ("best_model", "selected_by_rule", "tied_models", "tie_tolerance", "comparison", "test", "dataset")}

@app.get("/metrics/classwise", tags=["Model performance"])
def classwise(): return P.METRICS["classwise"]

@app.get("/metrics/confusion-matrix", tags=["Model performance"])
def cm(): return {"classes": P.METRICS["classes"], "matrix": P.METRICS["confusion_matrix"]}

@app.get("/metrics/robustness", tags=["Model performance"])
def robustness(): return P.robustness()

_rules = {}
@app.get("/metrics/decision-rules", tags=["Model performance"])
def rules():
    if not _rules:
        dt = DecisionTreeClassifier(max_depth=4, random_state=42).fit(DF[FEATURES], DF["label"])
        _rules.update(depth=4, accuracy_on_data=round(float(dt.score(DF[FEATURES], DF["label"])), 4),
                      rules=export_text(dt, feature_names=FEATURES),
                      note="A shallow, human-readable tree trained for illustration; the production model is " + P.METRICS["best_model"])
    return _rules

@app.get("/plots/{name}.png", tags=["Model performance"])
def plot(name: str):
    f = BASE / "plots" / f"{Path(name).name}.png"
    if not f.exists(): raise HTTPException(404, "Plot not found")
    return FileResponse(f)

if __name__ == "__main__":
    import uvicorn; uvicorn.run("main:app", host="127.0.0.1", port=int(os.getenv("PORT", 8000)))
