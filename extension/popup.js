const $ = (id) => document.getElementById(id);
const LABEL_TEXT = {
  support: "支持", partial: "部分支持", contradict: "矛盾",
  no_evidence: "无证据", not_checked: "未核验"
};

function endpointValue() {
  const raw = ($("endpoint").value || "").trim().replace(/\/+$/, "");
  return raw || "http://127.0.0.1:8010";
}

function updateCount() {
  $("claim-count").textContent = $("claim").value.length;
}

async function renderResult(data) {
  const label = data.label || "no_evidence";
  $("result").hidden = false;
  $("label").textContent = LABEL_TEXT[label] || label;
  $("label").className = label;
  $("confidence").textContent = data.confidence == null ? "" : `置信度 ${(Number(data.confidence) * 100).toFixed(0)}%`;
  $("reason").textContent = data.reason || "（模型未给出理由）";
  const quote = $("quote");
  if (data.evidence) { quote.hidden = false; quote.textContent = data.evidence; }
  else { quote.hidden = true; }
  const audit = $("audit");
  if (data.audit && typeof data.audit.fully_covered === "boolean") {
    audit.hidden = false;
    audit.textContent = data.audit.fully_covered ? "覆盖审计：全部要素已覆盖" : "覆盖审计：部分要素未覆盖（已按 partial 处理）";
  } else { audit.hidden = true; }
  $("error").hidden = true;
}

async function check() {
  const claim = $("claim").value.trim();
  const evidence = $("evidence").value.trim();
  const error = $("error");
  if (!claim || !evidence) {
    error.hidden = false;
    error.textContent = "引用句和证据片段都要填。";
    return;
  }
  $("check").disabled = true;
  $("check").textContent = "核验中…";
  try {
    const resp = await fetch(endpointValue() + "/api/support/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim, evidence })
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.ok === false) {
      throw new Error(data.error || `服务返回 ${resp.status}`);
    }
    await renderResult(data);
  } catch (err) {
    $("result").hidden = true;
    error.hidden = false;
    error.textContent = `核验失败：${err.message}。确认本地服务已启动（默认 8010）。`;
  } finally {
    $("check").disabled = false;
    $("check").textContent = "核验支持度";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const saved = await chrome.storage.local.get(["cg_endpoint", "cg_claim", "cg_evidence"]);
  $("endpoint").value = saved.cg_endpoint || "http://127.0.0.1:8010";
  if (saved.cg_claim) $("claim").value = saved.cg_claim;
  if (saved.cg_evidence) $("evidence").value = saved.cg_evidence;
  await chrome.storage.local.remove(["cg_claim"]);
  updateCount();
  $("claim").addEventListener("input", updateCount);
  $("endpoint").addEventListener("change", () => chrome.storage.local.set({ cg_endpoint: endpointValue() }));
  $("check").addEventListener("click", check);
});
