# Regional language support

The shared navigation has a native-script language selector on every page. Supported languages: English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Odia, Assamese and Urdu. English is the default. Selection is saved in browser localStorage (ca_language), works across page navigation/reloads and can be changed without submitting or clearing forms. Urdu switches the document to right-to-left; numeric inputs and charts retain left-to-right direction.

## Scope

Offline catalogs translate main navigation, tool headings, field labels, common actions, crop names, result/status labels, key uncertainty warnings, selected validation messages and chart labels. Dynamic results/options/toasts are translated when they are inserted. Search on Ideal Conditions accepts English and translated crop names.

Some detailed technical paragraphs, agronomy descriptions, government state/market proper names, diagnostic strings and pre-rendered plot images remain English. A localized notice explicitly discloses the technical-text fallback for non-English languages. Raw API responses and /docs remain English; translating labels does not change model predictions, HTTP payload keys, crop IDs, stored numeric inputs, thresholds or units. This is not automatic translation of arbitrary content or every language worldwide.

Translations are a starter vocabulary, not a certified agronomic translation. Have native speakers/local agricultural advisers review the terminology before field use. Untranslated messages remain the original English rather than being guessed. No external translation provider receives soil inputs or results; no translation API key or extra Python package is needed.

## Files

- static/js/translations.js: offline locale dictionaries and all 22 crop names.
- static/js/i18n.js: lossless source-text tracking, persistence, direction, chart localization and dynamic DOM updates.
- templates/base.html: accessible shared language selector and fallback notice.
- static/css/style.css: responsive control, script-friendly typography and RTL styles.
- tests/i18n.test.cjs: catalog and translation invariants (node --test tests/i18n.test.cjs).

When adding a language, add its native-script name to languages and provide all columns in the core/crop/safety/extra vocabularies. Startup validation catches mismatched columns. Add full-sentence translations explicitly for detailed guidance; do not translate numeric/model codes in API payloads. Set translate="no" on any technical component whose text must be preserved verbatim.

## Verification

Four Node tests cover all 13 catalogs, all 22 crop names, key safety notices, stored-language validation, English/unknown-text fallback and numeric limits. Browser checks verified Telugu recommendation controls and the asynchronously rendered rice result, English restoration, Urdu persistence across navigation, and a successful fertilizer request using untranslated crop identifiers. Screenshot capture was unavailable, so responsive/RTL CSS has not received visual screenshot QA. The local smoke test loaded the repository model with installed scikit-learn 1.7.2 and emitted its existing version-mismatch warnings; deployment should use the repository's pinned 1.9.1 environment. No backend logic or saved model was modified by this feature.
