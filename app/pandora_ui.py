PANDORA_UI = """<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#090b12">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="Pandora">
  <title>Pandora</title>
  <link rel="manifest" href="/static/pandora/manifest.webmanifest">
  <link rel="icon" href="/static/pandora/icon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/static/pandora/app.css">
  <script src="/static/pandora/app.js" defer></script>
</head>
<body>
  <div class="app-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">Prometheus Mobile Assistant</p>
        <h1>Pandora</h1>
      </div>
      <span class="shell-badge">PWA</span>
    </header>

    <main>
      <section class="status-card" aria-labelledby="connection-title">
        <span class="status-indicator" aria-hidden="true"></span>
        <div>
          <h2 id="connection-title">Bağlantı durumu</h2>
          <p id="connection-status" role="status" aria-live="polite">Bağlantı kontrol ediliyor</p>
        </div>
      </section>

      <section class="welcome-card" aria-labelledby="welcome-title">
        <div class="orb" aria-hidden="true"></div>
        <p class="eyebrow">Mobil çalışma alanı</p>
        <h2 id="welcome-title">Pandora hazırlanıyor</h2>
        <p>Prometheus ile güvenli mobil bağlantının temel uygulama kabuğu hazır.</p>
        <button class="microphone" type="button" disabled aria-describedby="voice-note">
          <span aria-hidden="true">●</span>
          Mikrofon kapalı
        </button>
        <p id="voice-note" class="voice-note">Sesli görüşme, yerel ses motoru doğrulandıktan sonra açılacak.</p>
      </section>
    </main>

    <nav class="bottom-nav" aria-label="Ana navigasyon">
      <a class="nav-item active" href="/pandora" aria-current="page">
        <span>Sohbet</span>
      </a>
      <span class="nav-item disabled" aria-disabled="true">
        <span>Görevler</span><small>Yakında</small>
      </span>
      <span class="nav-item disabled" aria-disabled="true">
        <span>Ayarlar</span><small>Yakında</small>
      </span>
    </nav>
  </div>
</body>
</html>
"""
