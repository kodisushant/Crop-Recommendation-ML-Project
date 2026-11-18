// Exercise real page markup and controllers without a server or translation API.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(__dirname,'..');
const tick=()=>new Promise(resolve=>setTimeout(resolve,15));
const read=name=>fs.readFileSync(path.join(root,name),'utf8');
const crop={crop:'rice',seasons:'Kharif',family:'Poaceae',soil:'Clay / clay loam',duration_days:130,
    ref_price:2369,yield_q_ha:45,cost_ha:55000,N:120,P2O5:60,K2O:40,
    ranges:{N:{ideal:[60,100],acceptable:[40,120]}}};

async function page(name='rotation',saved='en',responses={}){
    let base=read('templates/base.html');
    const template=fs.existsSync(path.join(root,`templates/${name}.html`))?`templates/${name}.html`:`user_history/templates/${name}.html`;
    const body=read(template).split('{% block body %}')[1].split('{% endblock %}')[0];
    const markup=base.replace('{% block body %}{% endblock %}',body)
        .replace('{{ page }}',name).replace(/{%[\s\S]*?%}/g,'');
    const errors=[];
    const virtualConsole=new VirtualConsole();
    virtualConsole.on('jsdomError',error=>errors.push(error.message));
    const dom=new JSDOM(markup,{url:'http://localhost/',runScripts:'outside-only',virtualConsole});
    const {window:w}=dom;
    w.localStorage.setItem('ca_language',saved);
    const requests=[];
    w.fetch=async(url,options)=>{
        requests.push({url,body:options?.body?JSON.parse(options.body):undefined,method:options?.method,headers:options?.headers});
        assert.ok(url.startsWith('/'),'no external request: '+url);
        const data=responses[url]??({'/crops':[crop],'/crops/rice':crop,'/states':['Telangana'],
            '/rotation':{suggestions:[],disclaimer:''},'/meta':{n_crops:22,test_accuracy:0.99,best_model:'Random Forest'},'/api/auth/me':{user:null}}[url]);
        assert.notEqual(data,undefined,'unmocked API: '+url);
        const result=typeof data==='function'?await data(url,options):data;
        return result.__http || {ok:true,json:async()=>result};
    };
    // Charts are exercised separately. Canvas rendering needs a real browser.
    w.Chart=class {constructor(canvas,config){this.canvas=canvas;this.data=config.data;this.options=config.options||{};}update(){}destroy(){}};
    w.HTMLElement.prototype.scrollIntoView=function(){};
    // Wait for jsdom's own DOMContentLoaded before installing application scripts.
    await tick();
    Object.defineProperty(w.document,'readyState',{configurable:true,get:()=> 'loading'});
    for(const file of ['static/js/translations.js','static/js/translations-complete.js','static/js/translations-reports.js','static/js/translations-messages.js','static/js/translations-descriptions.js','static/js/translations-weather.js','user_history/static/translations.js','static/js/i18n.js','user_history/static/accounts.js','user_history/static/history.js','static/js/script.js'])w.eval(read(file));
    w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
    Object.defineProperty(w.document,'readyState',{configurable:true,get:()=> 'complete'});
    await tick();
    return {dom,w,requests,errors};
}

