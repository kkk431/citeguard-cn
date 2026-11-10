/* Word task pane: one claim + one evidence passage -> /api/support/check. */
(function () {
  var claimEl = document.getElementById("claim");
  var evidenceEl = document.getElementById("evidence");
  var btn = document.getElementById("check");
  var resultEl = document.getElementById("result");
  var badgeEl = document.getElementById("badge");
  var reasonEl = document.getElementById("reason");
  var metaEl = document.getElementById("meta");
  var errEl = document.getElementById("err");

  var LABELS = {
    support: "支持",
    partial: "部分支持",
    contradict: "矛盾",
    no_evidence: "无证据",
    insufficient: "证据不足"
  };

  function showError(msg) {
    errEl.hidden = false;
    errEl.textContent = msg;
  }

  function fillFromSelection() {
    if (!window.Office || !Office.context || !Office.context.document) { return; }
    Office.context.document.getSelectedDataAsync(Office.CoercionType.Text, function (r) {
      if (r.status === Office.AsyncResultStatus.Succeeded) {
        var text = String(r.value || "").trim();
        if (text) { claimEl.value = text.slice(0, 500); }
      }
    });
  }

  function check() {
    errEl.hidden = true;
    var claim = claimEl.value.trim();
    var evidence = evidenceEl.value.trim();
    if (!claim || !evidence) { showError("引用句和证据片段都要填。"); return; }
    btn.disabled = true;
    btn.textContent = "核验中…";
    fetch("/api/support/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim: claim, evidence: evidence })
    }).then(function (resp) {
      return resp.json().then(function (body) { return { ok: resp.ok, status: resp.status, body: body }; });
    }).then(function (r) {
      if (!r.ok || r.body.ok === false) {
        throw new Error(r.body.error || ("HTTP " + r.status));
      }
      var data = r.body;
      var label = data.label || "insufficient";
      badgeEl.className = "badge " + label;
      badgeEl.textContent = (LABELS[label] || label) +
        (typeof data.confidence === "number" ? " · " + Math.round(data.confidence * 100) + "%" : "");
      reasonEl.textContent = data.reason || "（模型没有给出理由）";
      var bits = [];
      if (data.audit && data.audit.fully_covered === false) { bits.push("覆盖审计：证据可能不完整"); }
      if (data.numeric && data.numeric.checked) { bits.push("数值一致性：" + (data.numeric.note || "已检查")); }
      if (data.prompt_version) { bits.push(data.prompt_version); }
      metaEl.textContent = bits.join(" · ");
      resultEl.hidden = false;
    }).catch(function (e) {
      showError("核验失败：" + e.message);
    }).then(function () {
      btn.disabled = false;
      btn.textContent = "核验这句话";
    });
  }

  btn.addEventListener("click", check);
  if (window.Office && Office.onReady) { Office.onReady(fillFromSelection); }
})();
