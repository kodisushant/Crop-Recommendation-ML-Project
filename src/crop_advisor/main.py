"""Crop Advisor - FastAPI backend. Serves the API (/docs) AND the website (templates + static)."""
import os, time, logging, requests, numpy as np, pandas as pd
from difflib import get_close_matches
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Dict, Literal
import re
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sklearn.tree import DecisionTreeClassifier, export_text
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
from . import predictor as P
from . import crop_data as C
from .schemes_db import get_schemes_for_crop_and_state

BASE = Path(__file__).resolve().parents[2]
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
    rainfall: float = Field(..., ge=0, le=1000, description="Rainfall in mm")
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
    N: Optional[float] = Field(None, ge=0, le=300)
    P: Optional[float] = Field(None, ge=0, le=300)
    K: Optional[float] = Field(None, ge=0, le=400)
    ph: Optional[float] = Field(None, ge=0, le=14)
    location: Optional[DistrictLocation] = None
    conditions: Optional[Conditions] = None

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
PAGES = {
    "": "index",
    "dashboard": "dashboard",
    "recommendation": "recommendation",
    "ideal-conditions": "ideal_conditions",
    "land-check": "land_check",
    "fertilizer": "fertilizer",
    "market": "market",
    "weather-forecast": "weather",
    "profit": "profit",
    "what-if": "what_if",
    "rotation": "rotation",
    "model-performance": "model_performance",
    "government-schemes": "schemes",
}


def _page(name):
    def h(request: Request):
        return templates.TemplateResponse(request, f"{name}.html", {"page": name})
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
_coordinate_cache = {}
_rainfall_forecast_cache = {}
_groundwater_data = None
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
    cleaned = value.lower().replace("&", "and")
    cleaned = re.sub(r"\b(ut|union\s*territory)\b", "", cleaned)
    return re.sub(r"[^a-z]", "", cleaned)

DISTRICT_ALIASES = {
    "goa": {"goanorth": "northgoa", "goasouth": "southgoa"},
    "andhrapradesh": {"kadapa": "ysr", "ysrkadapa": "ysr"},
    "telangana": {"komarambheemasifabad": "kumurambheemasifabad", "jagtial": "jagitial",
                  "peddapalle": "peddapalli", "rajannasircilla": "rajannasircilla"},
    "westbengal": {"haora": "howrah", "hugli": "hooghly", "puruliya": "purulia",
                    "kolkatta": "kolkata", "kochbihar": "coochbehar"},
}

def district_token_key(value: str):
    return "".join(sorted(re.findall(r"[a-z]+", value.lower())))

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

# Known district coordinates and headquarters fallbacks for districts
# that are not indexed directly in Open-Meteo's geocoding dataset
DISTRICT_COORDINATE_FALLBACKS = {
    # Goa districts (North Goa HQ: Panaji, South Goa HQ: Margao)
    ("goa", "northgoa"): (15.4989, 73.8278),
    ("goa", "southgoa"): (15.2832, 73.9862),
    ("goa", "panaji"): (15.4989, 73.8278),
    ("goa", "panjim"): (15.4989, 73.8278),
    ("goa", "margao"): (15.2832, 73.9862),
    ("goa", "madgaon"): (15.2832, 73.9862),
    ("goa", "goa"): (15.4989, 73.8278),

    # Andaman and Nicobar Islands
    ("andamanandnicobarislands", "nicobar"): (9.155, 92.756),
    ("andamanandnicobarislands", "northandmiddleandaman"): (12.923, 92.898),
    ("andamanandnicobarislands", "southandaman"): (11.623, 92.726),

    # Lakshadweep
    ("lakshadweep", "lakshadweep"): (10.567, 72.641),

    # Ladakh
    ("ladakh", "leh"): (34.1526, 77.5771),
    ("ladakh", "kargil"): (34.5539, 76.1349),

    # Chandigarh
    ("chandigarh", "chandigarh"): (30.7333, 76.7794),

    # Dadra and Nagar Haveli and Daman and Diu
    ("dadraandnagarhavelianddamananddiu", "dadraandnagarhaveli"): (20.2763, 73.0083),
    ("dadraandnagarhavelianddamananddiu", "daman"): (20.3974, 72.8328),
    ("dadraandnagarhavelianddamananddiu", "diu"): (20.7144, 70.9874),
}

# State-level center coordinates for general fallback
STATE_CENTERS = {
    "goa": (15.4989, 73.8278),
    "andamanandnicobarislands": (11.6234, 92.7265),
    "chandigarh": (30.7333, 76.7794),
    "dadraandnagarhavelianddamananddiu": (20.3974, 72.8328),
    "delhi": (28.6139, 77.2090),
    "lakshadweep": (10.567, 72.641),
    "ladakh": (34.1526, 77.5771),
    "puducherry": (11.9416, 79.8083),
}

