"""Modern API portal with safe GET execution and opt-in simulator console.

Legacy write endpoints remain documentation-only. This UI is not authorization.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse


router = APIRouter(include_in_schema=False)


@router.get('/docs', response_class=HTMLResponse)
def modern_docs() -> HTMLResponse:
    return HTMLResponse(PORTAL_HTML)


@router.get('/docs/swagger', response_class=HTMLResponse)
def swagger_reference() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url='/openapi.json',
        title='Autonomous Plant Platform | API Reference',
        swagger_ui_parameters={
            'deepLinking': True,
            'docExpansion': 'none',
            'filter': True,
            'displayRequestDuration': True,
            # UI convenience only; not an actual authorization boundary.
            'supportedSubmitMethods': [],
        },
    )


def create_docs_router() -> APIRouter:
    """Return the module's static routes without touching the live simulator."""
    return router


PORTAL_HTML = r'''<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="color-scheme" content="dark"/>
<title>Developer Center — Autonomous Plant Platform</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%23152132'/%3E%3Cpath d='M33 9L17 35h14l-4 20 20-31H33z' fill='%2354e0c6'/%3E%3C/svg%3E"/>
<style>
:root {color-scheme:dark; --bg:#0b111c;--side:#0f1827;--panel:#152236;--panel2:#1b2a41;--line:#2d3b51;--ink:#edf4ff;--muted:#9caec4;--mint:#5ce3c6;--blue:#8eb4ff;--amber:#ffd180;--red:#ff8e9b;--violet:#cba8ff;--radius:16px}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,'Segoe UI',sans-serif;margin:0}
button,input,a{font:inherit}a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}button{cursor:pointer}
.layout{display:grid;grid-template-columns:262px minmax(0,1fr);min-height:100vh}
.sidebar{background:var(--side);border-right:1px solid var(--line);padding:24px 17px;position:sticky;top:0;height:100vh;overflow:auto}
.brand{display:flex;align-items:center;gap:12px;padding:2px 7px 24px}.brandicon{width:39px;height:39px;display:grid;place-items:center;border-radius:13px;background:linear-gradient(130deg,#204a64,#163f47);color:var(--mint);font-size:23px;font-weight:900;box-shadow:0 8px 25px #0004}
.brand strong{display:block;letter-spacing:.01em;font-size:14px}.brand small{display:block;color:var(--muted);font-size:11px;letter-spacing:.05em;text-transform:uppercase}
.search{position:relative;margin-bottom:20px}.search input{width:100%;background:#19283b;color:var(--ink);border:1px solid #3c5069;border-radius:11px;padding:11px 41px 11px 13px;outline:0}.search input:focus{border-color:var(--mint);box-shadow:0 0 0 3px #58d9bb20}.search kbd{position:absolute;right:10px;top:11px;font:11px/1.8 monospace;color:#bdcbdc;border:1px solid #526277;border-radius:5px;padding:0 4px}
.navlabel{color:#738ba7;text-transform:uppercase;font-size:10px;font-weight:800;letter-spacing:.18em;margin:20px 10px 9px}.navitem{color:#c4d3e5;display:flex;align-items:center;justify-content:space-between;padding:11px 12px;border-radius:9px;margin:2px 0;text-decoration:none;border:1px solid transparent}.navitem:hover,.navitem.active{background:#21354d;text-decoration:none;color:#fff}.navitem.active{border-color:#2a5965}.navitem .count{background:#28394f;border-radius:6px;padding:0 6px;font-size:11px;color:#a8bbd3}.navitem[hidden]{display:none}
.sidebottom{font-size:12px;color:var(--muted);padding:14px 10px;border-top:1px solid var(--line);margin-top:28px}
.main{padding:25px clamp(20px,4.4vw,75px) 85px;max-width:1700px;width:100%;margin:0 auto}
.topbar{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:30px}.breadcrumb{font-size:13px;color:var(--muted)}.toplinks{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.toplink{border:1px solid #3b4e66;border-radius:9px;padding:7px 12px;background:#152239;color:#d5e5fb;font-size:12px}.toplink:hover{border-color:var(--mint);text-decoration:none}
.hero{position:relative;overflow:hidden;border-radius:23px;border:1px solid #2e5265;background:radial-gradient(ellipse at 90% 10%,#215b636c,transparent 52%),radial-gradient(ellipse at 1% 96%,#2b406976,transparent 50%),linear-gradient(145deg,#142438,#12202f);padding:35px clamp(22px,4vw,48px);box-shadow:0 18px 55px #0003}
.hero:after{content:'◌';position:absolute;right:6%;top:-95px;color:#64d5c315;font-size:330px;line-height:1;pointer-events:none}.eyebrow{display:inline-flex;align-items:center;gap:7px;color:var(--mint);font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.dot{width:7px;height:7px;background:var(--mint);border-radius:50%;box-shadow:0 0 12px var(--mint)}h1{font-size:clamp(28px,3.6vw,45px);line-height:1.14;letter-spacing:-.045em;max-width:790px;margin:15px 0}.lead{color:#b8c9d9;max-width:740px;font-size:15px;margin:0}.heroactions{display:flex;flex-wrap:wrap;gap:10px;margin-top:25px}.action{display:inline-flex;gap:8px;align-items:center;border:1px solid #5a7084;background:#203b54;color:#edfaff;padding:10px 15px;border-radius:10px;font-weight:700;font-size:13px}.action.primary{background:var(--mint);color:#08262e;border-color:var(--mint)}.action:hover{text-decoration:none;filter:brightness(1.09)}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin:17px 0 23px}.stat{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:17px 20px}.stat strong{display:block;font-size:26px;font-weight:750;letter-spacing:-.035em}.stat span{display:block;color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.09em;font-weight:700}
.notice{display:flex;gap:12px;align-items:flex-start;background:#3b321f70;border:1px solid #8b6c3b80;border-radius:12px;padding:14px 17px;color:#f9dca4;font-size:13px}.notice strong{color:#fff0cb}.notice .mark{font-size:18px;line-height:1.1}
.sectionHead{margin-top:38px;margin-bottom:17px;display:flex;align-items:center;justify-content:space-between;gap:12px}.sectionHead h2{font-size:23px;letter-spacing:-.025em;margin:0}.sectionHead p{color:var(--muted);margin:3px 0 0;font-size:13px}.smallpill{font-size:11px;border-radius:20px;border:1px solid #395066;color:#becfe1;padding:5px 10px;white-space:nowrap}
.group{margin-bottom:31px;scroll-margin-top:26px}.grouptitle{display:flex;align-items:center;gap:9px;margin:0 0 12px;font-size:16px}.grouptitle .symbol{display:grid;place-items:center;background:#20344c;color:var(--mint);width:29px;height:29px;border-radius:9px}.grouptitle small{color:var(--muted);font-weight:500}
.endpoint{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin-bottom:9px;overflow:hidden}.endpoint[open]{border-color:#537185;box-shadow:0 13px 35px #0002}.endpoint>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:12px;padding:14px 16px;min-height:65px}.endpoint>summary::-webkit-details-marker{display:none}.endpoint>summary:hover{background:#1b2b40}.method{display:inline-flex;justify-content:center;align-items:center;font:800 11px/1 monospace;min-width:63px;padding:10px 9px;border-radius:7px;letter-spacing:.04em}.get{color:#92f5d6;background:#183e3a}.post{color:#ffdaa0;background:#584228}.delete{color:#ffb4b9;background:#553039}.put,.patch{color:#d4b8ff;background:#393050}.other{color:#b1cbff;background:#31425b}.path{font:600 13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.brief{color:#a5b5cb;font-size:12px;margin-left:auto;text-align:right;max-width:39%}.chev{color:var(--muted);font-size:17px;margin-left:5px}.endpoint[open] .chev{transform:rotate(90deg)}.endpointbody{padding:18px 18px 20px;border-top:1px solid var(--line);background:#101d2f}.endpointbody h4{font-size:12px;text-transform:uppercase;color:#a8bad1;letter-spacing:.1em;margin:22px 0 8px}.endpointbody p{font-size:13px;color:#b6c5d6;white-space:pre-wrap}.endpointbody .pill{display:inline-block;background:#294057;border:1px solid #435b72;border-radius:6px;padding:3px 8px;color:#b9d8ed;margin:4px 5px 4px 0;font:11px monospace}.endpointbody pre{color:#bbf3e6;background:#091420;border:1px solid #30415a;border-radius:11px;padding:14px;white-space:pre-wrap;overflow-wrap:anywhere;overflow:auto;max-height:310px;font:12px/1.6 ui-monospace,Consolas,monospace}.note{font-size:12px;color:#f3d3a0;background:#39312050;padding:11px 12px;border-radius:9px;border:1px solid #775f3d}.copy{background:#273f56;border:1px solid #48637a;color:#e8f8ff;border-radius:8px;padding:8px 11px;font-size:12px}.copy:focus-visible,button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid var(--mint);outline-offset:2px}
.empty{border:1px dashed #587087;padding:22px;border-radius:12px;color:var(--muted)}footer{margin-top:40px;color:#738ba7;font-size:12px}.loading{color:var(--muted)}
@media(max-width:1050px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.layout{grid-template-columns:215px minmax(0,1fr)}.sidebar{padding:20px 10px}.main{padding:23px 25px 65px}.brief{max-width:33%}}
@media(max-width:720px){.layout{display:block}.sidebar{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line)}.brand{padding-bottom:13px}.search{margin-bottom:7px}.navlabel,.navitem,.sidebottom{display:none}.topbar{margin-bottom:20px}.hero{padding:25px}.main{padding:19px 15px 50px}.stats{gap:8px}.stat{padding:12px}.stat strong{font-size:20px}.brief{display:none}}
@media(prefers-reduced-motion:no-preference){.endpoint,.action,.navitem{transition:background .16s,border-color .16s}}

.try-panel{background:#13283a;border:1px solid #36546d;border-radius:12px;padding:15px;margin-top:16px}
.try-panel label{display:block;color:#c7d9e8;font-size:12px;font-weight:650;margin:10px 0 5px}
.try-panel input,.try-panel textarea{display:block;width:100%;font:13px/1.5 ui-monospace,Consolas,monospace;border:1px solid #4f6b86;border-radius:8px;color:#effaff;background:#091c2b;padding:9px 11px}
.try-panel textarea{min-height:90px;resize:vertical}.try-panel .buttons{display:flex;align-items:center;gap:12px;margin-top:14px;flex-wrap:wrap}
.try-panel .buttons button{background:#56d9c0;color:#092532;border:0;border-radius:8px;font-weight:800;padding:9px 16px}
.try-panel .buttons button:disabled{opacity:.55;cursor:wait}.try-panel .verify{display:flex;gap:8px;align-items:center;color:#ffd79c;font-size:12px;margin-top:12px}
.try-panel .verify input{width:auto}.try-panel pre{max-height:290px;white-space:pre-wrap;overflow-wrap:anywhere}
</style>
</head>
<body>
<div class="layout">
<aside class="sidebar">
  <div class="brand"><span class="brandicon" aria-hidden="true">ϟ</span><div><strong>Autonomous Plant</strong><small>Developer Center</small></div></div>
  <div class="search"><label for="search" class="sr-only" style="position:absolute;left:-9999px">Endpoint ara</label><input id="search" type="search" autocomplete="off" placeholder="Endpoint veya açıklama ara" aria-label="Endpoint ara"><kbd>/</kbd></div>
  <div class="navlabel">API MODÜLLERİ</div><nav id="navigation" aria-label="API modülleri"><span class="loading">Yükleniyor…</span></nav>
  <div class="sidebottom">● Local API reference<br/>Gerçek PLC / SCADA bağlantısı yok.<br/>Üretim kontrolü için yetkilendirilmemiştir.</div>
</aside>
<main class="main">
 <div class="topbar"><div class="breadcrumb">PLATFORM <span aria-hidden="true"> / </span> GELİŞTİRİCİ DOKÜMANTASYONU</div><div class="toplinks"><a class="toplink" href="/platform/dashboard">Ana panel ↗</a><a class="toplink" href="/docs/swagger">Swagger ↗</a><a class="toplink" href="/openapi.json" target="_blank" rel="noopener">OpenAPI JSON ↗</a></div></div>
 <header class="hero">
  <span class="eyebrow"><span class="dot" aria-hidden="true"></span> SİMÜLASYON API · LOCAL INSTANCE</span>
  <h1>Enerji santralleri için etkileşimli API ve simülasyon konsolu.</h1>
  <p class="lead">HES, GES ve RES API uç noktalarını keşfet, GET çağrılarını dene; yalnızca yerel ve açıkça etkinleştirilmiş sentetik simülasyon komutlarını çalıştır.</p>
  <div class="heroactions"><a href="#endpoints" class="action primary">API’leri keşfet →</a><a href="/docs/swagger" class="action">Swagger referansı ↗</a></div>
 </header>
 <div class="stats" aria-label="API istatistikleri">
   <div class="stat"><span>Toplam endpoint</span><strong id="stat-total">—</strong></div>
   <div class="stat"><span>GET / Okuma</span><strong id="stat-gets">—</strong></div>
   <div class="stat"><span>Değişiklik komutları</span><strong id="stat-writes">—</strong></div>
   <div class="stat"><span>API grubu</span><strong id="stat-groups">—</strong></div>
 </div>
 <div class="notice"><span class="mark" aria-hidden="true">⚠</span><div><strong>Yalnızca sentetik simülasyon.</strong> Bu dokümantasyon ekranı kontrol komutu göndermez (varsayılan ayarda). Yerel simülasyon konsolu ayrıca etkinleştirildiğinde yalnızca izin verilen sentetik komutları gönderebilir. Diğer POST/PUT/DELETE yolları yalnızca belgelenir; üretim tesisine açılmadan önce gerçek kimlik doğrulama, erişim politikaları ve bağımsız güvenlik kontrolleri gerekir.</div></div>
 <section id="endpoints" aria-label="Endpoint listesi">
  <div class="sectionHead"><div><h2>API referansı</h2><p>Gruplandırılmış, aranabilir, OpenAPI şemasından otomatik oluşturulan liste</p></div><span class="smallpill" id="visibility">Yükleniyor…</span></div>
  <div id="results" role="region" aria-live="polite"><p class="loading">OpenAPI şeması yükleniyor…</p></div>
 </section>
 <footer>Autonomous Plant Platform · Simülasyon araştırma prototipi · API açıklamaları uygulamanın OpenAPI şemasından alınır.</footer>
</main>
</div>
<script>
'use strict';
const el = id => document.getElementById(id);
const search = el('search');
const verbs = new Set(['get','post','put','patch','delete','head','options','trace']);
const weights = {'Platform':0,'HES':1,'GES':2,'RES':3,'Sistem':4,'Diğer':5};
let operations = [];
let selectedGroup = 'Tümü';
function node(tag, cls, value) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (value !== undefined) e.textContent = String(value);
  return e;
}
function category(path, tags=[]) {
  const words = tags.join(' ').toLowerCase();
  const p = path.toLowerCase();
  if (/wind|turbine|res\b/.test(p+' '+words)) return 'RES';
  if (/solar|ges\b|mppt|inverter/.test(p+' '+words)) return 'GES';
  if (/platform|overview|sim-console/.test(p+' '+words)) return 'Platform';
  if (/hydro|hes\b|units|plant|sim\/|alarms|decisions|anomal|ml\//.test(p+' '+words)) return 'HES';
  if (/health|openapi|docs/.test(p)) return 'Sistem';
  return 'Diğer';
}
function addTag(target, str){target.append(node('span','pill',str));}
function canExecute(op) {
  return op.method === 'get' || (
    op.method === 'post' &&
    /^\/api\/v1\/sim-console\/(?:\{plant\}\/(?:start|pause|step|reset|mode)|hes\/(?:auto|unit\/(?:start|stop)|tick))$/.test(op.path)
  );
}
function testPanel(op) {
  const panel = node('div','try-panel');
  panel.append(node('h4','','Try it out · Execute'));
  const inputs=[];
  for (const param of op.info.parameters || []) {
    if (!['path','query'].includes(param.in)) continue;
    const label=node('label','',param.name+(param.required?' *':''));
    const input=node('input');input.type='text';
    input.value=param.name==='plant'?'ges':param.name==='active'?'true':param.name==='unit_id'?'UNIT_1':'';
    input.placeholder=param.name;label.append(input);panel.append(label);
    inputs.push({param,input});
  }
  let bodyBox=null;
  if (op.method==='post' && op.info.requestBody) {
    const label=node('label','','JSON istek gövdesi');
    bodyBox=node('textarea');
    bodyBox.value=op.path.endsWith('/mode')?'{"mode":"NORMAL"}':
      op.path.includes('/unit/')?'{"unit_id":"UNIT_1"}':'{}';
    label.append(bodyBox);panel.append(label);
  }
  let confirmBox=null;
  if(op.method!=='get') {
    const label=node('label','verify');confirmBox=node('input');
    confirmBox.type='checkbox';label.append(confirmBox);
    label.append(node('span','','Sadece yerel sentetik simülasyon — gerçek ekipman kontrolü değil.'));
    panel.append(label);
  }
  const buttons=node('div','buttons');const button=node('button','','Execute');button.type='button';
  const status=node('span','',op.method==='get'?'Salt-okunur çağrı':'Kontrol ön koşulu: APP_SIM_CONSOLE_WRITES=1');
  buttons.append(button,status);panel.append(buttons);
  const output=node('pre','','Henüz çağrı yapılmadı.');panel.append(output);
  button.addEventListener('click', async () => {
    if(confirmBox && !confirmBox.checked) {output.textContent='Önce sentetik simülasyon onayını işaretle.';return;}
    let path=op.path;const qs=new URLSearchParams();
    for(const {param,input} of inputs){
      const v=input.value.trim();
      if(param.required && !v){output.textContent='Eksik parametre: '+param.name;return;}
      if(param.in==='path') path=path.replace('{'+param.name+'}',encodeURIComponent(v));
      else if(v) qs.set(param.name,v);
    }
    if(path.includes('{')){output.textContent='Eksik path parametresi';return;}
    if(qs.size)path+='?'+qs.toString();
    let payload;
    if(bodyBox){try{payload=JSON.stringify(JSON.parse(bodyBox.value));}
      catch{output.textContent='JSON biçimi geçersiz';return;}}
    button.disabled=true;status.textContent='Gönderiliyor…';
    try{
      const headers={'Accept':'application/json'};
      if(op.method!=='get')headers['X-Sim-Console-Confirm']='SIMULATION_ONLY';
      if(payload!==undefined)headers['Content-Type']='application/json';
      const response=await fetch(path,{method:op.method.toUpperCase(),headers,
        body:payload,credentials:'same-origin',cache:'no-store'});
      const content=await response.text();
      let result=content;try{result=JSON.stringify(JSON.parse(content),null,2)}catch{}
      output.textContent=`HTTP ${response.status} ${response.statusText}\n${result}`;
      status.textContent=response.ok?'Başarılı':'İstek reddedildi';
    }catch(error){output.textContent='İstek başarısız: '+error.message;status.textContent='Bağlantı hatası';}
    finally{button.disabled=false;}
  });
  return panel;
}
function makeOperation(op) {
  const details = node('details','endpoint');
  const summary = node('summary');
  summary.append(node('span','method '+(verbs.has(op.method)?op.method:'other'),op.method.toUpperCase()));
  summary.append(node('span','path',op.path));
  summary.append(node('span','brief',op.info.summary || op.info.operationId || 'API endpoint'));
  summary.append(node('span','chev','›'));
  details.append(summary);
  const body = node('div','endpointbody');
  const desc = op.info.description || op.info.summary || 'Bu uç nokta için açıklama belirtilmemiş.';
  body.append(node('p','',desc));
  if (op.method !== 'get' && op.method !== 'head') {
    body.append(node('p','note',canExecute(op)?'Bu komut sadece yerel simülatörde ve açık opt-in sonrasında çalışır.':'Bu komut burada çalıştırılamaz; salt okunur olmayan genel API yolları kapalıdır.'));
  }
  if (op.info.parameters?.length) {
    body.append(node('h4','','Parametreler'));
    const wrap = node('div');
    for (const p of op.info.parameters) addTag(wrap, `${p.name} · ${p.in}${p.required?' · zorunlu':''}`);
    body.append(wrap);
  }
  if (op.info.requestBody) {
    body.append(node('h4','','İstek gövdesi'));
    const pre = node('pre');
    pre.textContent = JSON.stringify(op.info.requestBody.content ?? op.info.requestBody,null,2);
    body.append(pre);
  }
  if (op.info.responses) {
    body.append(node('h4','','Yanıtlar'));
    const wrap = node('div');
    for (const [status, spec] of Object.entries(op.info.responses)) addTag(wrap,`${status} · ${spec.description || 'Yanıt'}`);
    body.append(wrap);
    const first = op.info.responses['200'] || op.info.responses['201'] || Object.values(op.info.responses)[0];
    if (first?.content) {
      const pre = node('pre');
      pre.textContent = JSON.stringify(first.content,null,2);
      body.append(pre);
    }
  }
  if(canExecute(op)) body.append(testPanel(op));
  const curl = `curl -X ${op.method.toUpperCase()} "${location.origin}${op.path}"`;
  body.append(node('h4','','Komut referansı (çalıştırılmaz)'));
  const pre = node('pre','',curl);body.append(pre);
  const button = node('button','copy','Komutu kopyala');button.type='button';
  button.addEventListener('click',async () => {
    try {await navigator.clipboard.writeText(curl);button.textContent='Kopyalandı ✓';}
    catch {button.textContent='Kopyalama izni verilmedi';}
  });
  body.append(button);
  details.append(body);
  return details;
}
function renderNav(groups) {
  const nav = el('navigation');nav.replaceChildren();
  const names = ['Tümü', ...groups];
  for (const name of names) {
    const a = node('a','navitem'+(selectedGroup===name?' active':''));
    a.href='#endpoints';a.append(node('span','',name));
    a.append(node('span','count',name==='Tümü'?operations.length:operations.filter(x=>x.group===name).length));
    a.addEventListener('click',event=>{event.preventDefault();selectedGroup=name;render();el('endpoints').scrollIntoView({behavior:'smooth'});});
    nav.append(a);
  }
}
function render() {
  const query = search.value.trim().toLocaleLowerCase('tr-TR');
  const groups = [...new Set(operations.map(x=>x.group))].sort((a,b)=>(weights[a]??99)-(weights[b]??99)||a.localeCompare(b,'tr'));
  const matches = operations.filter(op=>
    (selectedGroup==='Tümü'||op.group===selectedGroup) &&
    [op.path,op.method,op.info.summary,op.info.description,...(op.info.tags||[])].join(' ').toLocaleLowerCase('tr-TR').includes(query));
  el('visibility').textContent = `${matches.length} / ${operations.length} endpoint`;
  renderNav(groups);
  const target=el('results');target.replaceChildren();
  if (!matches.length) {target.append(node('div','empty','Bu aramada endpoint bulunamadı. Filtreyi temizlemeyi dene.'));return;}
  for (const group of groups) {
    const items=matches.filter(op=>op.group===group);
    if (!items.length) continue;
    const section=node('section','group');
    const h=node('h3','grouptitle');h.append(node('span','symbol',({HES:'≋',GES:'☼',RES:'↗',Platform:'◇',Sistem:'⚙',Diğer:'·'})[group]));
    h.append(node('span','',group+' API'));h.append(node('small','',`${items.length} endpoint`));section.append(h);
    for (const op of items) section.append(makeOperation(op));
    target.append(section);
  }
}
async function load() {
  try {
    const response=await fetch('/openapi.json',{cache:'no-store'});
    if(!response.ok) throw Error(`OpenAPI HTTP ${response.status}`);
    const spec=await response.json();
    operations=[];
    for(const [path, methods] of Object.entries(spec.paths||{})) {
      for(const [method, info] of Object.entries(methods||{})) {
        if(!verbs.has(method)) continue;
        operations.push({path,method,info,group:category(path,info.tags||[])});
      }
    }
    operations.sort((a,b)=>a.path.localeCompare(b.path)||a.method.localeCompare(b.method));
    el('stat-total').textContent=operations.length;
    el('stat-gets').textContent=operations.filter(x=>x.method==='get').length;
    el('stat-writes').textContent=operations.filter(x=>!['get','head','options'].includes(x.method)).length;
    el('stat-groups').textContent=new Set(operations.map(x=>x.group)).size;
    render();
  } catch(error) {
    el('results').replaceChildren(node('div','empty',`OpenAPI şeması yüklenemedi: ${error.message}. /openapi.json adresini ve FastAPI kayıtlarını kontrol et.`));
    el('visibility').textContent='Bağlantı hatası';
  }
}
search.addEventListener('input',render);
document.addEventListener('keydown',event=>{
 if(event.key==='/' && document.activeElement!==search && !['INPUT','TEXTAREA'].includes(document.activeElement.tagName)) {event.preventDefault();search.focus();}
 if(event.key==='Escape' && document.activeElement===search) {search.value='';render();search.blur();}
});
load();
</script>

<script>
(() => {
  'use strict';

  const results = document.getElementById('results');
  if (!results) return;

  function enhance() {
    for (const row of results.querySelectorAll(
      'details.endpoint'
    )) {
      const path = row.querySelector(
        'summary .path'
      )?.textContent || '';

      if (!path.includes('/hydro/runs/{run_id}')) {
        continue;
      }

      const panel = row.querySelector('.try-panel');

      if (
        !panel ||
        panel.dataset.hesRunIdHelp === '1'
      ) {
        continue;
      }

      panel.dataset.hesRunIdHelp = '1';

      const label = [
        ...panel.querySelectorAll('label')
      ].find(
        item => item.textContent.trim().startsWith('run_id')
      );

      const input = label?.querySelector('input');
      const button = panel.querySelector(
        '.buttons button'
      );

      if (!input || !button) continue;

      input.type = 'number';
      input.step = '1';
      input.min = '1';
      input.placeholder = 'Örn. 12 (UNIT_1 değil)';

      const guide = document.createElement('p');
      guide.className = 'note';

      guide.textContent =
        'run_id sayısal geçmiş koşu numarasıdır; ' +
        'UNIT_1 canlı ünite kimliğidir. ' +
        'Canlı veriyi ' +
        '/api/v1/hes/live/units/UNIT_1 ' +
        'adresinden oku.';

      panel.insertBefore(guide, label);

      button.addEventListener('click', event => {
        const value = input.value.trim();

        if (
          /^[1-9][0-9]*$/.test(value) &&
          Number.isSafeInteger(Number(value))
        ) {
          return;
        }

        event.preventDefault();
        event.stopImmediatePropagation();

        const output = panel.querySelector('pre');

        if (output) {
          output.textContent =
            'Hatalı run_id. Pozitif tam sayı gir: ' +
            'örneğin 12. UNIT_1 için canlı ünite ' +
            'API’sini kullan.';
        }
      }, true);

      fetch('/api/v1/hydro/runs', {
        cache: 'no-store'
      })
        .then(response =>
          response.ok ? response.json() : []
        )
        .then(runs => {
          const id = Array.isArray(runs)
            ? runs[0]?.id
            : null;

          if (
            !input.value &&
            Number.isSafeInteger(id) &&
            id > 0
          ) {
            input.value = String(id);
          }
        })
        .catch(() => {});
    }
  }

  const observer = new MutationObserver(enhance);

  observer.observe(results, {
    childList: true,
    subtree: true
  });

  enhance();
})();
</script>

</body>
</html>'''
