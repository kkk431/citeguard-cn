/* CiteGuard Live v2 — side panel UI.
 *
 * The panel is deliberately dependency-free and textContent-only: candidate
 * titles, abstracts and evidence quotes are untrusted data from third-party
 * metadata APIs, so they are never interpolated into HTML.
 */
"use strict";

const DEFAULT_ENDPOINT = "http://127.0.0.1:8013";
const ENDPOINT_KEY = "cg_live_endpoint";
const REQUEST_KEY = "cg_live_request";
const LABELS = {
  support: { zh: "支持", cls: "support", note: "候选摘要中的句子支持该引用句" },
  partial: { zh: "部分支持", cls: "partial", note: "关键词或数字只匹配一部分，不能当作完整支持" },
  contradict: { zh: "矛盾", cls: "contradict", note: "候选摘要的方向与引用句相反" },
  no_evidence: { zh: "无证据", cls: "no-evidence", note: "没有检索到可判断的摘要证据" },
};

const $ = (id) => document.getElementById(id);
const claimEl = $("claim");
const checkBtn = $("check-btn");
const retryBtn = $("retry-btn");
const charCount = $("char-count");
const endpointLine = $("endpoint-line");
const stateIds = ["state-idle", "state-loading", "state-error", "state-result"];

let currentEndpoint = DEFAULT_ENDPOINT;
let currentRequest = null;
let lastHandledId = "";
let inFlight = null;

function normalizeEndpoint(raw) {
  let value = String(raw || "").trim();
  if (!value) {
    value = DEFAULT_ENDPOINT;
  }
  const url = new URL(value);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("服务地址必须是 http:// 或 https://");
  }
  let path = url.pathname.replace(/\/+$/, "");
  if (path.endsWith("/api/live/check")) {
    path = path.slice(0, -"/api/live/check".length).replace(/\/+$/, "");
  }
  return `${url.origin}${path}`;
}

function apiUrl(base) {
  const normalized = normalizeEndpoint(base);
  return normalized.endsWith("/api/live/check")
    ? normalized
    : `${normalized}/api/live/check`;
}

function safeHttpUrl(raw) {
  if (!raw) {
    return "";
  }
  try {
    const url = new URL(String(raw));
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
  } catch (error) {
    return "";
  }
}

function doiUrl(doi) {
  const clean = String(doi || "").trim();
  if (!clean) {
    return "";
  }
  return safeHttpUrl(`https://doi.org/${clean}`);
}

function setState(name) {
  for (const id of stateIds) {
    const node = $(id);
    node.hidden = id !== name;
  }
}

function setBusy(busy) {
  checkBtn.disabled = busy;
  retryBtn.disabled = busy;
  checkBtn.textContent = busy ? "核验中…" : "核验这句话";
}

function updateCount() {
  charCount.textContent = `${claimEl.value.length} / 500`;
}

function showEndpoint() {
  endpointLine.textContent = `本地服务：${currentEndpoint}`;
  endpointLine.title = currentEndpoint;
}

async function loadSettings() {
  try {
    const stored = await chrome.storage.local.get(ENDPOINT_KEY);
    try {
      currentEndpoint = normalizeEndpoint(stored[ENDPOINT_KEY] || DEFAULT_ENDPOINT);
    } catch (error) {
      currentEndpoint = DEFAULT_ENDPOINT;
    }
  } catch (error) {
    currentEndpoint = DEFAULT_ENDPOINT;
  }
  showEndpoint();
}

async function loadRequest() {
  try {
    const stored = await chrome.storage.local.get(REQUEST_KEY);
    handleRequest(stored[REQUEST_KEY]);
  } catch (error) {
    // Storage is a convenience; typing a sentence still works.
  }
}

function handleRequest(request) {
  if (!request || !String(request.claim || "").trim()) {
    return;
  }
  const id = String(request.id || "");
  if (id && id === lastHandledId) {
    return;
  }
  lastHandledId = id;
  currentRequest = request;
  claimEl.value = String(request.claim).slice(0, 500);
  updateCount();
  runCheck(claimEl.value);
}