test('all language switches preserve feature links, form elements and machine values',async()=>{
    const {dom,w,requests,errors}=await page('rotation');
    try{
        const d=w.document,season=d.querySelector('#season'),input=d.querySelector('#f-N');
        const links=[...d.querySelectorAll('.menu a')].map(a=>a.getAttribute('href'));
        input.value='101';season.value='Kharif';
        for(const [code]of w.CropTranslations.languages){
            w.CropI18n.setLanguage(code);await tick();
            assert.equal(d.querySelector('#f-N'),input);
            assert.equal(input.value,'101');
            assert.equal(season.value,'Kharif');
            assert.equal(d.querySelector('#crop').value,'rice');
            assert.deepEqual([...d.querySelectorAll('.menu a')].map(a=>a.getAttribute('href')),links);
            assert.equal(d.documentElement.dir,code==='ur'?'rtl':'ltr');
            d.querySelector('.burger').click();
            assert.equal(d.querySelector('.burger').getAttribute('aria-expanded'),'true');
            d.querySelector('.dd > button').click();
            assert.equal(d.querySelector('.dd > button').getAttribute('aria-expanded'),'true');
            d.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape'}));
            assert.equal(d.querySelector('.burger').getAttribute('aria-expanded'),'false');
            assert.equal(d.querySelector('.dd > button').getAttribute('aria-expanded'),'false');
            d.querySelector('#form').dispatchEvent(new w.Event('submit',{cancelable:true}));
            await tick();
            const sent=requests.filter(r=>r.url==='/rotation').at(-1);
            assert.equal(sent.body.previous_crop,'rice');assert.equal(sent.body.next_season,'Kharif');
        }
        w.CropI18n.setLanguage('en');await tick();
        assert.equal(season.options[1].textContent,'Kharif');
        assert.deepEqual(errors,[]);
    }finally{dom.window.close();}
});

test('translated season filters and crop searches still open matching cards',async()=>{
    const {dom,w,errors}=await page('ideal_conditions','te');
    try{
        const d=w.document;
        assert.equal(d.querySelectorAll('.crop-card').length,1);
        d.querySelector('#season').value='Kharif';
        d.querySelector('#season').dispatchEvent(new w.Event('change'));
        d.querySelector('#q').value=w.CropI18n.t('Rice');
        d.querySelector('#q').dispatchEvent(new w.Event('input'));
        await tick();assert.equal(d.querySelectorAll('.crop-card').length,1);
        d.querySelector('#q').value='';
        w.CropI18n.setLanguage('ur');await tick();
        assert.equal(d.querySelectorAll('.crop-card').length,1);
        assert.equal(d.querySelector('#season').value,'Kharif');
        assert.deepEqual(errors,[]);
    }finally{dom.window.close();}
});

test('new text/options/accessibility labels translate and English restoration is lossless',async()=>{
    const {dom,w}=await page();
    try{
        const d=w.document,button=d.createElement('button'),option=d.createElement('option');
        button.textContent='Create plan';button.title='Market Prices';
        option.textContent='Rabi';d.querySelector('#season').append(option);d.body.append(button);
        w.CropI18n.setLanguage('te');await tick();
        assert.equal(option.value,'Rabi');assert.notEqual(option.textContent,'Rabi');
        button.setAttribute('title','Land Suitability');button.firstChild.nodeValue='Market Prices';
        await tick();assert.equal(button.textContent,w.CropI18n.t('Market Prices'));
        assert.equal(button.title,w.CropI18n.t('Land Suitability'));
        w.CropI18n.setLanguage('en');await tick();
        assert.equal(button.textContent,'Market Prices');assert.equal(button.title,'Land Suitability');
        assert.equal(option.textContent,'Rabi');assert.equal(option.value,'Rabi');
    }finally{dom.window.close();}
});

test('a chart update failure cannot disable the selector or other charts',async()=>{
    const {dom,w}=await page();
    try{
        let updates=0,events=0;
        w.document.addEventListener('languagechange',()=>events++);
        for(const fail of [true,false]){
            const canvas=w.document.createElement('canvas');w.document.body.append(canvas);
            w.CropI18n.registerChart({canvas,data:{labels:['Rice'],datasets:[{label:'Test Accuracy'}]},options:{},
                update(){if(fail)throw Error('unavailable canvas');updates++;}});
        }
        for(const code of ['te','ur','en'])w.CropI18n.setLanguage(code);
        assert.equal(events,3);assert.equal(updates,4);assert.equal(w.CropI18n.language,'en');
    }finally{dom.window.close();}
});

