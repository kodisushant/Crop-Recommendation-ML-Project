/** Session cookies are managed by the browser. Never store passwords or session
 * tokens in localStorage; only preferences and reusable soil inputs belong there.
 */
(function(global){
    'use strict';
    const account={user:null,unavailable:false,ready:Promise.resolve(null)};
    function updateNavigation(){
        const link=document.getElementById('account-link');
        const name=document.getElementById('account-name');
        const logout=document.getElementById('sign-out');
        if(link)link.hidden=Boolean(account.user);
        if(name){name.textContent=account.user?.username||'';name.hidden=!account.user;}
        if(logout)logout.hidden=!account.user;
    }
    account.refresh=async function(){
        try{
            const response=await fetchApi('/api/auth/me');
            account.user=response.user;account.unavailable=false;
        }catch(_){account.user=null;account.unavailable=true;}
        updateNavigation();
        return account.user;
    };
    account.bindForm=function(mode){
        const form=document.getElementById('account-form');
        form.noValidate=true;
        form.addEventListener('submit',async event=>{
            event.preventDefault();
            const message=document.getElementById('account-message');
            const button=document.getElementById('account-submit');
            const password=document.getElementById('password').value;
            const username=document.getElementById('username').value.trim();
            if(!/^[A-Za-z0-9_.-]{3,32}$/.test(username)){
                message.textContent='Use 3–32 English letters, numbers, dots, underscores or hyphens.';return;
            }
            if(Array.from(password).length<12||Array.from(password).length>128){
                message.textContent='Use 12–128 characters for your password.';return;
            }
            if(mode==='register'&&password!==document.getElementById('confirm-password').value){
                message.textContent='Passwords do not match.';return;
            }
            button.disabled=true;message.textContent='';
            try{
                const data=await fetchApi('/api/auth/'+mode,{
                    username,password
                });
                account.user=data.user;updateNavigation();
                form.reset();window.location.assign('/history');
            }catch(error){message.textContent=error.message;}
            finally{button.disabled=false;}
        });
    };
    global.CropAccount=account;
    document.addEventListener('DOMContentLoaded',()=>{
        account.ready=account.refresh();
        document.getElementById('sign-out')?.addEventListener('click',async event=>{
            const button=event.currentTarget;button.disabled=true;
            try{
                await fetchApi('/api/auth/logout',{});
                account.user=null;updateNavigation();window.location.assign('/');
            }catch(error){showToast(error.message,'error');}
            finally{button.disabled=false;}
        });
    });
    // A back/forward cache must not resurrect private history after sign-out.
    window.addEventListener('pageshow',event=>{if(event.persisted)window.location.reload();});
})(window);
