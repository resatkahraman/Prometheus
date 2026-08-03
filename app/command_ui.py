COMMAND_UI = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Prometheus · Mission Control</title>
<style>
:root{
  color-scheme:dark;
  --bg:#090b0f;
  --sidebar:#0d1015;
  --panel:#12161d;
  --panel-2:#171c24;
  --panel-3:#0e1218;
  --line:#272e39;
  --line-2:#384252;
  --text:#f3f5f8;
  --muted:#939cab;
  --subtle:#687383;
  --brand:#7f8ff0;
  --brand-soft:rgba(127,143,240,.12);
  --good:#53bd92;
  --good-soft:rgba(83,189,146,.12);
  --warn:#dcae57;
  --warn-soft:rgba(220,174,87,.12);
  --bad:#df7080;
  --bad-soft:rgba(223,112,128,.12);
  --shadow:0 22px 56px rgba(0,0,0,.28);
  --r-lg:18px;
  --r-md:12px;
  --r-sm:9px;
}
*{box-sizing:border-box}
html,body{min-height:100%;margin:0}
body{
  background:
    radial-gradient(circle at 50% -25%,rgba(80,91,145,.13),transparent 34%),
    var(--bg);
  color:var(--text);
  font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased;
}
button,input,textarea{font:inherit}
button{border:0;cursor:pointer}
button:disabled{opacity:.38;cursor:not-allowed}
a{color:inherit;text-decoration:none}
.app{min-height:100vh;display:grid;grid-template-columns:230px minmax(0,1fr)}
.sidebar{
  position:sticky;top:0;height:100vh;padding:18px 14px 16px;
  display:flex;flex-direction:column;
  background:var(--sidebar);border-right:1px solid rgba(255,255,255,.06)
}
.brand{display:flex;align-items:center;gap:11px;padding:0 7px 20px}
.brandMark{
  width:38px;height:38px;border-radius:12px;display:grid;place-items:center;
  background:linear-gradient(145deg,#91a0ff,#6878df);font-weight:900;
  box-shadow:0 10px 28px rgba(77,93,196,.23)
}
.brandName{font-size:.82rem;font-weight:830}.brandSub{margin-top:2px;color:var(--muted);font-size:.57rem}
.nav{display:grid;gap:5px}
.navItem{
  min-height:42px;padding:0 11px;border-radius:10px;display:flex;align-items:center;gap:10px;
  color:#98a1af;font-size:.68rem;font-weight:720
}
.navItem.active{background:var(--brand-soft);color:#e3e7ff}
.navNo{width:22px;color:#657082;font-variant-numeric:tabular-nums}
.sideStatus{
  margin-top:auto;padding:12px;border-radius:12px;background:#10141a;border:1px solid rgba(255,255,255,.055)
}
.sideStatus strong{display:block;font-size:.65rem}.sideStatus span{display:block;margin-top:4px;color:var(--muted);font-size:.55rem;line-height:1.45}
.workspace{min-width:0}
.topbar{
  height:64px;position:sticky;top:0;z-index:40;padding:0 clamp(14px,2.6vw,34px);
  display:flex;align-items:center;justify-content:space-between;gap:14px;
  background:rgba(9,11,15,.89);backdrop-filter:blur(18px);
  border-bottom:1px solid rgba(255,255,255,.06)
}
.topTitle{font-size:.8rem;font-weight:790}.topMeta{margin-top:2px;color:var(--muted);font-size:.56rem}
.topActions{display:flex;align-items:center;gap:7px;flex-wrap:wrap;justify-content:flex-end}
.btn{
  min-height:37px;padding:0 12px;border-radius:10px;border:1px solid var(--line);
  color:#d9dee7;background:#171c23;font-size:.64rem;font-weight:760
}
.btn:hover:not(:disabled){background:#202630;border-color:var(--line-2)}
.btnPrimary{background:#7081e4;border-color:#7081e4;color:white}
.btnPrimary:hover:not(:disabled){background:#7b8bec}
.btnGood{background:#267657;border-color:#267657;color:#e3f9ef}
.btnBad{background:#843747;border-color:#843747;color:#ffe8ec}
.btnQuiet{background:transparent}
.content{
  width:min(1510px,100%);margin:0 auto;padding:20px clamp(12px,2.4vw,30px) 72px;
  display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:17px
}
.main{min-width:0;display:grid;gap:15px;align-content:start}
.inspector{min-width:0;display:grid;gap:15px;align-content:start;position:sticky;top:84px;max-height:calc(100vh - 104px);overflow:auto;padding-right:2px}
.card{
  background:linear-gradient(180deg,rgba(18,22,29,.99),rgba(15,18,24,.99));
  border:1px solid rgba(255,255,255,.075);border-radius:var(--r-lg);box-shadow:var(--shadow);overflow:hidden
}
.cardHead{
  min-height:54px;padding:0 17px;display:flex;align-items:center;justify-content:space-between;gap:12px;
  border-bottom:1px solid rgba(255,255,255,.055)
}
.cardTitle{font-size:.78rem;font-weight:800}.caption{margin-top:2px;color:var(--muted);font-size:.56rem}
.commandBar{padding:15px 17px}
.commandLabel{font-size:.56rem;text-transform:uppercase;letter-spacing:.11em;color:#8e98a8;font-weight:800}
.commandRow{margin-top:8px;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px;align-items:end}
.goal{
  width:100%;min-height:82px;max-height:210px;resize:vertical;border:1px solid var(--line);border-radius:12px;
  background:#0b0e13;color:var(--text);padding:12px 13px;outline:none;font-size:.72rem;line-height:1.5
}
.goal:focus,.decisionInput:focus{border-color:#6677ca;box-shadow:0 0 0 3px rgba(102,119,202,.13)}
.mission{padding:17px}
.missionTop{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
.eyebrow{text-transform:uppercase;letter-spacing:.12em;color:#858f9f;font-size:.52rem;font-weight:800}
.missionName{margin:6px 0 5px;font-size:clamp(1.08rem,2.2vw,1.52rem);line-height:1.32;letter-spacing:-.018em}
.missionId{color:var(--subtle);font-size:.53rem;word-break:break-all}
.status{
  min-height:28px;padding:0 9px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;
  background:#242b35;color:#cad1dc;font-size:.52rem;font-weight:780;letter-spacing:.065em;text-transform:uppercase;white-space:nowrap
}
.status.planning,.status.running,.status.reviewing{background:var(--brand-soft);color:#dfe4ff}
.status.awaiting_approval,.status.waiting_decision{background:var(--warn-soft);color:#f2d69f}
.status.completed{background:var(--good-soft);color:#c8f2df}
.status.failed,.status.rework_required{background:var(--bad-soft);color:#ffcbd2}
.healthRow{margin-top:16px;display:grid;grid-template-columns:1fr auto;gap:11px;align-items:center}
.progress{height:7px;border-radius:999px;background:#090c11;overflow:hidden;border:1px solid rgba(255,255,255,.05)}
.progress span{display:block;height:100%;width:0;border-radius:inherit;background:#8191ed;transition:width .38s ease}
.progressPct{font-size:.68rem;font-weight:780}
.stages{margin-top:12px;display:grid;grid-template-columns:repeat(5,1fr);gap:5px}
.stage{padding:7px 3px;border-radius:8px;text-align:center;border:1px solid var(--line);background:#0d1116;color:#5f6977;font-size:.51rem;font-weight:700}
.stage.active{color:#dfe3ff;border-color:#5969b5;background:rgba(89,105,181,.1)}
.stage.done{color:#aee0ca;border-color:#356652;background:rgba(53,102,82,.1)}
.operation{
  margin-top:12px;padding:11px 12px;border-radius:11px;background:#0d1116;border:1px solid rgba(255,255,255,.055);
  display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:start
}
.operationTitle{font-size:.67rem;font-weight:780}.operationCopy{margin-top:3px;color:var(--muted);font-size:.58rem;line-height:1.45}
.operationMeta{text-align:right;color:#717c8b;font-size:.54rem}
.alert{
  margin-top:11px;padding:10px 11px;border-radius:10px;background:var(--bad-soft);border:1px solid rgba(223,112,128,.24);
  color:#f4bec6;font-size:.59rem;line-height:1.45;display:none
}
.alert.show{display:block}
.actionCard{border-color:rgba(127,143,240,.23)}
.actionBody{padding:16px}
.actionKicker{text-transform:uppercase;letter-spacing:.12em;color:#8994a5;font-size:.51rem;font-weight:820}
.actionTitle{margin-top:6px;font-size:1rem;font-weight:830;line-height:1.35}
.actionText{margin-top:6px;color:var(--muted);font-size:.64rem;line-height:1.5}
.actionFacts{margin-top:12px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.fact{padding:10px;border-radius:10px;background:#0d1116;border:1px solid rgba(255,255,255,.055)}
.factLabel{text-transform:uppercase;letter-spacing:.08em;color:#6b7584;font-size:.47rem;font-weight:800}
.factValue{margin-top:5px;color:#d2d8e2;font-size:.61rem;line-height:1.42}
.previewHead{margin-top:12px;display:flex;align-items:center;justify-content:space-between;gap:8px}
.previewTitle{font-size:.57rem;font-weight:770}
.codeBox{
  width:100%;min-height:112px;max-height:250px;margin-top:6px;resize:vertical;border:1px solid var(--line);border-radius:10px;
  background:#090c11;color:#bdc7d5;padding:10px;outline:none;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;
  font-size:.55rem;line-height:1.48
}
.actionButtons{margin-top:10px;display:flex;gap:7px;flex-wrap:wrap}
.decisionInput{
  width:100%;min-height:105px;margin-top:11px;resize:vertical;border:1px solid #51452d;border-radius:11px;
  background:#100f0b;color:var(--text);padding:12px;outline:none;font-size:.68rem;line-height:1.5
}
.queue{margin-top:13px;display:grid;gap:6px}
.queueRow{display:grid;grid-template-columns:28px minmax(0,1fr) auto;gap:9px;align-items:start;padding:8px;border-radius:10px;background:#0d1116}
.queueRow.current{background:var(--brand-soft);border:1px solid rgba(127,143,240,.2)}
.queueRow.done{background:var(--good-soft)}
.queueNo{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:#262d37;font-size:.56rem;font-weight:820}
.queueTitle{font-size:.61rem;font-weight:760}.queueCopy{margin-top:2px;color:var(--muted);font-size:.54rem;line-height:1.4}.queueState{font-size:.5rem;color:#85909f;text-transform:uppercase}
.tableWrap{overflow:auto}
.taskTable{width:100%;border-collapse:collapse;min-width:780px}
.taskTable th{padding:10px 13px;text-align:left;color:#707a89;font-size:.5rem;text-transform:uppercase;letter-spacing:.08em;border-bottom:1px solid rgba(255,255,255,.06)}
.taskTable td{padding:12px 13px;border-bottom:1px solid rgba(255,255,255,.05);vertical-align:middle}
.taskTable tr:last-child td{border-bottom:0}.taskTable tbody tr{cursor:pointer}.taskTable tbody tr:hover{background:rgba(255,255,255,.018)}
.taskTable tbody tr.selected{background:var(--brand-soft)}
.taskId{font-size:.54rem;color:#7f8998}.taskName{font-size:.67rem;font-weight:770;line-height:1.4}.taskSub{margin-top:3px;color:var(--muted);font-size:.54rem}
.agentChip{display:inline-flex;align-items:center;gap:7px;font-size:.58rem}.agentAvatar{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;background:#252c36;font-size:.5rem;font-weight:820}
.evidenceMini{font-size:.55rem;color:#aeb6c3}.evidenceMini strong{color:#dfe3e9}
.empty{padding:30px 17px;text-align:center;color:var(--muted);font-size:.65rem}
.inspectorBody{padding:15px}
.inspectTitle{font-size:.88rem;font-weight:820;line-height:1.38}.inspectMeta{margin-top:6px;color:var(--muted);font-size:.58rem;line-height:1.45}
.section{margin-top:15px}.section:first-child{margin-top:0}.sectionTitle{font-size:.55rem;text-transform:uppercase;letter-spacing:.09em;color:#798493;font-weight:820;margin-bottom:7px}
.list{margin:0;padding-left:17px;color:#c0c7d2;font-size:.59rem;line-height:1.5}
.fileTag{display:inline-block;margin:0 5px 5px 0;padding:5px 7px;border-radius:7px;background:#0d1116;border:1px solid var(--line);font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.51rem;color:#b9c4d3}
.timeline{display:grid;gap:7px}.timelineItem{padding:9px 10px;border-radius:10px;background:#0d1116;border:1px solid rgba(255,255,255,.05)}
.timelineTop{display:flex;justify-content:space-between;gap:8px}.timelineName{font-size:.59rem;font-weight:770}.timelineState{font-size:.49rem;text-transform:uppercase;color:#8993a1}.timelineText{margin-top:4px;color:var(--muted);font-size:.54rem;line-height:1.42}
.outputBlock{border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-top:8px}.outputHead{min-height:38px;padding:0 9px;display:flex;align-items:center;justify-content:space-between;background:#11161d}.outputName{font-size:.55rem;font-weight:770}
.outputText{width:100%;min-height:105px;max-height:280px;resize:vertical;border:0;outline:none;background:#090c11;color:#bdc7d4;padding:10px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.54rem;line-height:1.48}
.tabs{display:flex;gap:4px}.tab{min-height:31px;padding:0 9px;border-radius:8px;background:transparent;color:#7d8796;font-size:.55rem;font-weight:750}.tab.active{background:#202630;color:#e1e5ec}
.tabPanel{display:none}.tabPanel.active{display:block}
.activity{max-height:310px;overflow:auto;padding:8px 13px 13px}.event{padding:8px 0;border-bottom:1px solid rgba(255,255,255,.045)}.event:last-child{border-bottom:0}.eventName{font-size:.56rem;font-weight:760}.eventText{margin-top:3px;color:var(--muted);font-size:.53rem;line-height:1.4}.eventTime{margin-top:4px;color:#596473;font-size:.48rem}
.diag{padding:12px 13px}.diagActions{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:8px}
.toast{position:fixed;right:16px;bottom:16px;z-index:90;max-width:min(390px,calc(100vw - 32px));padding:11px 13px;border-radius:10px;background:#232a34;border:1px solid #424c5a;box-shadow:var(--shadow);font-size:.64rem;opacity:0;transform:translateY(130%);transition:.2s}
.toast.show{opacity:1;transform:none}
@media(max-width:1160px){.content{grid-template-columns:1fr}.inspector{position:static;max-height:none;grid-template-columns:1fr 1fr}}
@media(max-width:820px){.app{display:block}.sidebar{display:none}.topbar{height:auto;min-height:58px;padding:10px 11px}.content{padding:12px 10px 52px;gap:12px}.inspector{grid-template-columns:1fr}.commandRow{grid-template-columns:1fr}.missionTop{display:block}.missionTop>div:last-child{margin-top:10px}.actionFacts{grid-template-columns:1fr}.stages{gap:3px}.stage{font-size:.45rem;padding:6px 1px}.operation{grid-template-columns:1fr}.operationMeta{text-align:left}.topActions .btn:nth-child(2){display:none}}
</style>
</head>
<body>
<div class="app">
<aside class="sidebar">
  <div class="brand"><div class="brandMark">P</div><div><div class="brandName">Prometheus Mission Control</div><div class="brandSub">v0.8.0 · Experience Kernel & Forge</div></div></div>
  <nav class="nav">
    <a class="navItem active" href="#overview"><span class="navNo">01</span>Genel Bakış</a>
    <a class="navItem" href="#action"><span class="navNo">02</span>Eylem Merkezi</a>
    <a class="navItem" href="#tasks"><span class="navNo">03</span>Görevler</a>
    <a class="navItem" href="#inspector"><span class="navNo">04</span>Görev İnceleyici</a>
    <a class="navItem" href="#activity"><span class="navNo">05</span>Aktivite ve Tanılama</a>
  </nav>
  <div class="sideStatus"><strong>Çalışma ilkesi</strong><span>Aynı anda yalnızca sıradaki karar veya onay aktif edilir. Uygulanmış araçlar yeniden çalıştırılmaz.</span></div>
</aside>
<section class="workspace">
<header class="topbar">
  <div><div class="topTitle">Mission Control</div><div id="syncText" class="topMeta">Yeni misyon bekleniyor</div></div>
  <div class="topActions">
    <button id="copyErrorTop" class="btn btnQuiet" disabled>Hata Raporu</button>
    <button id="copyDiagTop" class="btn btnQuiet" disabled>Tanılamayı Kopyala</button>
    <button id="refresh" class="btn" disabled>Yenile</button>
    <a href="/chat" class="btn">Agent Console</a>
  </div>
</header>
<div class="content">
<main class="main">
  <section class="card commandBar">
    <div class="commandLabel">Yeni misyon</div>
    <div class="commandRow">
      <textarea id="goal" class="goal" placeholder="Tamamlanacak hedefi, kısıtları ve kabul koşullarını yaz..."></textarea>
      <div style="display:grid;gap:8px;min-width:210px">
        <select id="autonomy" class="btn" title="Otonomi seviyesi">
          <option value="task" selected>Görev izni · önemli işlemlerde sor</option>
          <option value="locked">Kilitli · her işlemi onayla</option>
          <option value="trusted">Güvenilir workspace · otomatik</option>
        </select>
        <button id="create" class="btn btnPrimary">Planla ve Başlat</button>
      </div>
    </div>
  </section>

  <section id="overview" class="card mission">
    <div class="missionTop">
      <div><div class="eyebrow">Aktif misyon</div><div id="missionTitle" class="missionName">Henüz aktif misyon yok</div><div id="missionId" class="missionId">—</div></div>
      <div style="display:flex;gap:7px;align-items:center;flex-wrap:wrap"><button id="recompile" class="btn btnQuiet" disabled>Planı Yeniden Derle</button><span id="commandStatus" class="status">boş</span></div>
    </div>
    <div class="healthRow"><div class="progress"><span id="progressFill"></span></div><div id="progressPct" class="progressPct">%0</div></div>
    <div id="stages" class="stages"></div>
    <div class="operation"><div><div id="operationTitle" class="operationTitle">Sistem hazır</div><div id="operationCopy" class="operationCopy">Yeni bir misyon oluştur.</div></div><div id="operationMeta" class="operationMeta">—</div></div>
    <div id="missionAlert" class="alert"></div>
  </section>

  <section id="action" class="card actionCard">
    <div class="cardHead"><div><div class="cardTitle">Eylem Merkezi</div><div class="caption">Şu anda senden beklenen tek işlem</div></div><span id="actionBadge" class="status">bekliyor</span></div>
    <div id="actionBody" class="actionBody"><div class="empty">Yeni bir misyon oluştur.</div></div>
  </section>

  <section id="tasks" class="card">
    <div class="cardHead"><div><div class="cardTitle">Görev Portföyü</div><div id="taskCaption" class="caption">Henüz görev yok.</div></div><button id="advance" class="btn btnGood" disabled>Sıradaki Görevi Başlat</button></div>
    <div class="tableWrap"><table class="taskTable"><thead><tr><th>Görev</th><th>Uzman</th><th>Durum</th><th>Kanıt</th><th>İşlem</th></tr></thead><tbody id="taskRows"><tr><td colspan="5"><div class="empty">Yeni bir misyon planla.</div></td></tr></tbody></table></div>
  </section>

  <section id="activity" class="card">
    <div class="cardHead"><div><div class="cardTitle">Aktivite ve Tanılama</div><div class="caption">Kopyalanabilir teknik kayıtlar</div></div><div class="tabs"><button class="tab active" data-tab="events">Aktivite</button><button class="tab" data-tab="diagnostics">Tanılama</button><button class="tab" data-tab="plan">Plan</button></div></div>
    <div id="tab-events" class="tabPanel active"><div id="eventList" class="activity"><div class="empty">Henüz aktivite yok.</div></div></div>
    <div id="tab-diagnostics" class="tabPanel"><div class="diag"><div class="diagActions"><button id="copyErrors" class="btn" disabled>Tüm Hataları Kopyala</button><button id="copyDiagnostics" class="btn" disabled>Tam Tanılamayı Kopyala</button></div><textarea id="diagnosticsText" class="codeBox" readonly placeholder="Tanılama raporu burada gösterilir."></textarea></div></div>
    <div id="tab-plan" class="tabPanel"><div class="diag"><div class="diagActions"><button id="copyPlan" class="btn" disabled>Planı Kopyala</button></div><textarea id="planText" class="codeBox" readonly>—</textarea></div></div>
  </section>
</main>

<aside id="inspector" class="inspector">
  <section class="card">
    <div class="cardHead"><div><div class="cardTitle">Görev İnceleyici</div><div class="caption">Seçili görevin kapsamı ve kanıtları</div></div><button id="copyTask" class="btn btnQuiet" disabled>Görevi Kopyala</button></div>
    <div id="inspectorBody" class="inspectorBody"><div class="empty">Görev tablosundan bir satır seç.</div></div>
  </section>
  <section class="card">
    <div class="cardHead"><div><div class="cardTitle">Misyon Özeti</div><div class="caption">Durum dağılımı</div></div></div>
    <div style="padding:12px;display:grid;grid-template-columns:repeat(2,1fr);gap:7px">
      <div class="fact"><div class="factLabel">Toplam</div><div id="metricTotal" class="factValue" style="font-size:1.05rem;font-weight:820">0</div></div>
      <div class="fact"><div class="factLabel">Tamamlanan</div><div id="metricDone" class="factValue" style="font-size:1.05rem;font-weight:820">0</div></div>
      <div class="fact"><div class="factLabel">Hazır / Revizyon</div><div id="metricReady" class="factValue" style="font-size:1.05rem;font-weight:820">0</div></div>
      <div class="fact"><div class="factLabel">Onay / Karar</div><div id="metricAction" class="factValue" style="font-size:1.05rem;font-weight:820">0</div></div>
    </div>
  </section>
</aside>
</div>
</section>
</div>
<div id="toast" class="toast"></div>
<script>
const PROMETHEUS_CSRF_HEADER="X-Prometheus-CSRF";
const PROMETHEUS_CSRF_VALUE="1";
const PROMETHEUS_SAFE_METHODS=new Set(["GET","HEAD","OPTIONS"]);
const prometheusNativeFetch=window.fetch.bind(window);
window.fetch=(input,init={})=>{
  const inputMethod=input instanceof Request?input.method:"GET";
  const method=String(init.method||inputMethod||"GET").toUpperCase();
  if(PROMETHEUS_SAFE_METHODS.has(method))return prometheusNativeFetch(input,init);
  const headers=new Headers(input instanceof Request?input.headers:undefined);
  new Headers(init.headers||{}).forEach((value,key)=>headers.set(key,value));
  headers.set(PROMETHEUS_CSRF_HEADER,PROMETHEUS_CSRF_VALUE);
  return prometheusNativeFetch(input,{...init,headers});
};
let commandId=null,lastCommand=null,selectedTaskId=null,busy=false,polling=false,pollTimer=null,lastEventCount=0;
let editingDecisionId=null,resumeTimer=null;
const drafts=new Map(),approvalInFlight=new Set();
const $=id=>document.getElementById(id);
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const STATE_LABEL={blocked:"Bağımlılık Bekliyor",ready:"Hazır",running:"Çalışıyor",awaiting_approval:"Onay Gerekli",reviewing:"İncelemede",rework_required:"Devam Gerekli",completed:"Tamamlandı",failed:"Başarısız"};
const AGENT_LABEL={backend:"Backend",frontend:"Frontend",qa:"QA",reviewer:"Reviewer",worker:"Worker",database:"Database",integration:"Integration",architect:"Architect",planner:"Planner",calculation:"Calculation"};
const WEIGHT={blocked:0,ready:.08,running:.42,awaiting_approval:.58,reviewing:.82,rework_required:.45,completed:1,failed:.08};
function toast(message){const el=$("toast");el.textContent=message;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),2600)}
function setBusy(value){busy=value;$("create").disabled=value;$("refresh").disabled=value||!commandId;$("advance").disabled=value||!commandId}
async function api(url,options={}){
  let r;
  try{r=await fetch(url,{headers:{"Content-Type":"application/json"},...options})}
  catch(error){throw new Error(`Sunucuya bağlanılamadı: ${error.message}`)}
  const text=await r.text();
  let data=null;
  if(text){try{data=JSON.parse(text)}catch(_error){data=null}}
  if(!r.ok){
    const detail=data?.detail||text.trim()||r.statusText||"İşlem başarısız";
    throw new Error(`${detail} (HTTP ${r.status})`);
  }
  if(data===null){
    throw new Error(`Sunucu geçerli JSON döndürmedi (HTTP ${r.status}). Yanıt: ${text.slice(0,240)||"boş"}`);
  }
  return data;
}
async function copyText(text,label="Metin"){if(!text){toast("Kopyalanacak içerik yok.");return}try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(text)}else{const area=document.createElement("textarea");area.value=text;area.style.position="fixed";area.style.opacity="0";document.body.appendChild(area);area.focus();area.select();document.execCommand("copy");area.remove()}toast(`${label} kopyalandı.`)}catch(e){toast(`Kopyalama başarısız: ${e.message}`)}}
function pretty(value){if(value==null)return "Önizleme yok.";if(typeof value==="string")return value;try{return JSON.stringify(value,null,2)}catch{return String(value)}}
function elapsed(iso){if(!iso)return "—";const sec=Math.max(0,Math.floor((Date.now()-new Date(iso).getTime())/1000));return sec<60?`${sec} sn`:`${Math.floor(sec/60)} dk ${sec%60} sn`}
function progress(c){if(!c)return 0;if(c.status==="completed")return 100;if(!c.tasks.length)return c.status==="planning"?8:2;const avg=c.tasks.reduce((n,t)=>n+(WEIGHT[t.status]??0),0)/c.tasks.length;return Math.min(98,Math.max(16,Math.round(18+avg*80)))}
function stageData(c){const pendingDecision=c?.decisions?.some(d=>d.status==="pending"),hasTasks=(c?.tasks?.length||0)>0,hasWork=c?.tasks?.some(t=>["running","awaiting_approval","reviewing","completed","rework_required"].includes(t.status)),hasReview=c?.tasks?.some(t=>["reviewing","completed"].includes(t.status));return [["Plan",hasTasks?"done":c?.status==="planning"?"active":""],["Karar",pendingDecision?"active":hasTasks?"done":""],["Üretim",hasWork?(["running","awaiting_approval"].includes(c.status)?"active":"done"):(!pendingDecision&&hasTasks?"active":"")],["İnceleme",c?.status==="reviewing"?"active":hasReview?"done":""],["Teslim",c?.status==="completed"?"done":""]]}
function operation(c){if(!c)return["Sistem hazır","Yeni bir misyon oluştur."];if(c.active_operation)return[c.operation_phase?.replaceAll("_"," ")||c.active_operation,c.operation_message||"İşlem sürüyor."];if(c.decisions.some(d=>d.status==="pending"))return["Yönetici kararı bekleniyor","Karar verilene kadar görevler güvenli biçimde durur."];if(c.tasks.some(t=>t.approval_state==="pending"))return["Güvenli işlem onayı gerekiyor","Eylem Merkezi yalnızca sıradaki onayı gösterir."];if(c.tasks.some(t=>t.approval_state==="processing"))return["Onaylanan işlem uygulanıyor","Araç sonucu checkpoint edildikten sonra sıradaki adım açılır."];if(c.status==="reviewing")return["Bağımsız inceleme","Reviewer diff ve test kanıtlarını kontrol ediyor."];if(c.status==="completed")return["Misyon tamamlandı","Bütün görevler kabul edildi."];if(c.tasks.some(t=>t.status==="rework_required"))return["Devam gereken görev var","Uygulanmış işlemler tekrarlanmadan kalan adımdan devam edilir."];if(c.tasks.some(t=>t.status==="failed"))return["Kısmi başarısızlık","Başarısız görevin raporunu Görev İnceleyici'den kopyala."];if(c.status==="ready")return["Görevler hazır","Sıradaki görevi başlatabilirsin."];return["Durum güncelleniyor",c.status]}
function currentApproval(c){return c.tasks.find(t=>t.approval_state==="processing")||c.tasks.find(t=>t.approval_state==="pending"&&t.status==="awaiting_approval")}
function impact(task){const p=task.approval_preview||{};if(p.path)return p.path;if(p.command)return Array.isArray(p.command)?p.command.join(" "):p.command;if(p.preset)return p.preset;return "Workspace üzerinde güvenli işlem"}
function approvalTitle(task){if(task.approval_tool==="workspace_write")return "Dosya değişikliğini uygula";const p=task.approval_preview||{},text=String(p.preset||p.command||"").toLowerCase();if(/install/.test(text))return "Bağımlılıkları kur";if(/test|pytest|vitest/.test(text))return "Doğrulama testlerini çalıştır";if(/build/.test(text))return "Build doğrulamasını çalıştır";return task.approval_tool||"Güvenli işlem"}
function approvalQueue(task){const records=[...(task.approval_history||[])].sort((a,b)=>a.version-b.version);const rows=[`<div class="queueRow done"><div class="queueNo">✓</div><div><div class="queueTitle">Görev hazırlandı</div><div class="queueCopy">${esc(task.title)}</div></div><div class="queueState">tamam</div></div>`];for(const r of records){const cls=r.state==="applied"?"done":r.approval_id===task.approval_id?"current":"";rows.push(`<div class="queueRow ${cls}"><div class="queueNo">${r.version}</div><div><div class="queueTitle">${esc(r.tool||"Güvenli işlem")}</div><div class="queueCopy">${esc(r.description||r.message||"")}</div></div><div class="queueState">${esc(r.state)}</div></div>`)}rows.push(`<div class="queueRow"><div class="queueNo">→</div><div><div class="queueTitle">Sonraki adım</div><div class="queueCopy">Araç tamamlanınca Prometheus yeni onay, teslim veya Reviewer aşamasını açar.</div></div><div class="queueState">sonra</div></div>`);return rows.join("")}
function saveDrafts(){document.querySelectorAll("textarea[data-decision-id]").forEach(x=>drafts.set(x.dataset.decisionId,x.value))}
function bindDecision(input){const id=input.dataset.decisionId;input.addEventListener("focus",()=>{editingDecisionId=id;clearTimeout(resumeTimer);$("syncText").textContent="Karar yazarken yenileme durdu"});input.addEventListener("input",()=>drafts.set(id,input.value));input.addEventListener("blur",()=>{drafts.set(id,input.value);resumeTimer=setTimeout(()=>{editingDecisionId=null;schedulePoll()},450)})}
function renderAction(c){saveDrafts();const root=$("actionBody"),decision=c.decisions.find(d=>d.status==="pending"),approval=currentApproval(c);if(decision){$("actionBadge").textContent="karar";$("actionBadge").className="status waiting_decision";root.innerHTML=`<div class="actionKicker">Yönetici kararı</div><div class="actionTitle">${esc(decision.question)}</div><div class="actionText">Bu cevap görev grafiğini bağlayacak. Yazarken otomatik yenileme tamamen durur.</div><textarea id="answer-${decision.id}" data-decision-id="${decision.id}" class="decisionInput" placeholder="Kararını açık biçimde yaz...">${esc(drafts.get(decision.id)||"")}</textarea><div class="actionButtons"><button class="btn btnPrimary" onclick="answerDecision('${decision.id}')">Kararı Kaydet ve Planı Güncelle</button></div>`;bindDecision(root.querySelector("textarea"));return}
if(approval){const processing=approval.approval_state==="processing",preview=pretty(approval.approval_preview);$("actionBadge").textContent=processing?"uygulanıyor":"onay gerekli";$("actionBadge").className=`status ${processing?"running":"awaiting_approval"}`;root.innerHTML=`<div class="actionKicker">${approval.id} · Güvenli işlem ${approval.approval_version}</div><div class="actionTitle">${esc(approvalTitle(approval))}</div><div class="actionText">${processing?"Onay alındı. Araç sonucu checkpoint edilene kadar aynı işlemi tekrar göndermene gerek yok.":"Bu kart bütün komuttaki sıradaki tek aktif onaydır. Önizlemeyi kontrol edip uygula veya reddet."}</div><div class="actionFacts"><div class="fact"><div class="factLabel">Neden gerekli?</div><div class="factValue">${esc(approval.approval_description||"Workspace değişikliği kullanıcı izni gerektiriyor.")}</div></div><div class="fact"><div class="factLabel">Etkilenen hedef</div><div class="factValue">${esc(impact(approval))}</div></div><div class="fact"><div class="factLabel">Sonraki aşama</div><div class="factValue">Araç sonucu kaydedilir; ardından yalnızca kalan görev adımı hazırlanır.</div></div></div><div class="queue">${approvalQueue(approval)}</div><div class="previewHead"><span class="previewTitle">İşlem önizlemesi</span><button class="btn btnQuiet" onclick="copyText(pretty(currentApproval(lastCommand).approval_preview),'İşlem önizlemesi')">Kopyala</button></div><textarea class="codeBox" readonly>${esc(preview)}</textarea><div class="actionButtons"><button class="btn btnGood" ${processing||approvalInFlight.has(approval.approval_id)?"disabled":""} onclick="approveTask('${approval.id}','${approval.approval_id}',${approval.approval_version})">${processing?"Uygulanıyor...":(c.autonomy_mode==="task"&&!approval.autonomy_granted?"Bu Göreve İzin Ver":"Onayla ve Uygula")}</button><button class="btn btnBad" ${processing?"disabled":""} onclick="rejectTask('${approval.id}','${approval.approval_id}',${approval.approval_version})">Reddet</button></div>`;return}
const active=c.tasks.find(t=>["running","reviewing","awaiting_approval"].includes(t.status)||t.approval_state==="processing");if(active){$("actionBadge").textContent="çalışıyor";$("actionBadge").className="status running";root.innerHTML=`<div class="actionKicker">Aktif görev · ${active.id}</div><div class="actionTitle">${esc(active.title)}</div><div class="actionText">Bu görev tamamlanmadan veya onayı sonuçlanmadan ikinci görev başlatılamaz. Paylaşılan workspace güvenli biçimde seri çalışır.</div><div class="actionFacts"><div class="fact"><div class="factLabel">Uzman</div><div class="factValue">${esc(AGENT_LABEL[active.assigned_agent]||active.assigned_agent)}</div></div><div class="fact"><div class="factLabel">Durum</div><div class="factValue">${esc(STATE_LABEL[active.status]||active.status)}</div></div><div class="fact"><div class="factLabel">Sistem</div><div class="factValue">Kalp atışı izleniyor</div></div></div><div class="actionButtons"><button class="btn" onclick="selectTask('${active.id}')">Görevi İncele</button></div>`;return}
const rework=c.tasks.find(t=>t.status==="rework_required"||(t.status==="failed"&&(t.approval_history||[]).some(r=>r.state==="applied"))),ready=c.tasks.find(t=>t.status==="ready");if(rework){$("actionBadge").textContent="kanıt uzlaştırma";$("actionBadge").className="status rework_required";root.innerHTML=`<div class="actionKicker">Kurtarma devamı · ${rework.id}</div><div class="actionTitle">${esc(rework.title)}</div><div class="actionText">Önce yerel kanıt uzlaştırması yapılacak. Dosyalar ve başarılı test kanıtı yeterliyse model çağrısı olmadan görev tamamlanacak. Eksik iş varsa yalnızca eksik hedeflerle temiz bir agent oturumu açılacak.</div><div class="actionFacts"><div class="fact"><div class="factLabel">Normal deneme</div><div class="factValue">${rework.attempts}</div></div><div class="fact"><div class="factLabel">Continuation resume</div><div class="factValue">${rework.continuation_resumes||0}</div></div><div class="fact"><div class="factLabel">Eksik dosyalar</div><div class="factValue">${esc((rework.reconciliation_missing_files||[]).join(", ")||"Yerel kontrolde belirlenecek")}</div></div><div class="fact"><div class="factLabel">Doğrulama kanıtı</div><div class="factValue">${rework.reconciliation_verification_found?"Var":"Kontrol edilecek"}</div></div></div><div class="actionText">${esc(rework.last_approval_message||"Kanıt uzlaştırması gerekli")}</div><div class="actionButtons"><button class="btn btnPrimary" onclick="runTask('${rework.id}')">Kanıtları Uzlaştır ve Devam Et</button><button class="btn" onclick="selectTask('${rework.id}')">Görevi İncele</button></div>`;return}
if(ready){$("actionBadge").textContent="hazır";$("actionBadge").className="status";root.innerHTML=`<div class="actionKicker">Sıradaki görev · ${ready.id}</div><div class="actionTitle">${esc(ready.title)}</div><div class="actionText">Uzman: ${esc(AGENT_LABEL[ready.assigned_agent]||ready.assigned_agent)} · Bağımlılıklar: ${esc(ready.dependencies.join(", ")||"yok")}</div><div class="actionButtons"><button class="btn btnPrimary" onclick="runTask('${ready.id}')">Görevi Başlat</button><button class="btn" onclick="selectTask('${ready.id}')">Kapsamı İncele</button></div>`;return}
if(c.status==="reviewing"){const task=c.tasks.find(t=>t.status==="reviewing");$("actionBadge").textContent="inceleme";$("actionBadge").className="status reviewing";root.innerHTML=`<div class="actionKicker">Bağımsız kalite kapısı</div><div class="actionTitle">${esc(task?.title||"Reviewer incelemesi")}</div><div class="actionText">Şu anda senden işlem beklenmiyor. Reviewer gerçek dosya, diff ve başarılı test kanıtını değerlendiriyor.</div>`;return}
if(c.status==="completed"){ $("actionBadge").textContent="tamamlandı";$("actionBadge").className="status completed";root.innerHTML=`<div class="actionKicker">Teslim</div><div class="actionTitle">Misyon başarıyla tamamlandı</div><div class="actionText">Bütün görevler bağımsız kalite kapısından geçti.</div><div class="actionButtons"><button class="btn" onclick="copyDiagnostics()">Teslim Raporunu Kopyala</button></div>`;return}
if(c.tasks.some(t=>t.status==="failed")){const failed=c.tasks.find(t=>t.status==="failed");$("actionBadge").textContent="dikkat";$("actionBadge").className="status failed";root.innerHTML=`<div class="actionKicker">Başarısız görev</div><div class="actionTitle">${esc(failed.title)}</div><div class="actionText">Görev maksimum normal deneme sınırına veya doğrulanamayan bir hataya ulaştı. Teknik raporu kopyalayıp paylaşabilirsin.</div><div class="actionButtons"><button class="btn btnBad" onclick="selectTask('${failed.id}')">Görev Hatasını Aç</button><button class="btn" onclick="copyErrors()">Tüm Hataları Kopyala</button></div>`;return}
$("actionBadge").textContent="çalışıyor";$("actionBadge").className="status running";const op=operation(c);root.innerHTML=`<div class="actionKicker">Şu anda işlem gerekmiyor</div><div class="actionTitle">${esc(op[0])}</div><div class="actionText">${esc(op[1])}</div>`}
function evidenceSummary(t){const writes=(t.approval_history||[]).filter(r=>r.tool==="workspace_write"&&r.state==="applied"&&r.success!==false).length,tests=(t.approval_history||[]).filter(r=>r.tool==="safe_terminal"&&r.state==="applied"&&r.success===true).length,failed=(t.approval_history||[]).filter(r=>r.tool==="safe_terminal"&&r.state==="applied"&&r.success===false).length;return `<strong>${writes}</strong> yazma · <strong>${tests}</strong> başarılı komut${failed?` · <strong>${failed}</strong> başarısız`:""}`}
function renderTasks(c){const root=$("taskRows");root.innerHTML="";if(!c.tasks.length){root.innerHTML='<tr><td colspan="5"><div class="empty">Plan hazırlanıyor veya görev bulunmuyor.</div></td></tr>';return}if(!selectedTaskId||!c.tasks.some(t=>t.id===selectedTaskId))selectedTaskId=c.tasks[0].id;for(const t of c.tasks){const tr=document.createElement("tr");tr.className=t.id===selectedTaskId?"selected":"";tr.onclick=()=>selectTask(t.id);tr.innerHTML=`<td><div class="taskId">${t.id}</div><div class="taskName">${esc(t.title)}</div><div class="taskSub">${esc(t.priority)} · ${t.dependencies.length?`Bağımlı: ${t.dependencies.join(", ")}`:"Bağımsız"}</div></td><td><span class="agentChip"><span class="agentAvatar">${esc((AGENT_LABEL[t.assigned_agent]||t.assigned_agent).slice(0,2).toUpperCase())}</span>${esc(AGENT_LABEL[t.assigned_agent]||t.assigned_agent)}</span></td><td><span class="status ${t.status}">${esc(STATE_LABEL[t.status]||t.status)}</span></td><td><div class="evidenceMini">${evidenceSummary(t)}</div></td><td><button class="btn btnQuiet" onclick="event.stopPropagation();selectTask('${t.id}')">İncele</button></td>`;root.appendChild(tr)}}
function taskReport(t){return `${t.id} — ${t.title}\nDurum: ${t.status}\nAgent: ${t.assigned_agent}\nNormal deneme: ${t.attempts}\nContinuation resume: ${t.continuation_resumes||0}\nRecovery: ${t.recovery_reason||"yok"}\nKesin dosyalar: ${(t.exact_files||[]).join(", ")||"yok"}\nOnay: ${t.approval_state} ${t.last_approval_message||""}\n\nKabul kriterleri:\n${t.acceptance_criteria.map(x=>`- ${x}`).join("\n")}\n\nAgent çıktısı:\n${t.last_answer||"yok"}\n\nReviewer:\n${t.review_answer||"yok"}\n\nOnay geçmişi:\n${pretty(t.approval_history||[])}`}
function renderInspector(c){const t=c.tasks.find(x=>x.id===selectedTaskId),root=$("inspectorBody");$("copyTask").disabled=!t;if(!t){root.innerHTML='<div class="empty">Görev tablosundan bir satır seç.</div>';return}const history=(t.approval_history||[]).map(r=>`<div class="timelineItem"><div class="timelineTop"><div class="timelineName">#${r.version} · ${esc(r.tool||"işlem")}</div><div class="timelineState">${esc(r.state)}</div></div><div class="timelineText">${esc(r.message||r.description||"")} ${r.result?`<br>Sonuç: ${esc(typeof r.result==="object"?JSON.stringify(r.result):r.result)}`:""}</div></div>`).join("")||'<div class="caption">Henüz güvenli işlem yok.</div>';root.innerHTML=`<div class="inspectTitle">${esc(t.title)}</div><div class="inspectMeta">${t.id} · ${esc(AGENT_LABEL[t.assigned_agent]||t.assigned_agent)} · Normal deneme ${t.attempts} · Continuation ${t.continuation_resumes||0}</div><div class="section"><div class="sectionTitle">Durum</div><span class="status ${t.status}">${esc(STATE_LABEL[t.status]||t.status)}</span>${t.last_approval_message?`<div class="actionText">${esc(t.last_approval_message)}</div>`:""}</div><div class="section"><div class="sectionTitle">Kanıt uzlaştırma</div><div class="actionText">Eksik dosyalar: ${esc((t.reconciliation_missing_files||[]).join(", ")||"yok")}<br>Başarılı doğrulama: ${t.reconciliation_verification_found?"var":"yok"}<br>Gerçek komut: ${esc(t.effective_verification||"henüz yok")}<br>Strateji: ${esc(t.verification_strategy||"henüz yok")}<br>Son kontrol: ${esc(t.reconciliation_last_checked_at||"yapılmadı")}</div></div><div class="section"><div class="sectionTitle">Kesin dosyalar</div>${(t.exact_files||[]).map(x=>`<span class="fileTag">${esc(x)}</span>`).join("")||'<span class="caption">Belirtilmedi.</span>'}</div><div class="section"><div class="sectionTitle">Kabul kriterleri</div><ul class="list">${t.acceptance_criteria.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></div><div class="section"><div class="sectionTitle">Onay ve araç geçmişi</div><div class="timeline">${history}</div></div>${t.last_answer?`<div class="section"><div class="outputBlock"><div class="outputHead"><span class="outputName">Agent çıktısı</span><button class="btn btnQuiet" onclick="copyText(lastCommand.tasks.find(x=>x.id==='${t.id}').last_answer,'Agent çıktısı')">Kopyala</button></div><textarea class="outputText" readonly>${esc(t.last_answer)}</textarea></div></div>`:""}${t.review_answer?`<div class="section"><div class="outputBlock"><div class="outputHead"><span class="outputName">Reviewer kararı</span><button class="btn btnQuiet" onclick="copyText(lastCommand.tasks.find(x=>x.id==='${t.id}').review_answer,'Reviewer kararı')">Kopyala</button></div><textarea class="outputText" readonly>${esc(t.review_answer)}</textarea></div></div>`:""}`}
function renderEvents(c){const root=$("eventList");root.innerHTML="";if(!c.events.length){root.innerHTML='<div class="empty">Henüz aktivite yok.</div>';return}for(const e of [...c.events].reverse()){const div=document.createElement("div");div.className="event";div.innerHTML=`<div class="eventName">${esc(e.type)}${e.task_id?` · ${esc(e.task_id)}`:""}</div><div class="eventText">${esc(e.message)}</div><div class="eventTime">${new Date(e.created_at).toLocaleTimeString("tr-TR",{hour:"2-digit",minute:"2-digit",second:"2-digit"})}</div>`;root.appendChild(div)}}
function errorReport(c){if(!c)return"";const lines=["PROMETHEUS HATA RAPORU",`Komut: ${c.id}`,`Durum: ${c.status}`,`Hedef: ${c.goal}`];if(c.failure_reason)lines.push("",`Misyon hatası: ${c.failure_reason}`);for(const t of c.tasks){if(["failed","rework_required"].includes(t.status)||t.approval_state==="failed"){lines.push("",`${t.id} — ${t.title}`,`Durum: ${t.status}`,`Normal deneme: ${t.attempts}`,`Continuation resume: ${t.continuation_resumes||0}`,`Recovery: ${t.recovery_reason||"yok"}`,`Onay: ${t.approval_state} ${t.last_approval_message||""}`,"Agent:",t.last_answer||"yok","Reviewer:",t.review_answer||"yok")}}const errors=c.events.filter(e=>/(fail|error|timeout|rejected|protocol|quota|limit|stale|recovery)/i.test(`${e.type} ${e.message}`));if(errors.length){lines.push("","OLAYLAR");for(const e of errors)lines.push(`[${e.sequence}] ${e.type}: ${e.message}`)}return lines.join("\n")}
async function loadDiagnostics(){if(!commandId)return"";const r=await fetch(`/v1/supervisor/commands/${commandId}/diagnostics`);if(!r.ok)throw new Error("Tanılama raporu alınamadı.");const text=await r.text();$("diagnosticsText").value=text;return text}
async function copyDiagnostics(){try{await copyText(await loadDiagnostics(),"Tanılama raporu")}catch(e){toast(e.message)}}
function copyErrors(){copyText(errorReport(lastCommand),"Hata raporu")}
function selectTask(id){selectedTaskId=id;if(lastCommand){renderTasks(lastCommand);renderInspector(lastCommand)}document.querySelector("#inspector")?.scrollIntoView({behavior:"smooth",block:"start"})}
function shouldPoll(){if(!lastCommand)return false;if(lastCommand.active_operation)return true;return lastCommand.tasks.some(t=>t.status==="running"||t.status==="reviewing"||t.approval_state==="processing")}
function schedulePoll(){clearTimeout(pollTimer);if(editingDecisionId){$("syncText").textContent="Karar yazarken yenileme durdu";return}if(!shouldPoll()){$("syncText").textContent="Güncel";return}$("syncText").textContent="Aktif işlem · otomatik güncelleniyor";pollTimer=setTimeout(silentRefresh,1300)}
async function silentRefresh(){if(!commandId||polling||editingDecisionId)return;polling=true;try{render(await api(`/v1/supervisor/commands/${commandId}`))}catch(e){$("syncText").textContent="Bağlantı hatası"}finally{polling=false}}
function render(c){saveDrafts();lastCommand=c;commandId=c.id;const p=progress(c),op=operation(c),done=c.tasks.filter(t=>t.status==="completed").length,ready=c.tasks.filter(t=>["ready","rework_required"].includes(t.status)).length,actions=c.decisions.filter(d=>d.status==="pending").length+c.tasks.filter(t=>["pending","processing"].includes(t.approval_state)).length,failed=c.tasks.filter(t=>t.status==="failed").length;$("missionTitle").textContent=c.goal;$("missionId").textContent=c.id;$("commandStatus").textContent=c.status;$("commandStatus").className=`status ${c.status}`;$("progressFill").style.width=`${p}%`;$("progressPct").textContent=`%${p}`;$("stages").innerHTML=stageData(c).map(([n,s])=>`<div class="stage ${s}">${n}</div>`).join("");$("operationTitle").textContent=op[0];$("operationCopy").textContent=op[1];$("operationMeta").textContent=`${c.autonomy_mode||"task"} · ${c.auto_run?"otomatik misyon":"elle ilerletme"} · ${elapsed(c.operation_started_at)}`;$("missionAlert").classList.toggle("show",Boolean(c.failure_reason||failed));$("missionAlert").textContent=c.failure_reason||`${failed} görev başarısız. Görev İnceleyici üzerinden ayrıntıyı aç.`;$("taskCaption").textContent=`${done}/${c.tasks.length} tamamlandı · ${ready} hazır/devam · ${actions} kullanıcı eylemi`;$("metricTotal").textContent=c.tasks.length;$("metricDone").textContent=done;$("metricReady").textContent=ready;$("metricAction").textContent=actions;$("planText").value=c.plan_text||"Plan bekleniyor...";$("diagnosticsText").value=errorReport(c);$("copyErrorTop").disabled=false;$("copyDiagTop").disabled=false;$("copyErrors").disabled=false;$("copyDiagnostics").disabled=false;$("copyPlan").disabled=false;$("refresh").disabled=busy;const activeWork=c.tasks.some(t=>["running","reviewing","awaiting_approval"].includes(t.status)||t.approval_state==="processing");$("advance").disabled=busy||activeWork||!c.tasks.some(t=>["ready","rework_required"].includes(t.status));const canRecompile=!c.tasks.some(t=>t.attempts>0||["running","awaiting_approval","reviewing","completed"].includes(t.status))&&["failed","planning","waiting_decision","ready"].includes(c.status);$("recompile").disabled=busy||!canRecompile;renderAction(c);renderTasks(c);renderInspector(c);renderEvents(c);if(c.events.length>lastEventCount&&lastEventCount>0)toast(c.events[c.events.length-1].message);lastEventCount=c.events.length;schedulePoll()}
async function createCommand(){const goal=$("goal").value.trim(),autonomy_mode=$("autonomy").value;if(!goal)return;setBusy(true);try{render(await api("/v1/supervisor/commands",{method:"POST",body:JSON.stringify({goal,autonomy_mode,auto_start:true,background:true})}));toast("Misyon planlanıyor ve hazır olur olmaz başlatılacak.")}catch(e){toast(e.message)}finally{setBusy(false)}}
async function retryPlan(){if(!commandId)return;setBusy(true);try{render(await api(`/v1/supervisor/commands/${commandId}/retry-planning?background=true`,{method:"POST"}));toast("Plan yeniden derleniyor.")}catch(e){toast(e.message)}finally{setBusy(false)}}
async function runTask(id){const active=lastCommand?.tasks.find(t=>t.id!==id&&(["running","reviewing","awaiting_approval"].includes(t.status)||t.approval_state==="processing"));if(active){toast(`Önce ${active.id} aktif görevini tamamla.`);selectTask(active.id);return}setBusy(true);try{render(await api(`/v1/supervisor/commands/${commandId}/tasks/${id}/run?background=true`,{method:"POST"}));selectedTaskId=id;toast(`${id} başlatıldı.`)}catch(e){toast(e.message);await silentRefresh()}finally{setBusy(false)}}
async function advance(){const t=lastCommand?.tasks.find(x=>["rework_required","ready"].includes(x.status));if(t)await runTask(t.id)}
async function answerDecision(id){const input=$(`answer-${id}`),answer=(input?.value||drafts.get(id)||"").trim();if(!answer){toast("Karar alanı boş bırakılamaz.");input?.focus();return}editingDecisionId=null;clearTimeout(resumeTimer);setBusy(true);try{drafts.delete(id);render(await api(`/v1/supervisor/commands/${commandId}/decisions/${id}`,{method:"POST",body:JSON.stringify({answer,replan_when_complete:true,background:true})}));toast("Karar kaydedildi.")}catch(e){drafts.set(id,answer);toast(e.message)}finally{setBusy(false)}}
async function approveTask(id,approvalId,version){if(approvalInFlight.has(approvalId))return;approvalInFlight.add(approvalId);renderAction(lastCommand);try{render(await api(`/v1/supervisor/commands/${commandId}/tasks/${id}/approve`,{method:"POST",body:JSON.stringify({approval_id:approvalId,approval_version:version,background:true})}));toast("Onay kaydedildi; güvenli işlem uygulanıyor.")}catch(e){toast(e.message);await silentRefresh()}finally{approvalInFlight.delete(approvalId);schedulePoll()}}
async function rejectTask(id,approvalId,version){if(approvalInFlight.has(approvalId))return;approvalInFlight.add(approvalId);try{render(await api(`/v1/supervisor/commands/${commandId}/tasks/${id}/reject`,{method:"POST",body:JSON.stringify({approval_id:approvalId,approval_version:version,background:false})}));toast("İşlem reddedildi.")}catch(e){toast(e.message);await silentRefresh()}finally{approvalInFlight.delete(approvalId);schedulePoll()}}
$("create").onclick=createCommand;$("refresh").onclick=silentRefresh;$("advance").onclick=advance;$("recompile").onclick=retryPlan;$("copyErrorTop").onclick=copyErrors;$("copyDiagTop").onclick=copyDiagnostics;$("copyErrors").onclick=copyErrors;$("copyDiagnostics").onclick=copyDiagnostics;$("copyPlan").onclick=()=>copyText(lastCommand?.plan_text||"","Plan");$("copyTask").onclick=()=>{const t=lastCommand?.tasks.find(x=>x.id===selectedTaskId);if(t)copyText(taskReport(t),"Görev raporu")};document.querySelectorAll(".tab").forEach(btn=>btn.onclick=()=>{document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));document.querySelectorAll(".tabPanel").forEach(x=>x.classList.remove("active"));btn.classList.add("active");$(`tab-${btn.dataset.tab}`).classList.add("active");if(btn.dataset.tab==="diagnostics"&&commandId)loadDiagnostics().catch(()=>{})});
const initialId = new URLSearchParams(window.location.search).get("id") || localStorage.getItem("prometheus.activeCommandId") || localStorage.getItem("adam.activeCommandId");
if (initialId) { commandId = initialId; silentRefresh(); }
</script>
</body>
</html>"""
