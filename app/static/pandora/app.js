(() => {
  "use strict";

  const PROMETHEUS_CSRF_HEADER = "X-Prometheus-CSRF";
  const PROMETHEUS_CSRF_VALUE = "1";
  const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

  async function prometheusFetch(resource, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    if (!SAFE_METHODS.has(method)) {
      headers.set(PROMETHEUS_CSRF_HEADER, PROMETHEUS_CSRF_VALUE);
    }
    return fetch(resource, {
      ...options,
      method,
      headers,
      credentials: "same-origin",
    });
  }

  async function responsePayload(response) {
    try {
      return await response.json();
    } catch (_error) {
      return {};
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const statusCard = document.querySelector(".status-card");
    const statusNode = document.getElementById("connection-status");
    const pairingCard = document.getElementById("pairing-card");
    const pairingAdmin = document.getElementById("pairing-admin");
    const pairingForm = document.getElementById("pairing-form");
    const pairedSession = document.getElementById("paired-session");
    const prometheusSession = document.getElementById("prometheus-session");
    const remoteDisabled = document.getElementById("remote-disabled");
    const createCodeButton = document.getElementById("create-pairing-code");
    const pairingCode = document.getElementById("pairing-code");
    const pairingCodeNote = document.getElementById("pairing-code-note");
    const pairingCodeInput = document.getElementById("pairing-code-input");
    const deviceNameInput = document.getElementById("device-name-input");
    const pairingSubmit = document.getElementById("pairing-submit");
    const pairingFeedback = document.getElementById("pairing-feedback");
    const logoutButton = document.getElementById("pandora-logout");

    let refreshing = false;
    let codeExpiryTimer = null;

    const setStatus = (message, state = "checking") => {
      if (statusNode) statusNode.textContent = message;
      if (statusCard) statusCard.dataset.state = state;
    };

    const hidePairingViews = () => {
      for (const node of [
        pairingAdmin,
        pairingForm,
        pairedSession,
        prometheusSession,
        remoteDisabled,
      ]) {
        if (node) node.hidden = true;
      }
    };

    const resetPairingCode = (message = "Kod henüz oluşturulmadı.") => {
      if (pairingCode) pairingCode.textContent = "------";
      if (pairingCodeNote) pairingCodeNote.textContent = message;
      if (codeExpiryTimer !== null) {
        window.clearTimeout(codeExpiryTimer);
        codeExpiryTimer = null;
      }
    };

    const renderStatus = (payload) => {
      if (pairingCard) pairingCard.hidden = false;
      hidePairingViews();

      if (payload.remote_access === "disabled") {
        setStatus("Prometheus yerel olarak bağlı", "connected");
        if (remoteDisabled) remoteDisabled.hidden = false;
        return;
      }

      if (payload.authentication === "pandora") {
        setStatus("Pandora güvenli olarak bağlı", "connected");
        if (pairedSession) pairedSession.hidden = false;
        return;
      }

      if (payload.pairing_code_allowed) {
        setStatus("Yerel eşleştirme hazır", "connected");
        if (pairingAdmin) pairingAdmin.hidden = false;
        return;
      }

      if (payload.authentication === "prometheus") {
        setStatus("Prometheus yönetici bağlantısı etkin", "connected");
        if (prometheusSession) prometheusSession.hidden = false;
        return;
      }

      setStatus("Cihaz eşleştirmesi gerekli", "attention");
      if (pairingForm) pairingForm.hidden = false;
    };

    const refreshStatus = async () => {
      if (refreshing) return;
      if (!navigator.onLine) {
        setStatus("Cihaz çevrimdışı", "offline");
        return;
      }

      refreshing = true;
      setStatus("Bağlantı kontrol ediliyor", "checking");
      try {
        const response = await prometheusFetch("/v1/pandora/status");
        const payload = await responsePayload(response);
        if (response.ok) {
          renderStatus(payload);
        } else if (response.status === 401) {
          setStatus("Kimlik doğrulama gerekli", "attention");
        } else if (response.status === 403) {
          setStatus("Uzak erişim kapalı", "attention");
        } else {
          setStatus("Prometheus erişilemiyor", "offline");
        }
      } catch (_error) {
        setStatus(
          navigator.onLine ? "Prometheus erişilemiyor" : "Cihaz çevrimdışı",
          "offline"
        );
      } finally {
        refreshing = false;
      }
    };

    const createPairingCode = async () => {
      if (!createCodeButton) return;
      createCodeButton.disabled = true;
      resetPairingCode("Kod oluşturuluyor...");
      try {
        const response = await prometheusFetch("/v1/pandora/pairing-code", {
          method: "POST",
        });
        const payload = await responsePayload(response);
        if (!response.ok) {
          throw new Error(payload.detail || `HTTP ${response.status}`);
        }

        const code = String(payload.code || "");
        const expiresIn = Number(payload.expires_in || 0);
        if (!/^\d{6}$/.test(code) || expiresIn <= 0) {
          throw new Error("Sunucu geçerli bir eşleştirme kodu döndürmedi.");
        }

        if (pairingCode) pairingCode.textContent = code;
        if (pairingCodeNote) {
          pairingCodeNote.textContent = `Kod ${Math.ceil(expiresIn / 60)} dakika geçerli.`;
        }
        codeExpiryTimer = window.setTimeout(() => {
          resetPairingCode("Kodun süresi doldu. Yeni bir kod oluştur.");
        }, expiresIn * 1000);
      } catch (error) {
        resetPairingCode(error instanceof Error ? error.message : "Kod oluşturulamadı.");
      } finally {
        createCodeButton.disabled = false;
      }
    };

    const submitPairing = async (event) => {
      event.preventDefault();
      if (!pairingCodeInput || !deviceNameInput || !pairingSubmit) return;

      const code = pairingCodeInput.value.replace(/\D/g, "").slice(0, 6);
      const deviceName = deviceNameInput.value.trim() || "Pandora cihazı";
      pairingCodeInput.value = code;
      if (code.length !== 6) {
        if (pairingFeedback) pairingFeedback.textContent = "6 haneli kodu eksiksiz gir.";
        pairingCodeInput.focus();
        return;
      }

      pairingSubmit.disabled = true;
      if (pairingFeedback) pairingFeedback.textContent = "Cihaz eşleştiriliyor...";
      try {
        const response = await prometheusFetch("/v1/pandora/pair", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, device_name: deviceName }),
        });
        const payload = await responsePayload(response);
        if (!response.ok) {
          throw new Error(payload.detail || `HTTP ${response.status}`);
        }
        pairingCodeInput.value = "";
        if (pairingFeedback) pairingFeedback.textContent = "Cihaz güvenli olarak eşleştirildi.";
        await refreshStatus();
      } catch (error) {
        if (pairingFeedback) {
          pairingFeedback.textContent = error instanceof Error
            ? error.message
            : "Eşleştirme başarısız.";
        }
      } finally {
        pairingSubmit.disabled = false;
      }
    };

    const logoutPandora = async () => {
      if (!logoutButton) return;
      logoutButton.disabled = true;
      try {
        const response = await prometheusFetch("/v1/pandora/logout", {
          method: "POST",
        });
        if (!response.ok) {
          const payload = await responsePayload(response);
          throw new Error(payload.detail || `HTTP ${response.status}`);
        }
        await refreshStatus();
      } catch (error) {
        setStatus(
          error instanceof Error ? error.message : "Oturum kapatılamadı.",
          "attention"
        );
      } finally {
        logoutButton.disabled = false;
      }
    };

    if (pairingCodeInput) {
      pairingCodeInput.addEventListener("input", () => {
        pairingCodeInput.value = pairingCodeInput.value.replace(/\D/g, "").slice(0, 6);
      });
    }
    if (createCodeButton) createCodeButton.addEventListener("click", createPairingCode);
    if (pairingForm) pairingForm.addEventListener("submit", submitPairing);
    if (logoutButton) logoutButton.addEventListener("click", logoutPandora);

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/pandora-sw.js", { scope: "/" }).catch(() => {});
    }

    window.addEventListener("online", refreshStatus);
    window.addEventListener("offline", () => setStatus("Cihaz çevrimdışı", "offline"));
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") refreshStatus();
    });
    refreshStatus();
  });
})();
