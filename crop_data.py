"""Reference data for the 22 crops in the dataset.
IMPORTANT: everything here is INDICATIVE and NOT from the ML dataset. Prices, yields, costs,
fertilizer doses and durations must be confirmed with ICAR / your State Agricultural University.
Prices are Rs per quintal (MSP-like for notified crops, rough market levels for the rest)."""

# name: (family, legume, duration_days, seasons, ref_price, typical_yield_q_per_ha, cost_per_ha,
#        N, P2O5, K2O (kg/ha), heavy_feeder, soil)
_R = {
 "rice": ("Poaceae", 0, 130, "Kharif", 2369, 45, 55000, 120, 60, 40, 1, "Clay / clay loam"),
 "maize": ("Poaceae", 0, 100, "Kharif, Rabi", 2400, 55, 40000, 120, 60, 40, 1, "Well-drained loam"),
 "chickpea": ("Fabaceae", 1, 110, "Rabi", 5650, 14, 30000, 20, 50, 20, 0, "Sandy loam / loam"),
 "kidneybeans": ("Fabaceae", 1, 100, "Kharif, Rabi", 8000, 15, 35000, 30, 60, 30, 0, "Well-drained loam"),
 "pigeonpeas": ("Fabaceae", 1, 160, "Kharif", 8000, 12, 33000, 25, 50, 25, 0, "Loam / black soil"),
 "mothbeans": ("Fabaceae", 1, 75, "Kharif", 8000, 5, 18000, 20, 40, 0, 0, "Sandy / arid soil"),
 "mungbean": ("Fabaceae", 1, 65, "Kharif, Zaid", 8768, 8, 22000, 20, 40, 20, 0, "Loam / sandy loam"),
 "blackgram": ("Fabaceae", 1, 75, "Kharif, Rabi", 7800, 8, 22000, 20, 40, 20, 0, "Loam / clay loam"),
 "lentil": ("Fabaceae", 1, 110, "Rabi", 7000, 11, 25000, 20, 40, 20, 0, "Loam"),
 "pomegranate": ("Lythraceae", 0, 365, "Perennial", 9000, 120, 200000, 250, 125, 125, 1, "Light loam"),
 "banana": ("Musaceae", 0, 330, "Perennial", 1800, 400, 250000, 200, 60, 300, 1, "Rich loam"),
 "mango": ("Anacardiaceae", 0, 365, "Perennial", 4000, 80, 100000, 100, 50, 100, 0, "Deep loam"),
 "grapes": ("Vitaceae", 0, 365, "Perennial", 5000, 200, 400000, 200, 100, 200, 1, "Sandy loam"),
 "watermelon": ("Cucurbitaceae", 0, 90, "Zaid", 1200, 250, 90000, 100, 60, 60, 0, "Sandy loam"),
 "muskmelon": ("Cucurbitaceae", 0, 80, "Zaid", 2000, 150, 80000, 100, 60, 60, 0, "Sandy loam"),
 "apple": ("Rosaceae", 0, 365, "Perennial", 8000, 100, 300000, 100, 50, 100, 0, "Deep loam (hills)"),
 "orange": ("Rutaceae", 0, 365, "Perennial", 4000, 150, 120000, 200, 100, 100, 0, "Well-drained loam"),
 "papaya": ("Caricaceae", 0, 300, "Perennial", 1500, 400, 200000, 200, 200, 250, 1, "Light loam"),
 "coconut": ("Arecaceae", 0, 365, "Perennial", 3000, 80, 100000, 100, 50, 150, 0, "Sandy loam / coastal"),
 "cotton": ("Malvaceae", 0, 180, "Kharif", 7710, 20, 60000, 120, 60, 60, 1, "Black cotton soil"),
 "jute": ("Malvaceae", 0, 120, "Kharif", 5650, 25, 45000, 60, 30, 30, 1, "Alluvial loam"),
 "coffee": ("Rubiaceae", 0, 365, "Perennial", 20000, 8, 150000, 120, 90, 120, 0, "Forest loam (hills)"),
}
KEYS = ["family", "legume", "duration_days", "seasons", "ref_price", "yield_q_ha", "cost_ha",
        "N", "P2O5", "K2O", "heavy", "soil"]
CROPS = {c: dict(zip(KEYS, v)) for c, v in _R.items()}
for c in CROPS.values():
    c["legume"], c["heavy"] = bool(c["legume"]), bool(c["heavy"])

YIELD_FACTORS = {"low": 0.65, "typical": 1.0, "high": 1.3}
FERT_PRICE = {"urea": 5.4, "dap": 27.0, "mop": 34.0}  # Rs/kg, indicative
SPONSORS = [  # placeholders only - never affect quantities
    {"name": "Sample Brand A (placeholder)", "product": "NPK 10-26-26", "note": "Placeholder sponsor slot"},
    {"name": "Sample Brand B (placeholder)", "product": "Water-soluble 19-19-19", "note": "Placeholder sponsor slot"}]

STATES = ["Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
 "Chhattisgarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana",
 "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
 "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry",
 "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
 "West Bengal"]

# Agmarknet commodity names (data.gov.in); a miss simply falls back to the reference price
AGMARK = {"rice": "Rice", "maize": "Maize", "chickpea": "Bengal Gram(Gram)(Whole)", "kidneybeans": "Rajma",
 "pigeonpeas": "Arhar (Tur/Red Gram)(Whole)", "mothbeans": "Moath Dal", "mungbean": "Green Gram (Moong)(Whole)",
 "blackgram": "Black Gram (Urd Beans)(Whole)", "lentil": "Lentil (Masur)(Whole)", "pomegranate": "Pomegranate",
 "banana": "Banana", "mango": "Mango", "grapes": "Grapes", "watermelon": "Water Melon", "muskmelon": "Musk Melon",
 "apple": "Apple", "orange": "Orange", "papaya": "Papaya", "coconut": "Coconut", "cotton": "Cotton",
 "jute": "Jute", "coffee": "Coffee"}

# Commonly practised sequences (previous -> good next crops); simplified, not agronomic advice
SEQUENCES = {"rice": ["chickpea", "lentil", "mungbean", "blackgram", "maize"], "maize": ["chickpea", "lentil", "mungbean"],
 "cotton": ["chickpea", "lentil", "maize"], "jute": ["rice", "lentil", "chickpea"],
 "chickpea": ["rice", "maize", "cotton"], "lentil": ["rice", "maize", "jute"], "pigeonpeas": ["maize", "cotton"],
 "mungbean": ["rice", "maize", "cotton"], "blackgram": ["rice", "maize", "cotton"],
 "kidneybeans": ["maize", "rice"], "mothbeans": ["maize", "cotton"], "watermelon": ["chickpea", "lentil"],
 "muskmelon": ["chickpea", "lentil"]}