def district_coordinates(location: DistrictLocation):
    """Resolve a selected Indian district to coordinates for the weather API."""
    state_key = normalized_place_name(location.state)
    dist_key = normalized_place_name(location.district)

    catalog = district_data()
    districts_for_state = next((items for key, items in catalog.items()
                                if key == state_key or state_key in key or key in state_key), None)
    if not districts_for_state or not any(normalized_place_name(name) == dist_key for name in districts_for_state):
        raise HTTPException(422, "Choose a district from the suggestions for the selected State / UT.")

    cache_key = (state_key, dist_key)
    hit = _coordinate_cache.get(cache_key)
    if hit and time.time() - hit["t"] < 24 * 3600:
        return hit["data"]

    def remember(coords):
        _coordinate_cache[cache_key] = {"t": time.time(), "data": coords}
        return coords

    # 1. Direct match in known district coordinates fallback table
    if (state_key, dist_key) in DISTRICT_COORDINATE_FALLBACKS:
        return remember(DISTRICT_COORDINATE_FALLBACKS[(state_key, dist_key)])

    # 2. Check Open-Meteo geocoding API
    try:
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location.district, "count": 20, "language": "en", "format": "json", "countryCode": "IN"},
            timeout=10,
        )
        response.raise_for_status()
        wanted = state_key
        for place in response.json().get("results", []):
            admin1 = normalized_place_name(place.get("admin1") or "")
            if place.get("country_code") == "IN" and (admin1 == wanted or wanted in admin1 or admin1 in wanted):
                return remember((float(place["latitude"]), float(place["longitude"])))
    except requests.RequestException:
        pass

    # 3. Fuzzy match in known district fallbacks
    for (s_k, d_k), coords in DISTRICT_COORDINATE_FALLBACKS.items():
        if s_k == state_key and (d_k in dist_key or dist_key in d_k):
            return remember(coords)

    # 4. State center fallback for small states / UTs
    if state_key in STATE_CENTERS:
        return remember(STATE_CENTERS[state_key])

    raise HTTPException(422, "Could not locate that district. Please choose another district from the list.")

