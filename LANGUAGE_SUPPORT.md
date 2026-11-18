# Regional language support

The shared navigation has a native-script language selector on every page. Supported languages: English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Odia, Assamese and Urdu. English is the default. Selection is saved in browser localStorage (ca_language), works across page navigation/reloads and can be changed without submitting or clearing forms. Urdu switches the document to right-to-left; numeric inputs and charts retain left-to-right direction.

## Scope

Offline catalogs translate main navigation, tool headings, field labels, common actions, crop names, result/status labels, report-table vocabulary, uncertainty warnings, validation messages and chart labels. Parameterized uncertainty messages translate their wording while preserving measured values and thresholds. Dynamic results/options/toasts are translated when they are inserted. Search on Ideal Conditions accepts English and translated crop names.

Some detailed technical paragraphs, agronomy descriptions, government state/market proper names and diagnostic strings remain English. Complete page-copy coverage has not yet been achieved. A localized notice explicitly discloses the technical-text fallback for non-English languages. Model-comparison plots and the confusion matrix now use live charts/table cells so their labels can translate. Raw API responses and /docs remain English; translating labels does not change model predictions, HTTP payload keys, crop IDs, stored numeric inputs, thresholds or units. This is not automatic translation of arbitrary content or every language worldwide.

Translations are a starter vocabulary, not a certified agronomic translation. Have native speakers/local agricultural advisers review the terminology before field use. Untranslated messages remain the original English rather than being guessed. No external translation provider receives soil inputs or results; no translation API key or extra Python package is needed.

## Files

- static/js/translations.js: offline locale dictionaries and all 22 crop names.
- static/js/translations-complete.js: additional offline UI and planning vocabulary (the filename does not imply full page-copy coverage).
- static/js/translations-reports.js: report tables, controls and accessible labels.
- static/js/translations-messages.js: fixed and parameterized uncertainty/error messages.
- static/js/translations-weather.js: complete weather-page UI, descriptions, controls, loading states, provider-error messages and forecast labels for every supported regional language.
- static/js/i18n.js: lossless source-text tracking, persistence, direction, chart localization and dynamic DOM updates.
- templates/base.html: accessible shared language selector and fallback notice.
- static/css/style.css: responsive control, script-friendly typography and RTL styles.
- tests/i18n.test.cjs and tests/i18n-dom.test.cjs: catalog, model-value and DOM/controller regression checks.
- tools/translation_inventory.py: list visible template copy for translation review.

When adding a language, add its native-script name to languages and provide all columns in the core/crop/safety/extra vocabularies. Startup validation catches mismatched columns. Add full-sentence translations explicitly for detailed guidance; do not translate numeric/model codes in API payloads. Set translate="no" on any technical component whose text must be preserved verbatim.

## Verification

Soil Analysis has its own stable `/soil-analysis` URL, linked from the home card and Tools menu. It reuses the recommendation form and existing prediction endpoint, with a distinct translated heading/action and the feature-influence chart first in the result. Language changes preserve the current inputs and result. Unusual inputs still display the model's refusal instead of an analysis chart. A real-browser check opened the Telugu card, submitted the existing model and switched the resulting page to Urdu successfully.

Run `npm ci` and `npm test` for development verification. Node/jsdom are development dependencies only; running the app still uses the existing FastAPI setup and ordinary browser JavaScript. No translation service, subscription, or translation API key is required.

Twenty-one tests cover catalogs, all 22 crop names, numeric safety-message parameters, persistence, English restoration, dynamic text/options/accessibility labels, Urdu direction, canonical form payloads, menu toggles, season filtering, translated crop search, what-if controls, fertilizer submissions, Soil Analysis, chart-failure isolation and weather-language behavior. DOM tests use jsdom with mocked backend responses and charts; they do not establish pixel layout or native-language accuracy. The merged backend passed HTTP smoke checks for all thirteen pages, mocked 7-day weather results, empty location suggestions and provider timeouts. The existing model and dataset were preserved.

## Weather forecast

The weather feature from remote commit `39823da` is available at `/weather-forecast`. English and all twelve regional languages cover its headings, descriptions, home/dashboard/navigation links, search labels/placeholders, loading text, forecast table headings, safety note, empty results, validation and known provider errors. Dates use the selected locale. Switching language refreshes the existing result locally, without another forecast request or clearing the search input. A real-browser check retrieved a live Hyderabad forecast in Telugu and switched the completed result to Urdu successfully.

Open-Meteo and Photon still provide weather and location data. Translation stays entirely offline and uses no translation API. Provider place names and the Open-Meteo name remain unchanged; numeric readings and measurement units retain their values. Location names are never translated into crop names, even when a place shares a crop name such as Orange. Autocomplete retains canonical values for mouse and keyboard selection, ignores stale responses after edits/clears and uses accessible expansion/selection states. Missing readings show a dash. Weather errors containing typed locations are rendered as text.

The merge preserved the local language selector, Soil Analysis page, chart localization and toast notifications. The duplicate stylesheet reference and duplicate weather-page description were removed. Existing partial home-description translations from the cancelled task were preserved; weather support does not imply that every older technical paragraph has been translated.
