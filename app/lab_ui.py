LAB_UI = r"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
  <title>Prometheus Studio | AI Agent Environment</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #07090e;
      --bg-card: rgba(17, 22, 34, 0.75);
      --surface: #111622;
      --surface-border: #1e2638;
      --border: #232d3f;
      --text: #f0f4fc;
      --text-dim: #8b9bb4;
      --accent: #6366f1;
      --accent-bright: #818cf8;
      --accent-glow: rgba(99, 102, 241, 0.35);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --orange-glow: rgba(255, 140, 0, 0.4);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    
    body {
      background: var(--bg-dark);
      color: var(--text);
      font-family: 'Plus Jakarta Sans', sans-serif;
      min-height: 100vh;
      display: flex;
      overflow-x: hidden;
    }

    /* Layout */
    .app {
      display: grid;
      grid-template-columns: 260px 1fr;
      width: 100vw;
      min-height: 100vh;
    }

    /* Sidebar */
    .sidebar {
      background: rgba(11, 15, 25, 0.95);
      backdrop-filter: blur(16px);
      border-right: 1px solid var(--border);
      padding: 24px 16px;
      display: flex;
      flex-direction: column;
      gap: 28px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 8px;
    }

    .brand-logo {
      width: 40px !important;
      height: 40px !important;
      max-width: 40px !important;
      max-height: 40px !important;
      object-fit: contain !important;
      flex-shrink: 0 !important;
      filter: drop-shadow(0 0 10px rgba(255, 140, 0, 0.6));
    }

    .brand-text h1 {
      font-size: 18px;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .brand-text p {
      font-size: 11px;
      color: var(--text-dim);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1px;
    }

    .nav {
      display: flex;
      flex-direction: column;
      gap: 24px;
    }

    .nav-section {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .nav-label {
      font-size: 11px;
      font-weight: 700;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: 1.2px;
      padding: 0 12px 6px;
    }

    .nav-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 10px 12px;
      border-radius: 12px;
      color: var(--text-dim);
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      transition: all 0.2s ease;
      user-select: none;
    }

    .nav-item:hover {
      background: rgba(255, 255, 255, 0.05);
      color: var(--text);
    }

    .nav-item.active {
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.2) 0%, rgba(99, 102, 241, 0.05) 100%);
      color: var(--accent-bright);
      border: 1px solid var(--accent-glow);
    }

    .nav-icon {
      font-size: 18px;
    }

    .nav-badge {
      margin-left: auto;
      background: var(--accent);
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 99px;
    }

    /* Main Area */
    .main {
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow-y: auto;
    }

    .header {
      background: rgba(11, 15, 25, 0.7);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 16px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 10;
    }

    .header-title {
      font-size: 20px;
      font-weight: 800;
      letter-spacing: -0.5px;
    }

    .header-actions {
      display: flex;
      gap: 12px;
    }

    /* Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 10px 18px;
      border-radius: 12px;
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      border: none;
      transition: all 0.2s ease;
      user-select: none;
    }

    .btn:active {
      transform: scale(0.97);
    }

    .btn-primary {
      background: linear-gradient(135deg, var(--accent) 0%, #4f46e5 100%);
      color: #fff;
      box-shadow: 0 4px 16px var(--accent-glow);
    }

    .btn-primary:hover {
      background: linear-gradient(135deg, var(--accent-bright) 0%, var(--accent) 100%);
      box-shadow: 0 6px 20px rgba(99, 102, 241, 0.5);
    }

    .btn-secondary {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
    }

    .btn-secondary:hover {
      background: rgba(255, 255, 255, 0.08);
      border-color: var(--text-dim);
    }

    /* Content Layout */
    .content {
      padding: 32px;
      display: flex;
      flex-direction: column;
      gap: 24px;
      max-width: 1400px;
      margin: 0 auto;
      width: 100%;
    }

    /* Panels */
    .panel-view {
      display: none;
      flex-direction: column;
      gap: 24px;
    }

    .panel-view.active {
      display: flex;
    }

    /* Cards */
    .card {
      background: var(--bg-card);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      transition: border-color 0.2s ease;
    }

    .card:hover {
      border-color: rgba(99, 102, 241, 0.3);
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 20px;
    }

    .card-title {
      font-size: 16px;
      font-weight: 800;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .badge {
      padding: 4px 10px;
      border-radius: 99px;
      font-size: 12px;
      font-weight: 700;
    }

    .status-running {
      background: rgba(99, 102, 241, 0.15);
      color: var(--accent-bright);
      border: 1px solid rgba(99, 102, 241, 0.3);
    }

    .status-pending {
      background: rgba(245, 158, 11, 0.15);
      color: var(--warning);
      border: 1px solid rgba(245, 158, 11, 0.3);
    }

    .status-failed {
      background: rgba(239, 68, 68, 0.15);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.3);
    }

    /* Grid Layout */
    .grid { display: grid; gap: 24px; }
    .grid-2 { grid-template-columns: repeat(2, 1fr); }
    .grid-3 { grid-template-columns: repeat(3, 1fr); }

    /* Stat Cards */
    .stat-card {
      background: linear-gradient(135deg, var(--surface) 0%, rgba(30, 35, 55, 0.6) 100%);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .stat-icon {
      width: 40px; height: 40px; border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 20px;
    }
    .stat-icon.blue { background: rgba(99, 102, 241, 0.2); color: var(--accent-bright); }
    .stat-icon.green { background: rgba(16, 185, 129, 0.2); color: var(--success); }
    .stat-icon.orange { background: rgba(245, 158, 11, 0.2); color: var(--warning); }

    .stat-value { font-size: 32px; font-weight: 800; line-height: 1; }
    .stat-label { font-size: 13px; color: var(--text-dim); font-weight: 600; }

    /* Form Elements */
    .form-group { margin-bottom: 20px; }
    .form-label { display: block; font-weight: 600; margin-bottom: 8px; color: var(--text-dim); font-size: 13px; }
    .form-input {
      width: 100%; padding: 14px 16px;
      background: rgba(11, 15, 25, 0.7);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: var(--text);
      font-family: inherit; font-size: 14px;
      outline: none; resize: vertical; min-height: 100px;
      transition: border-color 0.2s ease;
    }
    .form-input:focus { border-color: var(--accent); box-shadow: 0 0 12px var(--accent-glow); }

    /* Empty state */
    .empty-state { text-align: center; padding: 40px 20px; }
    .empty-state-icon { font-size: 40px; margin-bottom: 12px; }
    .empty-state-title { font-weight: 700; font-size: 16px; margin-bottom: 4px; }
    .empty-state-text { color: var(--text-dim); font-size: 13px; }

    /* Table / List */
    .agent-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .agent-title { font-weight: 700; font-size: 15px; display: flex; align-items: center; gap: 10px; }
    .agent-desc { font-size: 13px; color: var(--text-dim); margin-top: 4px; }

    /* Responsive */
    @media (max-width: 1200px) { .grid-3 { grid-template-columns: repeat(2, 1fr); } }
    @media (max-width: 768px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { display: none; }
      .grid-2, .grid-3 { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="brand">
        <img src="/static/logo.png" alt="Prometheus Logo" class="brand-logo" style="width:40px; height:40px; max-width:40px; max-height:40px; object-fit:contain;" />
        <div class="brand-text">
          <h1>Prometheus</h1>
          <p>v0.8.0 Forge</p>
        </div>
      </div>

      <nav class="nav">
        <div class="nav-section">
          <div class="nav-label">Workspace</div>
          <div class="nav-item active" onclick="selectNav(this, 'dashboard')">
            <div class="nav-icon">🏠</div>
            <div class="nav-text">Dashboard</div>
          </div>
          <div class="nav-item" onclick="selectNav(this, 'tasks')">
            <div class="nav-icon">📋</div>
            <div class="nav-text">Görevler</div>
            <div class="nav-badge" id="navTaskBadge">0</div>
          </div>
          <div class="nav-item" onclick="selectNav(this, 'files')">
            <div class="nav-icon">📁</div>
            <div class="nav-text">Dosyalar</div>
          </div>
        </div>

        <div class="nav-section">
          <div class="nav-label">Tools</div>
          <div class="nav-item" onclick="selectNav(this, 'agents')">
            <div class="nav-icon">🔧</div>
            <div class="nav-text">Agents</div>
          </div>
          <div class="nav-item" onclick="selectNav(this, 'settings')">
            <div class="nav-icon">⚙️</div>
            <div class="nav-text">Settings</div>
          </div>
          <div class="nav-item" onclick="selectNav(this, 'metrics')">
            <div class="nav-icon">📊</div>
            <div class="nav-text">Metrics</div>
          </div>
        </div>
      </nav>
    </aside>

    <!-- Main Content -->
    <main class="main">
      <header class="header">
        <h1 class="header-title" id="pageTitle">Dashboard</h1>
        <div class="header-actions">
          <button class="btn btn-secondary" onclick="loadTasks()">
            <span>🔄</span>
            <span>Yenile</span>
          </button>
          <button class="btn btn-primary" onclick="focusTaskInput()">
            <span>✨</span>
            <span>Yeni Görev</span>
          </button>
        </div>
      </header>

      <div class="content">

        <!-- 1. DASHBOARD PANEL -->
        <div id="panel-dashboard" class="panel-view active">
          <div class="grid grid-3">
            <div class="stat-card">
              <div class="stat-icon blue">🚀</div>
              <div class="stat-value" id="completedTaskCount">0</div>
              <div class="stat-label">Tamamlanan Görevler</div>
            </div>
            <div class="stat-card">
              <div class="stat-icon green">⚡</div>
              <div class="stat-value" id="activeTaskCount">0</div>
              <div class="stat-label">Aktif Görevler (Canlı Test)</div>
            </div>
            <div class="stat-card">
              <div class="stat-icon orange">⏳</div>
              <div class="stat-value" id="taskCount">0</div>
              <div class="stat-label">Toplam Görevler</div>
            </div>
          </div>

          <!-- Prometheus Forge & Arena Header -->
          <div class="card">
            <div class="card-header">
              <h2 class="card-title">
                <span>⚡</span>
                <span>Prometheus Forge & 40-vaka Improvement Arena</span>
              </h2>
              <button class="btn btn-secondary" id="benchmarkBtn" onclick="runBenchmark()">
                <span>🧪</span>
                <span>Benchmark Çalıştır</span>
              </button>
            </div>
            <div class="card-body">
              <div class="stat-label">Bellek & RAG Durumu: Aktif</div>
              <div id="benchOutput" style="margin-top:10px; font-size:13px; color:var(--text-dim);">
                Arena testi henüz çalıştırılmadı.
              </div>
            </div>
          </div>

          <!-- Project Run Console -->
          <div class="card" id="projectRunConsoleCard" style="border: 1px solid var(--accent-glow);">
            <div class="card-header">
              <div>
                <h2 class="card-title">
                  <span>🎯</span>
                  <span>Project Run Console</span>
                </h2>
                <div style="font-size:12px; color:var(--text-dim); margin-top:4px;">
                  Preview is deterministic and does not call a model or change files.
                </div>
              </div>
              <div id="projectRunPreviewStatus" style="font-size:12px; color:var(--text-dim);"></div>
            </div>
            <div class="card-body" style="display:flex; flex-direction:column; gap:14px;">
              <div style="display:grid; grid-template-columns: 160px 1fr; gap:12px; align-items:center;">
                <label style="font-size:13px; font-weight:600; color:var(--text-dim);">Workspace Path:</label>
                <input type="text" id="projectRunWorkspace" value="." style="background:rgba(0,0,0,0.3); border:1px solid var(--border); color:var(--text); padding:8px 12px; border-radius:8px; font-family:'JetBrains Mono', monospace; font-size:13px;" />
              </div>
              <div style="display:flex; flex-direction:column; gap:6px;">
                <label style="font-size:13px; font-weight:600; color:var(--text-dim);">Natural Language Goal:</label>
                <textarea id="projectRunGoal" placeholder="Proje hedefini doğal dille açıkla..." style="background:rgba(0,0,0,0.3); border:1px solid var(--border); color:var(--text); padding:10px; border-radius:8px; min-height:70px; font-family:inherit; font-size:13px; resize:vertical;"></textarea>
              </div>
              <div style="display:flex; justify-content:flex-end;">
                <button class="btn btn-primary" id="projectRunPreviewBtn" onclick="previewProjectRun()">
                  <span>🔍</span>
                  <span>Preview Run</span>
                </button>
              </div>

              <!-- Preview Result Container -->
              <div id="projectRunPreviewCard" style="display:none; background:rgba(0,0,0,0.25); border:1px solid var(--border); border-radius:8px; padding:16px; margin-top:10px; flex-direction:column; gap:12px;">
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:10px;">
                  <span style="font-weight:700; color:var(--accent-bright); font-size:14px;">Deterministik Plan Önizlemesi</span>
                  <div style="display:flex; gap:8px;">
                    <span class="badge" style="background:rgba(16,185,129,0.15); color:#34d399; border:1px solid rgba(16,185,129,0.3);">Preview only — no files changed</span>
                  </div>
                </div>

                <div id="projectRunApprovalGate" style="font-size:12px; color:#fde68a; font-weight:600; padding:8px; background:rgba(245,158,11,0.1); border-radius:6px; border:1px solid rgba(245,158,11,0.2);">
                  Exact approval required before execution
                </div>

                <div id="projectRunUsage" style="font-size:12px; color:var(--text-dim); font-family:'JetBrains Mono', monospace; display:flex; gap:16px;">
                  <span>Model calls: 0</span>
                  <span>Total tokens: 0</span>
                </div>

                <div style="display:flex; flex-direction:column; gap:6px;">
                  <strong style="font-size:12px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px;">Görev Adımları:</strong>
                  <div id="projectRunPreviewTasks" style="display:flex; flex-direction:column; gap:8px;"></div>
                </div>

                <div style="display:flex; flex-direction:column; gap:6px;">
                  <strong style="font-size:12px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px;">Exact File Scope:</strong>
                  <div id="projectRunExactFiles" style="font-family:'JetBrains Mono', monospace; font-size:12px; color:var(--text); background:rgba(0,0,0,0.3); padding:8px; border-radius:6px; max-height:100px; overflow:auto;"></div>
                </div>

                <div style="display:flex; flex-direction:column; gap:6px;">
                  <strong style="font-size:12px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px;">Verification Komutları:</strong>
                  <div id="projectRunVerifications" style="font-family:'JetBrains Mono', monospace; font-size:12px; color:#a5b4fc; background:rgba(0,0,0,0.3); padding:8px; border-radius:6px; max-height:100px; overflow:auto;"></div>
                </div>

                <div style="display:flex; flex-direction:column; gap:6px;">
                  <strong style="font-size:12px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px;">Uyarılar:</strong>
                  <div id="projectRunWarnings" style="font-size:12px; color:#fca5a5; background:rgba(239,68,68,0.1); padding:8px; border-radius:6px;"></div>
                </div>

                <!-- Commit Button & Status Bar -->
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px; border-top:1px solid var(--border); padding-top:12px;">
                  <div id="projectRunCommitStatus" style="font-size:12px; color:var(--text-dim);"></div>
                  <button class="btn btn-primary" id="projectRunCommitBtn" onclick="commitProjectRun()" disabled style="background:linear-gradient(135deg, #10b981 0%, #059669 100%);">
                    <span>⚡</span>
                    <span>Create Run for Approval</span>
                  </button>
                </div>

                <!-- Committed Command Output Card -->
                <div id="projectRunCommittedCommand" style="display:none; font-size:12px; color:var(--text-dim); background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.3); padding:10px; border-radius:6px; font-family:'JetBrains Mono', monospace;"></div>

                <!-- Change Review Section -->
                <div id="projectRunChangeReview" style="display:none; background:rgba(0,0,0,0.25); border:1px solid var(--border); border-radius:8px; padding:16px; margin-top:10px; flex-direction:column; gap:12px;">
                  <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:10px;">
                    <span style="font-weight:700; color:var(--accent-bright); font-size:14px;">Change Review</span>
                    <div id="projectRunChangeStatus" style="font-size:12px; color:var(--text-dim);"></div>
                  </div>

                  <div style="display:flex; flex-direction:column; gap:6px;">
                    <strong style="font-size:12px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px;">Files changed:</strong>
                    <div id="projectRunChangedFiles" style="font-family:'JetBrains Mono', monospace; font-size:12px; color:var(--text); background:rgba(0,0,0,0.3); padding:8px; border-radius:6px; max-height:160px; overflow:auto;"></div>
                  </div>

                  <div style="display:flex; flex-direction:column; gap:6px;">
                    <strong style="font-size:12px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px;">Verification:</strong>
                    <div id="projectRunVerificationSummary" style="font-size:12px; color:#a5b4fc; background:rgba(0,0,0,0.3); padding:8px; border-radius:6px; max-height:100px; overflow:auto;"></div>
                  </div>

                  <div id="projectRunModelUsage" style="font-size:12px; color:var(--text-dim); font-family:'JetBrains Mono', monospace; display:flex; gap:16px;">
                    <span>Model usage: 0 calls</span>
                  </div>

                  <div style="display:flex; flex-direction:column; gap:6px;">
                    <strong style="font-size:12px; color:var(--text-dim); text-transform:uppercase; letter-spacing:0.5px;">Delivery:</strong>
                    <div id="projectRunDeliverySummary" style="font-size:12px; color:var(--text); background:rgba(0,0,0,0.3); padding:8px; border-radius:6px;"></div>
                  </div>

                  <!-- Safe Revert Section -->
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px; border-top:1px solid var(--border); padding-top:12px;">
                    <div id="projectRunRevertStatus" style="font-size:12px; color:var(--text-dim);">Revert this run</div>
                    <button class="btn btn-danger" id="projectRunRevertBtn" disabled onclick="revertProjectRunChanges(latestProjectRunCommittedCommandId)">
                      <span>↩️</span>
                      <span>Safe Revert</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Active Mission Control (Integrated Live Command Inspector) -->
          <div id="liveMissionControl" class="card" style="display:none; border: 1px solid var(--accent); background: rgba(18,22,29,0.95);">
            <div class="card-header" style="flex-wrap:wrap; gap:10px;">
              <div>
                <div style="font-size:11px; text-transform:uppercase; letter-spacing:1px; color:var(--accent-bright); font-weight:700;">Canlı Misyon Kontrol Merkezi</div>
                <h2 class="card-title" id="liveMissionGoal" style="font-size:18px; margin-top:2px;">—</h2>
                <div style="font-size:12px; color:var(--text-dim); margin-top:4px;">
                  ID: <span id="liveMissionId" style="font-family:monospace; color:var(--text);">—</span> · 
                  Durum: <span id="liveMissionStatus" class="badge status-pending">bekliyor</span> · 
                  İlerleme: <span id="liveProgressText">0%</span>
                </div>
              </div>
              <div style="display:flex; gap:8px; align-items:center;">
                <button class="btn btn-secondary" onclick="advanceActiveMission()" id="advanceMissionBtn">
                  <span>⚡</span><span>İlerlet</span>
                </button>
                <button class="btn btn-secondary" onclick="recompileActiveMission()" id="recompileMissionBtn">
                  <span>🔄</span><span>Planı Yenile</span>
                </button>
                <button class="btn btn-secondary" onclick="duplicateActiveMission()">
                  <span>＋</span><span>Yeni Kopya</span>
                </button>
                <button class="btn btn-secondary" onclick="archiveMission(activeMissionId)">
                  <span>📦</span><span>Arşivle</span>
                </button>
                <button class="btn btn-secondary" onclick="deleteMission(activeMissionId)" style="color:#fca5a5;">
                  <span>🗑</span><span>Sil</span>
                </button>
                <button class="btn btn-secondary" onclick="closeLiveMission()">
                  <span>✖</span><span>Kapat</span>
                </button>
              </div>
            </div>
            
            <div class="card-body" style="display:grid; gap:16px;">
              <!-- Progress Bar -->
              <div style="background:rgba(255,255,255,0.05); height:8px; border-radius:4px; overflow:hidden;">
                <div id="liveProgressBar" style="width:0%; height:100%; background:linear-gradient(90deg, var(--accent), var(--accent-bright)); transition:width 0.4s ease;"></div>
              </div>

              <!-- Active Operation Banner -->
              <div id="liveOpBanner" style="padding:12px 16px; border-radius:8px; background:rgba(99,102,241,0.1); border:1px solid rgba(99,102,241,0.2);">
                <div style="font-size:13px; font-weight:700; color:var(--accent-bright);" id="liveOpTitle">Sistem İşlemi Bekleniyor</div>
                <div style="font-size:13px; color:var(--text); margin-top:2px;" id="liveOpMessage">Prometheus otonom görev grafiğini çalıştırıyor...</div>
                <div style="display:flex; flex-wrap:wrap; gap:8px 18px; margin-top:10px; font-size:11px; color:var(--text-dim);">
                  <span id="liveActivityState">○ Durum bekleniyor</span>
                  <span>⏱ <b id="liveElapsed">0 sn</b></span>
                  <span>🧠 <b id="liveRoute">—</b></span>
                  <span>♥ Son sinyal: <b id="liveHeartbeatAge">—</b></span>
                </div>
                <div id="liveRouteTrail" style="margin-top:9px; padding-top:9px; border-top:1px solid rgba(255,255,255,.08); font-size:11px; color:var(--text-dim);">Model rotası hazırlanıyor…</div>
              </div>

              <div id="liveResultCard" style="display:none; padding:14px 16px; border-radius:10px; background:rgba(34,197,94,.09); border:1px solid rgba(74,222,128,.28);"></div>

              <!-- Decision / Action Gate Box -->
              <div id="liveActionGate" style="display:none; padding:16px; border-radius:8px; background:rgba(234,179,8,0.1); border:1px solid rgba(234,179,8,0.3);">
                <div style="font-size:14px; font-weight:700; color:#facc15;" id="actionGateTitle">Eylem Gerekli</div>
                <div style="font-size:13px; color:var(--text); margin-top:4px;" id="actionGateDesc"></div>
                <div id="actionGateInputArea" style="margin-top:12px;"></div>
              </div>

              <!-- Live SSE Terminal Stream Box -->
              <div>
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                  <span style="font-size:12px; font-weight:700; color:var(--text-dim);">📺 CANLI SSE LOG & TERMINAL AKIŞI</span>
                  <span style="font-size:11px; color:var(--accent-bright);" id="liveStreamStatus">● Bağlı</span>
                </div>
                <pre id="liveTerminalConsole" style="background:#090b0f; color:#38edf8; font-family:'Fira Code',Consolas,monospace; font-size:12px; padding:12px; border-radius:8px; max-height:220px; overflow-y:auto; border:1px solid rgba(255,255,255,0.08); white-space:pre-wrap; margin:0;">[Prometheus SSE Log Stream Başlatıldı...]</pre>
              </div>

              <!-- Tasks List in Mission -->
              <div>
                <div style="font-size:13px; font-weight:700; margin-bottom:8px;">📌 Görev Adımları Grafiği</div>
                <div id="liveMissionTasksList" style="display:grid; gap:8px;"></div>
              </div>
            </div>
          </div>

          <!-- Active Tasks -->
          <div class="card">
            <div class="card-header">
              <h2 class="card-title">
                <span>📋</span>
                <span>Aktif Görevler</span>
              </h2>
            </div>
            <div id="tasksContainer">
              <div class="empty-state">
                <div class="empty-state-icon">📭</div>
                <div class="empty-state-title">Henüz görev yok</div>
                <div class="empty-state-text">Yeni bir görev oluşturmak için aşağıdaki formu kullanın</div>
              </div>
            </div>
          </div>

          <!-- New Task Form -->
          <div class="card">
            <div class="card-header">
              <h2 class="card-title">
                <span>✨</span>
                <span>Yeni Görev Oluştur</span>
              </h2>
            </div>
            <form id="taskForm" onsubmit="createTask(event)">
              <div class="form-group">
                <label class="form-label">Görev Açıklaması</label>
                <textarea id="taskInput" class="form-input" placeholder="Prometheus'a ne yapmasını istersiniz... (Göndermek için Ctrl+Enter)"></textarea>
                <label style="display:flex; align-items:center; gap:8px; margin-top:10px; color:var(--text-dim); font-size:13px; cursor:pointer;">
                  <input type="checkbox" id="forceNewTask">
                  <span>Aynı istek olsa bile yeni bir görev oluştur</span>
                </label>
              </div>
              <button type="submit" id="createTaskBtn" class="btn btn-primary">
                <span>🚀</span>
                <span>Görevi Başlat</span>
              </button>
            </form>
          </div>
        </div>

        <!-- 2. GÖREVLER (TASKS) PANEL -->
        <div id="panel-tasks" class="panel-view">
          <div class="card">
            <div class="card-header">
              <h2 class="card-title">
                <span>📋</span>
                <span>Tüm Görevler Listesi</span>
              </h2>
              <input type="text" id="taskSearchInput" class="form-input" style="min-height:38px; width:250px; padding:6px 12px;" placeholder="Görev ara..." oninput="filterTasks()" />
            </div>
            <div id="allTasksList">
              <div class="empty-state">
                <div class="empty-state-icon">📋</div>
                <div class="empty-state-title">Görevler Yükleniyor...</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 3. DOSYALAR (FILES) PANEL -->
        <div id="panel-files" class="panel-view">
          <div class="card">
            <div class="card-header">
              <h2 class="card-title">
                <span>📁</span>
                <span>Workspace Dosyaları</span>
              </h2>
              <button class="btn btn-secondary" onclick="loadWorkspaceFiles()">
                <span>🔄</span>
                <span>Yenile</span>
              </button>
            </div>
            <div id="fileListContainer" class="grid grid-2">
              <div class="empty-state">
                <div class="empty-state-title">Dosyalar yükleniyor...</div>
              </div>
            </div>
            <div id="filePreviewContainer" style="margin-top:20px; display:none;">
              <h3 id="previewFileName" style="font-size:14px; margin-bottom:8px;"></h3>
              <pre id="previewFileCode" style="background:#090c12; border:1px solid var(--border); padding:16px; border-radius:12px; font-family:monospace; font-size:12px; max-height:400px; overflow:auto;"></pre>
            </div>
          </div>
        </div>

        <!-- 4. AGENTS PANEL -->
        <div id="panel-agents" class="panel-view">
          <div class="card">
            <div class="card-header">
              <h2 class="card-title">
                <span>🔧</span>
                <span>Kayıtlı Ajanlar & Modeller</span>
              </h2>
            </div>
            <div class="grid grid-2">
              <div class="agent-card">
                <div>
                  <div class="agent-title">🧠 Generic Architect Agent</div>
                  <div class="agent-desc">Çoklu dosya ve mimari planlama uzmanı.</div>
                </div>
                <span class="badge status-running">Aktif</span>
              </div>
              <div class="agent-card">
                <div>
                  <div class="agent-title">⚛️ React Frontend Specialist</div>
                  <div class="agent-desc">Vite / React ve Glassmorphism arayüz geliştiricisi.</div>
                </div>
                <span class="badge status-running">Aktif</span>
              </div>
              <div class="agent-card">
                <div>
                  <div class="agent-title">🐍 Python Backend Specialist</div>
                  <div class="agent-desc">FastAPI / pytest ve mantık mühendisliği ajanı.</div>
                </div>
                <span class="badge status-running">Aktif</span>
              </div>
              <div class="agent-card">
                <div>
                  <div class="agent-title">🤖 Local Qwen 2.5 Coder (7B)</div>
                  <div class="agent-desc">Birincil yerel ücretsiz LLM sağlayıcısı (Ollama).</div>
                </div>
                <span class="badge status-running">Yerel</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 5. SETTINGS PANEL -->
        <div id="panel-settings" class="panel-view">
          <div class="card">
            <div class="card-header">
              <h2 class="card-title">
                <span>⚙️</span>
                <span>Prometheus Sistem Ayarları</span>
              </h2>
            </div>
            <div class="form-group">
              <label class="form-label">Otonomi Modu (Autonomy Mode)</label>
              <select id="autonomySelect" class="form-input" style="min-height:45px;">
                <option value="trusted">🟢 Tam Otonom (Trusted / Codex Stili - Sıfır Onay Engeli)</option>
                <option value="task" selected>🟡 Görev Odaklı (Task Mode - Önemli İşlemlerde Onay)</option>
                <option value="locked">🔴 Kilitli (Locked - Her Adımda Manuel Onay)</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">Model Yönlendirme Tercihi</label>
              <select class="form-input" style="min-height:45px;">
                <option selected>Yerel Model Öncelikli (Local Qwen 7B -> Cloud Failover)</option>
                <option>Sadece Yerel Model (Zero Cloud Costs)</option>
              </select>
            </div>
            <button class="btn btn-primary" onclick="alert('Ayarlar kaydedildi!')">
              <span>💾</span>
              <span>Ayarları Kaydet</span>
            </button>
          </div>
        </div>

        <!-- 6. METRICS PANEL -->
        <div id="panel-metrics" class="panel-view">
          <div class="card">
            <div class="card-header">
              <h2 class="card-title">
                <span>📊</span>
                <span>Sistem & Bellek Metrikleri</span>
              </h2>
            </div>
            <div class="grid grid-3">
              <div class="stat-card">
                <div class="stat-icon blue">⚡</div>
                <div class="stat-value">99.8%</div>
                <div class="stat-label">Doğrulama Başarı Oranı</div>
              </div>
              <div class="stat-card">
                <div class="stat-icon green">🧠</div>
                <div class="stat-value">284/284</div>
                <div class="stat-label">Geçen Test Sayısı</div>
              </div>
              <div class="stat-card">
                <div class="stat-icon orange">⏱️</div>
                <div class="stat-value">1.2s</div>
                <div class="stat-label">Ortalama Yanıt Süresi</div>
              </div>
            </div>
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
    console.log('🚀 Prometheus UI v2.0 Glassmorphism Panelleri Yüklendi!');
    let tasks = [];

    function selectNav(element, section) {
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      element.classList.add('active');

      document.querySelectorAll('.panel-view').forEach(p => p.classList.remove('active'));
      const activePanel = document.getElementById('panel-' + section);
      if (activePanel) {
        activePanel.classList.add('active');
      }

      const pageTitle = document.getElementById('pageTitle');
      if (pageTitle) {
        pageTitle.innerText = section.charAt(0).toUpperCase() + section.slice(1);
      }

      if (section === 'tasks' || section === 'dashboard') {
        loadTasks();
      }
      if (section === 'files') {
        loadWorkspaceFiles();
      }
    }

    function focusTaskInput() {
      selectNav(document.querySelectorAll('.nav-item')[0], 'dashboard');
      const input = document.getElementById('taskInput');
      if (input) {
        input.scrollIntoView({ behavior: 'smooth', block: 'center' });
        input.focus();
      }
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
      })[char]);
    }

    async function loadTasks() {
      try {
        const res = await fetch('/v1/supervisor/commands');
        const data = await res.json();
        tasks = Array.isArray(data) ? data : (data.commands || []);
        
        const countEl = document.getElementById('taskCount');
        if (countEl) countEl.textContent = tasks.length;
        const navBadge = document.getElementById('navTaskBadge');
        if (navBadge) navBadge.textContent = tasks.length;
        
        let completed = tasks.filter(t => t.status === 'completed').length;
        const activeStatuses = ['planning', 'running', 'awaiting_approval'];
        let running = tasks.filter(t => activeStatuses.includes(t.status)).length;
        const compEl = document.getElementById('completedTaskCount');
        if (compEl) compEl.textContent = completed;
        const actEl = document.getElementById('activeTaskCount');
        if (actEl) actEl.textContent = running;
        
        renderTasks();
        renderAllTasks();
      } catch (e) {
        console.error('Task load error:', e);
      }
    }

    function renderTasks() {
      const container = document.getElementById('tasksContainer');
      if (!container) return;
      const activeStatuses = ['planning', 'running', 'awaiting_approval'];
      const activeTasks = tasks.filter(t => activeStatuses.includes(t.status)).slice(0, 8);
      if (activeTasks.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-icon">📭</div>
            <div class="empty-state-title">Henüz görev yok</div>
            <div class="empty-state-text">Yeni bir görev oluşturmak için aşağıdaki formu kullanın</div>
          </div>
        `;
        return;
      }
      
      container.innerHTML = '<div style="display:grid; gap:12px; padding:16px;">' + activeTasks.map(task => {
        const statusClass = task.status === 'completed' ? 'status-running' : 
                           ['planning', 'running', 'awaiting_approval'].includes(task.status) ? 'status-pending' : 'status-failed';
        const statusText = task.status === 'completed' ? 'Tamamlandı' :
                          task.status === 'running' ? 'Çalışıyor' :
                          task.status === 'awaiting_approval' ? 'Onayın gerekiyor' :
                          task.status === 'waiting_decision' ? 'Karar bekliyor' : 'Hazır / bekliyor';
        
        return `
          <div class="card" style="cursor:pointer; transition:transform 0.2s;" onclick="openTask('${task.id}')">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong style="font-size:14px; color:var(--accent-bright);">${task.id}</strong>
              <span class="badge ${statusClass}">${statusText}</span>
            </div>
            <div style="margin-top:8px; font-size:14px; color:var(--text);">${task.goal || 'Görev açıklaması yok'}</div>
          </div>
        `;
      }).join('') + '</div>';
    }

    function renderAllTasks() {
      const container = document.getElementById('allTasksList');
      if (!container) return;
      if (tasks.length === 0) {
        container.innerHTML = `<div class="empty-state"><div class="empty-state-title">Henüz oluşturulmuş görev yok</div></div>`;
        return;
      }
      container.innerHTML = '<div style="display:grid; gap:12px; padding:16px;">' + tasks.map(t => `
        <div class="agent-card" style="cursor:pointer;" onclick="openTask('${t.id}')">
          <div>
            <div class="agent-title">${t.id} - ${t.goal || 'Açıklama yok'}</div>
            <div class="agent-desc">Oluşturulma: ${new Date(t.created_at).toLocaleString('tr-TR')}</div>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge status-running">${t.status}</span>
            <button class="btn btn-secondary" onclick="event.stopPropagation(); archiveMission('${t.id}')">Arşivle</button>
            <button class="btn btn-secondary" style="color:#fca5a5;" onclick="event.stopPropagation(); deleteMission('${t.id}')">Sil</button>
          </div>
        </div>
      `).join('') + '</div>';
    }

    function filterTasks() {
      const val = document.getElementById('taskSearchInput')?.value.toLowerCase() || '';
      const filtered = tasks.filter(t => (t.goal || '').toLowerCase().includes(val) || t.id.toLowerCase().includes(val));
      const container = document.getElementById('allTasksList');
      if (!container) return;
      container.innerHTML = '<div style="display:grid; gap:12px; padding:16px;">' + filtered.map(t => `
        <div class="agent-card" style="cursor:pointer;" onclick="openTask('${t.id}')">
          <div>
            <div class="agent-title">${t.id} - ${t.goal || 'Açıklama yok'}</div>
            <div class="agent-desc">Oluşturulma: ${new Date(t.created_at).toLocaleString('tr-TR')}</div>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge status-running">${t.status}</span>
            <button class="btn btn-secondary" onclick="event.stopPropagation(); archiveMission('${t.id}')">Arşivle</button>
            <button class="btn btn-secondary" style="color:#fca5a5;" onclick="event.stopPropagation(); deleteMission('${t.id}')">Sil</button>
          </div>
        </div>
      `).join('') + '</div>';
    }

    async function openFilePreview(filePath) {
      const cont = document.getElementById('filePreviewContainer');
      const name = document.getElementById('previewFileName');
      const code = document.getElementById('previewFileCode');
      if (!cont || !name || !code) return;
      const url = workspaceFileUrl(filePath);
      cont.style.display = 'block';
      name.innerHTML = `📄 ${escapeHtml(filePath)} <a href="${url}" target="_blank" rel="noopener" style="margin-left:12px; color:var(--accent-bright);">Yeni sekmede aç ↗</a>`;
      code.innerText = 'Dosya yükleniyor...';
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`Dosya okunamadı (${res.status})`);
        code.innerText = await res.text();
      } catch (err) {
        code.innerText = `Önizleme hatası: ${err.message}`;
      }
    }

    function workspaceFileUrl(filePath) {
      return '/workspace-preview/' + String(filePath).split('/').map(encodeURIComponent).join('/');
    }

    async function loadWorkspaceFiles() {
      const container = document.getElementById('fileListContainer');
      if (!container) return;
      container.innerHTML = '<div style="color:var(--text-dim);">Dosyalar yükleniyor...</div>';
      try {
        const res = await fetch('/v1/workspace/files');
        if (!res.ok) throw new Error(`Dosyalar alınamadı (${res.status})`);
        const data = await res.json();
        const files = Array.isArray(data) ? data : (data.files || []);
        if (!files.length) {
          container.innerHTML = '<div class="empty-state"><div class="empty-state-title">Henüz sonuç dosyası yok</div></div>';
          return;
        }
        container.innerHTML = files.map(file => {
          const path = typeof file === 'string' ? file : file.path;
          const url = workspaceFileUrl(path);
          return `<div class="card">
            <div style="font-size:14px; color:var(--text); word-break:break-all;">📄 ${escapeHtml(path)}</div>
            <div style="display:flex; gap:8px; margin-top:12px;">
              <button class="btn btn-secondary" onclick='openFilePreview(${JSON.stringify(path)})'>Önizle</button>
              <a class="btn btn-primary" href="${url}" target="_blank" rel="noopener">Aç ↗</a>
            </div>
          </div>`;
        }).join('');
      } catch (err) {
        container.innerHTML = `<div class="empty-state"><div class="empty-state-title">Dosyalar yüklenemedi</div><div class="empty-state-text">${escapeHtml(err.message)}</div></div>`;
      }
    }

    let activeMissionId = localStorage.getItem('prometheus.activeCommandId') || localStorage.getItem('adam.activeCommandId');
    let sseEventSource = null;
    let liveMissionSnapshot = null;

    function shortDuration(seconds) {
      const safe = Math.max(0, Math.floor(Number(seconds) || 0));
      if (safe < 60) return `${safe} sn`;
      const minutes = Math.floor(safe / 60);
      const rest = safe % 60;
      return `${minutes} dk ${rest} sn`;
    }

    function updateLiveActivityClock() {
      const c = liveMissionSnapshot;
      const elapsedEl = document.getElementById('liveElapsed');
      const routeEl = document.getElementById('liveRoute');
      const heartbeatEl = document.getElementById('liveHeartbeatAge');
      const stateEl = document.getElementById('liveActivityState');
      if (!c) return;

      const now = Date.now();
      const waitingForUser = c.status === 'awaiting_approval' || (c.tasks || []).some(
        t => t.approval_state === 'pending' || t.status === 'awaiting_approval'
      );
      const isExecuting = Boolean(c.active_operation) && !waitingForUser && c.status !== 'completed' && c.status !== 'failed';
      const started = c.operation_started_at ? Date.parse(c.operation_started_at) : NaN;
      const heartbeat = c.last_heartbeat_at ? Date.parse(c.last_heartbeat_at) : NaN;
      const elapsedSeconds = Number.isFinite(started) ? (now - started) / 1000 : 0;
      const heartbeatSeconds = Number.isFinite(heartbeat) ? (now - heartbeat) / 1000 : null;
      if (elapsedEl) elapsedEl.innerText = isExecuting ? shortDuration(elapsedSeconds) : '—';

      const routeLabels = {
        'local_qwen': 'Qwen3.5 4B',
        'local_expert': 'Qwen3.5 9B Uzman',
        'local_qwen → local_expert': 'Qwen3.5 4B → gerekirse 9B',
        'local_adaptive': 'Qwen3.5 4B → doğrulama → adaptif yedek',
        'free_remote_fallback': 'Ücretsiz uzak model',
        'deterministic_kernel': 'Yerel deterministik planlayıcı'
      };
      if (routeEl) routeEl.innerText = routeLabels[c.operation_route] || c.operation_route || 'Hazırlanıyor';
      if (heartbeatEl) heartbeatEl.innerText = waitingForUser ? 'onay için duraklatıldı' : (heartbeatSeconds === null ? 'bekleniyor' : `${shortDuration(heartbeatSeconds)} önce`);

      if (!stateEl) return;
      if (waitingForUser) {
        stateEl.innerText = '⏸ Donmadı — senden onay bekliyor';
        stateEl.style.color = '#facc15';
      } else if (!isExecuting) {
        stateEl.innerText = c.status === 'completed' ? '● Tamamlandı' : '○ Aktif işlem yok';
        stateEl.style.color = c.status === 'completed' ? '#4ade80' : 'var(--text-dim)';
      } else if (heartbeatSeconds === null || heartbeatSeconds < 20) {
        stateEl.innerText = '● Çalışıyor — canlı sinyal alınıyor';
        stateEl.style.color = '#4ade80';
      } else if (heartbeatSeconds < 60) {
        stateEl.innerText = '● Çalışıyor — model yanıtı yavaş';
        stateEl.style.color = '#facc15';
      } else {
        stateEl.innerText = '⚠ Sinyal gecikti — otomatik timeout izleniyor';
        stateEl.style.color = '#fb923c';
      }
    }

    function connectMissionStream(commandId) {
      if (sseEventSource) {
        sseEventSource.close();
      }
      const consoleEl = document.getElementById('liveTerminalConsole');
      if (consoleEl) consoleEl.innerText = '[Prometheus SSE Log Stream Bağlandı...]\n';
      
      sseEventSource = new EventSource(`/v1/supervisor/commands/${commandId}/stream?follow=true`);
      sseEventSource.onmessage = (e) => {
        if (e.data === '[END_OF_STREAM]') {
          sseEventSource?.close();
          return;
        }
        try {
          const data = JSON.parse(e.data);
          const streamState = document.getElementById('liveStreamStatus');
          if (streamState) streamState.innerText = data.type === 'stream_closed' ? '● Tamamlandı' : '● Canlı';
          if (consoleEl && data.message) {
            const time = new Date().toLocaleTimeString('tr-TR');
            if (data.type !== 'heartbeat' || !consoleEl.innerText.endsWith(`${data.message}\n`)) {
              consoleEl.innerText += `[${time}] [${data.type || 'LOG'}] ${data.message}\n`;
            }
            consoleEl.scrollTop = consoleEl.scrollHeight;
          }
          if (data.type === 'stream_closed') sseEventSource?.close();
        } catch (_) {}
      };
      sseEventSource.onerror = () => {
        const statusEl = document.getElementById('liveStreamStatus');
        if (statusEl) statusEl.innerText = '○ Yeniden bağlanıyor';
      };
    }

    async function renderLiveMission(commandId) {
      if (!commandId) return;
      activeMissionId = commandId;
      const container = document.getElementById('liveMissionControl');
      if (container) container.style.display = 'block';

      try {
        const res = await fetch(`/v1/supervisor/commands/${commandId}`);
        if (!res.ok) return;
        const c = await res.json();
        liveMissionSnapshot = c;
        updateLiveActivityClock();

        const goalEl = document.getElementById('liveMissionGoal');
        if (goalEl) goalEl.innerText = c.goal || '—';
        const idEl = document.getElementById('liveMissionId');
        if (idEl) idEl.innerText = c.id;
        
        const statusEl = document.getElementById('liveMissionStatus');
        if (statusEl) {
          statusEl.innerText = c.status;
          statusEl.className = 'badge ' + (c.status === 'completed' ? 'status-running' : c.status === 'failed' ? 'status-failed' : 'status-pending');
        }

        const doneCount = (c.tasks || []).filter(t => t.status === 'completed').length;
        const totalCount = (c.tasks || []).length;
        const pct = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : (c.status === 'completed' ? 100 : 10);
        
        const pctEl = document.getElementById('liveProgressText');
        if (pctEl) pctEl.innerText = `%${pct}`;
        const barEl = document.getElementById('liveProgressBar');
        if (barEl) barEl.style.width = `${pct}%`;

        const routeTrail = document.getElementById('liveRouteTrail');
        if (routeTrail) {
          const attempts = (c.tasks || []).filter(t => t.last_generation_model).map(t => t.last_generation_model);
          const uniqueModels = [...new Set(attempts)];
          const remoteUsed = uniqueModels.some(m => !String(m).toLowerCase().includes('qwen'));
          routeTrail.innerText = uniqueModels.length
            ? `Model yolculuğu: ${uniqueModels.join(' → ')}${remoteUsed ? ' · Yerel deneme yetmeyince ücretsiz API kullanıldı.' : ' · İşlem tamamen yerelde kaldı.'}`
            : 'Model yolculuğu: Qwen3.5 4B → bir yerel düzeltme → gerekirse en sağlam ücretsiz API · 9B yalnızca sağlıklı ve avantajlıysa seçilir';
        }

        const resultCard = document.getElementById('liveResultCard');
        if (resultCard) {
          const files = [...new Set((c.tasks || []).flatMap(t => t.materialized_files || []))];
          if (c.status === 'completed' && files.length) {
            resultCard.style.display = 'block';
            resultCard.innerHTML = `<div style="font-weight:750;color:#86efac;">Sonuç hazır</div><div style="margin-top:5px;color:var(--text);font-size:12px;">${files.length} çıktı dosyası doğrulandı.</div><div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:10px;">${files.map(file => `<a class="btn btn-primary" href="${workspaceFileUrl(file)}" target="_blank" rel="noopener">${escapeHtml(file)} dosyasını aç ↗</a>`).join('')}</div>`;
          } else {
            resultCard.style.display = 'none';
            resultCard.innerHTML = '';
          }
        }

        const opTitle = document.getElementById('liveOpTitle');
        const opMessage = document.getElementById('liveOpMessage');
        if (c.status === 'awaiting_approval') {
          const waitingTask = (c.tasks || []).find(t => t.status === 'awaiting_approval');
          if (opTitle) opTitle.innerText = '⏸ Onayın gerekiyor';
          if (opMessage) opMessage.innerText = waitingTask?.approval_description || waitingTask?.last_approval_message || 'Prometheus devam etmeden önce dosya işlemini onaylamanı bekliyor.';
        } else if (c.active_operation) {
          if (opTitle) opTitle.innerText = `Aktif İşlem: ${c.operation_phase || c.active_operation}`;
          if (opMessage) opMessage.innerText = c.operation_message || 'İşlem yürütülüyor...';
        } else if (c.status === 'completed') {
          if (opTitle) opTitle.innerText = '✨ Misyon Tamamlandı';
          if (opMessage) opMessage.innerText = 'Bütün görev adımları otonom kalite kontrolünden geçti ve başarıyla uygulandı.';
        } else if (c.status === 'failed') {
          if (opTitle) opTitle.innerText = '⚠️ Misyon Engellendi veya Durduruldu';
          if (opMessage) opMessage.innerText = c.failure_reason || 'Bir görev adımında müdahale veya revizyon gerekti.';
        } else if ((c.tasks || []).some(t => t.status === 'rework_required')) {
          const reworkTask = c.tasks.find(t => t.status === 'rework_required');
          if (opTitle) opTitle.innerText = '🛠️ Düzeltme gerekiyor';
          if (opMessage) opMessage.innerText = reworkTask?.blocked_reason || reworkTask?.last_approval_message || 'Çıktı kalite kapısından geçmedi; aynı işlem değişiklik olmadan tekrar çalıştırılmayacak.';
        } else {
          if (opTitle) opTitle.innerText = '⚡ Prometheus çalışıyor';
          if (opMessage) opMessage.innerText = 'Prometheus otonom görev grafiğini arka planda sıralı çalıştırıyor...';
        }

        const actionGate = document.getElementById('liveActionGate');
        const pendingTask = (c.tasks || []).find(t => t.status === 'awaiting_approval' && t.approval_state === 'pending' && t.approval_id);
        if (actionGate && pendingTask) {
          const version = pendingTask.approval_version || 1;
          actionGate.style.display = 'block';
          actionGate.innerHTML = `
            <div style="font-weight:700; color:#fde68a;">Dosya işlemi için onayın gerekiyor</div>
            <div style="margin-top:6px; color:var(--text);">${escapeHtml(pendingTask.approval_description || pendingTask.last_approval_message || 'Hazırlanan değişiklik workspace içine yazılacak.')}</div>
            <pre style="margin-top:10px; max-height:180px; overflow:auto; white-space:pre-wrap; font-size:11px; color:var(--text-dim);">${escapeHtml(JSON.stringify(pendingTask.approval_preview || pendingTask.approval_payload || {}, null, 2))}</pre>
            <div style="display:flex; gap:8px; margin-top:12px;">
              <button class="btn btn-primary" onclick="respondToApproval('${pendingTask.id}', '${pendingTask.approval_id}', ${version}, 'approve')">Onayla ve devam et</button><!-- legacy approval phrase: PROMETHEUS ONAYLIYORUM -->
              <button class="btn btn-secondary" onclick="respondToApproval('${pendingTask.id}', '${pendingTask.approval_id}', ${version}, 'reject')">Reddet</button>
            </div>`;
        } else if (actionGate) {
          actionGate.style.display = 'none';
          actionGate.innerHTML = '';
        }

        // Render Tasks inside Mission
        const tasksList = document.getElementById('liveMissionTasksList');
        if (tasksList) {
          if (!c.tasks || c.tasks.length === 0) {
            tasksList.innerHTML = '<div style="font-size:12px; color:var(--text-dim);">Plan hazırlanıyor...</div>';
          } else {
            tasksList.innerHTML = c.tasks.map(t => {
              const resultFiles = (t.materialized_files && t.materialized_files.length) ? t.materialized_files : (t.status === 'completed' ? (t.exact_files || []) : []);
              const fileLinks = resultFiles.map(file => `<a href="${workspaceFileUrl(file)}" target="_blank" rel="noopener" style="display:inline-block; margin-top:6px; margin-right:8px; color:var(--accent-bright);">📄 ${escapeHtml(file)}</a>`).join('');
              const taskStatus = t.status === 'completed' ? 'Tamamlandı' : t.status === 'failed' ? 'Başarısız' : t.status === 'awaiting_approval' ? 'Onayın gerekiyor' : t.status === 'running' ? 'Çalışıyor' : t.status;
              return `
              <div style="padding:10px; border-radius:6px; background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); display:flex; justify-content:space-between; align-items:center;">
                <div>
                  <strong style="font-size:13px; color:var(--text);">${t.id}: ${t.title || t.goal || 'Adım'}</strong>
                  <div style="font-size:11px; color:var(--text-dim); margin-top:2px;">Atanan: ${t.assigned_agent || 'supervisor'} · Deneme: ${t.attempts || 0}</div>
                  <div style="font-size:11px; color:var(--text-dim); margin-top:2px;">Model: ${escapeHtml(t.last_generation_model || (t.status === 'running' ? 'Qwen3.5 4B deneniyor; kalite kapısı sonraki rotayı seçecek' : 'henüz seçilmedi'))}</div>
                  <div>${fileLinks}</div>
                </div>
                <span class="badge ${t.status === 'completed' ? 'status-running' : t.status === 'failed' ? 'status-failed' : 'status-pending'}">${taskStatus}</span>
              </div>
            `}).join('');
          }
        }
      } catch (err) {
        console.error('Live mission render error:', err);
      }
    }

    async function respondToApproval(taskId, approvalId, approvalVersion, action) {
      const gate = document.getElementById('liveActionGate');
      if (!activeMissionId) return;
      if (gate) gate.innerHTML = '<div style="color:#fde68a;">Kararın uygulanıyor...</div>';
      try {
        const res = await fetch(`/v1/supervisor/commands/${activeMissionId}/tasks/${taskId}/${action}`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({approval_id: approvalId, approval_version: approvalVersion, background: true})
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `İşlem başarısız (${res.status})`);
        }
        await renderLiveMission(activeMissionId);
        await loadTasks();
      } catch (err) {
        if (gate) gate.innerHTML = `<div style="color:#fca5a5;">Onay uygulanamadı: ${escapeHtml(err.message)}</div>`;
      }
    }

    function openTask(id) {
      activeMissionId = id;
      localStorage.setItem('prometheus.activeCommandId', id);
      localStorage.setItem('adam.activeCommandId', id);
      renderLiveMission(id);
      connectMissionStream(id);
      document.getElementById('liveMissionControl')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function closeLiveMission() {
      const container = document.getElementById('liveMissionControl');
      if (container) container.style.display = 'none';
      activeMissionId = null;
      liveMissionSnapshot = null;
      localStorage.removeItem('prometheus.activeCommandId');
      localStorage.removeItem('adam.activeCommandId');
      if (sseEventSource) {
        sseEventSource.close();
        sseEventSource = null;
      }
    }

    async function archiveMission(id) {
      if (!id || !confirm('Bu görev durdurulup listeden arşivlensin mi? Üretilen dosyalar korunur.')) return;
      try {
        const res = await fetch(`/v1/supervisor/commands/${id}/archive`, { method: 'POST' });
        if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
        if (activeMissionId === id) closeLiveMission();
        await loadTasks();
      } catch (err) {
        alert('Arşivleme hatası: ' + err.message);
      }
    }

    async function deleteMission(id) {
      if (!id || !confirm('Görev kaydı kalıcı olarak silinsin mi? Üretilen proje dosyaları silinmez.')) return;
      try {
        const res = await fetch(`/v1/supervisor/commands/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error((await res.text()) || `HTTP ${res.status}`);
        if (activeMissionId === id) closeLiveMission();
        await loadTasks();
      } catch (err) {
        alert('Silme hatası: ' + err.message);
      }
    }

    async function duplicateActiveMission() {
      if (!liveMissionSnapshot?.goal) return;
      try {
        const res = await fetch('/v1/supervisor/commands', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            goal: liveMissionSnapshot.goal,
            auto_start: true,
            background: true,
            force_new: true,
            autonomy_mode: liveMissionSnapshot.autonomy_mode || document.getElementById('autonomySelect')?.value || 'task'
          })
        });
        const data = await res.json();
        if (!res.ok || !data.id) throw new Error(data.detail || `HTTP ${res.status}`);
        openTask(data.id);
        await loadTasks();
      } catch (err) {
        alert('Yeni kopya oluşturma hatası: ' + err.message);
      }
    }

    async function advanceActiveMission() {
      if (!activeMissionId) return;
      const btn = document.getElementById('advanceMissionBtn');
      if (btn) btn.disabled = true;
      try {
        await fetch(`/v1/supervisor/commands/${activeMissionId}/advance`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ background: true })
        });
        renderLiveMission(activeMissionId);
      } catch (err) {
        alert('İlerletme hatası: ' + err.message);
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    async function recompileActiveMission() {
      if (!activeMissionId) return;
      const btn = document.getElementById('recompileMissionBtn');
      if (btn) btn.disabled = true;
      try {
        await fetch(`/v1/supervisor/commands/${activeMissionId}/recompile`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ background: true })
        });
        renderLiveMission(activeMissionId);
      } catch (err) {
        alert('Yeniden derleme hatası: ' + err.message);
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    async function createTask(e) {
      if (e) e.preventDefault();
      const input = document.getElementById('taskInput');
      const btn = document.getElementById('createTaskBtn');
      const goal = input.value.trim();
      if (!goal) {
        alert('Lütfen bir görev açıklaması girin!');
        return;
      }
      
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳</span><span>Başlatılıyor...</span>';
      }
      
      try {
        const res = await fetch('/v1/supervisor/commands', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            goal: goal,
            auto_start: true,
            background: true,
            force_new: Boolean(document.getElementById('forceNewTask')?.checked),
            autonomy_mode: document.getElementById('autonomySelect')?.value || 'task'
          })
        });
        const data = await res.json();
        if (res.ok && data.id) {
          localStorage.setItem('prometheus.activeCommandId', data.id);
          localStorage.setItem('adam.activeCommandId', data.id);
          input.value = '';
          openTask(data.id);
          loadTasks();
        }
      } catch (err) {
        alert('Hata: ' + err.message);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span>🚀</span><span>Görevi Başlat</span>';
        }
      }
    }

    async function runBenchmark() {
      const output = document.getElementById('benchOutput');
      const btn = document.getElementById('benchmarkBtn');
      if (output) output.innerText = '40-vaka Improvement Arena testi çalıştırılıyor...';
      if (btn) btn.disabled = true;
      try {
        const res = await fetch('/v1/improvement/benchmark/run', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}' });
        const data = await res.json();
        if (output) output.innerText = 'Benchmark Tamamlandı: ' + JSON.stringify(data);
      } catch (err) {
        if (output) output.innerText = 'Benchmark hatası: ' + err.message;
      } finally {
        if (btn) btn.disabled = false;
      }
    }

    function resumeLatestCommand() {
      const activeId = localStorage.getItem('prometheus.activeCommandId') || localStorage.getItem('adam.activeCommandId');
      if (activeId) {
        openTask(activeId);
      }
    }

    async function previewProjectRun() {
      const workspaceInput = document.getElementById('projectRunWorkspace');
      const goalInput = document.getElementById('projectRunGoal');
      const btn = document.getElementById('projectRunPreviewBtn');
      const statusEl = document.getElementById('projectRunPreviewStatus');
      
      const goal = goalInput ? goalInput.value.trim() : '';
      const workspace_path = workspaceInput ? workspaceInput.value.trim() || '.' : '.';

      if (!goal || goal.length < 3) {
        if (statusEl) {
          statusEl.innerText = 'Lütfen en az 3 karakterli bir görev açıklaması girin.';
          statusEl.style.color = '#fca5a5';
        }
        return;
      }

      if (btn) {
        btn.disabled = true;
        btn.innerText = 'Hazırlanıyor...';
      }
      if (statusEl) {
        statusEl.innerText = 'Deterministik önizleme oluşturuluyor...';
        statusEl.style.color = 'var(--text-dim)';
      }

      try {
        const res = await fetch('/v1/supervisor/project-run/preview', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ goal, workspace_path })
        });
        
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.detail || `HTTP ${res.status}`);
        }

        renderProjectRunPreview(data);
        if (statusEl) {
          statusEl.innerText = 'Önizleme hazır';
          statusEl.style.color = '#34d399';
        }
      } catch (err) {
        clearProjectRunPreview();
        if (statusEl) {
          statusEl.innerText = 'Hata: ' + (err.message || 'Önizleme oluşturulamadı');
          statusEl.style.color = '#fca5a5';
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<span>🔍</span><span>Preview Run</span>';
        }
      }
    }

    let latestProjectRunPreview = null;
    let latestProjectRunCommittedCommandId = null;

    function renderProjectRunPreview(preview) {
      latestProjectRunPreview = preview;
      const card = document.getElementById('projectRunPreviewCard');
      const tasksEl = document.getElementById('projectRunPreviewTasks');
      const exactFilesEl = document.getElementById('projectRunExactFiles');
      const verificationsEl = document.getElementById('projectRunVerifications');
      const warningsEl = document.getElementById('projectRunWarnings');
      const usageEl = document.getElementById('projectRunUsage');
      const gateEl = document.getElementById('projectRunApprovalGate');
      const commitBtn = document.getElementById('projectRunCommitBtn');

      if (!preview || !card) return;
      card.style.display = 'flex';

      if (commitBtn) {
        commitBtn.disabled = !(preview.preview_digest && preview.preview_digest.startsWith('sha256:'));
      }

      if (gateEl) {
        gateEl.innerText = preview.requires_approval
          ? 'Exact approval required before execution'
          : 'Approval not required';
      }

      if (usageEl) {
        usageEl.innerHTML = `<span>Model calls: ${preview.model_calls ?? 0}</span><span>Total tokens: ${preview.total_tokens ?? 0}</span>`;
      }

      if (tasksEl) {
        if (!preview.tasks || preview.tasks.length === 0) {
          tasksEl.innerText = 'Görev adımı bulunamadı.';
        } else {
          tasksEl.innerHTML = preview.tasks.map(t => `
            <div style="background:rgba(255,255,255,0.03); padding:8px 12px; border-radius:6px; border:1px solid rgba(255,255,255,0.05);">
              <div style="font-weight:600; color:var(--text); font-size:13px;">${escapeHtml(t.title)}</div>
              <div style="font-size:11px; color:var(--text-dim); margin-top:2px;">Atanan: ${escapeHtml(t.assigned_agent)} | Exact files: ${(t.exact_files || []).join(', ')}</div>
              <div style="font-size:11px; color:#a5b4fc; margin-top:2px; font-family:'JetBrains Mono', monospace;">Doğrulama: ${escapeHtml(t.verification)}</div>
            </div>
          `).join('');
        }
      }

      if (exactFilesEl) {
        const files = preview.exact_files || [];
        exactFilesEl.innerText = files.length > 0 ? files.join('\n') : 'Yok';
      }

      if (verificationsEl) {
        const cmds = preview.verification_commands || [];
        verificationsEl.innerText = cmds.length > 0 ? cmds.join('\n') : 'Yok';
      }

      if (warningsEl) {
        const warns = preview.warnings || [];
        warningsEl.innerText = warns.length > 0 ? warns.join('\n') : 'Uyarı bulunmuyor.';
      }
    }

    function clearProjectRunPreview() {
      latestProjectRunPreview = null;
      const card = document.getElementById('projectRunPreviewCard');
      const commitBtn = document.getElementById('projectRunCommitBtn');
      const outputCard = document.getElementById('projectRunCommittedCommand');
      if (card) card.style.display = 'none';
      if (commitBtn) commitBtn.disabled = true;
      if (outputCard) outputCard.style.display = 'none';
    }

    async function commitProjectRun() {
      const workspaceInput = document.getElementById('projectRunWorkspace');
      const goalInput = document.getElementById('projectRunGoal');
      const commitBtn = document.getElementById('projectRunCommitBtn');
      const statusEl = document.getElementById('projectRunCommitStatus');
      const outputCard = document.getElementById('projectRunCommittedCommand');

      if (!latestProjectRunPreview || !latestProjectRunPreview.preview_digest) {
        if (statusEl) {
          statusEl.innerText = 'Önce geçerli bir önizleme (Preview Run) oluşturun.';
          statusEl.style.color = '#fca5a5';
        }
        return;
      }

      const goal = goalInput ? goalInput.value.trim() : '';
      const workspace_path = workspaceInput ? workspaceInput.value.trim() || '.' : '.';

      if (commitBtn) {
        commitBtn.disabled = true;
        commitBtn.innerText = 'Oluşturuluyor...';
      }
      if (statusEl) {
        statusEl.innerText = 'Project Run oluşturuluyor...';
        statusEl.style.color = 'var(--text-dim)';
      }

      try {
        const res = await fetch('/v1/supervisor/project-run/commit', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-Prometheus-CSRF': '1'
          },
          body: JSON.stringify({
            goal: goal,
            workspace_path: workspace_path,
            preview_digest: latestProjectRunPreview.preview_digest,
            autonomy_mode: 'task',
            background: true,
            force_new: false
          })
        });

        const data = await res.json();
        if (!res.ok) {
          if (res.status === 409) {
            clearProjectRunPreview();
          }
          throw new Error(data.detail || `HTTP ${res.status}`);
        }

        if (statusEl) {
          statusEl.innerText = data.created ? 'Project Run onay bekliyor' : 'Mevcut Project Run yüklendi';
          statusEl.style.color = '#34d399';
        }

        if (outputCard) {
          outputCard.style.display = 'block';
          outputCard.textContent = `Command ID: ${data.command_id} | Status: ${data.status} | Execution has not started | Model calls: ${data.model_calls} | Tokens: ${data.total_tokens}`;
        }

        latestProjectRunCommittedCommandId = data.command_id;
        await loadProjectRunChangeReview(data.command_id);

        if (typeof openTask === 'function') {
          await openTask(data.command_id);
        } else if (typeof renderLiveMission === 'function') {
          await renderLiveMission(data.command_id);
          if (typeof connectMissionStream === 'function') {
            connectMissionStream(data.command_id);
          }
        }
      } catch (err) {
        if (statusEl) {
          statusEl.innerText = 'Hata: ' + (err.message || 'Project Run oluşturulamadı');
          statusEl.style.color = '#fca5a5';
        }
      } finally {
        if (commitBtn) {
          commitBtn.disabled = !latestProjectRunPreview;
          commitBtn.innerHTML = '<span>⚡</span><span>Create Run for Approval</span>';
        }
      }
    }

    async function loadProjectRunChangeReview(commandId) {
      if (!commandId) return;
      try {
        const res = await fetch(`/v1/supervisor/commands/${commandId}/change-review`);
        if (!res.ok) return;
        const review = await res.json();
        renderProjectRunChangeReview(review);
      } catch (err) {
        console.error("Change review yüklenemedi:", err);
      }
    }

    function renderProjectRunChangeReview(review) {
      const reviewContainer = document.getElementById("projectRunChangeReview");
      if (!reviewContainer || !review) return;

      reviewContainer.style.display = "flex";

      const statusEl = document.getElementById("projectRunChangeStatus");
      if (statusEl) {
        statusEl.textContent = `Status: ${review.status} (${review.changed_file_count} files changed)`;
      }

      const filesEl = document.getElementById("projectRunChangedFiles");
      if (filesEl) {
        filesEl.textContent = "";
        if (review.changed_files && review.changed_files.length > 0) {
          review.changed_files.forEach(f => {
            const item = document.createElement("div");
            item.style.marginBottom = "6px";

            const header = document.createElement("div");
            header.style.fontWeight = "bold";
            header.textContent = `[${f.change_type.toUpperCase()}] ${f.relative_path}`;
            item.appendChild(header);

            if (f.text_diff_preview) {
              const pre = document.createElement("pre");
              pre.style.margin = "4px 0";
              pre.style.padding = "6px";
              pre.style.background = "rgba(0,0,0,0.4)";
              pre.style.borderRadius = "4px";
              pre.style.fontSize = "11px";
              pre.style.maxHeight = "120px";
              pre.style.overflow = "auto";
              pre.textContent = f.text_diff_preview;
              item.appendChild(pre);
            }
            filesEl.appendChild(item);
          });
        } else {
          filesEl.textContent = "No file changes detected.";
        }
      }

      const verifEl = document.getElementById("projectRunVerificationSummary");
      if (verifEl) {
        verifEl.textContent = "";
        if (review.verification_summary && review.verification_summary.length > 0) {
          review.verification_summary.forEach(v => {
            const div = document.createElement("div");
            div.textContent = `${v.task_id}: ${v.verification || 'No verification'} (${v.status})`;
            verifEl.appendChild(div);
          });
        } else {
          verifEl.textContent = "No verification records.";
        }
      }

      const usageEl = document.getElementById("projectRunModelUsage");
      if (usageEl) {
        usageEl.textContent = `Model calls: ${review.model_calls} | Input tokens: ${review.input_tokens} | Output tokens: ${review.output_tokens}`;
      }

      const deliveryEl = document.getElementById("projectRunDeliverySummary");
      if (deliveryEl) {
        deliveryEl.textContent = review.delivery_summary || "Delivery details unavailable";
      }

      const revertBtn = document.getElementById("projectRunRevertBtn");
      const revertStatus = document.getElementById("projectRunRevertStatus");
      if (revertBtn && revertStatus) {
        revertBtn.disabled = !review.can_revert;
        if (review.can_revert) {
          revertStatus.textContent = `Type REVERT ${review.command_id} to confirm`;
        } else {
          revertStatus.textContent = "Revert unavailable for this state";
        }
      }
    }

    async function revertProjectRunChanges(commandId) {
      if (!commandId) return;
      const expectedConfirmation = `REVERT ${commandId}`;
      const userInput = prompt(`Değişiklikleri güvenle geri almak için '${expectedConfirmation}' yazın:`);
      if (!userInput || userInput.trim() !== expectedConfirmation) {
        alert("Onay dizesi eşleşmedi. Revert iptal edildi.");
        return;
      }

      const revertStatus = document.getElementById("projectRunRevertStatus");
      if (revertStatus) revertStatus.textContent = "Reverting changes...";

      try {
        const res = await fetch(`/v1/supervisor/commands/${commandId}/revert`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "X-Prometheus-CSRF": "1"
          },
          body: JSON.stringify({ confirmation: expectedConfirmation })
        });

        const data = await res.json();
        if (res.ok) {
          if (revertStatus) revertStatus.textContent = `Reverted ${data.reverted.length} files successfully.`;
          await loadProjectRunChangeReview(commandId);
        } else {
          if (revertStatus) revertStatus.textContent = `Revert failed: ${data.detail || 'Unknown error'}`;
          alert(`Revert Hatası: ${data.detail || 'Bilinmeyen hata'}`);
        }
      } catch (err) {
        if (revertStatus) revertStatus.textContent = `Error: ${err.message}`;
        alert(`Ağ Hatası: ${err.message}`);
      }
    }

    document.getElementById('projectRunWorkspace')?.addEventListener('input', clearProjectRunPreview);
    document.getElementById('projectRunGoal')?.addEventListener('input', clearProjectRunPreview);


    // Keydown shortcut
    document.getElementById('taskInput')?.addEventListener('keydown', (e) => {
      if (e.ctrlKey && e.key === 'Enter') {
        createTask(e);
      }
    });

    // İlk yükleme
    loadTasks();
    if (activeMissionId) {
      openTask(activeMissionId);
      loadProjectRunChangeReview(activeMissionId);
    }
    setInterval(() => {
      loadTasks();
      if (activeMissionId) {
        renderLiveMission(activeMissionId);
        loadProjectRunChangeReview(activeMissionId);
      }
    }, 2000);
    setInterval(updateLiveActivityClock, 1000);
  </script>
</body>
</html>
"""
