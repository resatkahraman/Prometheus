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
          <p>
            Bu cihaz Pandora metin sohbetine ve güvenli Project Run önizleme
            aktarımına yetkili. Kod çalıştırma ve dosya değişikliği için masaüstü
            Prometheus onayı zorunludur.
          </p>
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

      <section id="welcome-card" class="welcome-card" aria-labelledby="welcome-title">
        <div class="orb" aria-hidden="true"></div>
        <p class="eyebrow">Mobil çalışma alanı</p>
        <h2 id="welcome-title">Pandora bağlantı bekliyor</h2>
        <p>
          Güvenli cihaz eşleştirmesi tamamlandığında metin sohbeti ve Project Run
          önizleme aktarımı açılacak. Mobil oturum genel Prometheus API'sine veya
          doğrudan kod çalıştırmaya yetki vermez.
        </p>
        <button class="microphone" type="button" disabled aria-describedby="voice-note">
          <span aria-hidden="true">●</span>
          Mikrofon kapalı
        </button>
        <p id="voice-note" class="voice-note">Sesli görüşme, yerel ses motoru doğrulandıktan sonra açılacak.</p>
      </section>

      <section id="chat-card" class="chat-card app-view" aria-labelledby="chat-title" hidden>
        <header class="section-header">
          <div>
            <p class="eyebrow">Güvenli mobil sohbet</p>
            <h2 id="chat-title">Pandora metin sohbeti</h2>
          </div>
          <span class="scope-badge scope-chat">Sohbet-only</span>
        </header>

        <div
          id="chat-messages"
          class="chat-messages"
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          aria-label="Pandora konuşması"
        ></div>

        <form id="chat-form" class="chat-composer" novalidate>
          <label class="visually-hidden" for="chat-input">Pandora'ya mesaj yaz</label>
          <textarea
            id="chat-input"
            name="message"
            rows="2"
            maxlength="4000"
            enterkeyhint="send"
            autocomplete="off"
            placeholder="Pandora'ya yaz..."
            required
          ></textarea>
          <div class="composer-footer">
            <span id="chat-counter" class="counter" aria-live="off">0/4000</span>
            <button id="chat-submit" class="primary-action compact-action" type="submit">Gönder</button>
          </div>
          <p id="chat-feedback" class="support-note" role="status" aria-live="polite"></p>
        </form>

        <div class="voice-reserved" aria-label="Ses özelliği durumu">
          <button class="microphone" type="button" disabled aria-describedby="chat-voice-note">
            <span aria-hidden="true">●</span>
            Mikrofon kapalı
          </button>
          <p id="chat-voice-note" class="voice-note">Sesli görüşme bu görev kapsamında açılmadı.</p>
        </div>
      </section>

      <section id="project-run-card" class="project-run-card app-view" aria-labelledby="project-run-title" hidden>
        <header class="section-header">
          <div>
            <p class="eyebrow">Güvenli mobil görev aktarımı</p>
            <h2 id="project-run-title">Project Run</h2>
          </div>
          <span class="scope-badge scope-run">Masaüstü onaylı</span>
        </header>

        <div class="run-notice">
          <strong>Mobilde yalnız plan hazırlanır.</strong>
          <p>Önizleme dosya değiştirmez. Oluşturulan planın her adımı masaüstü Prometheus'ta ayrıca onaylanmadan çalışmaz.</p>
        </div>

        <form id="project-run-form" class="project-run-form" novalidate>
          <label for="project-run-workspace">Çalışma alanı</label>
          <select id="project-run-workspace" name="workspace_path" required>
            <option value="">Projeler yükleniyor...</option>
          </select>

          <label for="project-run-goal">Görev açıklaması</label>
          <textarea
            id="project-run-goal"
            name="goal"
            rows="5"
            minlength="3"
            maxlength="2000"
            autocomplete="off"
            placeholder="Örnek: app/main.py içindeki hata yanıtlarını düzenle ve ilgili testleri çalıştır."
            required
          ></textarea>
          <div class="composer-footer">
            <span id="project-run-counter" class="counter" aria-live="off">0/2000</span>
            <button id="project-run-preview-button" class="primary-action compact-action" type="submit">Güvenli önizleme</button>
          </div>
          <p id="project-run-feedback" class="support-note" role="status" aria-live="polite"></p>
        </form>

        <section id="project-run-preview" class="run-panel" aria-labelledby="project-run-preview-title" hidden>
          <div class="run-panel-heading">
            <div>
              <p class="eyebrow">Yan etkisiz plan</p>
              <h3 id="project-run-preview-title">Onay aktarımı önizlemesi</h3>
            </div>
            <span id="project-run-preview-meta" class="run-meta"></span>
          </div>
          <div id="project-run-preview-tasks" class="run-task-list"></div>
          <details class="run-files">
            <summary>Exact file kapsamı</summary>
            <ul id="project-run-preview-files"></ul>
          </details>
          <button id="project-run-commit-button" class="primary-action" type="button">
            Planı masaüstü onayına gönder
          </button>
          <p class="support-note">Bu düğme yürütmeyi başlatmaz ve hiçbir dosyayı değiştirmez.</p>
        </section>

        <section id="project-run-status" class="run-panel" aria-labelledby="project-run-status-title" hidden>
          <div class="run-panel-heading">
            <div>
              <p class="eyebrow">Aktarılan plan</p>
              <h3 id="project-run-status-title">Project Run durumu</h3>
            </div>
            <button id="project-run-refresh-button" class="secondary-action compact-action" type="button">Yenile</button>
          </div>
          <p id="project-run-status-copy" class="run-status-copy"></p>
          <div class="progress-track" aria-hidden="true"><span id="project-run-progress"></span></div>
          <div id="project-run-status-tasks" class="run-task-list"></div>
          <p class="support-note">Onay, çalıştırma, reddetme, yeniden deneme ve geri alma işlemleri masaüstü Prometheus'ta kalır.</p>
        </section>
      </section>
    </main>

    <nav class="bottom-nav" aria-label="Ana navigasyon">
      <button id="nav-chat" class="nav-item active" type="button" aria-current="page">
        <span>Sohbet</span><small>Metin hazır</small>
      </button>
      <button id="nav-project-run" class="nav-item" type="button" disabled>
        <span>Görevler</span><small>Onay aktarımı</small>
      </button>
      <span class="nav-item disabled" aria-disabled="true">
        <span>Ayarlar</span><small>Yakında</small>
      </span>
    </nav>
  </div>
</body>
</html>
"""
