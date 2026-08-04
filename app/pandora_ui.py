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
      <section class="status-card" aria-labelledby="connection-title" data-state="checking">
        <span class="status-indicator" aria-hidden="true"></span>
        <div>
          <h2 id="connection-title">Bağlantı durumu</h2>
          <p id="connection-status" role="status" aria-live="polite">Bağlantı kontrol ediliyor</p>
        </div>
      </section>

      <section id="pairing-card" class="pairing-card" aria-labelledby="pairing-title" hidden>
        <p class="eyebrow">Güvenli cihaz bağlantısı</p>
        <h2 id="pairing-title">Pandora eşleştirme</h2>

        <div id="pairing-admin" hidden>
          <p>
            Bu bilgisayarda tek kullanımlık bir kod oluştur. Kodu beş dakika
            içinde telefonundaki Pandora ekranına gir.
          </p>
          <button id="create-pairing-code" class="primary-action" type="button">
            Eşleştirme kodu oluştur
          </button>
          <output id="pairing-code" class="pairing-code" aria-live="polite">------</output>
          <p id="pairing-code-note" class="support-note">Kod henüz oluşturulmadı.</p>
        </div>

        <form id="pairing-form" novalidate hidden>
          <label for="pairing-code-input">6 haneli eşleştirme kodu</label>
          <input
            id="pairing-code-input"
            name="code"
            type="text"
            inputmode="numeric"
            autocomplete="one-time-code"
            pattern="[0-9]{6}"
            minlength="6"
            maxlength="6"
            placeholder="000000"
            required
          >
          <label for="device-name-input">Cihaz adı</label>
          <input
            id="device-name-input"
            name="device_name"
            type="text"
            autocomplete="off"
            maxlength="64"
            value="Pandora cihazı"
            required
          >
          <button id="pairing-submit" class="primary-action" type="submit">Bu cihazı bağla</button>
          <p id="pairing-feedback" class="support-note" role="status" aria-live="polite"></p>
        </form>

        <div id="paired-session" hidden>
          <p>Bu cihaz, sınırlı Pandora oturumuyla Prometheus'a bağlı.</p>
          <button id="pandora-logout" class="secondary-action" type="button">
            Bu cihazın bağlantısını kes
          </button>
        </div>

        <div id="prometheus-session" hidden>
          <p>Bu tarayıcı Prometheus yönetici kimliğiyle bağlı.</p>
        </div>

        <div id="remote-disabled" hidden>
          <p>
            Mobil eşleştirme için Prometheus uzak HTTP erişimini güvenli bir
            ağda etkinleştirmen gerekiyor.
          </p>
        </div>
      </section>

      <section class="welcome-card" aria-labelledby="welcome-title">
        <div class="orb" aria-hidden="true"></div>
        <p class="eyebrow">Mobil çalışma alanı</p>
        <h2 id="welcome-title">Pandora hazırlanıyor</h2>
        <p>
          Güvenli mobil bağlantı ve cihaz oturumu hazırlandı. Gerçek sohbet
          bir sonraki aşamada bu sınırlı Pandora oturumu üzerinden açılacak.
        </p>
        <button class="microphone" type="button" disabled aria-describedby="voice-note">
          <span aria-hidden="true">●</span>
          Mikrofon kapalı
        </button>
        <p id="voice-note" class="voice-note">Sesli görüşme, yerel ses motoru doğrulandıktan sonra açılacak.</p>
      </section>
    </main>

    <nav class="bottom-nav" aria-label="Ana navigasyon">
      <a class="nav-item active" href="/pandora" aria-current="page">
        <span>Sohbet</span><small>Hazırlanıyor</small>
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