function labelInfo(label) {
  return LABELS[label] || LABELS.no_evidence;
}

function setBadge(label) {
  const info = labelInfo(label);
  const badge = $("label-badge");
  badge.textContent = `${info.zh} · ${label}`;
  badge.className = `badge ${info.cls}`;
  badge.title = info.note;
}

function appendText(parent, tag, text, className) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  node.textContent = text;
  parent.appendChild(node);
  return node;
}

function renderEvidence(evidence) {
  const box = $("evidence-box");
  const note = $("no-evidence-note");
  const quote = evidence && String(evidence.quote || "").trim();
  if (!quote) {
    box.hidden = true;
    note.hidden = false;
    return;
  }
  note.hidden = true;
  box.hidden = false;
  $("evidence-quote").textContent = quote;
  const link = $("evidence-link");
  const title = String(evidence.title || "候选来源");
  link.textContent = title;
  const href = safeHttpUrl(evidence.url);
  if (href) {
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer noopener";
    link.hidden = false;
  } else {
    link.removeAttribute("href");
    link.hidden = false;
  }
  $("evidence-meta").textContent = evidence.url ? "在摘要中逐字核对" : "来源链接缺失，请按标题检索";
}

function renderCandidate(candidate) {
  const item = document.createElement("details");
  item.className = "candidate";

  const summary = document.createElement("summary");
  appendText(summary, "span", String(candidate.title || "（无标题）"), "candidate-title");
  const metaParts = [
    candidate.year ? String(candidate.year) : "",
    String(candidate.venue || ""),
    String(candidate.source || ""),
  ].filter(Boolean);
  if (metaParts.length) {
    appendText(summary, "span", metaParts.join(" · "), "candidate-meta");
  }
  item.appendChild(summary);

  const body = document.createElement("div");
  body.className = "candidate-body";
  if (candidate.label) {
    const info = labelInfo(candidate.label);
    const score = Number(candidate.confidence);
    const text = `${info.zh} · ${candidate.label}${Number.isFinite(score) ? `（${Math.round(score * 100)}%）` : ""}`;
    appendText(body, "p", text, "candidate-verdict");
  }
  if (Array.isArray(candidate.authors) && candidate.authors.length) {
    appendText(body, "p", candidate.authors.join("、"), "hint");
  }
  if (candidate.abstract) {
    appendText(body, "p", String(candidate.abstract), "candidate-abstract");
  }
  const links = document.createElement("p");
  links.className = "candidate-links";
  const url = safeHttpUrl(candidate.url) || doiUrl(candidate.doi);
  if (url) {
    const link = document.createElement("a");
    link.href = url;
    link.target = "_blank";
    link.rel = "noreferrer noopener";
    link.textContent = "打开来源";
    links.appendChild(link);
  }
  if (candidate.doi) {
    const doiLink = document.createElement("a");
    doiLink.href = doiUrl(candidate.doi);
    doiLink.target = "_blank";
    doiLink.rel = "noreferrer noopener";
    doiLink.textContent = `DOI: ${candidate.doi}`;
    links.appendChild(doiLink);
  }
  if (links.childNodes.length) {
    body.appendChild(links);
  }
  item.appendChild(body);
  return item;
}

function renderCandidates(candidates) {
  const list = $("candidate-list");
  list.replaceChildren();
  const items = Array.isArray(candidates) ? candidates : [];
  $("candidate-count").textContent = `（${items.length}）`;
  if (!items.length) {
    appendText(list, "p", "没有候选文献。可能原因：网络不可用、主题过窄，或服务处于离线模式。", "notice");
    return;
  }
  for (const candidate of items.slice(0, 5)) {
    list.appendChild(renderCandidate(candidate || {}));
  }
}

function renderResult(data) {
  const label = LABELS[data.label] ? data.label : "no_evidence";
  setBadge(label);
  const confidence = Number(data.confidence);
  $("confidence").textContent = Number.isFinite(confidence)
    ? `置信度 ${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%`
    : "置信度 —";
  $("reason").textContent = String(data.reason || labelInfo(label).note);
  renderEvidence(data.evidence);
  renderCandidates(data.candidates);
  setState("state-result");
}

