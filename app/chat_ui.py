CHAT_UI = r"""
<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>Prometheus</title>
  <style>
    :root {
      --bg:#0c0f14; --panel:#131821; --panel2:#191f2a; --line:#2a3342;
      --text:#f5f7fb; --muted:#9da8b8; --accent:#7c9cff;
      --accent2:#9b8cff; --danger:#ff8f8f; --success:#79d7a6;
      --warning:#f2c879; --user:#25304a; --assistant:#171d27;
      --shadow:0 12px 40px rgba(0,0,0,.22);
    }
    *{box-sizing:border-box}
    html,body{height:100%;margin:0;background:var(--bg);color:var(--text);
      font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
    button,textarea,select{font:inherit} button{cursor:pointer}
    .app{min-height:100%;display:grid;grid-template-columns:310px minmax(0,1fr)}
    .sidebar{border-right:1px solid var(--line);background:
      radial-gradient(circle at top left,rgba(124,156,255,.11),transparent 35%),
      var(--panel);padding:18px;display:flex;flex-direction:column;gap:16px;
      position:sticky;top:0;height:100vh;overflow:auto}
    .brand{display:flex;align-items:center;justify-content:space-between;gap:10px}
    .brand h1{margin:0;font-size:1.18rem}.version{font-size:.75rem;color:var(--muted);
      border:1px solid var(--line);border-radius:999px;padding:4px 8px}
    .new-chat,.send{border:1px solid var(--line);border-radius:12px;padding:11px 13px;
      color:var(--text);background:var(--panel2)}
    .new-chat{width:100%;background:linear-gradient(135deg,rgba(124,156,255,.25),
      rgba(155,140,255,.18));font-weight:700}
    .section-title{margin:2px 0 8px;font-size:.74rem;text-transform:uppercase;
      letter-spacing:.1em;color:var(--muted);font-weight:800}
    .field{display:grid;gap:7px;margin-bottom:11px}.field label{color:var(--muted);
      font-size:.82rem}select{width:100%;background:#0f141c;color:var(--text);
      border:1px solid var(--line);border-radius:10px;padding:10px;outline:none}
    .quota-card,.score-card{background:rgba(10,13,18,.56);border:1px solid var(--line);
      border-radius:14px;padding:12px;display:grid;gap:10px}
    .quota-head,.score-head{display:flex;justify-content:space-between;gap:10px;
      font-size:.78rem}.quota-head span:last-child,.score-head span:last-child{
      color:var(--muted)}
    .bar{height:6px;border-radius:999px;overflow:hidden;background:#0c1017;
      border:1px solid #222a37}.bar>div{height:100%;width:0%;
      background:linear-gradient(90deg,var(--accent),var(--accent2));
      transition:width .25s ease}
    .score-item{display:grid;gap:5px;padding-bottom:8px;border-bottom:1px solid #232b37}
    .score-item:last-child{border-bottom:0;padding-bottom:0}
    .sidebar-foot{margin-top:auto;display:grid;gap:8px}.sidebar-foot a,.sidebar-foot button{
      color:var(--muted);text-decoration:none;background:transparent;border:0;padding:5px 0;
      text-align:left;font-size:.86rem}
    .main{min-width:0;height:100vh;display:grid;grid-template-rows:auto minmax(0,1fr) auto}
    .topbar{min-height:66px;padding:13px 24px;border-bottom:1px solid var(--line);
      background:rgba(12,15,20,.9);backdrop-filter:blur(14px);display:flex;
      align-items:center;justify-content:space-between;gap:16px;position:sticky;top:0;z-index:3}
    .topbar-left{display:flex;align-items:center;gap:10px;min-width:0}.status-dot{
      width:9px;height:9px;border-radius:50%;background:var(--warning);
      box-shadow:0 0 16px rgba(242,200,121,.55);flex:0 0 auto}.status-dot.ok{
      background:var(--success);box-shadow:0 0 16px rgba(121,215,166,.55)}
    .topbar-title{font-weight:750}.topbar-subtitle{color:var(--muted);font-size:.8rem;
      overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:620px}
    .topbar-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
    .badge{color:var(--muted);border:1px solid var(--line);background:var(--panel);
      border-radius:999px;padding:6px 10px;font-size:.77rem;white-space:nowrap}
    .conversation{overflow-y:auto;padding:28px max(24px,calc((100vw - 1120px)/2));
      scroll-behavior:smooth}.empty{min-height:62vh;display:grid;place-items:center;
      text-align:center;color:var(--muted)}.empty-inner{max-width:620px}.empty h2{
      color:var(--text);font-size:clamp(1.55rem,4vw,2.35rem);margin:0 0 12px;
      letter-spacing:-.04em}.empty p{margin:0;line-height:1.7}
    .message{display:grid;grid-template-columns:38px minmax(0,1fr);gap:12px;margin:0 0 20px}
    .avatar{width:38px;height:38px;border-radius:12px;display:grid;place-items:center;
      font-weight:800;font-size:.8rem;border:1px solid var(--line);background:var(--panel2)}
    .message.user .avatar{background:var(--user)}.bubble{border:1px solid var(--line);
      border-radius:16px;padding:15px 17px;background:var(--assistant);box-shadow:var(--shadow);
      min-width:0}.message.user .bubble{background:var(--user)}.message-head{display:flex;
      justify-content:space-between;align-items:center;gap:10px;margin-bottom:9px}
    .message-name{font-weight:750;font-size:.9rem}.message-meta{color:var(--muted);
      font-size:.74rem;text-align:right}.message-content{white-space:pre-wrap;
      overflow-wrap:anywhere;line-height:1.62}.message-content code{
      font-family:"Cascadia Code",Consolas,monospace;font-size:.9em}.message-content pre{
      white-space:pre;overflow-x:auto;background:#090c11;border:1px solid #252d3a;
      padding:13px;border-radius:12px}.error-text{color:var(--danger)}
    .composer-wrap{padding:12px max(20px,calc((100vw - 1120px)/2)) 20px;
      background:linear-gradient(180deg,rgba(12,15,20,0),rgba(12,15,20,.95) 26%)}
    .composer{border:1px solid var(--line);border-radius:18px;background:var(--panel);
      box-shadow:var(--shadow);padding:12px}textarea{width:100%;min-height:72px;
      max-height:220px;resize:none;color:var(--text);background:transparent;border:0;
      outline:0;padding:6px 7px;line-height:1.5}.composer-bottom{display:flex;
      justify-content:space-between;align-items:center;gap:12px;margin-top:8px}
    .composer-hint{color:var(--muted);font-size:.76rem}.send{width:auto;min-width:102px;
      border:0;background:linear-gradient(135deg,var(--accent),var(--accent2));
      color:white;font-weight:800}.send:disabled{opacity:.55;cursor:wait}
    .mobile-menu{display:none;border:1px solid var(--line);background:var(--panel);
      color:var(--text);border-radius:10px;padding:8px 10px}
    @media(max-width:840px){.app{grid-template-columns:1fr}.sidebar{display:none;position:fixed;
      inset:0 auto 0 0;width:min(90vw,330px);z-index:20;box-shadow:12px 0 50px rgba(0,0,0,.45)}
      .sidebar.open{display:flex}.mobile-menu{display:inline-flex}.topbar{padding:11px 14px}
      .topbar-right .badge:nth-child(n+3){display:none}.conversation{padding:20px 13px}
      .composer-wrap{padding:10px 10px 12px}.message{grid-template-columns:32px minmax(0,1fr);
      gap:8px}.avatar{width:32px;height:32px;border-radius:10px}.bubble{padding:13px}
      .composer-hint{display:none}}
  </style>
</head>
<body>
<div class="app">
  <aside id="sidebar" class="sidebar">
    <div class="brand"><h1>Prometheus</h1><span class="version">v0.8.0</span></div>
    <button id="newChat" class="new-chat">+ Yeni sohbet</button>

    <section>
      <div class="section-title">Çalışma modu</div>
      <div class="field">
        <label for="mode">Mod</label>
        <select id="mode">
          <option value="auto">Auto — puanlama ile seç</option>
          <option value="economy">Economy — sabit ucuz sıra</option>
          <option value="verify">Verify — iki sağlayıcı + judge</option>
          <option value="direct">Direct — tek model rotası</option>
          <option value="agent">Agent Army — seçili uzmanla çalış</option>
        </select>
      </div>
      <div id="providerField" class="field" hidden>
        <label for="provider">Model rotası</label>
        <select id="provider">
          <option value="local_qwen">Local Qwen3.5 4B</option>
          <option value="local_expert">Local Qwen3.5 9B Expert</option>
          <option value="gemini">Gemini Flash Lite</option>
          <option value="github">GitHub GPT-4.1 Mini</option>
          <option value="groq_fast">Groq Llama 3.1 8B Fast</option>
          <option value="groq_strong">Groq Llama 3.3 70B</option>
        </select>
      </div>
      <div id="agentField" class="field" hidden>
        <label for="agentProfile">Uzman agent</label>
        <select id="agentProfile"><option value="worker">General Worker</option></select>
      </div>
    </section>

    <section>
      <div class="section-title">Seçili agent profili</div>
      <div id="agentProfileCard" class="quota-card"><div style="color:var(--muted);font-size:.8rem">Agent profilleri yükleniyor...</div></div>
    </section>

    <section>
      <div class="section-title">Workspace</div>
      <div id="workspaceCard" class="quota-card">
        <div style="color:var(--muted);font-size:.8rem">Workspace kontrol ediliyor...</div>
      </div>
    </section>

    <section>
      <div class="section-title">Bekleyen kullanıcı kararı</div>
      <div id="approvalCard" class="score-card">
        <div style="color:var(--muted);font-size:.8rem">Bekleyen işlem yok.</div>
      </div>
    </section>

    <section>
      <div class="section-title">Bugünkü kullanım</div>
      <div id="quotaCard" class="quota-card"></div>
    </section>

    <section>
      <div class="section-title">Agent işlem izi</div>
      <div id="agentTraceCard" class="score-card">
        <div style="color:var(--muted);font-size:.8rem">Agent modunda araç adımları burada gösterilir.</div>
      </div>
    </section>

    <section>
      <div class="section-title">Son yönlendirme puanları</div>
      <div id="scoreCard" class="score-card">
        <div style="color:var(--muted);font-size:.8rem">İlk mesajdan sonra gösterilecek.</div>
      </div>
    </section>

    <div class="sidebar-foot">
      <button id="refreshStats">Kotaları yenile</button>
      <button id="clearCache">API cache'ini temizle</button>
      <a href="/docs" target="_blank" rel="noreferrer">Swagger geliştirici paneli</a>
      <a href="/v1/operations" target="_blank" rel="noreferrer">Ham operasyon verisi</a>
    </div>
  </aside>

  <main class="main">
    <header class="topbar">
      <div class="topbar-left">
        <button id="mobileMenu" class="mobile-menu">☰</button>
        <span id="statusDot" class="status-dot"></span>
        <div>
          <div class="topbar-title">Agent Army Console · <a href="/command" style="color:inherit">Command Center</a></div>
          <div id="statusText" class="topbar-subtitle">Sunucu kontrol ediliyor...</div>
        </div>
      </div>
      <div class="topbar-right">
        <span id="modelBadge" class="badge">Rota: —</span>
        <span id="taskBadge" class="badge">Görev: —</span>
        <span id="cacheBadge" class="badge">Cache: —</span>
        <span id="latencyBadge" class="badge">Süre: —</span>
      </div>
    </header>

    <section id="conversation" class="conversation">
      <div id="emptyState" class="empty">
        <div class="empty-inner">
          <h2>Projeyi oku, değişikliği göster, onaydan sonra uygula.</h2>
          <p>
            Agent modu workspace dosyalarını okuyabilir, kod arayabilir,
            sembolik hesap yapabilir ve onayından sonra dosya yazıp test
            çalıştırabilir.
          </p>
        </div>
      </div>
    </section>

    <div class="composer-wrap">
      <div class="composer">
        <textarea id="messageInput" placeholder="Bir şey sor veya görev ver..."
          aria-label="Mesaj"></textarea>
        <div class="composer-bottom">
          <div class="composer-hint">Enter gönderir · Shift+Enter yeni satır</div>
          <button id="sendButton" class="send">Gönder</button>
        </div>
      </div>
    </div>
  </main>
</div>

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
(() => {
  const STORAGE_KEY="prometheus.chat.v080", MODE_KEY="prometheus.mode.v080",
    PROVIDER_KEY="prometheus.provider.v080", AGENT_KEY="prometheus.agent.v080";
  const LEGACY_STORAGE_KEY="adam_chat_v0717", LEGACY_MODE_KEY="adam_mode_v0717",
    LEGACY_PROVIDER_KEY="adam_provider_v0717", LEGACY_AGENT_KEY="adam_agent_v0717";
  const sidebar=document.getElementById("sidebar"),conversation=document.getElementById("conversation"),
    emptyState=document.getElementById("emptyState"),input=document.getElementById("messageInput"),
    sendButton=document.getElementById("sendButton"),modeSelect=document.getElementById("mode"),
    providerSelect=document.getElementById("provider"),providerField=document.getElementById("providerField"),
    agentSelect=document.getElementById("agentProfile"),agentField=document.getElementById("agentField");
  function readStored(primary,legacy){const current=localStorage.getItem(primary);
    if(current!==null)return current;const previous=localStorage.getItem(legacy);
    if(previous!==null)localStorage.setItem(primary,previous);return previous}
  const state={messages:loadMessages(),busy:false,pending:null,agents:[]};
  modeSelect.value=readStored(MODE_KEY,LEGACY_MODE_KEY)||"auto";
  providerSelect.value=readStored(PROVIDER_KEY,LEGACY_PROVIDER_KEY)||"gemini";
  updateModeFields();

  function loadMessages(){try{const v=JSON.parse(readStored(STORAGE_KEY,LEGACY_STORAGE_KEY)||"[]");
    return Array.isArray(v)?v:[]}catch{return[]}}
  function persistMessages(){localStorage.setItem(STORAGE_KEY,JSON.stringify(state.messages))}
  function escapeHtml(v){return String(v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")}
  function renderText(v){return escapeHtml(v)
    .replace(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g,(_,l,c)=>`<pre><code data-language="${l}">${c.trim()}</code></pre>`)
    .replace(/`([^`\n]+)`/g,"<code>$1</code>")}
  function renderConversation(){conversation.innerHTML="";if(!state.messages.length){
      conversation.appendChild(emptyState);return}
    for(const m of state.messages){const item=document.createElement("article");item.className=`message ${m.role}`;
      const avatar=document.createElement("div");avatar.className="avatar";avatar.textContent=m.role==="user"?"SEN":"AI";
      const bubble=document.createElement("div");bubble.className="bubble";const head=document.createElement("div");
      head.className="message-head";const name=document.createElement("span");name.className="message-name";
      name.textContent=m.role==="user"?"Sen":"Prometheus";const meta=document.createElement("span");
      meta.className="message-meta";meta.textContent=m.meta||"";const content=document.createElement("div");
      content.className="message-content";if(m.error)content.classList.add("error-text");
      content.innerHTML=renderText(m.content);head.append(name,meta);bubble.append(head,content);
      item.append(avatar,bubble);conversation.appendChild(item)}
    conversation.scrollTop=conversation.scrollHeight}
  function setBusy(v){state.busy=v;sendButton.disabled=v;input.disabled=v;
    sendButton.textContent=v?"Çalışıyor...":"Gönder"}
  function setStatus(ok,text){document.getElementById("statusDot").classList.toggle("ok",ok);
    document.getElementById("statusText").textContent=text}
  function updateBadges(d){document.getElementById("modelBadge").textContent=`Rota: ${d.selected_route}`;
    document.getElementById("taskBadge").textContent=`Görev: ${d.task_type}`;
    document.getElementById("cacheBadge").textContent=`Cache: ${d.cache_hit?"evet":"hayır"}`;
    document.getElementById("latencyBadge").textContent=`Süre: ${d.latency_ms} ms`}
  function renderScores(scores){const card=document.getElementById("scoreCard");card.innerHTML="";
    for(const s of scores.slice(0,4)){const item=document.createElement("div");item.className="score-item";
      item.innerHTML=`<div class="score-head"><strong>${s.route_key}</strong><span>${s.eligible?s.score:"kapalı"}</span></div>
      <div class="bar"><div style="width:${s.eligible?Math.max(0,Math.min(100,s.score)):"0"}%"></div></div>`;
      card.appendChild(item)}}
  function renderAgentTrace(trace){const card=document.getElementById("agentTraceCard");card.innerHTML="";
    if(!trace.length){card.innerHTML='<div style="color:var(--muted);font-size:.8rem">Agent işlem izi bulunmuyor.</div>';return}
    for(const step of trace){const item=document.createElement("div");item.className="score-item";
      const tool=step.tool?` · ${step.tool}`:"";
      const result=step.tool_result!=null?`<div style="color:var(--muted);font-size:.73rem;overflow-wrap:anywhere">${escapeHtml(JSON.stringify(step.tool_result)).slice(0,220)}</div>`:"";
      item.innerHTML=`<div class="score-head"><strong>${step.step}. ${step.action}${tool}</strong><span>${step.selected_route}</span></div>
      <div style="color:var(--muted);font-size:.74rem">${escapeHtml(step.reason||"")}</div>${result}`;
      card.appendChild(item)}}
  function renderApproval(pending,sessionId){const card=document.getElementById("approvalCard");
    state.pending=pending&&sessionId?{pending,sessionId}:null;
    if(!state.pending){card.innerHTML='<div style="color:var(--muted);font-size:.8rem">Bekleyen işlem yok.</div>';return}
    const preview=escapeHtml(JSON.stringify(pending.preview,null,2));
    card.innerHTML=`<div class="score-item"><div class="score-head"><strong>${escapeHtml(pending.tool_name)}</strong><span>Onay gerekli</span></div>
      <div style="color:var(--muted);font-size:.75rem">${escapeHtml(pending.description)}</div>
      <pre style="white-space:pre-wrap;max-height:240px;overflow:auto;font-size:.7rem">${preview}</pre>
      <div style="display:flex;gap:8px"><button id="approveAction" class="new-chat" style="padding:8px">Onayla</button>
      <button id="rejectAction" class="new-chat" style="padding:8px;background:transparent">Reddet</button></div></div>`;
    document.getElementById("approveAction").addEventListener("click",()=>resolveApproval(true));
    document.getElementById("rejectAction").addEventListener("click",()=>resolveApproval(false))}
  function handleAgentResponse(data){state.messages.push({role:"assistant",content:data.answer,
      meta:`${data.agent_name||"Agent"} · ${data.final_route||"—"} · ${data.steps_used} adım · ${data.model_calls_used} çağrı`});
    document.getElementById("modelBadge").textContent=`Rota: ${data.final_route||"—"}`;
    document.getElementById("taskBadge").textContent=`${data.agent_name||"Agent"}: ${data.status}`;
    document.getElementById("cacheBadge").textContent=`Araç: ${(data.tools_used||[]).join(", ")||"yok"}`;
    document.getElementById("latencyBadge").textContent=`Adım: ${data.steps_used}`;
    renderScores(data.routing_scores||[]);renderAgentTrace(data.trace||[]);
    renderApproval(data.pending_approval,data.session_id);
    setStatus(data.status==="completed"||data.status==="awaiting_approval",
      data.status==="awaiting_approval"?"Kullanıcı kararı bekleniyor.":`Worker ${data.status}: ${data.steps_used} adım.`)}
  async function resolveApproval(approve){if(!state.pending||state.busy)return;
    const snapshot=state.pending;
    const {pending,sessionId}=snapshot;
    const approveButton=document.getElementById("approveAction");
    const rejectButton=document.getElementById("rejectAction");
    if(approveButton)approveButton.disabled=true;
    if(rejectButton)rejectButton.disabled=true;
    setBusy(true);setStatus(true,approve?"İşlem uygulanıyor...":"İşlem reddediliyor...");
    try{const action=approve?"approve":"reject";
      const response=await fetch(`/v1/agent/${encodeURIComponent(sessionId)}/${action}/${encodeURIComponent(pending.id)}`,
        {method:"POST"});
      let data={};try{data=await response.json()}catch(_error){}
      if(!response.ok)throw new Error(data.detail||`HTTP ${response.status}`);
      renderApproval(null,null);handleAgentResponse(data);persistMessages();renderConversation();await refreshOperations()}
    catch(error){renderApproval(snapshot.pending,snapshot.sessionId);
      state.messages.push({role:"assistant",content:`Onay işlemi başarısız: ${error.message}`,meta:"Hata",error:true});
      persistMessages();renderConversation();setStatus(false,"Onay işlemi başarısız oldu. Tekrar deneyebilir veya görevi yeniden başlatabilirsin.")}
    finally{setBusy(false)}}
  function renderAgentProfile(){const card=document.getElementById("agentProfileCard"),a=state.agents.find(x=>x.id===agentSelect.value);
    if(!a){card.innerHTML='<div style="color:var(--muted);font-size:.8rem">Agent seçilmedi.</div>';return}
    card.innerHTML=`<div class="quota-head"><span>${escapeHtml(a.name)}</span><span>${a.read_only?"read-only":"worker"}</span></div><div style="color:var(--muted);font-size:.74rem">${escapeHtml(a.description)}</div><div style="color:var(--muted);font-size:.7rem;margin-top:7px"><strong>Model sırası:</strong> ${escapeHtml((a.preferred_routes||[]).join(" → "))}</div>`}
  async function refreshAgents(){try{const r=await fetch("/v1/agents"),data=await r.json();if(!r.ok)throw new Error(data.detail||"Agentlar alınamadı");state.agents=data;agentSelect.innerHTML="";for(const a of data){const o=document.createElement("option");o.value=a.id;o.textContent=`${a.short_name} — ${a.name}`;agentSelect.appendChild(o)}const saved=readStored(AGENT_KEY,LEGACY_AGENT_KEY)||"worker";agentSelect.value=data.some(x=>x.id===saved)?saved:"worker";renderAgentProfile()}catch(e){document.getElementById("agentProfileCard").innerHTML=`<div class="error-text">${escapeHtml(e.message)}</div>`}}
  async function refreshWorkspace(){try{const response=await fetch("/v1/workspace"),data=await response.json();
      if(!response.ok)throw new Error(data.detail||"Workspace alınamadı.");
      document.getElementById("workspaceCard").innerHTML=`<div class="quota-head"><span>Proje</span><span>${escapeHtml((data.project_types||[]).join(", "))}</span></div>
        <div style="color:var(--muted);font-size:.72rem;overflow-wrap:anywhere">${escapeHtml(data.root)}</div>
        <div class="quota-head"><span>Git</span><span>${data.git_repository?"evet":"hayır"}</span></div>
        <div class="quota-head"><span>Ücretli model</span><span>${data.paid_models_enabled?"açık":"kapalı"}</span></div>`}
    catch(error){document.getElementById("workspaceCard").innerHTML=`<div class="error-text">${escapeHtml(error.message)}</div>`}}
  function messagesForApi(){return state.messages.filter(m=>!m.error).map(m=>({role:m.role,content:m.content}))}
  async function sendMessage(){const text=input.value.trim();if(!text||state.busy)return;
    state.messages.push({role:"user",content:text,meta:new Date().toLocaleTimeString("tr-TR",
      {hour:"2-digit",minute:"2-digit"})});persistMessages();renderConversation();input.value="";
    resizeInput();setBusy(true);setStatus(true,"Model rotaları puanlanıyor...");
    const mode=modeSelect.value;
    const isAgent=mode==="agent";
    const endpoint=isAgent?"/v1/agent/run":"/v1/orchestrate";
    const body=isAgent
      ? {messages:messagesForApi(),agent_id:agentSelect.value,routing_mode:"auto",include_trace:true}
      : {messages:messagesForApi(),mode,include_candidates:false};
    if(mode==="direct")body.provider=providerSelect.value;
    try{const response=await fetch(endpoint,{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw new Error(data.detail||JSON.stringify(data));
      if(isAgent){
        handleAgentResponse(data);
      }else{
        state.messages.push({role:"assistant",content:data.answer,
          meta:`${data.selected_route} · ${data.model} · ${data.latency_ms} ms · ${data.calls_used} çağrı${data.cache_hit?" · cache":""}`});
        updateBadges(data);renderScores(data.routing_scores||[]);
        document.getElementById("agentTraceCard").innerHTML='<div style="color:var(--muted);font-size:.8rem">Agent modu kullanılmadı.</div>';
        setStatus(true,data.route_reason);
      }
      persistMessages();renderConversation();await refreshOperations()}
    catch(error){state.messages.push({role:"assistant",content:`İstek başarısız: ${error.message}`,meta:"Hata",error:true});
      persistMessages();renderConversation();setStatus(false,"İstek başarısız oldu.")}
    finally{setBusy(false);input.focus()}}
  function resizeInput(){input.style.height="auto";input.style.height=`${Math.min(input.scrollHeight,220)}px`}
  function routeBar(route){const used=route.requests_today,budget=route.daily_budget;
    const percent=budget?Math.min(100,(used/budget)*100):0;
    const remote=route.remote_requests_remaining!=null?` · Groq kalan ${route.remote_requests_remaining}`:"";
    return `<div><div class="quota-head"><span>${route.label}</span><span>${used} / ${budget||"∞"}${remote}</span></div>
      <div class="bar"><div style="width:${percent}%"></div></div></div>`}
  async function refreshOperations(){try{const response=await fetch("/v1/operations"),data=await response.json();
      if(!response.ok)throw new Error(data.detail||"Kota bilgisi alınamadı.");
      document.getElementById("quotaCard").innerHTML=data.routes.map(routeBar).join("")+
        `<div><div class="quota-head"><span>Verify</span><span>${data.verify_requests_today} / ${data.verify_daily_budget}</span></div>
        <div class="bar"><div style="width:${Math.min(100,(data.verify_requests_today/data.verify_daily_budget)*100)}%"></div></div></div>`;
      setStatus(true,"Etkin API rotaları hazır.")}
    catch(error){setStatus(false,error.message)}}
  function updateModeFields(){providerField.hidden=modeSelect.value!=="direct";agentField.hidden=modeSelect.value!=="agent"}
  modeSelect.addEventListener("change",()=>{localStorage.setItem(MODE_KEY,modeSelect.value);updateModeFields()});
  providerSelect.addEventListener("change",()=>localStorage.setItem(PROVIDER_KEY,providerSelect.value));
  agentSelect.addEventListener("change",()=>{localStorage.setItem(AGENT_KEY,agentSelect.value);renderAgentProfile()});
  input.addEventListener("input",resizeInput);input.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){
    e.preventDefault();sendMessage()}});sendButton.addEventListener("click",sendMessage);
  document.getElementById("newChat").addEventListener("click",()=>{state.messages=[];persistMessages();
    renderConversation();["modelBadge","taskBadge","cacheBadge","latencyBadge"].forEach((id,i)=>{
      document.getElementById(id).textContent=["Rota: —","Görev: —","Cache: —","Süre: —"][i]});
    document.getElementById("scoreCard").innerHTML='<div style="color:var(--muted);font-size:.8rem">İlk mesajdan sonra gösterilecek.</div>';
    document.getElementById("agentTraceCard").innerHTML='<div style="color:var(--muted);font-size:.8rem">Agent modunda araç adımları burada gösterilir.</div>';
    renderApproval(null,null);input.focus();sidebar.classList.remove("open")});
  document.getElementById("refreshStats").addEventListener("click",refreshOperations);
  document.getElementById("clearCache").addEventListener("click",async()=>{if(!confirm("API cevap cache'i temizlensin mi?"))return;
    const response=await fetch("/v1/cache",{method:"DELETE"}),data=await response.json();
    if(!response.ok){alert(data.detail||"Cache temizlenemedi.");return}alert(`${data.deleted} cache kaydı silindi.`);refreshOperations()});
  document.getElementById("mobileMenu").addEventListener("click",()=>sidebar.classList.toggle("open"));
  renderConversation();refreshAgents();refreshOperations();refreshWorkspace();resizeInput();input.focus();
})();
</script>
</body>
</html>
"""
