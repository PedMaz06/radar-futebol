'use strict';
// API client sem dependências. Tokens desta sessão não são expostos ao repositório.
(function(){
 const cfg=window.RADAR_CONFIG||{};
 const base=String(cfg.supabaseUrl||'').replace(/\/+$/,'');
 const publicKey=String(cfg.supabasePublishableKey||'');
 const configured=/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(base) && publicKey.length>15 && !publicKey.includes('COLE_AQUI');
 const AUTH_STORE='radar-v6-session';
 let session=null;
 try{session=JSON.parse(sessionStorage.getItem(AUTH_STORE)||'null')}catch{}
 function store(x){session=x; if(x)sessionStorage.setItem(AUTH_STORE,JSON.stringify(x));else sessionStorage.removeItem(AUTH_STORE)}
 function requireConfig(){if(!configured)throw Error('Configure docs/config.js com a URL e a chave publicável do Supabase. Para conhecer a interface, abra demo.html.')}
 async function jsonRequest(url, options={}){
  const r=await fetch(url,{...options,cache:'no-store'});
  let j=null;try{j=await r.json()}catch{}
  if(!r.ok){throw Error(j?.msg||j?.error_description||j?.message||j?.error||'Falha HTTP '+r.status)}
  return j;
 }
 function keyHeaders(){return {'apikey':publicKey,'Content-Type':'application/json'}}
 async function refresh(){
  requireConfig();if(!session?.refresh_token)throw Error('Sessão expirada. Faça login novamente.');
  try{
   const r=await jsonRequest(base+'/auth/v1/token?grant_type=refresh_token',{method:'POST',headers:keyHeaders(),body:JSON.stringify({refresh_token:session.refresh_token})});
   store({access_token:r.access_token,refresh_token:r.refresh_token,expires_at:Date.now()+r.expires_in*1000,user:r.user||session.user});return session;
  }catch(e){store(null);throw e}
 }
 async function ensure(){requireConfig();if(!session?.access_token)throw Error('Entre com seu e-mail e senha.');if(Date.now()>Number(session.expires_at||0)-90000)await refresh();return session}
 async function query(table,method='GET',params='',body=null,prefer=''){
   await ensure();const headers={...keyHeaders(),Authorization:'Bearer '+session.access_token};if(prefer)headers.Prefer=prefer;
   return jsonRequest(base+'/rest/v1/'+table+(params?'?'+params:''),{method,headers,...(body!==null?{body:JSON.stringify(body)}:{})});
 }
 function sourceState(r){if(!r)return 'not_checked';if(!r.ok)return 'error';return Date.now()-Date.parse(r.checked_at)>90*60000?'stale':'online'}
 const piloted=new Set(cfg.pilotIds||[]);
 const defaults={selected:[...piloted],alertMode:'discreet',period:'72',category:'all',sort:'recent',autoTranslate:false};
 async function snapshot(){
  const [articleRows,sourceRows,settingRows,markRows]=await Promise.all([
   query('radar_articles','GET','select=*&order=first_seen.desc&limit=1000'),
   query('radar_sources','GET','select=*'),
   query('radar_settings','GET','select=prefs&limit=1'),
   query('radar_marks','GET','select=article_id,saved,hidden')
  ]);
  const found=Object.fromEntries(sourceRows.map(r=>[r.id,r]));
  const sources=window.RADAR_CATALOG.entities.map(e=>{const isPilot=piloted.has(e.id);const x=found[e.id];return {id:e.id,state:isPilot?sourceState(x):'unconfigured',checked_at:x?.checked_at||null,error:x?.error||(isPilot?'Ainda não executou a coleta':'Fora do piloto')};});
  const marks=Object.fromEntries(markRows.map(r=>[r.article_id,{saved:r.saved,hidden:r.hidden}]));
  const articles=articleRows.map(a=>({...a,origin:'institutional',priority:a.priority||3,status:'official_domain',first_seen:a.first_seen,published_at:a.published_at||null}));
  const checked=sourceRows.map(s=>Date.parse(s.checked_at)).filter(Number.isFinite);
  return {articles,sources,marks,translations:{},settings:{...defaults,...(settingRows[0]?.prefs||{})},updated_at:checked.length?new Date(Math.max(...checked)).toISOString():null,translation_configured:false};
 }
 async function signIn(email,password){requireConfig();const r=await jsonRequest(base+'/auth/v1/token?grant_type=password',{method:'POST',headers:keyHeaders(),body:JSON.stringify({email,password})});store({access_token:r.access_token,refresh_token:r.refresh_token,expires_at:Date.now()+r.expires_in*1000,user:r.user});return {ok:true}}
 async function checkSession(){await ensure();await jsonRequest(base+'/auth/v1/user',{headers:{...keyHeaders(),Authorization:'Bearer '+session.access_token}});return {authenticated:true}}
 async function signOut(){try{await ensure();await jsonRequest(base+'/auth/v1/logout',{method:'POST',headers:{...keyHeaders(),Authorization:'Bearer '+session.access_token}})}catch{}store(null);return {ok:true}}
 async function saveSettings(x){const old=await query('radar_settings','GET','select=prefs&limit=1');const prefs={...defaults,...(old[0]?.prefs||{}),...x};await query('radar_settings','POST','on_conflict=user_id',[{user_id:session.user.id,prefs}], 'resolution=merge-duplicates,return=minimal');return {settings:prefs}}
 async function mark(x){const rows=await query('radar_marks','GET','select=saved,hidden&article_id=eq.'+encodeURIComponent(x.id)+'&limit=1');let saved=rows[0]?.saved===true,hidden=rows[0]?.hidden===true;if(x.action==='save')saved=!!x.value;else if(x.action==='hide')hidden=!!x.value;else throw Error('Ação inválida');await query('radar_marks','POST','on_conflict=user_id,article_id',[{user_id:session.user.id,article_id:x.id,saved,hidden}], 'resolution=merge-duplicates,return=minimal');return {mark:{saved,hidden}}}
 async function dispatch(path, body){
   if(path==='/api/snapshot')return snapshot();
   if(path==='/api/login')return signIn(body.email,body.password);
   if(path==='/api/logout')return signOut();
   if(path==='/api/settings')return saveSettings(body);
   if(path==='/api/mark')return mark(body);
   if(path==='/api/translate')throw Error('A tradução no painel não está configurada no piloto gratuito. Use o link “Traduzir página”.');
   throw Error('Operação desconhecida');
 }
 window.radarCloud={configured,dispatch,checkSession,piloted};
})();
