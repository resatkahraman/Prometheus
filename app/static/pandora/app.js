(() => {
  "use strict";

  const PROMETHEUS_CSRF_HEADER = "X-Prometheus-CSRF";
  const PROMETHEUS_CSRF_VALUE = "1";
  const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
  const CHAT_MESSAGE_MAX_CHARS = 4000;
  const CHAT_HISTORY_MAX_MESSAGES = 12;
  const CHAT_REQUEST_TIMEOUT_MS = 90000;
  const PROJECT_RUN_GOAL_MAX_CHARS = 2000;
  const PROJECT_RUN_REQUEST_TIMEOUT_MS = 60000;
  const PROJECT_RUN_REFRESH_MS = 5000;

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
    const projectRunCard = document.getElementById("project-run-card");
    const projectRunForm = document.getElementById("project-run-form");
    const projectRunWorkspace = document.getElementById("project-run-workspace");
    const projectRunGoal = document.getElementById("project-run-goal");
    const projectRunCounter = document.getElementById("project-run-counter");
    const projectRunPreviewButton = document.getElementById("project-run-preview-button");
    const projectRunFeedback = document.getElementById("project-run-feedback");
    const projectRunPreview = document.getElementById("project-run-preview");
    const projectRunPreviewMeta = document.getElementById("project-run-preview-meta");
    const projectRunPreviewTasks = document.getElementById("project-run-preview-tasks");
    const projectRunPreviewFiles = document.getElementById("project-run-preview-files");
    const projectRunCommitButton = document.getElementById("project-run-commit-button");
    const projectRunStatus = document.getElementById("project-run-status");
    const projectRunRefreshButton = document.getElementById("project-run-refresh-button");
    const projectRunStatusCopy = document.getElementById("project-run-status-copy");
    const projectRunProgress = document.getElementById("project-run-progress");
    const projectRunStatusTasks = document.getElementById("project-run-status-tasks");
    const navChat = document.getElementById("nav-chat");
    const navProjectRun = document.getElementById("nav-project-run");

    let refreshing = false;
    let sending = false;
    let previewing = false;
    let committing = false;
    let projectStatusRefreshing = false;
    let codeExpiryTimer = null;
    let projectRefreshTimer = null;
    let conversation = [];
    let authenticated = false;
    let activeView = "chat";
    let projectsLoaded = false;
    let projectRecoveryChecked = false;
    let currentPreview = null;
    let activeProjectRunId = null;
    let activeProjectRunTerminal = false;

    const setStatus = (message, state = "checking") => {
      if (statusNode) statusNode.textContent = message;
      if (statusCard) statusCard.dataset.state = state;
    };

    const clearNode = (node) => {
      if (!node) return;
      while (node.firstChild) node.removeChild(node.firstChild);
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

    const stopProjectRefresh = () => {
      if (projectRefreshTimer !== null) {
        window.clearTimeout(projectRefreshTimer);
        projectRefreshTimer = null;
      }
    };

    const scheduleProjectRefresh = () => {
      stopProjectRefresh();
      if (
        authenticated
        && activeView === "project-run"
        && activeProjectRunId
        && !activeProjectRunTerminal
        && document.visibilityState === "visible"
      ) {
        projectRefreshTimer = window.setTimeout(refreshProjectRunStatus, PROJECT_RUN_REFRESH_MS);
      }
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
        for (const item of conversation) appendChatMessage(item.role, item.content);
      }
      window.requestAnimationFrame(() => {
        chatMessages.scrollTop = chatMessages.scrollHeight;
      });
    };

    const updateChatCounter = () => {
      if (chatCounter && chatInput) {
        chatCounter.textContent = `${chatInput.value.length}/${CHAT_MESSAGE_MAX_CHARS}`;
      }
    };

    const updateProjectRunCounter = () => {
      if (projectRunCounter && projectRunGoal) {
        projectRunCounter.textContent = `${projectRunGoal.value.length}/${PROJECT_RUN_GOAL_MAX_CHARS}`;
      }
    };

    const updateControls = () => {
      const unavailable = !authenticated || !navigator.onLine;
      if (chatInput) chatInput.disabled = unavailable || sending;
      if (chatSubmit) chatSubmit.disabled = unavailable || sending;
      if (navProjectRun) navProjectRun.disabled = !authenticated;
      if (projectRunWorkspace) projectRunWorkspace.disabled = unavailable || previewing || committing;
      if (projectRunGoal) projectRunGoal.disabled = unavailable || previewing || committing;
      if (projectRunPreviewButton) projectRunPreviewButton.disabled = unavailable || previewing || committing;
      if (projectRunCommitButton) projectRunCommitButton.disabled = unavailable || previewing || committing || !currentPreview;
      if (projectRunRefreshButton) projectRunRefreshButton.disabled = unavailable || projectStatusRefreshing || !activeProjectRunId;
    };

    const clearConversation = () => {
      conversation = [];
      if (chatInput) chatInput.value = "";
      if (chatFeedback) chatFeedback.textContent = "";
      updateChatCounter();
      renderConversation();
    };

    const clearProjectRunState = () => {
      stopProjectRefresh();
      projectsLoaded = false;
      projectRecoveryChecked = false;
      currentPreview = null;
      activeProjectRunId = null;
      activeProjectRunTerminal = false;
      if (projectRunGoal) projectRunGoal.value = "";
      if (projectRunFeedback) projectRunFeedback.textContent = "";
      if (projectRunPreview) projectRunPreview.hidden = true;
      if (projectRunStatus) projectRunStatus.hidden = true;
      if (projectRunWorkspace) {
        clearNode(projectRunWorkspace);
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "Projeler yükleniyor...";
        projectRunWorkspace.appendChild(option);
      }
      clearNode(projectRunPreviewTasks);
      clearNode(projectRunPreviewFiles);
      clearNode(projectRunStatusTasks);
      updateProjectRunCounter();
    };

    const showView = (view) => {
      activeView = view === "project-run" ? "project-run" : "chat";
      if (chatCard) chatCard.hidden = !authenticated || activeView !== "chat";
      if (projectRunCard) projectRunCard.hidden = !authenticated || activeView !== "project-run";
      if (navChat) {
        navChat.classList.toggle("active", activeView === "chat");
        navChat.toggleAttribute("aria-current", activeView === "chat");
      }
      if (navProjectRun) {
        navProjectRun.classList.toggle("active", activeView === "project-run");
        navProjectRun.toggleAttribute("aria-current", activeView === "project-run");
      }
      if (activeView === "project-run" && authenticated) {
        loadProjects();
        if (activeProjectRunId) refreshProjectRunStatus();
      } else {
        stopProjectRefresh();
      }
    };

    const expireSession = async (message) => {
      authenticated = false;
      clearConversation();
      clearProjectRunState();
      showView("chat");
      if (projectRunFeedback) projectRunFeedback.textContent = message;
      await refreshStatus();
    };

    const renderStatus = (payload) => {
      if (pairingCard) pairingCard.hidden = false;
      hidePairingViews();

      const nextAuthenticated = (
        payload.authentication === "pandora"
        && payload.pandora_chat === "ready"
        && payload.pandora_project_run === "ready"
      );
      if (authenticated && !nextAuthenticated) {
        clearConversation();
        clearProjectRunState();
      }
      authenticated = nextAuthenticated;
      if (welcomeCard) welcomeCard.hidden = authenticated;
      showView(activeView);
      updateControls();

      if (payload.remote_access === "disabled") {
        setStatus("Prometheus yerel olarak bağlı", "connected");
        if (remoteDisabled) remoteDisabled.hidden = false;
        return;
      }
      if (payload.authentication === "pandora") {
        setStatus("Pandora sohbet ve görev aktarımına güvenli olarak bağlı", "connected");
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
        updateControls();
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
          authenticated = false;
          updateControls();
          setStatus("Kimlik doğrulama gerekli", "attention");
        } else if (response.status === 403) {
          authenticated = false;
          updateControls();
          setStatus("Uzak erişim kapalı", "attention");
        } else {
          setStatus("Prometheus erişilemiyor", "offline");
        }
      } catch (_error) {
        setStatus(navigator.onLine ? "Prometheus erişilemiyor" : "Cihaz çevrimdışı", "offline");
      } finally {
        refreshing = false;
        updateControls();
      }
    };

    const createPairingCode = async () => {
      if (!createCodeButton) return;
      createCodeButton.disabled = true;
      resetPairingCode("Kod oluşturuluyor...");
      try {
        const response = await prometheusFetch("/v1/pandora/pairing-code", { method: "POST" });
        const payload = await responsePayload(response);
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        const code = String(payload.code || "");
        const expiresIn = Number(payload.expires_in || 0);
        if (!/^\d{6}$/.test(code) || expiresIn <= 0) {
          throw new Error("Sunucu geçerli bir eşleştirme kodu döndürmedi.");
        }
        if (pairingCode) pairingCode.textContent = code;
        if (pairingCodeNote) pairingCodeNote.textContent = `Kod ${Math.ceil(expiresIn / 60)} dakika geçerli.`;
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
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        pairingCodeInput.value = "";
        if (pairingFeedback) pairingFeedback.textContent = "Cihaz güvenli olarak eşleştirildi.";
        await refreshStatus();
        if (chatInput && authenticated) chatInput.focus();
      } catch (error) {
        if (pairingFeedback) {
          pairingFeedback.textContent = error instanceof Error ? error.message : "Eşleştirme başarısız.";
        }
      } finally {
        pairingSubmit.disabled = false;
      }
    };

    const submitChat = async (event) => {
      event.preventDefault();
      if (!authenticated || sending || !chatInput || !chatSubmit) return;
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
      const history = conversation.slice(-CHAT_HISTORY_MAX_MESSAGES).map((item) => ({
        role: item.role,
        content: item.content,
      }));
      const previousLength = conversation.length;
      conversation.push({ role: "user", content: message });
      chatInput.value = "";
      updateChatCounter();
      renderConversation();
      sending = true;
      updateControls();
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
          await expireSession("Pandora oturumunun süresi doldu. Cihazı yeniden eşleştir.");
          return;
        }
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
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
            : error instanceof Error ? error.message : "Mesaj gönderilemedi.";
        }
        chatInput.value = message;
        updateChatCounter();
      } finally {
        window.clearTimeout(timeout);
        sending = false;
        updateControls();
        if (authenticated && chatInput) chatInput.focus();
      }
    };

    const loadProjects = async () => {
      if (!authenticated || projectsLoaded || !projectRunWorkspace) return;
      if (projectRunFeedback) projectRunFeedback.textContent = "Çalışma alanları yükleniyor...";
      try {
        const response = await prometheusFetch("/v1/pandora/projects");
        const payload = await responsePayload(response);
        if (response.status === 401) {
          await expireSession("Pandora oturumunun süresi doldu. Cihazı yeniden eşleştir.");
          return;
        }
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        clearNode(projectRunWorkspace);
        const projects = Array.isArray(payload.projects) ? payload.projects : [];
        if (projects.length === 0) {
          const option = document.createElement("option");
          option.value = ".";
          option.textContent = "Ana workspace (.)";
          projectRunWorkspace.appendChild(option);
        } else {
          for (const project of projects) {
            const option = document.createElement("option");
            option.value = String(project.workspace_path || ".");
            const name = String(project.name || project.workspace_path || "Workspace");
            const dirty = project.dirty ? " · değişiklik var" : "";
            option.textContent = `${name} (${option.value})${dirty}`;
            projectRunWorkspace.appendChild(option);
          }
        }
        projectsLoaded = true;
        await recoverLatestProjectRun();
        if (projectRunFeedback && !activeProjectRunId) {
          projectRunFeedback.textContent = payload.truncated
            ? "İlk güvenli çalışma alanları gösteriliyor."
            : "";
        }
      } catch (error) {
        if (projectRunFeedback) {
          projectRunFeedback.textContent = error instanceof Error ? error.message : "Çalışma alanları yüklenemedi.";
        }
      } finally {
        updateControls();
      }
    };

    const createTaskNode = (task, includeStatus = false) => {
      const article = document.createElement("article");
      article.className = "run-task";
      const title = document.createElement("strong");
      title.textContent = String(task.title || "Görev adımı");
      article.appendChild(title);
      const detail = document.createElement("p");
      if (includeStatus) {
        detail.textContent = `${Number(task.exact_file_count || 0)} exact file`;
      } else {
        const files = Array.isArray(task.exact_files) ? task.exact_files.length : 0;
        detail.textContent = `${files} exact file · ${String(task.verification || "Doğrulama belirtilmedi")}`;
      }
      article.appendChild(detail);
      if (includeStatus) {
        const status = document.createElement("span");
        status.className = "run-task-status";
        status.textContent = `${String(task.status || "bekliyor")} · ${String(task.approval_state || "idle")}`;
        article.appendChild(status);
      }
      return article;
    };

    const renderProjectRunPreview = (payload) => {
      currentPreview = payload;
      if (projectRunPreviewTasks) {
        clearNode(projectRunPreviewTasks);
        for (const task of Array.isArray(payload.tasks) ? payload.tasks : []) {
          projectRunPreviewTasks.appendChild(createTaskNode(task));
        }
      }
      if (projectRunPreviewFiles) {
        clearNode(projectRunPreviewFiles);
        for (const file of Array.isArray(payload.exact_files) ? payload.exact_files : []) {
          const item = document.createElement("li");
          item.textContent = String(file);
          projectRunPreviewFiles.appendChild(item);
        }
      }
      if (projectRunPreviewMeta) {
        const minutes = Math.max(1, Math.ceil(Number(payload.expires_in || 0) / 60));
        projectRunPreviewMeta.textContent = `${Number(payload.task_count || 0)} adım · ${Number(payload.exact_file_count || 0)} dosya · ${minutes} dk`;
      }
      if (projectRunPreview) projectRunPreview.hidden = false;
      if (projectRunStatus) projectRunStatus.hidden = true;
      updateControls();
    };

    const submitProjectRunPreview = async (event) => {
      event.preventDefault();
      if (!authenticated || previewing || committing || !projectRunGoal || !projectRunWorkspace) return;
      const goal = projectRunGoal.value.trim();
      const workspacePath = projectRunWorkspace.value || ".";
      if (goal.length < 3) {
        if (projectRunFeedback) projectRunFeedback.textContent = "En az 3 karakterli bir görev açıklaması yaz.";
        projectRunGoal.focus();
        return;
      }
      if (goal.length > PROJECT_RUN_GOAL_MAX_CHARS) {
        if (projectRunFeedback) projectRunFeedback.textContent = "Görev açıklaması 2000 karakteri aşamaz.";
        return;
      }
      previewing = true;
      currentPreview = null;
      if (projectRunPreview) projectRunPreview.hidden = true;
      if (projectRunFeedback) projectRunFeedback.textContent = "Yan etkisiz Project Run önizlemesi hazırlanıyor...";
      updateControls();
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), PROJECT_RUN_REQUEST_TIMEOUT_MS);
      try {
        const response = await prometheusFetch("/v1/pandora/project-run/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ goal, workspace_path: workspacePath }),
          signal: controller.signal,
        });
        const payload = await responsePayload(response);
        if (response.status === 401) {
          await expireSession("Pandora oturumunun süresi doldu. Cihazı yeniden eşleştir.");
          return;
        }
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        renderProjectRunPreview(payload);
        if (projectRunFeedback) projectRunFeedback.textContent = "Önizleme hazır. Kapsamı kontrol edip masaüstü onayına gönderebilirsin.";
      } catch (error) {
        if (projectRunFeedback) {
          projectRunFeedback.textContent = error instanceof DOMException && error.name === "AbortError"
            ? "Project Run önizleme süresi doldu. Yeniden deneyebilirsin."
            : error instanceof Error ? error.message : "Project Run önizlemesi hazırlanamadı.";
        }
      } finally {
        window.clearTimeout(timeout);
        previewing = false;
        updateControls();
      }
    };

    const commitProjectRun = async () => {
      if (!authenticated || committing || !currentPreview) return;
      committing = true;
      if (projectRunFeedback) projectRunFeedback.textContent = "Plan masaüstü onay kuyruğuna aktarılıyor...";
      updateControls();
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), PROJECT_RUN_REQUEST_TIMEOUT_MS);
      try {
        const response = await prometheusFetch("/v1/pandora/project-run/commit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            goal: currentPreview.goal,
            workspace_path: currentPreview.workspace_path,
            preview_digest: currentPreview.preview_digest,
          }),
          signal: controller.signal,
        });
        const payload = await responsePayload(response);
        if (response.status === 401) {
          await expireSession("Pandora oturumunun süresi doldu. Cihazı yeniden eşleştir.");
          return;
        }
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        activeProjectRunId = String(payload.command_id || "");
        if (!activeProjectRunId) throw new Error("Sunucu geçerli bir Project Run kimliği döndürmedi.");
        currentPreview = null;
        if (projectRunPreview) projectRunPreview.hidden = true;
        if (projectRunStatus) projectRunStatus.hidden = false;
        if (projectRunFeedback) projectRunFeedback.textContent = payload.created
          ? "Plan aktarıldı. Çalıştırma için masaüstü onayı bekleniyor."
          : "Mevcut plan yüklendi. Masaüstü onayı bekleniyor.";
        await refreshProjectRunStatus();
      } catch (error) {
        if (projectRunFeedback) {
          projectRunFeedback.textContent = error instanceof DOMException && error.name === "AbortError"
            ? "Project Run aktarım süresi doldu. Önizlemeyi yenileyip tekrar dene."
            : error instanceof Error ? error.message : "Project Run aktarılamadı.";
        }
      } finally {
        window.clearTimeout(timeout);
        committing = false;
        updateControls();
      }
    };

    const renderProjectRunStatus = (payload) => {
      activeProjectRunTerminal = Boolean(payload.terminal);
      if (projectRunStatus) projectRunStatus.hidden = false;
      if (projectRunStatusCopy) {
        const approvalCopy = payload.requires_desktop_approval
          ? "Masaüstü onayı bekleniyor."
          : payload.terminal ? "Project Run terminal duruma ulaştı." : "Project Run masaüstünde ilerliyor.";
        projectRunStatusCopy.textContent = `${String(payload.status || "bekliyor")} · ${Number(payload.completed_tasks || 0)}/${Number(payload.total_tasks || 0)} tamamlandı. ${approvalCopy}`;
      }
      if (projectRunProgress) {
        const percent = Math.max(0, Math.min(100, Number(payload.progress_percent || 0)));
        projectRunProgress.style.width = `${percent}%`;
      }
      if (projectRunStatusTasks) {
        clearNode(projectRunStatusTasks);
        for (const task of Array.isArray(payload.tasks) ? payload.tasks : []) {
          projectRunStatusTasks.appendChild(createTaskNode(task, true));
        }
      }
      scheduleProjectRefresh();
    };

    async function recoverLatestProjectRun() {
      if (!authenticated || projectRecoveryChecked || activeProjectRunId) return;
      projectRecoveryChecked = true;
      try {
        const response = await prometheusFetch("/v1/pandora/project-run/latest");
        const payload = await responsePayload(response);
        if (response.status === 404) return;
        if (response.status === 401) {
          await expireSession("Pandora oturumunun süresi doldu. Cihazı yeniden eşleştir.");
          return;
        }
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        activeProjectRunId = String(payload.command_id || "");
        if (!activeProjectRunId) return;
        renderProjectRunStatus(payload);
      } catch (error) {
        projectRecoveryChecked = false;
        if (projectRunFeedback) {
          projectRunFeedback.textContent = error instanceof Error
            ? error.message
            : "Son Project Run durumu alınamadı.";
        }
      }
    }

    async function refreshProjectRunStatus() {
      if (!authenticated || !activeProjectRunId || projectStatusRefreshing) return;
      projectStatusRefreshing = true;
      updateControls();
      try {
        const response = await prometheusFetch(`/v1/pandora/project-run/${encodeURIComponent(activeProjectRunId)}`);
        const payload = await responsePayload(response);
        if (response.status === 401) {
          await expireSession("Pandora oturumunun süresi doldu. Cihazı yeniden eşleştir.");
          return;
        }
        if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
        renderProjectRunStatus(payload);
      } catch (error) {
        if (projectRunStatusCopy) {
          projectRunStatusCopy.textContent = error instanceof Error ? error.message : "Project Run durumu alınamadı.";
        }
        scheduleProjectRefresh();
      } finally {
        projectStatusRefreshing = false;
        updateControls();
      }
    }

    const logoutPandora = async () => {
      if (!logoutButton) return;
      logoutButton.disabled = true;
      try {
        const response = await prometheusFetch("/v1/pandora/logout", { method: "POST" });
        if (!response.ok) {
          const payload = await responsePayload(response);
          throw new Error(payload.detail || `HTTP ${response.status}`);
        }
        clearConversation();
        clearProjectRunState();
        await refreshStatus();
      } catch (error) {
        setStatus(error instanceof Error ? error.message : "Oturum kapatılamadı.", "attention");
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
    if (projectRunGoal) projectRunGoal.addEventListener("input", updateProjectRunCounter);
    if (createCodeButton) createCodeButton.addEventListener("click", createPairingCode);
    if (pairingForm) pairingForm.addEventListener("submit", submitPairing);
    if (chatForm) chatForm.addEventListener("submit", submitChat);
    if (projectRunForm) projectRunForm.addEventListener("submit", submitProjectRunPreview);
    if (projectRunCommitButton) projectRunCommitButton.addEventListener("click", commitProjectRun);
    if (projectRunRefreshButton) projectRunRefreshButton.addEventListener("click", refreshProjectRunStatus);
    if (logoutButton) logoutButton.addEventListener("click", logoutPandora);
    if (navChat) navChat.addEventListener("click", () => showView("chat"));
    if (navProjectRun) navProjectRun.addEventListener("click", () => showView("project-run"));

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/pandora-sw.js", { scope: "/" }).catch(() => {});
    }

    window.addEventListener("online", () => {
      refreshStatus();
      if (activeView === "project-run") loadProjects();
    });
    window.addEventListener("offline", () => {
      stopProjectRefresh();
      setStatus("Cihaz çevrimdışı", "offline");
      updateControls();
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        refreshStatus();
        if (activeView === "project-run" && activeProjectRunId) refreshProjectRunStatus();
      } else {
        stopProjectRefresh();
      }
    });

    renderConversation();
    updateChatCounter();
    updateProjectRunCounter();
    updateControls();
    refreshStatus();
  });
})();
