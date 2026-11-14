/* CiteGuard Live v2 — MV3 service worker.
 *
 * Two entry points:
 *   - right-click a selection → store it and open the side panel
 *   - click the toolbar action → open the side panel
 *
 * No network request is made here; the side panel owns the call to the local
 * service so the user can see and retry it.
 */
"use strict";

const MENU_ID = "citeguard-live-check";
const REQUEST_KEY = "cg_live_request";
const ENDPOINT_KEY = "cg_live_endpoint";
const DEFAULT_ENDPOINT = "http://127.0.0.1:8013";

function liveBase(raw) {
  let value = String(raw || "").trim() || DEFAULT_ENDPOINT;
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return DEFAULT_ENDPOINT;
    }
    let path = url.pathname.replace(/\/+$/, "");
    if (path.endsWith("/api/live/check")) {
      path = path.slice(0, -"/api/live/check".length).replace(/\/+$/, "");
    }
    return `${url.origin}${path}`;
  } catch (error) {
    return DEFAULT_ENDPOINT;
  }
}

/* Start the expensive arXiv HTML / OpenAlex reference fetch while the side
 * panel is still opening.  The first selected sentence then starts from a warm
 * page cache.  Failures are silent: Live still works without prewarming. */
async function prewarmPage(tab) {
  if (!tab || !tab.url) {
    return;
  }
  let base = DEFAULT_ENDPOINT;
  try {
    const stored = await chrome.storage.local.get(ENDPOINT_KEY);
    base = liveBase(stored[ENDPOINT_KEY]);
  } catch (error) {
    /* storage is optional */
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try {
    await fetch(`${base}/api/live/prewarm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_url: String(tab.url || "").slice(0, 2048),
        page_title: String(tab.title || "").slice(0, 300),
      }),
      signal: controller.signal,
    });
  } catch (error) {
    /* prewarm is best effort */
  } finally {
    clearTimeout(timer);
  }
}

function installMenu() {
  chrome.contextMenus.removeAll(() => {
    // Reading lastError avoids noisy "duplicate id" errors on reload.
    void chrome.runtime.lastError;
    chrome.contextMenus.create(
      {
        id: MENU_ID,
        title: "用 CiteGuard Live 核验选中句",
        contexts: ["selection"],
      },
      () => void chrome.runtime.lastError
    );
  });
}

function enableActionToOpenPanel() {
  if (!chrome.sidePanel || typeof chrome.sidePanel.setPanelBehavior !== "function") {
    return;
  }
  try {
    const pending = chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
    if (pending && typeof pending.catch === "function") {
      pending.catch(() => {
        /* Older builds may not support this; the action click handler still works. */
      });
    }
  } catch (error) {
    /* Keep the action-click fallback usable. */
  }
}

chrome.runtime.onInstalled.addListener(() => {
  installMenu();
  enableActionToOpenPanel();
});

chrome.runtime.onStartup.addListener(() => {
  installMenu();
});

async function openSidePanel(tabId) {
  if (chrome.sidePanel && typeof chrome.sidePanel.open === "function") {
    try {
      await chrome.sidePanel.open({ tabId });
      return;
    } catch (error) {
      console.warn("CiteGuard Live: sidePanel.open failed", error);
    }
  }
  // Fallback for browsers without the side panel API: a normal extension tab
  // still renders the same UI.
  if (tabId && chrome.tabs && typeof chrome.tabs.create === "function") {
    try {
      await chrome.tabs.create({ url: chrome.runtime.getURL("sidepanel.html") });
    } catch (error) {
      console.warn("CiteGuard Live: could not open fallback tab", error);
    }
  }
}

function broadcastRequest(request) {
  // The panel may not be open yet; storage is the durable hand-off. This
  // message is a best-effort live update when it already exists.
  chrome.runtime.sendMessage({ type: "citeguard-live-request", request }, () => {
    void chrome.runtime.lastError;
  });
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID) {
    return;
  }
  const claim = String(info.selectionText || "").trim();
  if (!claim) {
    return;
  }
  const request = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    claim,
    pageUrl: (tab && tab.url) || info.pageUrl || "",
    pageTitle: (tab && tab.title) || "",
    createdAt: new Date().toISOString(),
  };
  const tabId = tab && typeof tab.id === "number" ? tab.id : undefined;
  // sidePanel.open must run in the user-gesture task; do not wait for storage
  // first. The panel reads the request from storage / the broadcast below.
  const opening = openSidePanel(tabId);
  void prewarmPage(tab);
  try {
    await chrome.storage.local.set({ [REQUEST_KEY]: request });
  } catch (error) {
    console.warn("CiteGuard Live: could not store selection", error);
  }
  await opening;
  broadcastRequest(request);
});

chrome.action.onClicked.addListener(async (tab) => {
  const tabId = tab && typeof tab.id === "number" ? tab.id : undefined;
  void prewarmPage(tab);
  await openSidePanel(tabId);
});
