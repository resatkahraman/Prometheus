(() => {
  "use strict";

  const PROMETHEUS_CSRF_HEADER = "X-Prometheus-CSRF";
  const PROMETHEUS_CSRF_VALUE = "prometheus-browser-ui";
  const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

  async function prometheusFetch(resource, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    if (!SAFE_METHODS.has(method)) {
      headers.set(PROMETHEUS_CSRF_HEADER, PROMETHEUS_CSRF_VALUE);
    }
    return fetch(resource, { ...options, method, headers });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const statusNode = document.getElementById("connection-status");
    let refreshing = false;

    const setStatus = (message) => {
      if (statusNode) statusNode.textContent = message;
    };

    const refreshStatus = async () => {
      if (refreshing) return;
      if (!navigator.onLine) {
        setStatus("Cihaz çevrimdışı");
        return;
      }
      refreshing = true;
      setStatus("Bağlantı kontrol ediliyor");
      try {
        const response = await prometheusFetch("/v1/pandora/status");
        if (response.status === 401) {
          setStatus("Kimlik doğrulama gerekli");
        } else if (response.ok) {
          setStatus("Prometheus bağlı");
        } else {
          setStatus("Prometheus erişilemiyor");
        }
      } catch (_error) {
        setStatus(navigator.onLine ? "Prometheus erişilemiyor" : "Cihaz çevrimdışı");
      } finally {
        refreshing = false;
      }
    };

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/pandora-sw.js", { scope: "/" }).catch(() => {});
    }

    window.addEventListener("online", refreshStatus);
    window.addEventListener("offline", () => setStatus("Cihaz çevrimdışı"));
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") refreshStatus();
    });
    refreshStatus();
  });
})();