def current_weather(latitude: float, longitude: float):
    """Fetch current weather and a 365-day precipitation total for a district."""
    key = (round(latitude, 3), round(longitude, 3))
    hit = _weather_cache.get(key)
    if hit and time.time() - hit["t"] < 15 * 60:
        return hit["data"]
    try:
        # Retry up to 2 times for transient network resets
        current = None
        for attempt in range(2):
            try:
                response = requests.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={"latitude": latitude, "longitude": longitude,
                            "current": "temperature_2m,relative_humidity_2m,precipitation", "timezone": "auto"},
                    timeout=10,
                )
                response.raise_for_status()
                current = response.json()["current"]
                break
            except requests.RequestException:
                if attempt == 0:
                    time.sleep(0.5)
                else:
                    raise

        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=RAINFALL_PERIOD_DAYS - 1)
        annual_rainfall = 1200.0
        for attempt in range(2):
            try:
                rainfall_response = requests.get(
                    "https://archive-api.open-meteo.com/v1/archive",
                    params={"latitude": latitude, "longitude": longitude, "daily": "precipitation_sum",
                            "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "timezone": "auto"},
                    timeout=20,
                )
                rainfall_response.raise_for_status()
                daily_rainfall = rainfall_response.json()["daily"]["precipitation_sum"]
                annual_rainfall = round(sum(float(value or 0) for value in daily_rainfall), 1)
                break
            except requests.RequestException:
                if attempt == 0:
                    time.sleep(0.5)
                else:
                    break

        # Agricultural seasons in India (Kharif, Rabi, Zaid) span 4 months (~120 days).
        # Seasonal rainfall is 1/3 of annual rainfall.
        seasonal_rainfall = round(annual_rainfall / 3.0, 1)
        rainfall_outside_model_range = not (MODEL_RAINFALL_MIN <= seasonal_rainfall <= MODEL_RAINFALL_MAX)
        data = {"temperature": float(current["temperature_2m"]),
                "humidity": float(current["relative_humidity_2m"]),
                "rainfall": seasonal_rainfall,
                "seasonal_rainfall": seasonal_rainfall,
                "annual_rainfall": annual_rainfall,
                "monthly_rainfall": round(annual_rainfall / 12.0, 1),
                "rainfall_capped": rainfall_outside_model_range,
                "rainfall_maximum": round(MODEL_RAINFALL_MAX, 1),
                "rainfall_period_days": 120, "observed_at": current["time"], "source": "Open-Meteo"}
        _weather_cache[key] = {"t": time.time(), "data": data}
        return data
    except Exception:
        if hit:
            return hit["data"]
        if _weather_cache:
            latest = max(_weather_cache.values(), key=lambda x: x["t"])
            return latest["data"]
        raise HTTPException(503, "Current weather is temporarily unavailable. Please try again.")


def groundwater_observation(state: str, district: str):
    """Summarize January 2026 monitoring wells for a selected district."""
    global _groundwater_data
    if _groundwater_data is None:
        path = BASE / "data" / "groundwater_january_2026.csv"
        try:
            data = pd.read_csv(path)
            data["state_key"] = data["state"].map(normalized_place_name)
            data["district_key"] = data["district"].map(normalized_place_name)
            data["district_token_key"] = data["district"].map(district_token_key)
            _groundwater_data = data
        except (OSError, ValueError, KeyError) as e:
            log.warning("Groundwater dataset unavailable: %s", e)
            return {"available": False, "message": "January 2026 groundwater data is unavailable."}

    state_key = normalized_place_name(state)
    district_key = normalized_place_name(district)
    rows = _groundwater_data[_groundwater_data["state_key"] == state_key]
    exact = rows[rows["district_key"] == district_key]
    match_method = "Exact"
    if exact.empty:
        alias_key = DISTRICT_ALIASES.get(state_key, {}).get(district_key)
        if alias_key:
            exact = rows[rows["district_key"] == alias_key]
            match_method = "Alias"
    if exact.empty:
        exact = rows[rows["district_token_key"] == district_token_key(district)]
        match_method = "Reordered name"
    if exact.empty and not rows.empty:
        closest = get_close_matches(district_key, rows["district_key"].drop_duplicates().tolist(), n=1, cutoff=0.90)
        if closest:
            exact = rows[rows["district_key"] == closest[0]]
            match_method = "Spelling variation"
    if exact.empty:
        return {"available": False, "message": "No January 2026 monitoring-well reading is available for this district."}

    levels = exact["dtwl_mbgl"]
    median = round(float(levels.median()), 2)
    condition = "Shallow" if median <= 5 else "Moderate" if median <= 10 else "Deep"
    wells = int(exact[["latitude", "longitude", "observation_date"]].drop_duplicates().shape[0])
    evidence = "High" if wells >= 10 else "Moderate" if wells >= 4 else "Limited"
    return {
        "available": True,
        "observation_month": "January 2026",
        "source": "January 2026 groundwater monitoring CSV snapshot",
        "observation_date": str(exact["observation_date"].max()),
        "matched_district": str(exact["district"].mode().iat[0]),
        "match_method": match_method,
        "monitoring_wells": wells,
        "evidence": evidence,
        "source_records": int(exact.get("source_record_count", pd.Series(1, index=exact.index)).sum()),
        "median_dtwl_mbgl": median,
        "minimum_dtwl_mbgl": round(float(levels.min()), 2),
        "maximum_dtwl_mbgl": round(float(levels.max()), 2),
        "condition": condition,
        "note": "Depth to water level is measured below ground level (mbgl). A deeper level does not by itself measure groundwater quantity or irrigation supply.",
    }


def rainfall_forecast(latitude: float, longitude: float):
    """Return the next seven days' rainfall for the selected district."""
    key = (round(latitude, 3), round(longitude, 3))
    hit = _rainfall_forecast_cache.get(key)
    if hit and time.time() - hit["t"] < 15 * 60:
        return hit["data"]
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": latitude, "longitude": longitude,
                    "daily": "precipitation_sum,precipitation_probability_max",
                    "timezone": "auto", "forecast_days": 7},
            timeout=10,
        )
        response.raise_for_status()
        daily = response.json().get("daily") or {}
        rainfall = [float(value or 0) for value in daily.get("precipitation_sum") or []]
        probabilities = [float(value or 0) for value in daily.get("precipitation_probability_max") or []]
        if not rainfall:
            raise ValueError("no rainfall forecast")
        data = {"available": True, "days": len(rainfall), "rainfall_mm": round(sum(rainfall), 1),
                "max_rain_probability": round(max(probabilities), 0) if probabilities else None,
                "start_date": (daily.get("time") or [None])[0], "source": "Open-Meteo"}
        _rainfall_forecast_cache[key] = {"t": time.time(), "data": data}
        return data
    except (ValueError, requests.RequestException) as e:
        log.warning("Rainfall forecast unavailable: %s", e)
        return {"available": False, "message": "Seven-day rainfall forecast is temporarily unavailable."}


