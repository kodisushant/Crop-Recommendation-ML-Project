# CROP ADVISOR – Grow Smarter. Harvest Better.

AI crop recommendation (22 crops) with confidence, out-of-range detection and planning tools. FastAPI serves both the API and the website.

## Honest scope notes
- **Dataset:** `Crop_recommendation.csv` has 2,200 rows, 22 crops, and 7 model inputs: N, P, K, temperature, humidity, pH, and rainfall. State, season, and soil type are not ML inputs.
- **Location support:** the selected district supplies local weather, a seven-day rainfall outlook, the January 2026 groundwater monitoring snapshot, and relevant Central/State/UT support programmes. Location does not itself determine the ML crop result.
- **Groundwater scope:** the January 2026 data reports depth to water level below ground (mbgl) at monitoring wells. It does not measure total groundwater quantity, well yield, or guaranteed irrigation supply.
- **Accuracy (~99.5%)** is measured on this clean, well-separated dataset. It is not a guarantee of field performance; real farm results will vary.
- **Model choice:** Gaussian NB, Random Forest and Extra Trees are statistically tied (CV 0.9915–0.9949). Random Forest is the production model because its probabilities suit confidence analysis. The tie-break result is recorded in `models/metrics.json`.
- **Indicative data:** prices, yields, costs, fertilizer doses, durations, soil types (`src/crop_advisor/crop_data.py`) are *not* verified. Confirm with ICAR / your state agricultural university. Sponsor entries are placeholders.
- **Not tested here:** live data.gov.in prices (needs your free API key) and the public Render deployment. Without a key the app shows clearly-labelled reference prices.
- `reliability.png` is not generated.

## Run locally (Windows PowerShell, VS Code terminal)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
copy .env.example .env             # optional: add DATA_GOV_API_KEY
python -m uvicorn src.crop_advisor.main:app --reload
```
Open http://127.0.0.1:8000 (website) and http://127.0.0.1:8000/docs (Swagger). Models are already trained; to retrain: `python -m src.crop_advisor.train_model`.

## Test the API in Postman
Import `postman/Crop_Advisor.postman_collection.json` (variable `base` = `http://127.0.0.1:8000`) and send requests.

## Deploy publicly on Render (free, HTTPS)
1. Create a GitHub account and a new repository; upload this folder (keep `models/`, `data/`, `plots/`; `.env` is git-ignored).
2. Sign up at https://render.com → **New → Blueprint** (or Web Service) → connect the repo. `render.yaml` supplies the build and start commands.
3. In the service's **Environment** tab set `DATA_GOV_API_KEY` (free key from https://data.gov.in → Register → My Account).
4. Deploy. Render gives you an `https://….onrender.com` URL. The free tier sleeps when idle (first load ~30 s).
5. Redeploy after changes: `git add . && git commit -m "update" && git push` – Render redeploys automatically.

## Files
`src/crop_advisor/` backend and ML package (`preprocessing.py`, `train_model.py`, `predictor.py`, `crop_data.py`, `main.py`) · `templates/` + `static/` frontend.

## How confidence works
LOW_CONFIDENCE: top probability < 0.50, or top-2 margin < 0.15, or top crop changes in > 30% of 40 noisy re-runs. OUT_OF_RANGE: a value outside the training min/max, or Mahalanobis distance beyond the 99th percentile of training rows → no crop returned. Limitation: combinations where every value is individually normal can be missed.
