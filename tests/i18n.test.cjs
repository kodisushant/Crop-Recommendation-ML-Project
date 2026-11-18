// Run with node --test tests/i18n.test.cjs. Node is only a development check;
// the shipped feature is ordinary browser JavaScript and requires no build.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
function runtime(saved='en'){
    const context={window:{},localStorage:{getItem:()=>saved},document:{addEventListener(){}},console};
    vm.createContext(context);
    for(const name of ['translations.js','translations-complete.js','translations-reports.js','translations-messages.js','translations-descriptions.js','translations-weather.js','i18n.js'])vm.runInContext(fs.readFileSync(path.join(root,'static/js',name),'utf8'),context);
    return context.window;
}
test('all advertised languages have complete core, crop and safety entries',()=>{
    const app=runtime();
    assert.equal(app.CropTranslations.languages.length,13);
    for(const [code]of app.CropTranslations.languages){
        if(code==='en')continue;
        for(const text of [...app.CropTranslations.english,...app.CropTranslations.cropKeys,'No crop is recommended for unusual inputs.','Probability is not a guarantee of crop success.']){
            assert.ok(app.CropTranslations.catalogs[code][text],code+': '+text);
            assert.notEqual(app.CropI18n.t(text,code),text,code+': '+text);
        }
    }
});
test('English and unreviewed technical strings remain unchanged',()=>{
    const app=runtime('te');
    assert.equal(app.CropI18n.t('Rice','en'),'Rice');
    assert.equal(app.CropI18n.t('A detailed note not in the catalog'),'A detailed note not in the catalog');
    assert.equal(app.CropI18n.t('₹2,000 / 40%'),'₹2,000 / 40%');
});
test('selection survives reload and invalid stored codes fall back to English',()=>{
    assert.equal(runtime('te').CropI18n.language,'te');
    assert.equal(runtime('ur').CropI18n.language,'ur');
    assert.equal(runtime('unsupported').CropI18n.language,'en');
});
test('feature values and validation limits survive translation',()=>{
    const {CropI18n:i18n}=runtime('te');
    assert.equal(i18n.t('N = 90'),'నత్రజని = 90');
    assert.ok(i18n.t('Enter between 0 and 300').endsWith('0 – 300'));
    assert.ok(i18n.t(' Soil nitrogen content · 0–300 ').includes('0–300'));
    assert.equal(i18n.t('LOW_CONFIDENCE'),'తక్కువ విశ్వాసం');
    assert.equal(i18n.t(' · Confidence '),' · విశ్వాస స్థాయి ');
    assert.ok(i18n.t("Probability is the model's score on this dataset, not a guarantee of agricultural success. Technical detail.").startsWith('సంభావ్యత'));
});

test('parameterized safety messages translate without changing limits or measurements',()=>{
    const app=runtime();
    for(const [code]of app.CropTranslations.languages){
        if(code==='en')continue;
        for(const text of ['Top probability is only 41% (below 50%).','Top two crops are close (margin 12%, below 15%).','N = 350 is outside the training range (0.0–140.0).','Changed in 40 noisy re-runs','Unusualness (limit 17.25)']){
            const translated=app.CropI18n.t(text,code);
            assert.notEqual(translated,text,code+': '+text);
            assert.deepEqual(translated.match(/\d+(?:\.\d+)?/g),text.match(/\d+(?:\.\d+)?/g));
        }
    }
});

test('weather provider messages translate in every regional language and preserve location parameters',()=>{
    const {CropTranslations:vocabulary,CropI18n:i18n}=runtime();
    const messages=['Weather location service timed out. Please try again.',
        'Weather location service is currently unavailable. Please try again later.',
        'Weather forecast service timed out. Please try again.',
        'Weather forecast service is currently unavailable. Please try again later.',
        'Weather forecast data could not be read from Open-Meteo.'];
    for(const [code]of vocabulary.languages){
        if(code==='en')continue;
        messages.forEach(text=>assert.notEqual(i18n.t(text,code),text,code+': '+text));
        const error="Location 'Orange' not found. Please check the spelling and try another city, district, or state.";
        assert.notEqual(i18n.t(error,code),error);
        assert.ok(i18n.t(error,code).includes('Orange'));
    }
});