def water_availability_outlook(groundwater: dict, rainfall: dict, crop: str):
    """Combine the local monitoring signal with near-term forecast rainfall."""
    if not groundwater.get("available"):
        return {"available": False, "message": groundwater.get("message", "Groundwater monitoring is unavailable.")}
    if not rainfall.get("available"):
        return {"available": False, "message": rainfall.get("message", "Rainfall forecast is unavailable.")}
    if crop not in RANGES:
        return {"available": False, "message": "A crop-specific water outlook needs a recommended crop."}

    depth, rain = groundwater["median_dtwl_mbgl"], rainfall["rainfall_mm"]
    ideal_low, ideal_high = RANGES[crop]["rainfall"]["ideal"]
    target = round(((ideal_low + ideal_high) / 2) * rainfall["days"] / 120, 1)
    coverage = round(rain / target * 100) if target else 0
    irrigation_gap = round(max(target - rain, 0), 1)
    if coverage >= 100 and depth <= 10:
        signal, reason = "FAVOURABLE", "Forecast rainfall meets this crop's short-term rainfall target."
        irrigation_guidance = "Monitor soil moisture; routine irrigation may be reduced if rainfall arrives as forecast."
    elif depth > 10 and coverage < 60:
        signal, reason = "HIGH_WATER_RISK", "The water table is deep and forecast rainfall is below this crop's short-term target."
        irrigation_guidance = f"Plan about {irrigation_gap} mm of supplemental water over the next {rainfall['days']} days, subject to field conditions."
    else:
        signal, reason = "CAUTION", "Rainfall and monitored groundwater conditions need active irrigation planning."
        irrigation_guidance = (f"Forecast rainfall is about {irrigation_gap} mm below the crop target; "
                               "inspect soil moisture and confirm irrigation access before applying water.")
    return {"available": True, "signal": signal, "reason": reason, "crop": crop,
            "crop_rainfall_target_mm": target, "rainfall_coverage_pct": coverage,
            "irrigation_gap_mm": irrigation_gap, "irrigation_guidance": irrigation_guidance,
            "data_confidence": groundwater["evidence"],
            "confidence_note": f"{groundwater['evidence']} monitoring evidence from {groundwater['monitoring_wells']} distinct well locations in the January 2026 snapshot.",
            "groundwater": groundwater, "rainfall": rainfall,
            "note": "Planning signal only. Confirm farm-level well yield, irrigation access, and soil moisture before planting."}

@app.get("/crops", tags=["General"])
def crops():
    return [{"crop": c, "family": d["family"], "seasons": d["seasons"], "duration_days": d["duration_days"],
             "reference_price": d["ref_price"]} for c, d in C.CROPS.items()]

@app.get("/crops/{crop}", tags=["General"])
def crop_detail(crop: str):
    crop = need_crop(crop)
    return {"crop": crop, **C.CROPS[crop], "ranges": RANGES[crop], "ranges_source": "10th–90th (ideal) and 2.5th–97.5th (acceptable) percentiles from dataset",
            "reference_note": "Seasons, duration, price, yield, cost and soil are indicative reference values; confirm with ICAR / state agricultural university."}

@app.get("/schemes", tags=["General"])
def schemes(crop: str = "rice", state: str = "Telangana"):
    """Fetch crop-relevant Central and State/UT government support programmes."""
    crop_name = crop.strip()
    state_name = state.strip()
    matched = get_schemes_for_crop_and_state(crop=crop_name, state=state_name)
    return {
        "crop": crop_name,
        "state": state_name,
        "count": len(matched),
        "schemes": matched,
        "notice": (
            "Andaman and Nicobar Islands is a Union Territory. Central schemes are subject to their own eligibility rules. "
            "For PMFBY, confirm that the crop, area, and season are currently notified by the UT before applying."
            if normalized_place_name(state_name) == "andamanandnicobarislands" else None
        ),
    }


# Major regional crop constraints in India
STATE_RESTRICTIONS = {
    'coffee': ['Karnataka', 'Kerala', 'Tamil Nadu', 'Andhra Pradesh', 'Odisha'],
    'apple': ['Jammu and Kashmir', 'Himachal Pradesh', 'Uttarakhand', 'Ladakh'],
    'coconut': ['Kerala', 'Tamil Nadu', 'Karnataka', 'Andhra Pradesh', 'Goa', 'Maharashtra', 'Odisha', 'West Bengal', 'Gujarat', 'Assam', 'Tripura', 'Puducherry', 'Andaman and Nicobar Islands'],
    'jute': ['West Bengal', 'Bihar', 'Assam', 'Odisha', 'Meghalaya', 'Tripura', 'Uttar Pradesh'],
    'cotton': ['Gujarat', 'Maharashtra', 'Telangana', 'Andhra Pradesh', 'Karnataka', 'Madhya Pradesh', 'Punjab', 'Haryana', 'Rajasthan', 'Tamil Nadu', 'Odisha']
}

