chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "citeguard-check",
    title: "用引证卫士核验选中文字",
    contexts: ["selection"]
  });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== "citeguard-check" || !info.selectionText) return;
  await chrome.storage.local.set({ cg_claim: info.selectionText.trim().slice(0, 500) });
  try {
    await chrome.action.openPopup();
  } catch (e) {
    await chrome.action.setBadgeText({ text: "1" });
    await chrome.action.setBadgeBackgroundColor({ color: "#3ce6b4" });
  }
});
