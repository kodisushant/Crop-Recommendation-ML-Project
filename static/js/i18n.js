/** Lightweight UI localisation. Machine-readable values and model inputs stay
 * English/numeric; only visible text, accessible names and chart labels change.
 * Keep source text per node so switching back to English is lossless.
 */
(function (global) {
    'use strict';
    const vocabulary=global.CropTranslations;
    const aliases={
        'AI Crop Recommendation':'Crop Recommendation','Recommend a Crop':'Crop Recommendation',
        'Land Suitability Checker':'Land Suitability','Ideal Crop Conditions':'Ideal Conditions',
        'Crop Rotation Suggestions':'Crop Rotation','Market Price Information':'Market Prices',
        'Model Performance & Evaluation':'Model Performance','Model Analytics':'Model Performance',
        'Estimate Profit':'Profit Estimation','Get Mandi Prices':'Market Prices',
        'Suggest crops':'Recommend crop','Check suitability':'Land Suitability',
        'Check Land Suitability':'Land Suitability','Try What-If Analysis':'What-If Analysis',
        'Fertilizer Plan':'Fertilizer Planning','State':'State / UT', 'Area (ha)':'Area (hectares)',
        'LOW_CONFIDENCE':'LOW CONFIDENCE','OUT_OF_RANGE':'OUT OF RANGE',
        'NOT_SUITABLE':'NOT SUITABLE',
        'Why confidence is not high:':'LOW CONFIDENCE',
        'Soil nitrogen content':'Nitrogen','Soil phosphorus content':'Phosphorus',
        'Soil potassium content':'Potassium','Average temperature':'Temperature','Relative humidity':'Humidity',
        'Soil nitrogen':'Nitrogen','Soil phosphorus':'Phosphorus','Soil potassium':'Potassium',
        'Acidity':'Soil pH','Previous crop':'Last crop grown',
        'Selected Production Model':'Production model','Best production model':'Production model',
        'crops supported':'Supported crops','production model':'Production model',
        'Estimated Fertilizer Cost':'Estimated cost','Total Cultivation Cost':'Total Cost',
        'Modal Price':'Modal (Typical)','Min':'Min Price','Max':'Max Price',
        'REFERENCE PRICE (not live)':'Reference price','LIVE MANDI PRICES':'Live price',
        'What Drove This Prediction':'Explanation','Suitability score for':'Land Suitability',
        'Model\'s top recommendation for this land:':'Recommended crop',
        'Probability score for':'Model probability','Reference Price per Quintal':'Reference price'
    };
    const features={N:'Nitrogen',P:'Phosphorus',K:'Potassium',ph:'Soil pH',temperature:'Temperature',humidity:'Humidity',rainfall:'Rainfall'};
    const skip='script,style,canvas,code,[translate="no"],#language-select';
    const originals=new WeakMap(),attributes=new WeakMap(),chartSources=new WeakMap(),charts=new Set();
    let language='en', observer=null;
    const originalTitle=typeof document.title==='string'?document.title:'';
    try {const saved=localStorage.getItem('ca_language');if(vocabulary.catalogs[saved])language=saved;} catch (_) {}
    const lowerIndexes={};
    Object.entries(vocabulary.catalogs).forEach(([code,values])=>{
        lowerIndexes[code]=Object.fromEntries(Object.entries(values).map(([key,value])=>[key.toLowerCase(),value]));
    });
    // Only known message templates are matched. Values are inserted as text,
    // never HTML, and are not sent to a provider or used to change API payloads.
    const messagePatterns=(vocabulary.messageTemplates||[]).map(template=>({
        template,
        regex:new RegExp('^'+template.split(/\{\d+\}/).map(part=>part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('(.+?)')+'$')
    }));
    function translate(text, code=language) {
        if(code==='en'||!vocabulary.catalogs[code]||typeof text!=='string')return text;
        const leading=text.match(/^\s*/)[0], trailing=text.match(/\s*$/)[0];
        const source=text.trim().replace(/\s+/g,' ');
        if(!source)return text;
        const key=aliases[source]||source;
        const dict=vocabulary.catalogs[code];
        let result=dict[key]||lowerIndexes[code][key.toLowerCase()];
        if(!result){
            for(const {template,regex} of messagePatterns){
                const match=source.match(regex);
                if(match){
                    result=dict[template].replace(/\{(\d+)\}/g,(_,index)=>{
                        const value=match[Number(index)+1];
                        return vocabulary.literalMessageTemplates?.includes(template)?value:translate(features[value]||value,code);
                    });
                    break;
                }
            }
        }
        if(!result){
            const feature=source.match(/^(N|P|K|ph|temperature|humidity|rainfall)(\s*=\s*[-\d.]+)$/);
            const range=source.match(/^Enter between ([\d.-]+) and ([\d.-]+)$/);
            const probabilityNote="Probability is the model's score on this dataset, not a guarantee of agricultural success.";
            if(feature)result=translate(features[feature[1]],code)+feature[2];
            else if(range)result=translate('Enter between',code)+' '+range[1]+' – '+range[2];
            else if(source.startsWith(probabilityNote+' '))result=translate(probabilityNote,code)+source.slice(probabilityNote.length);
            else if(source.includes(' · '))result=source.split(' · ').map(s=>translate(s,code)).join(' · ');
            else if(/^[·:]\s+/.test(source))result=source.match(/^[·:]\s+/)[0]+translate(source.replace(/^[·:]\s+/,''),code);
            else if(source==='Top 3 Recommended Crops')result=translate('Recommended crop',code)+' (3)';
            else if(source.endsWith(' (%)'))result=translate(source.slice(0,-4),code)+' (%)';
            else if(source==='Probability')result=translate('Model probability',code);
            else if(source==='Confidence:')result=translate('Confidence',code)+':';
            else if(source.endsWith(':'))result=translate(source.slice(0,-1),code)+':';
            else if(source==='Select crop…')result=translate('Select crop',code)+'…';
            else if(/^\([^()]+\)$/.test(source))result='('+translate(source.slice(1,-1),code)+')';
            else if(/^Total (Urea|DAP|MOP)$/.test(source))result=translate('Total',code)+' '+translate(source.slice(6),code);
            else if(/^\d+ days$/.test(source))result=source.replace('days',translate('days',code));
            else if(source.includes(', ')&&source.split(', ').every(part=>dict[part]))result=source.split(', ').map(part=>translate(part,code)).join(', ');
            else {
                // Keep standard unit notation intact while translating the label.
                const labelled=source.match(/^(.+?)(\s+\([^()]+\))$/);
                if(labelled&&translate(labelled[1],code)!==labelled[1])result=translate(labelled[1],code)+labelled[2];
            }
        }
        return result?leading+result+trailing:text;
    }
    function rememberAndTranslate(node) {
        const current=node.nodeValue;
        const previous=originals.get(node);
        const source=previous&&previous.rendered===current?previous.source:current;
        const rendered=translate(source);
        if(current!==rendered)node.nodeValue=rendered;
        originals.set(node,{source,rendered});
    }
    function translateElement(element) {
        if(element.closest(skip))return;
        // Options without a value inherit their label as the value. Capture it
        // BEFORE changing the label, or API payloads/season filters would break.
        if(element.tagName==='OPTION'&&!element.hasAttribute('value'))element.value=element.textContent;
        let saved=attributes.get(element)||{};
        ['placeholder','title','aria-label','alt'].forEach(name=>{
            if(!element.hasAttribute(name))return;
            const current=element.getAttribute(name),old=saved[name];
            const source=old&&old.rendered===current?old.source:current;
            const rendered=translate(source);
            if(rendered!==current)element.setAttribute(name,rendered);
            saved[name]={source,rendered};
        });
        attributes.set(element,saved);
    }
    function translateTree(root) {
        if(root.nodeType===3){
            if(!root.parentElement?.closest(skip)){
                // A label may be replaced asynchronously on an existing option.
                // Save its machine value before translating that text node too.
                if(root.parentElement)translateElement(root.parentElement);
                rememberAndTranslate(root);
            }
            return;
        }
        if(root.nodeType!==1||root.closest(skip))return;
        translateElement(root);
        const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
        let node;while((node=walker.nextNode())){
            if(node.nodeType===1)translateElement(node);
            else if(!node.parentElement?.closest(skip))rememberAndTranslate(node);
        }
    }
    function observe(){observer.observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label','alt']});}
    function apply(root=document.body){
        observer?.disconnect();
        translateTree(root);
        if(observer)observe();
    }
    function localizeChart(chart){
        let source=chartSources.get(chart);
        if(!source){
            source={labels:[...(chart.data.labels||[])],datasets:chart.data.datasets.map(d=>d.label),
                    axes:Object.fromEntries(Object.entries(chart.options.scales||{}).filter(([,s])=>s.title?.text).map(([key,s])=>[key,s.title.text]))};
            chartSources.set(chart,source);
        }
        chart.data.labels=source.labels.map(label=>typeof label==='string'?translate(label):label);
        chart.data.datasets.forEach((d,i)=>{if(source.datasets[i])d.label=translate(source.datasets[i]);});
        Object.entries(source.axes).forEach(([key,value])=>{chart.options.scales[key].title.text=translate(value);});
        chart.update('none');
    }
    function setLanguage(code){
        language=vocabulary.catalogs[code]?code:'en';
        try{localStorage.setItem('ca_language',language);}catch(_){}
        document.documentElement.lang=language;
        document.documentElement.dir=language==='ur'?'rtl':'ltr';
        if(originalTitle)document.title=originalTitle.split(' | ').map(part=>translate(part)).join(' | ');
        document.getElementById('language-select').value=language;
        const notice=document.getElementById('language-notice');
        notice.hidden=language==='en';
        notice.textContent=translate('Some detailed technical notes are shown in English.');
        apply();
        charts.forEach(chart=>{if(chart.canvas?.isConnected){try{localizeChart(chart);}catch(error){console.warn('Chart translation skipped',error);}}else charts.delete(chart);});
        document.dispatchEvent(new CustomEvent('languagechange',{detail:{language}}));
    }
    global.CropI18n={t:translate,setLanguage,apply,get language(){return language;},
        registerChart(chart){charts.add(chart);try{localizeChart(chart);}catch(error){console.warn('Chart translation skipped',error);}}};
    document.addEventListener('DOMContentLoaded',()=>{
        const select=document.getElementById('language-select');
        vocabulary.languages.forEach(([code,name])=>{const option=document.createElement('option');option.value=code;option.textContent=name;option.lang=code;select.appendChild(option);});
        select.addEventListener('change',()=>setLanguage(select.value));
        observer=new MutationObserver(records=>{
            observer.disconnect();
            // Mutation callbacks include asynchronously inserted results, errors,
            // dropdown options and toasts. Never replace elements or event handlers.
            const roots=new Set();records.forEach(record=>{
                if(record.type==='characterData'||record.type==='attributes')roots.add(record.target);
                else record.addedNodes.forEach(node=>roots.add(node));
            });
            roots.forEach(root=>{if(root.isConnected)translateTree(root);});
            observe();
        });
        setLanguage(language);
    });
})(window);