function friendlyStatus(status) {
  if (status === 400) return "请求无效：引用句为空、过长或字段格式不对。";
  if (status === 401) return "本地服务要求访问令牌；扩展尚未配置令牌，请在服务端为 Live 接口放行或关闭访问令牌。";
  if (status === 404) return "本地服务没有 /api/live/check 路由，请确认服务版本与端口是否正确。";
  if (status === 429) return "请求过于频繁，请稍后再试。";
  if (status === 500) return "本地服务内部错误，请查看服务端日志。";
  if (status === 503) return "本地服务当前不可用（可能处于离线模式或正在启动）。";
  return `本地服务返回 HTTP ${status}。`;
}

function showError(message, detail) {
  $("error-msg").textContent = message;
  const details = $("error-details");
  if (detail) {
    $("error-detail").textContent = String(detail);
    details.hidden = false;
  } else {
    $("error-detail").textContent = "";
    details.hidden = true;
  }
  setState("state-error");
}

async function runCheck(rawClaim) {
  const claim = String(rawClaim || "").trim();
  if (!claim) {
    showError("请先在网页上选中一句话，或在输入框里粘贴一句话。", "");
    return;
  }
  if (inFlight) {
    inFlight.abort();
  }
  setBusy(true);
  setState("state-loading");

  const controller = new AbortController();
  inFlight = controller;
  const timer = setTimeout(() => controller.abort(), 15000);
  const payload = {
    claim,
    page_url: (currentRequest && currentRequest.pageUrl) || "",
    page_title: (currentRequest && currentRequest.pageTitle) || "",
  };

  try {
    const response = await fetch(apiUrl(currentEndpoint), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (error) {
      throw new Error("本地服务返回的不是 JSON，可能地址指向了别的页面。");
    }
    if (!response.ok) {
      throw new Error(friendlyStatus(response.status));
    }
    if (!data || typeof data !== "object" || !LABELS[data.label]) {
      throw new Error("本地服务返回的数据缺少有效的 label 字段。");
    }
    renderResult(data);
  } catch (error) {
    if (inFlight !== controller) {
      // A newer check superseded this one; its UI owns the panel now.
      return;
    }
    if (error && error.name === "AbortError") {
      showError("请求超时（15 秒）。请确认本地服务已启动，或在“设置”里检查地址。", "");
    } else if (error instanceof TypeError) {
      showError(
        `无法连接本地服务（${currentEndpoint}）。请确认服务已启动，并在“设置”里检查地址。`,
        error.message
      );
    } else {
      showError(error && error.message ? error.message : "核验失败。", "");
    }
  } finally {
    clearTimeout(timer);
    if (inFlight === controller) {
      inFlight = null;
      setBusy(false);
    }
  }
}

checkBtn.addEventListener("click", () => runCheck(claimEl.value));
retryBtn.addEventListener("click", () => runCheck(claimEl.value || (currentRequest && currentRequest.claim)));
claimEl.addEventListener("input", updateCount);
claimEl.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    runCheck(claimEl.value);
  }
});
$("open-options").addEventListener("click", () => {
  if (chrome.runtime.openOptionsPage) {
    chrome.runtime.openOptionsPage();
  }
});

chrome.runtime.onMessage.addListener((message) => {
  if (message && message.type === "citeguard-live-request") {
    handleRequest(message.request);
  }
});

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") {
    return;
  }
  if (changes[ENDPOINT_KEY]) {
    try {
      currentEndpoint = normalizeEndpoint(changes[ENDPOINT_KEY].newValue || DEFAULT_ENDPOINT);
    } catch (error) {
      currentEndpoint = DEFAULT_ENDPOINT;
    }
    showEndpoint();
  }
  if (changes[REQUEST_KEY] && changes[REQUEST_KEY].newValue) {
    handleRequest(changes[REQUEST_KEY].newValue);
  }
});

updateCount();
setState("state-idle");
loadSettings().then(loadRequest);