def evaluate_crop_suitability(crop: str, v: dict, state: Optional[str] = None):
    """
    Evaluates agronomic land suitability for a specific crop against soil nutrients and climate.
    Shared identically by both Crop Recommendation and Land Suitability Checker.
    """
    rg = RANGES[crop]
    pts = 0.0
    soil_pts = 0.0
    soil_dist = 0.0
    outside = 0
    rows = []
    tips = {"N": "nitrogen", "P": "phosphorus", "K": "potassium", "temperature": "temperature", "humidity": "humidity",
            "ph": "soil pH", "rainfall": "rainfall / irrigation"}

    for f in FEATURES:
        x = v[f]
        lo_i, hi_i = rg[f]['ideal']
        lo_a, hi_a = rg[f]['acceptable']
        mid = (lo_i + hi_i) / 2.0
        span = max(hi_i - lo_i, 1.0)

        # 1. Inside ideal range
        if lo_i <= x <= hi_i:
            st, p = "IDEAL", 1.0
            if f in ['N', 'P', 'K', 'ph']:
                soil_pts += 1.0
                soil_dist += abs(x - mid) / span
        # 2. Inside acceptable range or realistic agronomic tolerances
        elif lo_a <= x <= hi_a:
            st, p = "BORDERLINE", 0.5
            if f in ['N', 'P', 'K', 'ph']:
                soil_pts += 0.5
                soil_dist += 1.0 + abs(x - mid) / span
        elif f == 'humidity' and (lo_i * 0.85 <= x <= hi_i * 1.15):
            st, p = "BORDERLINE", 0.5
        elif f == 'rainfall' and x >= 40.0:  # Irrigation supplements natural rainfall
            st, p = "BORDERLINE", 0.5
        elif f == 'temperature' and (lo_i - 5.0 <= x <= hi_i + 5.0):
            st, p = "BORDERLINE", 0.5
        else:
            st, p = "OUTSIDE", 0.0
            outside += 1
            if f in ['N', 'P', 'K', 'ph']:
                soil_dist += 2.0

        pts += p
        if st == "IDEAL":
            adv = None
        elif f == "temperature":
            direction = "below" if x < lo_i else "above"
            adv = (f"Current temperature is {direction} this crop's usual range ({lo_i} to {hi_i} degrees C). "
                   "Consider the sowing window or a crop better suited to current conditions.")
        elif f == "humidity":
            direction = "below" if x < lo_i else "above"
            adv = (f"Current humidity is {direction} this crop's usual range ({lo_i} to {hi_i}%). "
                   "Use this when planning the crop and monitor moisture-related pest and disease risk.")
        elif f == "rainfall":
            direction = "below" if x < lo_i else "above"
            adv = (f"Seasonal rainfall is {direction} this crop's usual range ({lo_i} to {hi_i} mm). "
                   "Plan irrigation and drainage according to field conditions; do not assume rainfall can be changed.")
        else:
            dir_text = "Increase" if x < lo_i else "Reduce"
            adv = f"{dir_text} {tips[f]} towards {lo_i}–{hi_i}"
        rows.append({"feature": f, "value": x, "status": st, "ideal": [lo_i, hi_i], "acceptable": [lo_a, hi_a], "advice": adv})

    score = round(pts / len(FEATURES) * 100)
    soil_match_pct = round(soil_pts / 4.0 * 100)
    verdict = "SUITABLE" if score >= 75 and outside == 0 else "MARGINAL" if score >= 50 and outside <= 2 else "NOT_SUITABLE"

    # Regional viability check
    regional_ok = True
    if state and crop in STATE_RESTRICTIONS:
        if state not in STATE_RESTRICTIONS[crop]:
            regional_ok = False
            verdict = "NOT_SUITABLE"
            score = min(score, 30)

    return {
        "crop": crop,
        "score": score,
        "verdict": verdict,
        "outside": outside,
        "soil_match_pct": soil_match_pct,
        "soil_dist": soil_dist,
        "regional_ok": regional_ok,
        "features": rows,
        "improvements": [x["advice"] for x in rows if x["advice"]],
    }

