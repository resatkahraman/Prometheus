ANTIGRAVITY_UI = r"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <meta name="color-scheme" content="dark">
  <title>Antigravity AI — Uzaktan Kontrol İstemcisi</title>
  <style>
    :root {
      --bg: #090c10;
      --panel: #121720;
      --panel2: #1a2230;
      --border: #283347;
      --text: #f0f4fc;
      --muted: #8b9bb4;
      --accent: #3b82f6;
      --accent2: #8b5cf6;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --shadow: 0 10px 30px rgba(0,0,0,0.4);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    header {
      background: rgba(18, 23, 32, 0.85);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border);
      padding: 14px 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      z-index: 10;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .logo-icon {
      width: 28px;
      height: 28px;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      border-radius: 8px;
      display: grid;
      place-items: center;
      font-weight: 900;
      font-size: 14px;
      color: #fff;
      box-shadow: 0 0 12px rgba(59, 130, 246, 0.5);
    }
    .brand-title {
      font-weight: 800;
      font-size: 1.05rem;
      letter-spacing: -0.02em;
    }
    .status-badge {
      display: flex;
      align-items: center;
      gap: 6px;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: var(--success);
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 700;
    }
    .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--success);
      box-shadow: 0 0 8px var(--success);
    }
    main {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      scroll-behavior: smooth;
    }
    .welcome-card {
      background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(139, 92, 246, 0.1));
      border: 1px solid rgba(139, 92, 246, 0.25);
      border-radius: 16px;
      padding: 18px;
    }
    .welcome-title {
      font-weight: 800;
      font-size: 1.1rem;
      margin-bottom: 6px;
      color: #fff;
    }
    .welcome-desc {
      color: var(--muted);
      font-size: 0.86rem;
      line-height: 1.5;
    }
    .quick-chips {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding-bottom: 4px;
      scrollbar-width: none;
    }
    .quick-chips::-webkit-scrollbar { display: none; }
    .chip {
      background: var(--panel);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 8px 14px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
      white-space: nowrap;
      cursor: pointer;
      transition: all 0.2s;
    }
    .chip:active {
      transform: scale(0.96);
      background: var(--panel2);
    }
    .chat-stream {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .msg {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-width: 90%;
    }
    .msg.user {
      align-self: flex-end;
    }
    .msg.agent {
      align-self: flex-start;
      max-width: 95%;
    }
    .msg-bubble {
      padding: 14px 16px;
      border-radius: 16px;
      font-size: 0.92rem;
      line-height: 1.55;
      word-break: break-word;
      box-shadow: var(--shadow);
    }
    .msg.user .msg-bubble {
      background: linear-gradient(135deg, var(--accent), #2563eb);
      color: #fff;
      border-bottom-right-radius: 4px;
    }
    .msg.agent .msg-bubble {
      background: var(--panel);
      border: 1px solid var(--border);
      border-bottom-left-radius: 4px;
    }
    .tool-step {
      background: #0d1117;
      border: 1px solid #21262d;
      border-left: 3px solid var(--accent);
      border-radius: 8px;
      padding: 10px 12px;
      font-family: "Cascadia Code", Consolas, monospace;
      font-size: 0.78rem;
      color: #c9d1d9;
      margin-top: 6px;
      white-space: pre-wrap;
    }
    footer {
      background: rgba(18, 23, 32, 0.95);
      border-top: 1px solid var(--border);
      padding: 12px 14px 20px;
    }
    .input-box {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 6px 6px 6px 14px;
    }
    .input-box:focus-within {
      border-color: var(--accent);
      box-shadow: 0 0 14px rgba(59, 130, 246, 0.3);
    }
    textarea {
      flex: 1;
      background: transparent;
      border: 0;
      color: var(--text);
      font-size: 0.95rem;
      resize: none;
      outline: none;
      max-height: 120px;
      min-height: 24px;
      font-family: inherit;
    }
    .send-btn {
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      border: 0;
      color: #fff;
      width: 40px;
      height: 40px;
      border-radius: 12px;
      display: grid;
      place-items: center;
      font-weight: 900;
      cursor: pointer;
      flex-shrink: 0;
      transition: transform 0.15s ease;
    }
    .send-btn:active {
      transform: scale(0.92);
    }
    .send-btn svg {
      width: 18px;
      height: 18px;
      fill: currentColor;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <div class="logo-icon">AG</div>
      <div class="brand-title">Antigravity AI</div>
    </div>
    <div class="status-badge">
      <div class="dot"></div>
      <span>CANLI UZAKTAN MOD</span>
    </div>
  </header>

  <main id="chatMain">
    <div class="welcome-card">
      <div class="welcome-title">👾 Antigravity Mobil İstemci</div>
      <div class="welcome-desc">
        Bilgisayarındaki Antigravity AI asistanına doğrudan prompt ver, otonom geliştirmeyi telefondan yönet ve kod çıktılarını anlık izle.
      </div>
    </div>

    <div class="quick-chips">
      <div class="chip" onclick="setPrompt('3D Dünya simülasyonunu baştan sona oluştur ve testlerini çalıştır')">🌍 3D Dünya Simülasyonu</div>
      <div class="chip" onclick="setPrompt('T-Shirt Mağazası web uygulamasını kontrol et ve geliştir')">👕 T-Shirt Mağazası</div>
      <div class="chip" onclick="setPrompt('Projedeki tüm birim testleri çalıştır ve özet ver')">🧪 Birim Testleri</div>
      <div class="chip" onclick="setPrompt('Sistem ve aktif çalışma alanının durumunu özetle')">📊 Sistem Durumu</div>
    </div>

    <div id="chatStream" class="chat-stream">
      <div class="msg agent">
        <div class="msg-bubble">
          Merhaba! Ben Antigravity AI Asistanı. Bilgisayarda senin için ne geliştirmemi, hangi dosyaları yazmamı veya hangi görevi başlatmamı istersin?
        </div>
      </div>
    </div>
  </main>

  <footer>
    <div class="input-box">
      <textarea id="promptInput" placeholder="Antigravity'ye komut / prompt ver..." rows="1"></textarea>
      <button id="sendBtn" class="send-btn" onclick="sendPrompt()">
        <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
      </button>
    </div>
  </footer>

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
    const stream = document.getElementById('chatStream');
    const input = document.getElementById('promptInput');
    const main = document.getElementById('chatMain');

    input.addEventListener('input', function() {
      this.style.height = 'auto';
      this.style.height = (this.scrollHeight) + 'px';
    });

    input.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendPrompt();
      }
    });

    function setPrompt(text) {
      input.value = text;
      input.focus();
    }

    async function sendPrompt() {
      const text = input.value.trim();
      if (!text) return;

      input.value = '';
      input.style.height = 'auto';

      // Append user msg
      const userDiv = document.createElement('div');
      userDiv.className = 'msg user';
      userDiv.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
      stream.appendChild(userDiv);

      // Append agent loading msg
      const agentDiv = document.createElement('div');
      agentDiv.className = 'msg agent';
      agentDiv.innerHTML = `<div class="msg-bubble">⚡ Antigravity görevi işliyor ve kodlamaya başlıyor...</div>`;
      stream.appendChild(agentDiv);
      main.scrollTop = main.scrollHeight;

      try {
        const resp = await fetch('/v1/supervisor/commands', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ goal: text, auto_start: true, autonomy_mode: 'task' })
        });
        const data = await resp.json();
        
        agentDiv.querySelector('.msg-bubble').innerHTML = `
          ✅ <strong>Görev Başlatıldı! (ID: ${data.id})</strong><br>
          Antigravity otonom olarak kodlamaya başladı.<br><br>
          <div class="tool-step">🎯 Hedef: ${escapeHtml(data.goal)}\n⚙️ Durum: ${data.status}</div>
        `;
        
        pollCommand(data.id, agentDiv);
      } catch (err) {
        agentDiv.querySelector('.msg-bubble').innerHTML = `<span style="color:var(--danger)">⚠️ Hata oluştu: ${escapeHtml(err.message)}</span>`;
      }
    }

    async function pollCommand(cmdId, agentDiv) {
      for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 2000));
        try {
          const resp = await fetch('/v1/supervisor/commands/' + cmdId);
          const data = await resp.json();
          let taskLogs = (data.tasks || []).map(t => `• [${t.status}] ${t.title}`).join('\n');
          agentDiv.querySelector('.msg-bubble').innerHTML = `
            <strong>⚡ Antigravity Otonom İlerleme:</strong><br>
            <div class="tool-step">${escapeHtml(taskLogs || 'Görev grafiği hazırlanıyor...')}</div>
          `;
          main.scrollTop = main.scrollHeight;
          if (data.status === 'completed' || data.status === 'failed') break;
        } catch (e) {}
      }
    }

    function escapeHtml(str) {
      return (str || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
  </script>
</body>
</html>
"""
