# Crop Advisor

Crop Advisor is a web-based decision-support tool for farmers, agricultural officers, and researchers. It combines soil-test values, district weather, rainfall outlooks, and groundwater-monitoring data to help users compare crop options and plan the next steps before sowing.

It is built with FastAPI and serves both the website and the API from one application.

## What it helps with

- Crop recommendations based on soil nutrients, soil pH, temperature, humidity, and rainfall.
- A clear shortlist of crop options, suitability signals, and warnings when confidence is low.
- District weather, a seven-day rainfall outlook, and a crop-aware irrigation planning signal.
- January 2026 groundwater-monitoring summaries, including the number of wells behind the district result.
- Land suitability checks, fertilizer planning, profit estimates, crop rotation suggestions, and weather forecasts.
- Central, State, and Union Territory agricultural-support programme information, with eligibility reminders.

## Quick start

From the repository root in Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn src.crop_advisor.main:app --reload
```

Open the website at `http://127.0.0.1:8000`.

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

`DATA_GOV_API_KEY` in `.env` is optional. It enables live mandi-price requests through data.gov.in; without it, the app clearly labels stored reference prices.

## Data and decision scope

The crop recommendation model uses `data/Crop_recommendation.csv`, which contains 2,200 rows, 22 crops, and seven inputs:

- Nitrogen, phosphorus, and potassium
- Soil pH
- Temperature, humidity, and rainfall

State, season, and soil type are not direct model inputs. The selected district is used to provide supporting local context, such as weather, rainfall, groundwater information, and relevant schemes; it does not by itself determine the model recommendation.

The groundwater feature uses the January 2026 monitoring snapshot in `data/groundwater_january_2026.csv`. Its depth-to-water-level values are measured below ground level (mbgl). They are not a measurement of total groundwater quantity, well yield, or guaranteed irrigation supply.

## Using results responsibly

Crop Advisor is a planning aid, not a replacement for field inspection or professional agronomic advice.

- Recommendations can be marked low-confidence or unavailable when the input pattern is unlike the training data.
- The model's approximately 99.5% test accuracy is specific to its clean, well-separated dataset. It does not guarantee field performance.
- Rainfall forecasts and groundwater readings are time- and location-specific. Confirm irrigation access, soil moisture, and local weather alerts before farm operations.
- Fertilizer doses, yields, costs, prices, profit estimates, and scheme eligibility are indicative. Confirm them with a KVK, Agriculture Department, agricultural university, or the relevant official portal before spending money.

## Project layout

| Path | Purpose |
| --- | --- |
| `src/crop_advisor/` | FastAPI application, model logic, crop data, and scheme lookup code |
| `templates/` and `static/` | Website pages, styles, and browser-side behaviour |
| `data/` | Crop dataset, groundwater snapshot, and scheme database |
| `models/` | Trained model files and evaluation metrics |
| `postman/` | Postman collection for API testing |
| `render.yaml` | Render deployment configuration |

## Testing the API

Import `postman/Crop_Advisor.postman_collection.json` into Postman and set the `base` variable to `http://127.0.0.1:8000`.

## Deployment

The repository includes `render.yaml` for Render deployment. Connect the repository as a Blueprint or Web Service, then set `DATA_GOV_API_KEY` in the service environment only if live mandi prices are required. Keep `.env` private and do not commit API keys.

## Model details

Technical evaluation, model comparison, and accuracy information are available on the application's Model Performance page. The production model and its metrics are recorded in `models/metrics.json`.