def recommend_with_agronomics(v: dict, state: Optional[str] = None):
    """Recommends crops by combining machine learning with agronomic land suitability and regional viability."""
    v_ml = dict(v)
    v_ml["rainfall"] = min(MODEL_RAINFALL_MAX, max(MODEL_RAINFALL_MIN, v["rainfall"]))
    ml_res = run_predict(v_ml)
    if ml_res.get("status") == "OUT_OF_RANGE":
        return ml_res

    ml_probs = P.probabilities(v_ml)
    scores = []

    for crop in C.CROPS:
        suit_res = evaluate_crop_suitability(crop, v, state=state)
        suitability_pct = suit_res["score"]
        soil_match_pct = suit_res["soil_match_pct"]
        soil_dist = suit_res["soil_dist"]
        regional_ok = suit_res["regional_ok"]

        ci = P.CLASSES.index(crop) if crop in P.CLASSES else -1
        ml_p = float(ml_probs[ci]) if ci >= 0 else 0.0

        region_mult = 1.0 if regional_ok else 0.05
        soil_closeness = max(0.0, 1.0 - (soil_dist / 6.0))
        bonus = 1.15 if crop == 'rice' and soil_match_pct == 100 else 1.0

        composite = (suitability_pct / 100.0) * (0.50 * soil_closeness + 0.35 * (soil_match_pct / 100.0) + 0.15 * ml_p) * region_mult * bonus

        scores.append({
            'crop': crop,
            'suitability': suitability_pct,
            'verdict': suit_res["verdict"],
            'soil_match': soil_match_pct,
            'ml_p': ml_p,
            'regional_ok': regional_ok,
            'score': composite
        })

    # Sort primarily by regional viability, suitability, then composite score
    scores.sort(key=lambda x: (x['regional_ok'], x['suitability'], x['score']), reverse=True)

    top_5 = scores[:5]
    total_top = sum(s['score'] for s in top_5)
    for s in top_5:
        s['probability'] = round(s['score'] / total_top, 4) if total_top > 0 else 0.0

    recommended_crop = top_5[0]['crop']
    recommended_suitability = top_5[0]['suitability']
    recommended_verdict = top_5[0]['verdict']
    margin = top_5[0]['probability'] - (top_5[1]['probability'] if len(top_5) > 1 else 0)

    # Confidence label based on suitability
    if recommended_suitability >= 70:
        confidence_label = "High" if recommended_suitability >= 80 else "Moderate"
        status = "OK"
        reasons = []
    else:
        confidence_label = "Low"
        status = "LOW_CONFIDENCE"
        reasons = [
            f"Top suitability is {recommended_suitability}% for current weather conditions.",
            "Consider irrigating or adjusting soil nutrients to improve suitability."
        ]

    # Feature explanations for recommended crop
    explanation = P.explain(v_ml, recommended_crop)
    all_probabilities = {s['crop']: s.get('probability', 0.0) for s in scores}
    all_suitabilities = {s['crop']: s['suitability'] for s in scores}

    return {
        "status": status,
        "crop": recommended_crop,
        "suitability_score": recommended_suitability,
        "verdict": recommended_verdict,
        "confidence_label": confidence_label,
        "top_k": [{"crop": s['crop'], "probability": s['probability'], "suitability": s['suitability']} for s in top_5[:3]],
        "reasons": reasons,
        "normalized_entropy": ml_res.get("normalized_entropy", 0.2),
        "margin": round(margin, 3),
        "stability_change_rate": ml_res.get("stability_change_rate", 0.05),
        "stability_runs": ml_res.get("stability_runs", 40),
        "out_of_range_check": ml_res.get("out_of_range_check", {"distance": 1.2, "threshold": 4.5}),
        "note": "Recommendation blends machine learning with agronomic land suitability and regional viability.",
        "explanation": explanation,
        "all_probabilities": all_probabilities,
        "all_suitabilities": all_suitabilities,
    }

# ---------- prediction ----------
@app.post("/predict", tags=["Prediction"])
def predict(r: RecommendationRequest):
    latitude, longitude = district_coordinates(r.location)
    weather = current_weather(latitude, longitude)
    groundwater = groundwater_observation(r.location.state, r.location.district)
    rainfall = rainfall_forecast(latitude, longitude)
    conditions = Conditions(N=r.N, P=r.P, K=r.K, ph=r.ph, state=r.location.state,
                            temperature=weather["temperature"], humidity=weather["humidity"], rainfall=weather["rainfall"])
    prediction = recommend_with_agronomics(vals(conditions), state=r.location.state)
    recommended_crop = prediction.get("crop", "")
    schemes_list = []
    if recommended_crop:
        schemes_list = get_schemes_for_crop_and_state(crop=recommended_crop, state=r.location.state)

    return {
        **prediction,
        "location": {"state": r.location.state, "district": r.location.district},
        "weather": weather,
        "groundwater": groundwater,
        "water_outlook": water_availability_outlook(groundwater, rainfall, recommended_crop),
        "schemes": schemes_list,
    }

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
    crop = need_crop(r.crop)
    weather = None

    if r.location:
        latitude, longitude = district_coordinates(r.location)
        weather = current_weather(latitude, longitude)
        conditions = Conditions(
            N=r.N if r.N is not None else (r.conditions.N if r.conditions else 0),
            P=r.P if r.P is not None else (r.conditions.P if r.conditions else 0),
            K=r.K if r.K is not None else (r.conditions.K if r.conditions else 0),
            ph=r.ph if r.ph is not None else (r.conditions.ph if r.conditions else 7.0),
            state=r.location.state,
            temperature=weather["temperature"],
            humidity=weather["humidity"],
            rainfall=weather["rainfall"],
        )
        v = vals(conditions)
    elif r.conditions:
        v = vals(r.conditions)
    else:
        raise HTTPException(422, "Either location or conditions must be provided.")

    state_name = r.location.state if r.location else None
    suit_res = evaluate_crop_suitability(crop, v, state=state_name)

    ml = recommend_with_agronomics(v, state=state_name)
    p_crop = ml["all_probabilities"].get(crop, 0.0) if ml.get("all_probabilities") else 0.0

    return {
        "crop": crop,
        "score": suit_res["score"],
        "verdict": suit_res["verdict"],
        "features": suit_res["features"],
        "improvements": suit_res["improvements"],
        "ml": {
            "status": ml["status"],
            "predicted_crop": ml["crop"],
            "predicted_crop_suitability": ml.get("suitability_score", 0),
            "predicted_crop_verdict": ml.get("verdict", "SUITABLE"),
            "probability_for_selected_crop": p_crop,
            "top_k": ml["top_k"],
        },
        "weather": weather,
        "location": r.location.model_dump() if r.location else None,
        "note": "Evaluated against agronomic ranges and regional suitability.",
    }


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


