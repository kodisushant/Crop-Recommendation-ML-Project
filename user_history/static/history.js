/** History UI uses stable record IDs; translated labels never become API keys. */
(function(global){
    'use strict';
    function node(tag,text,className){
        const element=document.createElement(tag);
        if(text!==undefined)element.textContent=text;
        if(className)element.className=className;
        return element;
    }
    function formatDate(value){
        return new Intl.DateTimeFormat(global.CropI18n?.language||'en',{
            dateStyle:'medium',timeStyle:'short'
        }).format(new Date(value));
    }
    let recentItems=null;
    async function recent(){
        const target=document.getElementById('hist');
        if(!target)return;
        target.replaceChildren();
        const row=node('tr'),cell=node('td');cell.colSpan=3;row.append(cell);target.append(row);
        await global.CropAccount.ready;
        if(!global.CropAccount.user){
            cell.textContent=global.CropAccount.unavailable?'Account and history storage is unavailable. Please try again.':'Sign in to view your history.';
            return;
        }
        try{
            if(recentItems===null)recentItems=(await fetchApi('/api/history?limit=6')).items;
            target.replaceChildren();
            if(!recentItems.length){cell.textContent='No saved history yet.';target.append(row);return;}
            for(const item of recentItems){
                const entry=node('tr');
                entry.append(node('td',formatDate(item.created_at)),node('td',item.crop?capitalizeFirstLetter(item.crop):'OUT OF RANGE'),node('td',item.status));
                target.append(entry);
            }
        }catch(error){cell.textContent=error.message;target.replaceChildren(row);}
    }
    async function start(){
        const container=document.getElementById('history-items');
        const message=document.getElementById('history-message');
        const more=document.getElementById('history-more');
        const report=document.getElementById('result');
        const records=new Map();let cursor=null,busy=false;
        function render(){
            container.replaceChildren();
            for(const item of records.values()){
                const card=node('article',undefined,'card');card.dataset.id=item.id;
                const date=node('time',formatDate(item.created_at),'note');date.dateTime=item.created_at;
                card.append(date,node('h3',item.crop?capitalizeFirstLetter(item.crop):'OUT OF RANGE'));
                card.append(node('p',item.source==='soil-analysis'?'Soil Analysis':'Crop Recommendation'));
                const status=node('p');status.append(node('span','Status'),document.createTextNode(': '),node('span',item.status));card.append(status);
                if(item.probability!==null){
                    const confidence=node('p');confidence.append(node('span','Model probability'),document.createTextNode(': '+(item.probability*100).toFixed(1)+'%'));card.append(confidence);
                }
                const table=node('table');
                for(const [key,value]of Object.entries(item.inputs)){
                    if(value===null)continue;
                    const row=node('tr');row.append(node('th',global.CropFields[key]?.label||'State'),node('td',String(value)));table.append(row);
                }
                card.append(table);
                const actions=node('div',undefined,'inl history-actions');
                for(const [action,label]of [['view','View report'],['reuse','Use these inputs'],['delete','Delete entry']]){
                    const button=node('button',label,'btn ghost sm');button.type='button';button.dataset.action=action;actions.append(button);
                }
                card.append(actions);container.append(card);
            }
        }
        async function load(){
            if(busy)return;
            busy=true;more.disabled=true;message.textContent='Loading history...';
            try{
                const url='/api/history?limit=20'+(cursor?'&before='+encodeURIComponent(cursor):'');
                const response=await fetchApi(url);
                response.items.forEach(item=>records.set(item.id,item));cursor=response.next_cursor;
                render();more.hidden=!cursor;message.textContent=records.size?'':'No saved history yet.';
            }catch(error){message.textContent=error.message;}
            finally{busy=false;more.disabled=false;}
        }
        await global.CropAccount.ready;
        if(!global.CropAccount.user){
            message.textContent=global.CropAccount.unavailable?'Account and history storage is unavailable. Please try again.':'Sign in to view your history.';
            document.getElementById('history-login').hidden=false;return;
        }
        more.addEventListener('click',load);
        container.addEventListener('click',async event=>{
            const button=event.target.closest('button[data-action]');if(!button)return;
            const card=button.closest('[data-id]'),item=records.get(card.dataset.id);if(!item)return;
            const action=button.dataset.action;
            if(action==='reuse'){
                saveFormValues(item.inputs);
                window.location.assign(item.source==='soil-analysis'?'/soil-analysis':'/recommendation');return;
            }
            if(action==='delete'&&!window.confirm(global.CropI18n.t('Delete this history entry?')))return;
            button.disabled=true;
            try{
                if(action==='view'){
                    const detail=await fetchApi('/api/history/'+encodeURIComponent(item.id));
                    report.hidden=false;displayRecommendationResult(detail.result);
                    report.dataset.recordId=item.id;report.scrollIntoView({behavior:'smooth',block:'start'});
                }else if(action==='delete'){
                    await fetchApi('/api/history/'+encodeURIComponent(item.id),null,'DELETE');
                    records.delete(item.id);render();message.textContent='History entry deleted.';
                    if(report.dataset.recordId===item.id){report.replaceChildren();report.hidden=true;}
                }
            }catch(error){message.textContent=error.message;}
            finally{button.disabled=false;}
        });
        document.addEventListener('languagechange',render);
        await load();
    }
    global.CropHistory={start,recent};
})(window);
