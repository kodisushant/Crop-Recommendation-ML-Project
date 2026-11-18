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
- static/js/i18n.js: lossless source-text tracking, persistence, direction, chart localization and dynamic DOM updates.
- templates/base.html: accessible shared language selector and fallback notice.
- static/css/style.css: responsive control, script-friendly typography and RTL styles.
- tests/i18n.test.cjs and tests/i18n-dom.test.cjs: catalog, model-value and DOM/controller regression checks.
- tools/translation_inventory.py: list visible template copy for translation review.

When adding a language, add its native-script name to languages and provide all columns in the core/crop/safety/extra vocabularies. Startup validation catches mismatched columns. Add full-sentence translations explicitly for detailed guidance; do not translate numeric/model codes in API payloads. Set translate="no" on any technical component whose text must be preserved verbatim.

## Verification

Soil Analysis now has its own stable `/soil-analysis` URL, linked from the home card and Tools menu. It reuses the recommendation form and existing prediction endpoint, with a distinct translated heading/action and the feature-influence chart first in the result. Language changes preserve the current inputs and result. Unusual inputs still display the model's refusal instead of an analysis chart. The regression suite now has thirteen tests, including the home-card destination in every advertised language and Soil Analysis submissions/restoration in Telugu, Hindi, Urdu and English. A real-browser check opened the Telugu card, submitted the existing model and switched the resulting page to Urdu successfully.

Run `npm ci` and `npm test` for development verification. Node/jsdom are development dependencies only; running the app still uses the existing FastAPI setup and ordinary browser JavaScript. No translation service, subscription, or translation API key is required.

Eleven tests cover catalogs, all 22 crop names, numeric safety-message parameters, persistence, English restoration, dynamic text/options/accessibility labels, Urdu direction, canonical form payloads, menu toggles, season filtering, translated crop search, what-if controls, fertilizer submissions and chart-failure isolation. These DOM tests use jsdom with mocked backend responses and charts; they do not establish pixel layout or native-language accuracy. A separate HTTP smoke check returned 200 for all eleven page routes and verified the 22-class confusion-matrix endpoint. Responsive/RTL CSS still needs real-browser visual review. No backend logic or saved model was modified by this feature.