test('what-if controls retain set/add/pct modes and initialized callbacks',async()=>{
    const {dom,w,errors}=await page('what_if','te');
    try{
        const d=w.document;
        for(const code of ['hi','ur','en']){
            w.CropI18n.setLanguage(code);await tick();
            assert.deepEqual([...d.querySelector('.c-m').options].map(o=>o.value),['set','add','pct']);
            const count=d.querySelectorAll('.chg').length;d.querySelector('#add-change').click();
            await tick();assert.equal(d.querySelectorAll('.chg').length,count+1);
            d.querySelector('.chg:last-child button').click();assert.equal(d.querySelectorAll('.chg').length,count);
            d.querySelector('#sw-f').value='N';d.querySelector('#sw-f').dispatchEvent(new w.Event('change'));
            assert.equal(d.querySelector('#sw-a').value,'0');
        }
        assert.deepEqual(errors,[]);
    }finally{dom.window.close();}
});

test('fertilizer form sends original crop IDs and soil values after switching language',async()=>{
    const fertilizer={quantity:{urea_kg:10,dap_kg:20,mop_kg:30},estimated_cost_inr:1000,
        soil_class:{N:'LOW',P:'MEDIUM',K:'HIGH'},recommended_dose_kg_ha:{N:120,P2O5:60,K2O:40},
        nutrient_need_kg_ha:{N:120,P2O5:60,K2O:40},adjustment:{N:1,P:1,K:1},area_ha:1,
        basal:{urea_kg:5,dap_kg:20,mop_kg:30},top_dressing:[],sponsored:{items:[],note:''},assumptions:[]};
    const {dom,w,requests,errors}=await page('fertilizer','te',{'/fertilizer':fertilizer});
    try{
        const d=w.document;d.querySelector('#f-N').value='123';
        for(const code of ['hi','ur','en']){
            w.CropI18n.setLanguage(code);
            d.querySelector('#form').dispatchEvent(new w.Event('submit',{cancelable:true}));
            await tick();
            const sent=requests.filter(r=>r.url==='/fertilizer').at(-1);
            assert.equal(sent.body.crop,'rice');assert.equal(sent.body.N,123);assert.equal(sent.body.area_ha,1);
            assert.equal(d.querySelector('#go').disabled,false);
            assert.ok(d.querySelector('#result table'));
        }
        assert.deepEqual(errors,[]);
    }finally{dom.window.close();}
});

test('home Soil Analysis card keeps a distinct route in every language',async()=>{
    const {dom,w}=await page('index');
    try{
        const link=w.document.querySelector('#soil-analysis-link');
        for(const [code]of w.CropTranslations.languages){
            w.CropI18n.setLanguage(code);await tick();
            assert.equal(link.getAttribute('href'),'/soil-analysis');
            assert.equal(link.querySelector('h3').textContent,w.CropI18n.t('Soil Analysis'));
            assert.equal(w.document.querySelector('.dd-m a[href="/soil-analysis"]').getAttribute('href'),'/soil-analysis');
        }
    }finally{dom.window.close();}
});

test('soil mode keeps the analysis visible when language changes after a prediction',async()=>{
    const prediction={status:'OK',crop:'rice',confidence_label:'High',top_k:[{crop:'rice',probability:0.95}],
        reasons:[],normalized_entropy:0.1,margin:0.9,stability_change_rate:0,stability_runs:40,
        out_of_range_check:{distance:1,threshold:10},note:'Probability is not a guarantee of crop success.',
        explanation:[{feature:'N',value:90,effect:0.1},{feature:'ph',value:6.5,effect:0.02}]};
    const {dom,w,requests,errors}=await page('recommendation','te',{'/predict':prediction});
    try{
        const d=w.document;d.body.dataset.analysisMode='soil';
        for(const code of ['te','hi','ur','en']){
            w.CropI18n.setLanguage(code);
            d.querySelector('#predict-form').dispatchEvent(new w.Event('submit',{cancelable:true}));
            await tick();
            assert.equal(d.querySelector('#result').firstElementChild.id,'soil-analysis-panel');
            assert.equal(d.querySelector('#soil-analysis-panel h3').textContent.trim(),w.CropI18n.t('Soil Analysis'));
            assert.ok(d.querySelector('#c-exp'));
            assert.equal(d.querySelector('#go').disabled,false);
            const payload=requests.filter(r=>r.url==='/predict').at(-1).body;
            assert.equal(payload.N,90);assert.equal(payload.ph,6.5);
        }
        // No crop analysis is shown when the model refuses unusual inputs.
        w.displayRecommendationResult({...prediction,status:'OUT_OF_RANGE',top_k:[],explanation:[],
            reasons:['This combination of values is more unusual than 99% of training rows.']});
        await tick();assert.equal(d.querySelector('#soil-analysis-panel'),null);
        assert.ok(d.querySelector('#result .alert.bad'));
        assert.deepEqual(errors,[]);
    }finally{dom.window.close();}
});

