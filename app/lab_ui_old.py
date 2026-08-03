LAB_UI = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>⚡ Prometheus AI Agent</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0a0e1a;
  --surface:rgba(20,25,40,.7);
  --glass:rgba(255,255,255,.05);
  --border:rgba(255,255,255,.1);
  --text:#e8edf7;
  --text-dim:#8b95ad;
  --primary:#6366f1;
  --primary-glow:rgba(99,102,241,.3);
  --success:#10b981;
  --warning:#f59e0b;
  --danger:#ef4444;
  --cyan:#06b6d4;
}
body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:
    radial-gradient(circle at 10% 20%,rgba(99,102,241,.15),transparent 40%),
    radial-gradient(circle at 90% 80%,rgba(6,182,212,.12),transparent 40%),
    radial-gradient(circle at 50% 50%,rgba(16,185,129,.08),transparent 50%),
    #0a0e1a;
  color:var(--text);
  min-height:100vh;
  overflow-x:hidden;
}
.container{
  display:grid;
  grid-template-columns:280px 1fr;
  gap:24px;
  padding:24px;
  max-width:1800px;
  margin:0 auto;
  min-height:100vh;
}

/* SIDEBAR */
.sidebar{
  position:sticky;
  top:24px;
  height:calc(100vh - 48px);
  background:var(--surface);
  backdrop-filter:blur(20px) saturate(180%);
  border:1px solid var(--border);
  border-radius:24px;
  padding:32px 20px;
  display:flex;
  flex-direction:column;
  box-shadow:0 20px 60px rgba(0,0,0,.4);
}
.logo{
  display:flex;
  align-items:center;
  gap:12px;
  margin-bottom:40px;
  padding:0 8px;
}
.logo-icon{
  width:48px;
  height:48px;
  background:linear-gradient(135deg,var(--primary),var(--cyan));
  border-radius:14px;
  display:grid;
  place-items:center;
  font-size:24px;
  font-weight:900;
  position:relative;
  box-shadow:0 8px 24px var(--primary-glow);
  animation:float 3s ease-in-out infinite;
}
@keyframes float{
  0%,100%{transform:translateY(0px)}
  50%{transform:translateY(-8px)}
}
.logo-text h1{
  font-size:20px;
  font-weight:800;
  background:linear-gradient(135deg,#fff,var(--cyan));
  -webkit-background-clip:text;
  -webkit-text-fill-color:transparent;
  background-clip:text;
}
.logo-text p{
  font-size:11px;
  color:var(--text-dim);
  text-transform:uppercase;
  letter-spacing:2px;
  font-weight:600;
}

.nav{
  flex:1;
  display:flex;
  flex-direction:column;
  gap:8px;
}
.nav-btn{
  position:relative;
  padding:16px 20px;
  border:none;
  background:transparent;
  color:var(--text-dim);
  text-align:left;
  border-radius:14px;
  cursor:pointer;
  font-size:15px;
  font-weight:600;
  display:flex;
  align-items:center;
  gap:12px;
  transition:all .3s cubic-bezier(.4,0,.2,1);
  overflow:hidden;
}
.nav-btn:before{
  content:'';
  position:absolute;
  inset:0;
  background:linear-gradient(135deg,var(--glass),transparent);
  opacity:0;
  transition:opacity .3s;
}
.nav-btn:hover{
  color:var(--text);
  transform:translateX(4px);
}
.nav-btn:hover:before{opacity:1}
.nav-btn.active{
  background:linear-gradient(135deg,var(--primary),var(--cyan));
  color:#fff;
  box-shadow:0 8px 24px var(--primary-glow);
}
.nav-icon{
  width:20px;
  height:20px;
  display:grid;
  place-items:center;
  font-size:18px;
}

.status-card{
  margin-top:auto;
  padding:20px;
  background:var(--glass);
  border:1px solid var(--border);
  border-radius:14px;
  backdrop-filter:blur(10px);
}
.status-row{
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin-bottom:12px;
}
.status-row:last-child{margin-bottom:0}
.status-label{
  font-size:12px;
  color:var(--text-dim);
  text-transform:uppercase;
  letter-spacing:1px;
}
.status-value{
  font-size:14px;
  font-weight:700;
  display:flex;
  align-items:center;
  gap:6px;
}
.status-dot{
  width:8px;
  height:8px;
  border-radius:50%;
  background:var(--success);
  box-shadow:0 0 12px var(--success);
  animation:pulse 2s ease-in-out infinite;
}
@keyframes pulse{
  0%,100%{opacity:1}
  50%{opacity:.4}
}

/* MAIN CONTENT */
.main{
  display:flex;
  flex-direction:column;
  gap:24px;
  padding-bottom:24px;
}

/* HEADER */
.header{
  background:var(--surface);
  backdrop-filter:blur(20px) saturate(180%);
  border:1px solid var(--border);
  border-radius:24px;
  padding:32px 40px;
  box-shadow:0 8px 32px rgba(0,0,0,.3);
}
.header h2{
  font-size:32px;
  font-weight:900;
  margin-bottom:8px;
  background:linear-gradient(135deg,#fff,var(--cyan));
  -webkit-background-clip:text;
  -webkit-text-fill-color:transparent;
  background-clip:text;
}
.header p{
  color:var(--text-dim);
  font-size:15px;
}

/* NEW TASK CARD */
.task-input-card{
  background:var(--surface);
  backdrop-filter:blur(20px) saturate(180%);
  border:1px solid var(--border);
  border-radius:24px;
  padding:32px 40px;
  box-shadow:0 8px 32px rgba(0,0,0,.3);
}
.task-input-card h3{
  font-size:20px;
  font-weight:700;
  margin-bottom:20px;
  display:flex;
  align-items:center;
  gap:10px;
}
.task-textarea{
  width:100%;
  min-height:120px;
  padding:20px;
  background:rgba(0,0,0,.3);
  border:2px solid var(--border);
  border-radius:16px;
  color:var(--text);
  font-size:15px;
  font-family:inherit;
  resize:vertical;
  margin-bottom:20px;
  transition:border .3s;
}
.task-textarea:focus{
  outline:none;
  border-color:var(--primary);
  box-shadow:0 0 0 4px var(--primary-glow);
}
.task-actions{
  display:flex;
  gap:12px;
}
.btn{
  padding:14px 32px;
  border:none;
  border-radius:12px;
  font-size:15px;
  font-weight:700;
  cursor:pointer;
  transition:all .3s cubic-bezier(.4,0,.2,1);
  display:flex;
  align-items:center;
  gap:8px;
}
.btn-primary{
  background:linear-gradient(135deg,var(--primary),var(--cyan));
  color:#fff;
  box-shadow:0 8px 24px var(--primary-glow);
}
.btn-primary:hover{
  transform:translateY(-2px);
  box-shadow:0 12px 32px var(--primary-glow);
}
.btn-secondary{
  background:var(--glass);
  color:var(--text);
  border:1px solid var(--border);
}
.btn-secondary:hover{
  background:rgba(255,255,255,.1);
}

/* TASKS GRID */
.tasks-grid{
  display:grid;
  gap:20px;
}
.task-card{
  background:var(--surface);
  backdrop-filter:blur(20px) saturate(180%);
  border:1px solid var(--border);
  border-radius:20px;
  padding:28px 32px;
  transition:all .3s cubic-bezier(.4,0,.2,1);
  cursor:pointer;
  position:relative;
  overflow:hidden;
}
.task-card:before{
  content:'';
  position:absolute;
  top:0;
  left:0;
  width:4px;
  height:100%;
  background:var(--primary);
  transform:scaleY(0);
  transition:transform .3s;
}
.task-card:hover{
  transform:translateY(-4px);
  box-shadow:0 16px 48px rgba(0,0,0,.4);
  border-color:rgba(255,255,255,.2);
}
.task-card:hover:before{
  transform:scaleY(1);
}
.task-header{
  display:flex;
  justify-content:space-between;
  align-items:start;
  margin-bottom:16px;
}
.task-id{
  font-size:12px;
  color:var(--text-dim);
  font-weight:600;
  text-transform:uppercase;
  letter-spacing:1px;
}
.task-status{
  padding:6px 14px;
  border-radius:20px;
  font-size:11px;
  font-weight:700;
  text-transform:uppercase;
  letter-spacing:1px;
}
.status-running{
  background:rgba(99,102,241,.2);
  color:var(--primary);
  border:1px solid var(--primary);
  animation:statusPulse 2s ease-in-out infinite;
}
.status-completed{
  background:rgba(16,185,129,.2);
  color:var(--success);
  border:1px solid var(--success);
}
.status-pending{
  background:rgba(245,158,11,.2);
  color:var(--warning);
  border:1px solid var(--warning);
}
@keyframes statusPulse{
  0%,100%{opacity:1}
  50%{opacity:.6}
}
.task-goal{
  font-size:16px;
  font-weight:600;
  margin-bottom:12px;
  line-height:1.5;
}
.task-meta{
  display:flex;
  gap:20px;
  font-size:13px;
  color:var(--text-dim);
}

/* EMPTY STATE */
.empty-state{
  text-align:center;
  padding:80px 40px;
  background:var(--surface);
  backdrop-filter:blur(20px);
  border:2px dashed var(--border);
  border-radius:24px;
}
.empty-icon{
  font-size:64px;
  margin-bottom:20px;
  opacity:.5;
}
.empty-state h3{
  font-size:24px;
  margin-bottom:12px;
}
.empty-state p{
  color:var(--text-dim);
  font-size:15px;
}

/* LOADING */
.loading{
  display:inline-block;
  width:20px;
  height:20px;
  border:3px solid rgba(255,255,255,.2);
  border-top-color:#fff;
  border-radius:50%;
  animation:spin 1s linear infinite;
}
@keyframes spin{
  to{transform:rotate(360deg)}
}

/* RESPONSIVE */
@media(max-width:1200px){
  .container{
    grid-template-columns:1fr;
  }
  .sidebar{
    position:relative;
    height:auto;
    top:0;
  }
}
</style>
</head>
<body>
<div class="container">
  <aside class="sidebar">
    <div class="logo">
      <div class="logo-icon">⚡</div>
      <div class="logo-text">
        <h1>Prometheus</h1>
        <p>AI Agent v0.8</p>
      </div>
    </div>
    
    <nav class="nav">
      <button class="nav-btn active">
        <span class="nav-icon">🎯</span>
        Görevler
      </button>
      <button class="nav-btn">
        <span class="nav-icon">📊</span>
        İstatistikler
      </button>
      <button class="nav-btn">
        <span class="nav-icon">⚙️</span>
        Ayarlar
      </button>
    </nav>
    
    <div class="status-card">
      <div class="status-row">
        <span class="status-label">Durum</span>
        <span class="status-value">
          <span class="status-dot"></span>
          Aktif
        </span>
      </div>
      <div class="status-row">
        <span class="status-label">Model</span>
        <span class="status-value">qwen3 4B</span>
      </div>
      <div class="status-row">
        <span class="status-label">Görevler</span>
        <span class="status-value" id="taskCount">0</span>
      </div>
    </div>
  </aside>
  
  <main class="main">
    <div class="header">
      <h2>🚀 Prometheus Workspace</h2>
      <p>Yapay zeka agent'ınız sizin için kod yazıyor, test ediyor ve dağıtıyor.</p>
    </div>
    
    <div class="task-input-card">
      <h3>✨ Yeni Görev Oluştur</h3>
      <textarea 
        id="taskInput" 
        class="task-textarea" 
        placeholder="Ne yapmak istiyorsun? Örnek: 'Basit bir hesap makinesi yap'"></textarea>
      <div class="task-actions">
        <button class="btn btn-primary" onclick="createTask()">
          <span>🚀</span>
          Görevi Başlat
        </button>
        <button class="btn btn-secondary" onclick="clearInput()">
          Temizle
        </button>
      </div>
    </div>
    
    <div id="tasksContainer"></div>
  </main>
</div>

<script>
let tasks = [];
let pollInterval;

async function loadTasks() {
  try {
    const res = await fetch('/v1/supervisor/commands');
    const data = await res.json();
    tasks = data.commands || [];
    document.getElementById('taskCount').textContent = tasks.length;
    renderTasks();
  } catch (e) {
    console.error('Task load error:', e);
  }
}

function renderTasks() {
  const container = document.getElementById('tasksContainer');
  
  if (tasks.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <h3>Henüz görev yok</h3>
        <p>Yukarıdan yeni bir görev oluşturarak başlayın</p>
      </div>
    `;
    return;
  }
  
  container.innerHTML = '<div class="tasks-grid">' + tasks.map(task => {
    const statusClass = task.status === 'completed' ? 'status-completed' : 
                       task.status === 'running' ? 'status-running' : 'status-pending';
    const statusText = task.status === 'completed' ? 'Tamamlandı' :
                      task.status === 'running' ? 'Çalışıyor' : 'Bekliyor';
    
    return `
      <div class="task-card" onclick="openTask('${task.id}')">
        <div class="task-header">
          <div class="task-id">${task.id}</div>
          <div class="task-status ${statusClass}">${statusText}</div>
        </div>
        <div class="task-goal">${task.goal || 'Görev açıklaması yok'}</div>
        <div class="task-meta">
          <span>⏰ ${new Date(task.created_at).toLocaleString('tr-TR')}</span>
        </div>
      </div>
    `;
  }).join('') + '</div>';
}

async function createTask() {
  const input = document.getElementById('taskInput');
  const goal = input.value.trim();
  
  if (!goal) {
    alert('Lütfen bir görev girin!');
    return;
  }
  
  const btn = event.target;
  btn.disabled = true;
  btn.innerHTML = '<span class="loading"></span> Oluşturuluyor...';
  
  try {
    const res = await fetch('/v1/supervisor/commands', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        goal,
        auto_start: true,
        autonomy_mode: 'task'
      })
    });
    
    if (res.ok) {
      input.value = '';
      await loadTasks();
    }
  } catch (e) {
    alert('Hata: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>🚀</span> Görevi Başlat';
  }
}

function clearInput() {
  document.getElementById('taskInput').value = '';
}

function openTask(id) {
  window.location.href = `/v1/supervisor/commands/${id}`;
}

// Enter tuşu ile gönder
document.getElementById('taskInput').addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'Enter') {
    createTask();
  }
});

// İlk yükleme
loadTasks();

// 3 saniyede bir güncelle
pollInterval = setInterval(loadTasks, 3000);
</script>
</body>
</html>
"""
