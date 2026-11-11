(function () {
  const $ = (id) => document.getElementById(id);
  const LABELS = {
    support: "支持", partial: "部分支持", contradict: "矛盾",
    no_evidence: "无证据", not_checked: "未核验",
  };
  const form = $("sp-form");
  const chip = $("sp-chip");
  const body = $("sp-body");
  const empty = $("sp-empty");

  function setText(id, value) { const el = $(id); if (el) el.textContent = value || ""; }

  function render(data) {
    empty.hidden = true;
    body.hidden = false;
    const label = data.label || "no_evidence";
    chip.className = "sp-chip " + label;
    chip.textContent = LABELS[label] || label;
    const conf = typeof data.confidence === "number" ? data.confidence : 0;
    setText("sp-conf", (conf * 100).toFixed(0) + "%");
    $("sp-meter").style.width = Math.max(0, Math.min(100, conf * 100)) + "%";
    setText("sp-reason", data.reason || "（模型未给出理由）");

    const quote = (data.evidence || "").trim();
    $("sp-quote").hidden = !quote;
    if (quote) setText("sp-quote-text", quote);

    const numeric = data.numeric || {};
    const notes = Array.isArray(numeric.notes) ? numeric.notes.filter(Boolean) : [];
    $("sp-numeric").hidden = notes.length === 0;
    if (notes.length) $("sp-numeric").textContent = "数字/方向提示：" + notes.join("；");

    const err = $("sp-err");
    err.hidden = true;
  }

  async function submit(event) {
    if (event) event.preventDefault();
    const claim = $("sp-claim").value.trim();
    const evidence = $("sp-evidence").value.trim();
    const err = $("sp-err");
    err.hidden = true;
    if (!claim || !evidence) {
      empty.hidden = false; body.hidden = true;
      empty.textContent = "引用句和证据片段都要填：只有证据才能判断这句话支不支持。";
      return;
    }
    const btn = $("sp-submit");
    btn.disabled = true;
    const hint = $("sp-hint");
    const old = hint.textContent;
    hint.textContent = "核验中…";
    try {
      const resp = await fetch("/api/support/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ claim, evidence }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.detail || data.message || ("HTTP " + resp.status));
      render(data);
    } catch (e) {
      empty.hidden = false; body.hidden = true;
      empty.textContent = "核验失败：" + (e.message || e);
    } finally {
      btn.disabled = false;
      hint.textContent = old;
    }
  }

  form.addEventListener("submit", submit);
  form.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") submit(e);
  });
  document.querySelectorAll(".sp-ex").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("sp-claim").value = btn.dataset.claim || "";
      $("sp-evidence").value = btn.dataset.evidence || "";
      $("sp-claim").focus();
    });
  });
})();