const weatherFixture={location:'Orange',state:'California',country:'United States',source:'Open-Meteo',
    note:'Forecast is approximate. Check local weather alerts before farm operations.',
    days:Array.from({length:7},(_,index)=>({date:`2026-11-${19+index}`,min_temp_c:17.5,max_temp_c:29,
        humidity_percent:index?65:null,rain_mm:1.2,rain_probability:index?30:null}))};

test('weather headings, instructions, home card and controls translate in all advertised languages',async()=>{
    const {dom,w}=await page('weather');
    const home=await page('index');
    try{
        const d=w.document;
        const description=d.querySelector('.app-head p').textContent.trim().replace(/\s+/g,' ');
        const empty=d.querySelector('#result .empty').textContent.trim();
        const field=d.querySelector('#city'),placeholder=field.placeholder;
        const card=home.w.document.querySelector('#features a[href="/weather-forecast"]');
        const homeDescription=card.querySelector('p').textContent;
        for(const [code]of w.CropTranslations.languages){
            w.CropI18n.setLanguage(code);home.w.CropI18n.setLanguage(code);await tick();
            for(const source of ['7-Day Weather Forecast',description,empty,placeholder,'Get Forecast']){
                const translated=w.CropI18n.t(source);
                if(code!=='en')assert.notEqual(translated,source,code+': '+source);
            }
            assert.equal(d.querySelector('h1').textContent,w.CropI18n.t('7-Day Weather Forecast'));
            assert.equal(d.querySelector('.app-head p').textContent.trim().replace(/\s+/g,' '),w.CropI18n.t(description));
            assert.equal(field.placeholder,w.CropI18n.t(placeholder));assert.equal(field.value,'Hyderabad');
            assert.equal(card.getAttribute('href'),'/weather-forecast');
            assert.equal(card.querySelector('h3').textContent,home.w.CropI18n.t('7-Day Weather Forecast'));
            assert.equal(card.querySelector('p').textContent,home.w.CropI18n.t(homeDescription));
            if(code!=='en')assert.notEqual(card.querySelector('p').textContent,homeDescription);
        }
    }finally{dom.window.close();home.dom.window.close();}
});

