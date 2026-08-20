/**
 * Shared helpers for login/register forms (vanilla JS — no Alpine dependency).
 */
(function () {
  function formatApiError(detail, fallback) {
    if (!detail) return fallback;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => (item && item.msg) || String(item))
        .filter(Boolean)
        .join(" ");
    }
    return fallback;
  }

  async function authFetch(url, body, timeoutMs) {
    const ms = timeoutMs || 30000;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ms);

    try {
      const response = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      let data = {};
      const text = await response.text();
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (_) {
          data = { detail: text.slice(0, 200) };
        }
      }

      return { response, data };
    } catch (err) {
      if (err && err.name === "AbortError") {
        throw new Error(
          "Request timed out. The server may be busy — please try again."
        );
      }
      throw new Error("Network error. Please check your connection.");
    } finally {
      clearTimeout(timer);
    }
  }

  function setLoading(form, loading) {
    const btn = form.querySelector("[type='submit']");
    const label = btn && btn.querySelector("[data-label]");
    const spinner = btn && btn.querySelector("[data-spinner]");
    if (btn) btn.disabled = loading;
    if (label) label.hidden = loading;
    if (spinner) spinner.hidden = !loading;
  }

  function showFieldError(form, field, message) {
    const el = form.querySelector(`[data-error-for="${field}"]`);
    if (el) {
      el.textContent = message || "";
      el.hidden = !message;
    }
  }

  function showGeneralError(form, message) {
    const box = form.querySelector("[data-error-general]");
    const text = form.querySelector("[data-error-general-text]");
    if (box && text) {
      text.textContent = message || "";
      box.hidden = !message;
    }
  }

  function clearErrors(form) {
    form.querySelectorAll("[data-error-for]").forEach((el) => {
      el.textContent = "";
      el.hidden = true;
    });
    showGeneralError(form, "");
  }

  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  window.DramValueAuth = {
    formatApiError,
    authFetch,
    setLoading,
    showFieldError,
    showGeneralError,
    clearErrors,
    isValidEmail,
  };
})();