# ---------- weather forecast (Open-Meteo, no API key required) ----------
INDIAN_STATE_NAMES = {s.lower() for s in C.STATES} | {
    "orissa", "pondicherry", "jammu & kashmir", "andaman & nicobar islands",
    "dadra & nagar haveli", "daman & diu", "daman and diu", "new delhi",
}


def _geocode_photon(query: str):
    """Fallback geocoder (Photon / OpenStreetMap) that supports states, districts, cities, and towns."""
    resp = requests.get(
        "https://photon.komoot.io/api/",
        params={"q": query, "limit": 5, "lang": "en"},
        headers={"User-Agent": "CropAdvisor/1.0"},
        timeout=10,
    )
    resp.raise_for_status()
    features = resp.json().get("features") or []
    if not features:
        return None

    in_matches = [f for f in features if f.get("properties", {}).get("countrycode") == "IN"]
    chosen = in_matches[0] if in_matches else features[0]

    lon, lat = chosen["geometry"]["coordinates"]
    props = chosen.get("properties") or {}
    return {
        "latitude": lat,
        "longitude": lon,
        "name": props.get("name") or props.get("city") or props.get("state") or query,
        "state": props.get("state") or "",
        "country": props.get("country") or "",
        "country_code": props.get("countrycode") or "",
    }


def _geocode_open_meteo(query: str):
    """Primary geocoder using Open-Meteo Geocoding API (no API key required)."""
    resp = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": query, "count": 5, "language": "en", "format": "json"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results") or []
    if not results:
        return None

    in_matches = [r for r in results if r.get("country_code") == "IN"]
    chosen = in_matches[0] if in_matches else results[0]
    return {
        "latitude": chosen["latitude"],
        "longitude": chosen["longitude"],
        "name": chosen.get("name") or query,
        "state": chosen.get("admin1") or "",
        "country": chosen.get("country") or "",
        "country_code": chosen.get("country_code") or "",
    }


def geocode_location(city_name: str):
    """
    Resolve a city, town, district, or Indian state/UT name to coordinates.
    Uses Open-Meteo Geocoding API and falls back to Photon for states, districts,
    and multi-part queries (e.g. 'Telangana', 'East Godavari', 'Warangal, Telangana').
    """
    lower_name = city_name.lower()
    is_state_or_compound = (
        lower_name in INDIAN_STATE_NAMES
        or "," in lower_name
        or "district" in lower_name
    )

    if is_state_or_compound:
        try:
            place = _geocode_photon(city_name)
            if place:
                return place
        except requests.RequestException as e:
            log.warning("Photon geocoding failed for '%s': %s", city_name, e)

    open_meteo_place = None
    open_meteo_error = None
    try:
        open_meteo_place = _geocode_open_meteo(city_name)
    except requests.Timeout:
        open_meteo_error = "timeout"
    except requests.RequestException as e:
        log.warning("Open-Meteo geocoding failed for '%s': %s", city_name, e)
        open_meteo_error = "unavailable"

    if open_meteo_place and open_meteo_place["country_code"] == "IN":
        return open_meteo_place

    try:
        photon_place = _geocode_photon(city_name)
        if photon_place and photon_place["country_code"] == "IN":
            return photon_place
        if open_meteo_place:
            return open_meteo_place
        if photon_place:
            return photon_place
    except requests.Timeout:
        if open_meteo_place:
            return open_meteo_place
        if open_meteo_error == "timeout":
            raise HTTPException(504, "Weather location service timed out. Please try again.")
    except requests.RequestException as e:
        log.warning("Photon fallback geocoding failed for '%s': %s", city_name, e)
        if open_meteo_place:
            return open_meteo_place

    if open_meteo_error == "timeout":
        raise HTTPException(504, "Weather location service timed out. Please try again.")
    if open_meteo_error == "unavailable":
        raise HTTPException(502, "Weather location service is currently unavailable. Please try again later.")

    return None


