(() => {
  "use strict";

  const PROMETHEUS_CSRF_HEADER = "X-Prometheus-CSRF";
  const PROMETHEUS_CSRF_VALUE = "1";
  const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
  const CHAT_MESSAGE_MAX_CHARS = 4000;
  const CHAT_HISTORY_MAX_MESSAGES = 12;
  const CHAT_REQUEST_TIMEOUT_MS = 90000;

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
    const welcomeCard = document.getElementById("welcome-card");
    const chatCard = document.getElementById("chat-card");
    const chatMessages = document.getElementById("chat-messages");
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const chatSubmit = document.getElementById("chat-submit");
    const chatCounter = document.getElementById("chat-counter");
    const chatFeedback = document.getElementById("chat-feedback");

    let refreshing = false;
    let sending = false;
    let codeExpiryTimer = null;
    let conversation = [];
    let chatAuthenticated = false;

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

    const clearNode = (node) => {
      if (!node) return;
      while (node.firstChild) node.removeChild(node.firstChild);
    };

    const appendChatMessage = (role, content) => {
      if (!chatMessages) return;
      const article = document.createElement("article");
      article.className = "chat-message";
      article.dataset.role = role;

      const paragraph = document.createElement("p");
      paragraph.textContent = content;
      article.appendChild(paragraph);
      chatMessages.appendChild(article);
    };

    const renderConversation = () => {
      if (!chatMessages) return;
      clearNode(chatMessages);
      if (conversation.length === 0) {
        const empty = document.createElement("p");
        empty.className = "chat-empty";
        empty.textContent = "Pandora hazır. İlk mesajını yazarak güvenli metin sohbetini başlat.";
        chatMessages.appendChild(empty);
      } else {
        for (const item of conversation) {
          appendChatMessage(item.role, item.content);
        }
      }
      window.requestAnimationFrame(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
      });
    };

    const updateChatCounter = () => {
      if (!chatCounter || !chatInput) return;
      chatCounter.textContent = `${chatInput.value.length}/${CHAT_MESSAGE_MAX_CHARS}`;
    };

    const updateChatControls = () => {
      const disabled = !chatAuthenticated || sending || !navigator.onLine;
      if (chatInput) chatInput.disabled = disabled;
      if (chatSubmit) chatSubmit.disabled = disabled;
    };

    const clearConversation = () => {
      conversation = [];
      if (chatInput) chatInput.value = "";
      if (chatFeedback) chatFeedback.textContent = "";
      updateChatCounter();
      renderConversation();
    };

    const renderStatus = (payload) => {
      if (pairingCard) pairingCard.hidden = false;
      hidePairingViews();

      const nextChatAuthenticated = (
        payload.authentication === "pandora"
        && payload.pandora_chat === "ready"
      );
      if (chatAuthenticated && !nextChatAuthenticated) clearConversation();
      chatAuthenticated = nextChatAuthenticated;
      if (chatCard) chatCard.hidden = !chatAuthenticated;
      if (welcomeCard) welcomeCard.hidden = chatAuthenticated;
      updateChatControls();

      if (payload.remote_access === "disabled") {
        setStatus("Prometheus yerel olarak bağlı", "connected");
        if (remoteDisabled) remoteDisabled.hidden = false;
        return;
      }

      if (payload.authentication === "pandora") {
        setStatus("Pandora metin sohbetine güvenli olarak bağlı", "connected");
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
        updateChatControls();
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
          chatAuthenticated = false;
          updateChatControls();
          setStatus("Kimlik doğrulama gerekli", "attention");
        } else if (response.status === 403) {
          chatAuthenticated = false;
          updateChatControls();
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
        updateChatControls();
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
        if (chatInput && chatAuthenticated) chatInput.focus();
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

    const submitChat = async (event) => {
      event.preventDefault();
      if (!chatAuthenticated || sending || !chatInput || !chatSubmit) return;

      const message = chatInput.value.trim();
      if (!message) {
        if (chatFeedback) chatFeedback.textContent = "Göndermek için bir mesaj yaz.";
        chatInput.focus();
        return;
      }
      if (message.length > CHAT_MESSAGE_MAX_CHARS) {
        if (chatFeedback) chatFeedback.textContent = "Mesaj 4000 karakteri aşamaz.";
        return;
      }

      const history = conversation
        .slice(-CHAT_HISTORY_MAX_MESSAGES)
        .map((item) => ({ role: item.role, content: item.content }));
      const previousLength = conversation.length;
      conversation.push({ role: "user", content: message });
      chatInput.value = "";
      updateChatCounter();
      renderConversation();

      sending = true;
      updateChatControls();
      if (chatFeedback) chatFeedback.textContent = "Pandora düşünüyor...";

      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), CHAT_REQUEST_TIMEOUT_MS);
      try {
        const response = await prometheusFetch("/v1/pandora/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, history }),
          signal: controller.signal,
        });
        const payload = await responsePayload(response);

        if (response.status === 401) {
          conversation = conversation.slice(0, previousLength);
          renderConversation();
          if (chatFeedback) chatFeedback.textContent = "Pandora oturumunun süresi doldu. Cihazı yeniden eşleştir.";
          await refreshStatus();
          return;
        }
        if (!response.ok) {
          throw new Error(payload.detail || `HTTP ${response.status}`);
        }

        const answer = String(payload.answer || "").trim();
        if (!answer) throw new Error("Pandora boş bir yanıt döndürdü.");

        conversation.push({ role: "assistant", content: answer });
        if (conversation.length > CHAT_HISTORY_MAX_MESSAGES) {
          conversation = conversation.slice(-CHAT_HISTORY_MAX_MESSAGES);
        }
        renderConversation();
        if (chatFeedback) chatFeedback.textContent = "";
      } catch (error) {
        conversation = conversation.slice(0, previousLength);
        renderConversation();
        if (chatFeedback) {
          chatFeedback.textContent = error instanceof DOMException && error.name === "AbortError"
            ? "Pandora yanıt süresi doldu. Yeniden deneyebilirsin."
            : error instanceof Error
              ? error.message
              : "Mesaj gönderilemedi.";
        }
        chatInput.value = message;
        updateChatCounter();
      } finally {
        window.clearTimeout(timeout);
        sending = false;
        updateChatControls();
        if (chatAuthenticated && chatInput) chatInput.focus();
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
        clearConversation();
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
    if (chatInput) {
      chatInput.addEventListener("input", updateChatCounter);
      chatInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          if (chatForm) chatForm.requestSubmit();
        }
      });
    }
    if (createCodeButton) createCodeButton.addEventListener("click", createPairingCode);
    if (pairingForm) pairingForm.addEventListener("submit", submitPairing);
    if (chatForm) chatForm.addEventListener("submit", submitChat);
    if (logoutButton) logoutButton.addEventListener("click", logoutPandora);

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/pandora-sw.js", { scope: "/" }).catch(() => {});
    }

    window.addEventListener("online", refreshStatus);
    window.addEventListener("offline", () => {
      setStatus("Cihaz çevrimdışı", "offline");
      updateChatControls();
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") refreshStatus();
    });

    renderConversation();
    updateChatCounter();
    updateChatControls();
    refreshStatus();
  });
})();
