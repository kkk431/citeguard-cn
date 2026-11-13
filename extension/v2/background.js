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
  await openSidePanel(tabId);
});