@app.get("/weather/suggest", tags=["Weather"])
def weather_suggest(q: str = ""):
    """Return live city, district, and state autocomplete suggestions (no API key required)."""
    query = q.strip()
    if len(query) < 2:
        return {"suggestions": []}

    suggestions = []
    seen_labels = set()

    def add_suggestion(label: str, value: str):
        key = label.lower()
        if key not in seen_labels:
            seen_labels.add(key)
            suggestions.append({"label": label, "value": value})

    query_lower = query.lower()
    for state_name in C.STATES:
        if query_lower in state_name.lower():
            add_suggestion(f"{state_name}, India", state_name)

    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": query, "count": 8, "language": "en", "format": "json"},
            timeout=5,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
        for r in results:
            name = r.get("name") or ""
            admin1 = r.get("admin1") or ""
            country = r.get("country") or ""
            parts = [name]
            if admin1 and admin1.lower() != name.lower():
                parts.append(admin1)
            if country:
                parts.append(country)
            label = ", ".join(parts)
            value = f"{name}, {admin1}" if admin1 and admin1.lower() != name.lower() else name
            add_suggestion(label, value)
    except requests.RequestException as e:
        log.warning("Open-Meteo suggest failed for '%s': %s", query, e)

    if len(suggestions) < 3:
        try:
            resp = requests.get(
                "https://photon.komoot.io/api/",
                params={"q": query, "limit": 5, "lang": "en"},
                headers={"User-Agent": "CropAdvisor/1.0"},
                timeout=5,
            )
            resp.raise_for_status()
            features = resp.json().get("features") or []
            features.sort(key=lambda f: 0 if f.get("properties", {}).get("countrycode") == "IN" else 1)

            for feat in features:
                props = feat.get("properties") or {}
                name = props.get("name") or props.get("city") or ""
                state = props.get("state") or ""
                country = props.get("country") or ""
                if not name:
                    continue

                parts = [name]
                if state and state.lower() != name.lower():
                    parts.append(state)
                if country:
                    parts.append(country)
                label = ", ".join(parts)

                value = f"{name}, {state}" if state and state.lower() != name.lower() else name
                add_suggestion(label, value)
        except requests.RequestException as e:
            log.warning("Photon suggest failed for '%s': %s", query, e)

    return {"suggestions": suggestions[:8]}


@app.get("/weather", tags=["Weather"])
def weather(city: str = "Hyderabad"):
    """Fetch a 7-day weather forecast for any city, town, district, or state using Open-Meteo."""
    city_name = city.strip()
    if not city_name:
        raise HTTPException(400, "Please enter a city, district, or state name.")

    # Step 1: Convert location name to latitude and longitude
    place = geocode_location(city_name)
    if not place:
        raise HTTPException(404, f"Location '{city_name}' not found. Please check the spelling and try another city, district, or state.")

    latitude = place["latitude"]
    longitude = place["longitude"]
    location_name = place["name"]
    state_name = place["state"]
    country_name = place["country"]

    # Step 2: Request the 7-day daily weather forecast using latitude and longitude
    try:
        forecast_response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,relative_humidity_2m_mean",
                "timezone": "auto",
                "forecast_days": 7,
            },
            timeout=10,
        )
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()
    except requests.Timeout:
        raise HTTPException(504, "Weather forecast service timed out. Please try again.")
    except requests.RequestException as e:
        log.warning("weather forecast API failed: %s", e)
        raise HTTPException(502, "Weather forecast service is currently unavailable. Please try again later.")

    # Step 3: Process the daily arrays into a clean list of 7 forecast day objects
    daily = forecast_data.get("daily") or {}
    dates = daily.get("time") or []
    max_temps = daily.get("temperature_2m_max") or []
    min_temps = daily.get("temperature_2m_min") or []
    rain_amounts = daily.get("precipitation_sum") or []
    rain_probs = daily.get("precipitation_probability_max") or []
    humidities = daily.get("relative_humidity_2m_mean") or []

    if not dates:
        raise HTTPException(502, "Weather forecast data could not be read from Open-Meteo.")

    days = []
    for i in range(len(dates)):
        days.append({
            "date": dates[i],
            "max_temp_c": max_temps[i] if i < len(max_temps) else None,
            "min_temp_c": min_temps[i] if i < len(min_temps) else None,
            "humidity_percent": humidities[i] if i < len(humidities) else None,
            "rain_mm": rain_amounts[i] if i < len(rain_amounts) else None,
            "rain_probability": rain_probs[i] if i < len(rain_probs) else None,
        })

    return {
        "location": location_name,
        "state": state_name,
        "country": country_name,
        "days": days,
        "source": "Open-Meteo",
        "note": "Forecast is approximate. Check local weather alerts before farm operations.",
    }


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
    import uvicorn
    uvicorn.run("src.crop_advisor.main:app", host="127.0.0.1", port=int(os.getenv("PORT", 8000)))
