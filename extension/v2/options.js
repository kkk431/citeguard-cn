/* CiteGuard Live v2 — options page. */
"use strict";

const DEFAULT_ENDPOINT = "http://127.0.0.1:8013";
const ENDPOINT_KEY = "cg_live_endpoint";
const endpointEl = document.getElementById("endpoint");
const statusEl = document.getElementById("status");

function normalizeEndpoint(raw) {
  let value = String(raw || "").trim();
  if (!value) {
    value = DEFAULT_ENDPOINT;
  }
  const url = new URL(value);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("地址必须以 http:// 或 https:// 开头。");
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

function setStatus(message, kind) {
  statusEl.textContent = message;
  statusEl.className = `notice${kind ? ` status-${kind}` : ""}`;
}

async function load() {
  try {
    const stored = await chrome.storage.local.get(ENDPOINT_KEY);
    endpointEl.value = normalizeEndpoint(stored[ENDPOINT_KEY] || DEFAULT_ENDPOINT);
  } catch (error) {
    endpointEl.value = DEFAULT_ENDPOINT;
  }
}

async function save() {
  let normalized;
  try {
    normalized = normalizeEndpoint(endpointEl.value);
  } catch (error) {
    setStatus(error.message || "地址格式不正确。", "bad");
    return;
  }
  await chrome.storage.local.set({ [ENDPOINT_KEY]: normalized });
  endpointEl.value = normalized;
  setStatus(`已保存：${normalized}`, "ok");
}

async function testConnection() {
  let endpoint;
  try {
    endpoint = apiUrl(endpointEl.value);
  } catch (error) {
    setStatus(error.message || "地址格式不正确。", "bad");
    return;
  }
  setStatus("正在连接本地服务…");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ claim: "AI 能提升学习效果。", page_url: "", page_title: "CiteGuard Live 连接测试" }),
      signal: controller.signal,
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (error) {
      setStatus(`服务可达（HTTP ${response.status}），但返回的不是 JSON；地址可能指向了别的页面。`, "bad");
      return;
    }
    if (response.status === 200 && data && typeof data.label === "string") {
      setStatus(`连接成功：${endpoint} 返回 label=${data.label}。`, "ok");
    } else if (response.status === 404) {
      setStatus("服务可达，但没有 /api/live/check 路由；请确认服务版本或让服务端接入该路由。", "bad");
    } else if (response.status === 401) {
      setStatus("服务要求访问令牌（401）；请为 Live 接口放行，或关闭访问令牌。", "bad");
    } else {
      setStatus(`服务返回 HTTP ${response.status}：${(data && (data.error || data.detail)) || text.slice(0, 200)}`, "bad");
    }
  } catch (error) {
    if (error && error.name === "AbortError") {
      setStatus("连接超时（8 秒）。请确认本地服务已启动，并检查地址与端口。", "bad");
    } else {
      setStatus(`无法连接 ${endpoint}。请确认本地服务已启动，并检查地址与端口。`, "bad");
    }
  } finally {
    clearTimeout(timer);
  }
}

document.getElementById("save-btn").addEventListener("click", () => {
  save().catch((error) => setStatus(error.message || "保存失败。", "bad"));
});
document.getElementById("test-btn").addEventListener("click", () => {
  testConnection();
});
document.getElementById("reset-btn").addEventListener("click", () => {
  endpointEl.value = DEFAULT_ENDPOINT;
  save().catch((error) => setStatus(error.message || "保存失败。", "bad"));
});

load().catch(() => {
  endpointEl.value = DEFAULT_ENDPOINT;
});