test('forecast switches all locales without refetching or changing place names and measurements',async()=>{
    const {dom,w,requests,errors}=await page('weather','te',{'/weather?city=Orange':weatherFixture});
    try{
        const d=w.document,field=d.querySelector('#city');field.value='Orange';
        d.querySelector('#form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
        for(const [code]of w.CropTranslations.languages){
            w.CropI18n.setLanguage(code);await tick();
            assert.equal(d.querySelector('#city'),field);assert.equal(field.value,'Orange');
            assert.equal(d.querySelectorAll('#result tbody tr').length,7);
            assert.equal(d.querySelector('#result h3 span').textContent,'Orange, California, United States');
            const headers=[...d.querySelectorAll('#result th')].map(cell=>cell.textContent);
            assert.deepEqual(headers,['Date','Min Temperature (°C)','Max Temperature (°C)','Humidity (%)','Rainfall (mm)','Rain Probability (%)'].map(text=>w.CropI18n.t(text)));
            const cells=[...d.querySelectorAll('#result tbody tr:first-child td')].slice(1).map(cell=>cell.textContent);
            assert.deepEqual(cells,['17.5','29','–','1.2','–']);
            assert.equal(d.querySelector('#result time').getAttribute('datetime'),'2026-11-19');
            assert.equal(d.querySelector('#result time').textContent,new w.Intl.DateTimeFormat(code,{weekday:'short',day:'numeric',month:'short',timeZone:'UTC'}).format(new w.Date('2026-11-19T12:00:00Z')));
            assert.equal(d.querySelector('#result .note').textContent,w.CropI18n.t(weatherFixture.note));
            assert.equal(d.querySelector('#go').disabled,false);
            assert.equal(d.documentElement.dir,code==='ur'?'rtl':'ltr');
        }
        assert.equal(requests.filter(r=>r.url.startsWith('/weather?')).length,1);
        assert.deepEqual(errors,[]);
    }finally{dom.window.close();}
});

test('loading and completed forecasts follow a language switch during a request',async()=>{
    let finish;
    const pending=new Promise(resolve=>{finish=resolve;});
    const {dom,w}=await page('weather','te',{'/weather?city=Hyderabad':()=>pending});
    try{
        const d=w.document;
        d.querySelector('#form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
        assert.equal(d.querySelector('#go').disabled,true);
        assert.ok(d.querySelector('#result').textContent.includes(w.CropI18n.t('Loading 7-day weather forecast...')));
        w.CropI18n.setLanguage('ur');await tick();
        assert.ok(d.querySelector('#result').textContent.includes(w.CropI18n.t('Loading 7-day weather forecast...')));
        finish(weatherFixture);await tick();
        assert.equal(d.querySelector('#result th').textContent,w.CropI18n.t('Date'));
        assert.equal(d.querySelector('#go').disabled,false);
    }finally{dom.window.close();}
});

test('weather validation, provider errors and empty forecasts translate and allow retry',async()=>{
    const responses={'/weather?city=Orange':{__http:{ok:false,json:async()=>({detail:"Location 'Orange' not found. Please check the spelling and try another city, district, or state."})}},
        '/weather?city=Empty':{...weatherFixture,days:[]}};
    const {dom,w,requests}=await page('weather','te',responses);
    try{
        const d=w.document,field=d.querySelector('#city'),form=d.querySelector('#form');
        field.value='';form.dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
        assert.ok(d.querySelector('#result').textContent.includes(w.CropI18n.t('Please enter a city, district, or state name.')));
        assert.equal(requests.filter(r=>!r.url.startsWith('/api/auth/')).length,0);
        field.value='Orange';form.dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
        const english="Location 'Orange' not found. Please check the spelling and try another city, district, or state.";
        for(const code of ['te','hi','ur','en']){
            w.CropI18n.setLanguage(code);await tick();
            assert.ok(d.querySelector('#result').textContent.includes(w.CropI18n.t(english)));
            assert.ok(d.querySelector('#result').textContent.includes('Orange'));
        }
        field.value='Empty';form.dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
        assert.ok(d.querySelector('#result').textContent.includes(w.CropI18n.t('No forecast data is available for this location.')));
        assert.equal(d.querySelector('#go').disabled,false);
    }finally{dom.window.close();}
});

test('weather suggestions keep canonical values and keyboard selection across language changes',async()=>{
    const {dom,w,requests}=await page('weather','te',{'/weather/suggest?q=Or':{suggestions:[{label:'Orange, California, United States',value:'Orange, California'}]}});
    try{
        const d=w.document,field=d.querySelector('#city');field.value='Or';field.dispatchEvent(new w.Event('input'));
        await new Promise(resolve=>setTimeout(resolve,300));
        assert.equal(field.getAttribute('aria-expanded'),'true');
        w.CropI18n.setLanguage('ur');await tick();
        assert.equal(d.querySelector('.ac-item span').textContent,'Orange, California, United States');
        field.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowDown',cancelable:true}));
        assert.equal(field.getAttribute('aria-activedescendant'),'weather-suggestion-0');
        field.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Enter',cancelable:true}));
        assert.equal(field.value,'Orange, California');assert.equal(field.getAttribute('aria-expanded'),'false');
        assert.equal(requests.filter(r=>!r.url.startsWith('/api/auth/')).length,1);
    }finally{dom.window.close();}
});

test('a cleared location cannot reopen stale autocomplete results',async()=>{
    let finish;const pending=new Promise(resolve=>{finish=resolve;});
    const {dom,w}=await page('weather','te',{'/weather/suggest?q=Hy':()=>pending});
    try{
        const d=w.document,field=d.querySelector('#city');field.value='Hy';field.dispatchEvent(new w.Event('input'));
        await new Promise(resolve=>setTimeout(resolve,300));
        field.value='';field.dispatchEvent(new w.Event('input'));
        finish({suggestions:[{label:'Hyderabad, Telangana',value:'Hyderabad'}]});await tick();
        assert.equal(d.querySelector('#city-suggestions').hidden,true);
        assert.equal(d.querySelectorAll('.ac-item').length,0);
    }finally{dom.window.close();}
});

test('weather provider errors display a typed location as text, never executable markup',async()=>{
    const city='<img src=x onerror=alert(1)>';
    const message=`Location '${city}' not found. Please check the spelling and try another city, district, or state.`;
    const {dom,w}=await page('weather','te',{['/weather?city='+encodeURIComponent(city)]:{__http:{ok:false,json:async()=>({detail:message})}}});
    try{
        const d=w.document;d.querySelector('#city').value=city;
        d.querySelector('#form').dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
        assert.equal(d.querySelector('#result img'),null);
        assert.ok(d.querySelector('#result').textContent.includes(city));
        assert.ok(d.querySelector('#result').textContent.includes(w.CropI18n.t(message)));
    }finally{dom.window.close();}
});

test('account forms and history instructions translate without changing typed credentials',async()=>{
    for(const name of ['login','register','history']){
        const {dom,w,errors}=await page(name);
        try{
            const d=w.document;
            const nodes=[...d.querySelectorAll('main h1,main p,main label,main button,main a,.app-head h1,.app-head p')]
                .map(element=>({element,source:element.textContent.trim()})).filter(item=>item.source);
            const username=d.querySelector('#username'),password=d.querySelector('#password');
            if(username)username.value='Rice';if(password)password.value='test-only-password';
            for(const [code]of w.CropTranslations.languages){
                w.CropI18n.setLanguage(code);await tick();
                for(const {element,source}of nodes){
                    assert.equal(element.textContent.trim(),w.CropI18n.t(source),name+' '+code+' '+source);
                    if(code!=='en')assert.notEqual(w.CropI18n.t(source),source,code+' '+source);
                }
                if(username)assert.equal(username.value,'Rice');if(password)assert.equal(password.value,'test-only-password');
            }
            assert.deepEqual(errors,[]);
        }finally{dom.window.close();}
    }
});

test('registration validation and server messages translate without storing passwords',async()=>{
    const {dom,w,requests}=await page('register','te',{'/api/auth/register':{__http:{ok:false,status:409,json:async()=>({detail:'This username is already taken.'})}}});
    try{
        const d=w.document,form=d.querySelector('#account-form');
        const username=d.querySelector('#username'),password=d.querySelector('#password'),confirm=d.querySelector('#confirm-password');
        username.value='Rice';password.value='test-only-password';confirm.value='different-password';
        form.dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
        assert.equal(d.querySelector('#account-message').textContent,w.CropI18n.t('Passwords do not match.'));
        assert.equal(requests.filter(r=>r.url==='/api/auth/register').length,0);
        confirm.value=password.value;
        form.dispatchEvent(new w.Event('submit',{cancelable:true}));await tick();
        assert.equal(d.querySelector('#account-message').textContent,w.CropI18n.t('This username is already taken.'));
        const sent=requests.filter(r=>r.url==='/api/auth/register').at(-1);
        assert.equal(sent.headers['X-Crop-Request'],'1');assert.equal(sent.body.username,'Rice');
        assert.equal(d.querySelector('#account-submit').disabled,false);
        for(let index=0;index<w.localStorage.length;index++)assert.ok(!String(w.localStorage.getItem(w.localStorage.key(index))).includes(password.value));
    }finally{dom.window.close();}
});

test('saved history translates, paginates and opens/deletes reports using stable IDs',async()=>{
    const prediction={status:'OK',crop:'rice',confidence_label:'High',top_k:[{crop:'rice',probability:0.95}],reasons:[],
        normalized_entropy:0.1,margin:0.9,stability_change_rate:0,stability_runs:40,out_of_range_check:{distance:1,threshold:10},
        note:'Probability is not a guarantee of crop success.',explanation:[{feature:'N',value:90,effect:0.1}]};
    const first={id:'000000000000000000000003',created_at:'2026-11-18T12:00:00+00:00',source:'soil-analysis',inputs:{N:90,P:42,K:43,ph:6.5},crop:'rice',status:'OK',confidence_label:'High',probability:0.95};
    const second={...first,id:'000000000000000000000002',crop:null,status:'OUT_OF_RANGE',probability:null};
    const last={...first,id:'000000000000000000000001'};
    const responses={
        '/api/auth/me':{user:{id:'private-owner',username:'Rice',role:'user'}},
        '/api/history?limit=20':{items:[first,second],next_cursor:second.id},
        ['/api/history?limit=20&before='+second.id]:{items:[last],next_cursor:null},
        ['/api/history/'+first.id]:(url,options)=>options.method==='DELETE'?{deleted:true}:{...first,result:prediction}
    };
    const {dom,w,requests,errors}=await page('history','te',responses);
    try{
        const d=w.document;
        assert.equal(d.querySelectorAll('#history-items article').length,2);
        for(const [code]of w.CropTranslations.languages){
            w.CropI18n.setLanguage(code);await tick();
            assert.equal(d.querySelector('#account-name').textContent,'Rice');
            assert.equal(d.querySelector('#history-items h3').textContent,w.CropI18n.t('Rice'));
            assert.equal(d.querySelector('[data-action="view"]').textContent,w.CropI18n.t('View report'));
            assert.equal(d.querySelector('#history-items td').textContent,'90');
            assert.equal(d.querySelector('#history-items article').dataset.id,first.id);
        }
        d.querySelector('[data-action="view"]').click();await tick();
        assert.equal(d.querySelector('#result').hidden,false);assert.ok(d.querySelector('#c-exp'));
        d.querySelector('#history-more').click();await tick();
        assert.equal(d.querySelectorAll('#history-items article').length,3);
        assert.equal(d.querySelector('#history-more').hidden,true);
        w.confirm=()=>true;d.querySelector('[data-action="delete"]').click();await tick();
        assert.equal(d.querySelectorAll('#history-items article').length,2);
        assert.equal(d.querySelector('#result').hidden,true);
        const deletion=requests.find(r=>r.method==='DELETE');assert.equal(deletion.url,'/api/history/'+first.id);
        assert.equal(deletion.headers['X-Crop-Request'],'1');
        assert.equal(w.localStorage.getItem('ca_hist'),null);assert.deepEqual(errors,[]);
    }finally{dom.window.close();}
});

test('history storage outages and unsaved model results are explicit and translated',async()=>{
    const failure={__http:{ok:false,status:503,json:async()=>({detail:'Account and history storage is unavailable. Please try again.'})}};
    const history=await page('history','te',{'/api/auth/me':failure});
    try{
        assert.equal(history.w.document.querySelector('#history-message').textContent,history.w.CropI18n.t('Account and history storage is unavailable. Please try again.'));
        assert.equal(history.w.document.querySelector('#history-login').hidden,false);
    }finally{history.dom.window.close();}
    const result={status:'OUT_OF_RANGE',crop:null,top_k:[],explanation:[],reasons:[],normalized_entropy:0.1,margin:0,
        stability_change_rate:0,stability_runs:40,out_of_range_check:{distance:9,threshold:4},note:'Probability is not a guarantee of crop success.',
        history:{saved:false,reason:'storage_unavailable'}};
    const prediction=await page('recommendation','te',{'/predict':result});
    try{
        const d=prediction.w.document;d.querySelector('#predict-form').dispatchEvent(new prediction.w.Event('submit',{cancelable:true}));await tick();
        assert.ok(d.querySelector('#result .alert.bad'));
        assert.ok(d.querySelector('#result').textContent.includes(prediction.w.CropI18n.t('This result could not be saved. Please try again later.')));
        assert.equal(d.querySelector('#go').disabled,false);
    }finally{prediction.dom.window.close();}
});
