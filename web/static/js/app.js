/* Shared helpers: toast + fetch wrappers. */
(function () {
  const toastEl = document.getElementById("toast");
  let toastTimer = null;

  function toast(message, ms) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.classList.remove("show");
    }, ms || 2600);
  }

  async function getJSON(url) {
    const resp = await fetch(url, { headers: { Accept: "application/json" } });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return resp.json();
  }

  async function postForm(url, formData) {
    const resp = await fetch(url, { method: "POST", body: formData });
    const data = await resp.json().catch(function () { return {}; });
    if (!resp.ok) throw new Error(data.detail || "HTTP " + resp.status);
    return data;
  }

  window.CiteGuard = { toast: toast, getJSON: getJSON, postForm: postForm };
})();
