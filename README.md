# CROP ADVISOR – Grow Smarter. Harvest Better.

Regional language selector: English plus 12 major Indian languages, remembered across pages; Urdu includes RTL layout. Main controls, crop names, status messages and chart labels use offline dictionaries. Unreviewed detailed technical text remains English with a visible notice. See [LANGUAGE_SUPPORT.md](LANGUAGE_SUPPORT.md) for coverage, limitations and translation-review guidance.
AI crop recommendation (22 crops) with confidence, out-of-range detection and planning tools. FastAPI serves both the API and the website.

## Honest scope notes
- **Dataset:** the uploaded `Crop_recommendation.csv` has 2,200 rows, 22 crops, 7 features (N, P, K, temperature, humidity, pH, rainfall). The Feature Guide PDF describes a different dataset (12 crops, state/season/soil). **State, season and soil type are not ML inputs.** State is only used to filter market prices.
- **Accuracy (~99.5%)** is genuine for this clean, well-separated dataset; real farm data will score lower.
- **Model choice:** Gaussian NB, Random Forest and Extra Trees are statistically tied (CV 0.9915–0.9949). Random Forest is the production model because its probabilities suit confidence analysis. The tie-break result is recorded in `models/metrics.json`.
- **Indicative data:** prices, yields, costs, fertilizer doses, durations, soil types (`crop_data.py`) are *not* verified. Confirm with ICAR / your state agricultural university. Sponsor entries are placeholders.
- **Not tested here:** live data.gov.in prices (needs your free API key) and the public Render deployment. Without a key the app shows clearly-labelled reference prices.
- `reliability.png` is not generated.

## Run locally (Windows PowerShell, VS Code terminal)
```powershell
cd crop-advisor
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
copy .env.example .env             # optional: add DATA_GOV_API_KEY
python -m uvicorn main:app --reload
```
Open http://127.0.0.1:8000 (website) and http://127.0.0.1:8000/docs (Swagger). Models are already trained; to retrain: `python train_model.py`.

## Test the API in Postman
Import `Crop_Advisor.postman_collection.json` (variable `base` = `http://127.0.0.1:8000`) and send requests.

## Deploy publicly on Render (free, HTTPS)
1. Create a GitHub account and a new repository; upload this folder (keep `models/`, `data/`, `plots/`; `.env` is git-ignored).
2. Sign up at https://render.com → **New → Blueprint** (or Web Service) → connect the repo. `render.yaml` supplies the build and start commands.
3. In the service's **Environment** tab set `DATA_GOV_API_KEY` (free key from https://data.gov.in → Register → My Account).
4. Deploy. Render gives you an `https://….onrender.com` URL. The free tier sleeps when idle (first load ~30 s).
5. Redeploy after changes: `git add . && git commit -m "update" && git push` – Render redeploys automatically.

## Files
`preprocessing.py` load/clean/split · `train_model.py` 8 models, 5-fold CV, plots, saves models · `predictor.py` prediction, confidence, OOD, stability, explanations · `crop_data.py` reference tables · `main.py` FastAPI + pages · `templates/` + `static/` frontend.

## How confidence works
LOW_CONFIDENCE: top probability < 0.50, or top-2 margin < 0.15, or top crop changes in > 30% of 40 noisy re-runs. OUT_OF_RANGE: a value outside the training min/max, or Mahalanobis distance beyond the 99th percentile of training rows → no crop returned. Limitation: combinations where every value is individually normal can be missed.
