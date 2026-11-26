/* Shared helpers: motion preference, toast, skeletons, overlays, command palette, fetch. */
(function () {
  "use strict";

  /* ---- motion preference (G4) ------------------------------------------ */
  var motionQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  function prefersReducedMotion() {
    return Boolean(motionQuery && motionQuery.matches);
  }
  function syncMotionPreference() {
    var reduced = prefersReducedMotion();
    document.documentElement.setAttribute("data-motion", reduced ? "reduced" : "full");
    document.documentElement.classList.toggle("cg-reduced", reduced);
    return reduced;
  }
  syncMotionPreference();
  if (motionQuery) {
    if (motionQuery.addEventListener) motionQuery.addEventListener("change", syncMotionPreference);
    else if (motionQuery.addListener) motionQuery.addListener(syncMotionPreference);
  }
  document.documentElement.classList.add("cg-js");

  function pageBoot() {
    if (!document.body) return;
    document.body.classList.add("cg-boot");
    requestAnimationFrame(function () { document.body.classList.add("cg-ready"); });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", pageBoot);
  else pageBoot();

  /* ---- toast (queue, variants, close button) ---------------------------- */
  var toastEl = document.getElementById("toast");
  var toastTimer = null;
  var toastCurrent = null;
  var toastQueue = [];

  function ensureToastDom() {
    if (!toastEl) return null;
    if (!toastEl.querySelector(".toast-msg")) {
      toastEl.innerHTML = '<span class="toast-ico" aria-hidden="true"></span>' +
        '<span class="toast-msg"></span>' +
        '<button type="button" class="toast-x" aria-label="关闭提示">×</button>';
      toastEl.querySelector(".toast-x").addEventListener("click", dismissToast);
    }
    return toastEl;
  }

  function paintToast(entry) {
    var el = ensureToastDom();
    if (!el) return;
    var msg = el.querySelector(".toast-msg");
    msg.textContent = entry.message;
    el.classList.remove("toast--success", "toast--error", "toast--info");
    el.classList.add("toast--" + entry.type);
    el.setAttribute("role", entry.type === "error" ? "alert" : "status");
    el.classList.add("show");
    toastCurrent = entry;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(dismissToast, entry.ms);
  }

  function showNextToast() {
    if (toastCurrent || !toastQueue.length) return;
    paintToast(toastQueue.shift());
  }

  function dismissToast() {
    clearTimeout(toastTimer);
    if (toastEl) toastEl.classList.remove("show");
    toastCurrent = null;
    setTimeout(showNextToast, prefersReducedMotion() ? 0 : 160);
  }

  function toast(message, options) {
    if (!toastEl || message === undefined || message === null) return;
    var opts = (typeof options === "number") ? { ms: options } : (options || {});
    var entry = {
      message: String(message),
      type: opts.type === "success" || opts.type === "error" ? opts.type : "info",
      ms: Number(opts.ms) > 0 ? Number(opts.ms) : 2600,
    };
    if (toastCurrent) {
      toastQueue.push(entry);
      if (toastQueue.length > 3) toastQueue.shift();
    } else {
      paintToast(entry);
    }
  }
  toast.hide = dismissToast;

  /* ---- skeleton primitives (G4) ----------------------------------------- */
  function skeletonHTML(rows) {
    var count = Math.max(1, Math.min(8, parseInt(rows, 10) || 3));
    var html = '<div class="cg-skel" aria-hidden="true">';
    html += '<span class="cg-skel-line cg-skel-title"></span>';
    for (var i = 0; i < count; i += 1) {
      html += '<span class="cg-skel-line' + (i === count - 1 ? " cg-skel-short" : "") + '"></span>';
    }
    html += "</div>";
    return html;
  }

  function skeleton(target, rows) {
    var el = typeof target === "string" ? document.querySelector(target) : target;
    if (!el) return null;
    el.innerHTML = skeletonHTML(rows);
    el.setAttribute("aria-busy", "true");
    el.classList.add("cg-skel-host");
    return el;
  }

  function clearSkeleton(target) {
    var el = typeof target === "string" ? document.querySelector(target) : target;
    if (!el) return;
    el.removeAttribute("aria-busy");
    el.classList.remove("cg-skel-host");
    var node = el.querySelector(".cg-skel");
    if (node) node.remove();
  }

  function hydrateSkeleton(el) {
    if (!el || el.getAttribute("data-cg-skel") === "1") return;
    if (el.textContent.trim()) return;
    skeleton(el, el.getAttribute("data-skeleton-rows"));
    el.setAttribute("data-cg-skel", "1");
    var observer = new MutationObserver(function () {
      if (el.textContent.trim()) {
        el.removeAttribute("data-cg-skel");
        observer.disconnect();
      }
    });
    observer.observe(el, { childList: true, subtree: true, characterData: true });
  }

  function initDeclarativeSkeletons() {
    var nodes = document.querySelectorAll("[data-skeleton]");
    Array.prototype.forEach.call(nodes, function (el) {
      if (el.children.length || el.textContent.trim()) return;
      skeleton(el, el.getAttribute("data-skeleton"));
    });
  }

  /* ---- overlay scroll lock + empty-drawer skeletons (G4) ---------------- */
  var OVERLAY_SELECTOR = "#palette:not([hidden]), #ref-drawer.open, #evidence-drawer:not([hidden]), " +
    "#checks-drawer:not([hidden]), #repair-modal:not([hidden]), #fix-modal:not([hidden]), " +
    "#page-viewer:not([hidden]), .lib-modal:not([hidden])";
  var overlayLocked = false;
  var overlayTick = null;

  function syncOverlayState() {
    var open = Boolean(document.querySelector(OVERLAY_SELECTOR));
    if (open !== overlayLocked) {
      overlayLocked = open;
      if (open) {
        var gap = Math.max(0, window.innerWidth - document.documentElement.clientWidth);
        document.body.style.setProperty("--cg-scrollbar", gap + "px");
        document.body.classList.add("cg-overlay-open");
      } else {
        document.body.classList.remove("cg-overlay-open");
        document.body.style.removeProperty("--cg-scrollbar");
      }
    }
    Array.prototype.forEach.call(document.querySelectorAll("#ref-drawer, #evidence-drawer"), function (overlay) {
      if (!overlay) return;
      var body = overlay.querySelector(".ref-drawer-body, .drawer-body");
      if (!body) return;
      if (overlay.hidden) {
        body.removeAttribute("data-cg-skel");
        return;
      }
      hydrateSkeleton(body);
    });
  }

  function scheduleOverlaySync() {
    if (overlayTick) return;
    overlayTick = requestAnimationFrame(function () {
      overlayTick = null;
      syncOverlayState();
    });
  }

  if (document.body) {
    new MutationObserver(scheduleOverlaySync).observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ["hidden", "class", "style"],
    });
  }

  /* ---- page transition progress (G4) ------------------------------------ */
  var navBar = document.getElementById("cg-nav-progress");
  function startPageTransition() {
    if (!navBar || prefersReducedMotion()) return;
    navBar.hidden = false;
    navBar.classList.remove("on");
    void navBar.offsetWidth;
    navBar.classList.add("on");
  }
  function stopPageTransition() {
    if (!navBar) return;
    navBar.classList.remove("on");
    navBar.hidden = true;
  }
  window.addEventListener("pageshow", stopPageTransition);

  document.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey ||
        event.shiftKey || event.altKey) return;
    var anchor = event.target && event.target.closest ? event.target.closest("a[href]") : null;
    if (!anchor) return;
    var href = anchor.getAttribute("href");
    if (!href || href.charAt(0) === "#" || anchor.target === "_blank" || anchor.hasAttribute("download")) return;
    if (/^(mailto:|tel:|javascript:)/i.test(href)) return;
    var url;
    try { url = new URL(anchor.href, window.location.href); } catch (err) { return; }
    if (url.origin !== window.location.origin) return;
    if (url.pathname === window.location.pathname && url.search === window.location.search) return;
    startPageTransition();
  });

  /* ---- fetch wrappers --------------------------------------------------- */
  async function getJSON(url) {
    const resp = await fetch(url, { headers: { Accept: "application/json" } });
    if (!resp.ok) throw new Error(window.humanHttpError(resp.status, null, "请求没有完成，请稍后重试"));
    return resp.json();
  }

  async function postForm(url, formData) {
    const resp = await fetch(url, { method: "POST", body: formData });
    const data = await resp.json().catch(function () { return {}; });
    if (!resp.ok) throw new Error(window.humanHttpError(resp.status, data.detail, "请求没有完成，请稍后重试"));
    return data;
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (err) {
      /* fall through to the textarea fallback */
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (err) {
      return false;
    }
  }

  window.CiteGuard = {
    toast: toast,
    getJSON: getJSON,
    postForm: postForm,
    copyText: copyText,
    skeleton: skeleton,
    skeletonHTML: skeletonHTML,
    clearSkeleton: clearSkeleton,
    prefersReducedMotion: prefersReducedMotion,
    syncMotionPreference: syncMotionPreference,
  };
  window.showToast = toast;

  /* ---- command palette -------------------------------------------------- */
  const palette = document.getElementById("palette");
  const paletteInput = document.getElementById("palette-input");
  const paletteList = document.getElementById("palette-list");
  const paletteOpen = document.getElementById("palette-open");
  const paletteClose = document.getElementById("palette-close");
  const paletteCount = document.getElementById("palette-count");
  if (palette && paletteInput && paletteList) {
    const RECENT_KEY = "citeguard.palette.recent.v1";
    const groups = [
      {
        name: "页面",
        items: [
          { kind: "page", label: "工作台", sub: "论文体检 · 快速判定 · 批量判定", url: "/workspace" },
          { kind: "page", label: "报告", sub: "全部报告 · 批量聚合", url: "/history" },
          { kind: "page", label: "题录库", sub: "本地中文元数据", url: "/library" },
          { kind: "page", label: "工具", sub: "图表 · 对比 · 发现", url: "/figure" },
          { kind: "page", label: "关于", sub: "评测 · 模型 · 边界", url: "/about" },
        ],
      },
      {
        name: "动作",
        items: [
          { kind: "action", label: "快速判定一句话", sub: "证据支不支持这条结论", url: "/support" },
          { kind: "action", label: "批量判定", sub: "一次最多 50 条", url: "/batch" },
          { kind: "action", label: "多篇对比", sub: "横向看几篇论文", url: "/compare" },
          { kind: "action", label: "文献发现", sub: "按主题找候选", url: "/discover" },
          { kind: "action", label: "CiteMap 证据地图", sub: "2 个主题 × 15 篇开放论文", url: "/citemap" },
          { kind: "action", label: "批量聚合", sub: "一批论文的体检账", url: "/aggregate" },
          { kind: "action", label: "评测", sub: "可复核的数字与证据", url: "/benchmark" },
          { kind: "action", label: "模型", sub: "本地或托管判官", url: "/settings/models" },
          { kind: "action", label: "开始一次新体检", sub: "回到工作台并选择文件", url: "/workspace#upload-card" },
          { kind: "action", label: "用示例论文试试", sub: "工作台内置示例", url: "/workspace?sample=1" },
        ],
      },
      {
        name: "链接",
        items: [
          { kind: "link", label: "GitHub 仓库", sub: "kkk431/citeguard-cn", url: "https://github.com/kkk431/citeguard-cn" },
        ],
      },
    ];
    const allItems = groups.reduce(function (acc, group) {
      group.items.forEach(function (item) { item.group = group.name; acc.push(item); });
      return acc;
    }, []);
    const byUrl = {};
    allItems.forEach(function (item) { byUrl[item.url] = item; });

    let entries = [];
    let cursor = 0;
    let lastFocus = null;
    let openState = false;

    function readRecent() {
      try {
        const raw = window.localStorage.getItem(RECENT_KEY);
        const urls = raw ? JSON.parse(raw) : [];
        if (!Array.isArray(urls)) return [];
        return urls.map(function (url) { return byUrl[url]; }).filter(Boolean).slice(0, 3);
      } catch (err) {
        return [];
      }
    }

    function remember(item) {
      try {
        const urls = readRecent().map(function (entry) { return entry.url; });
        const next = [item.url].concat(urls.filter(function (url) { return url !== item.url; })).slice(0, 3);
        window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
      } catch (err) {
        /* localStorage may be blocked; recent entries are a nicety */
      }
    }

    function matches(item, query) {
      if (!query) return true;
      return (item.label + " " + item.sub + " " + item.url + " " + item.group).toLowerCase().indexOf(query) >= 0;
    }

    function buildEntries() {
      const query = paletteInput.value.trim().toLowerCase();
      const result = [];
      const recent = query ? [] : readRecent();
      if (recent.length) {
        recent.forEach(function (item) { result.push({ item: item, group: "最近", recent: true }); });
      }
      groups.forEach(function (group) {
        group.items.forEach(function (item) {
          if (!matches(item, query)) return;
          if (query && recent.indexOf(item) >= 0) return;
          result.push({ item: item, group: group.name, recent: false });
        });
      });
      return result;
    }

    function render() {
      entries = buildEntries();
      if (cursor >= entries.length) cursor = Math.max(0, entries.length - 1);
      paletteList.innerHTML = "";
      paletteList.setAttribute("role", "listbox");
      paletteList.setAttribute("aria-label", "页面与动作");
      if (!entries.length) {
        const empty = document.createElement("div");
        empty.className = "palette-empty";
        empty.textContent = "没有匹配的页面或动作";
        paletteList.appendChild(empty);
        paletteInput.removeAttribute("aria-activedescendant");
        updateCount(0);
        return;
      }
      entries.forEach(function (entry, index) {
        if (index === 0 || entries[index - 1].group !== entry.group) {
          const label = document.createElement("div");
          label.className = "palette-group-label";
          label.id = "palette-group-" + index;
          label.setAttribute("role", "presentation");
          label.textContent = entry.group;
          paletteList.appendChild(label);
        }
        const row = document.createElement("div");
        row.className = "palette-item" + (index === cursor ? " on" : "");
        row.id = "palette-opt-" + index;
        row.dataset.url = entry.item.url;
        row.setAttribute("role", "option");
        row.setAttribute("aria-selected", index === cursor ? "true" : "false");
        row.innerHTML = '<span class="p-kind">' + entry.item.kind + "</span><span>" +
          entry.item.label + '</span><span class="p-sub">' + entry.item.sub + "</span>";
        row.addEventListener("mouseenter", function () { cursor = index; paint(); });
        row.addEventListener("click", function () { go(entry.item); });
        paletteList.appendChild(row);
      });
      paint();
      updateCount(entries.length);
    }

    function updateCount(count) {
      if (paletteCount) paletteCount.textContent = count + " 个入口";
    }

    function paint() {
      const rows = paletteList.querySelectorAll(".palette-item");
      Array.prototype.forEach.call(rows, function (row, index) {
        const on = index === cursor;
        row.classList.toggle("on", on);
        row.setAttribute("aria-selected", on ? "true" : "false");
      });
      const active = paletteList.querySelector("#palette-opt-" + cursor);
      if (active) {
        paletteInput.setAttribute("aria-activedescendant", active.id);
        if (active.scrollIntoView) active.scrollIntoView({ block: "nearest" });
      }
    }

    function openPalette() {
      if (openState) return;
      openState = true;
      lastFocus = document.activeElement;
      palette.hidden = false;
      paletteInput.value = "";
      cursor = 0;
      paletteInput.setAttribute("aria-expanded", "true");
      render();
      paletteInput.focus();
      scheduleOverlaySync();
    }

    function closePalette() {
      if (!openState) return;
      openState = false;
      palette.hidden = true;
      paletteInput.setAttribute("aria-expanded", "false");
      paletteInput.removeAttribute("aria-activedescendant");
      if (lastFocus && lastFocus.focus) lastFocus.focus();
      scheduleOverlaySync();
    }

    function go(item) {
      remember(item);
      closePalette();
      startPageTransition();
      if (item.url.indexOf("http") === 0) window.open(item.url, "_blank", "noopener");
      else window.location.href = item.url;
    }

    if (paletteOpen) paletteOpen.addEventListener("click", openPalette);
    if (paletteClose) paletteClose.addEventListener("click", closePalette);
    if (window.location.hash === "#palette") openPalette();
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (openState) closePalette(); else openPalette();
        return;
      }
      if (!openState) return;
      if (e.key === "Escape") {
        e.preventDefault();
        closePalette();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        cursor = Math.min(cursor + 1, entries.length - 1);
        paint();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        cursor = Math.max(cursor - 1, 0);
        paint();
      } else if (e.key === "Home") {
        e.preventDefault();
        cursor = 0;
        paint();
      } else if (e.key === "End") {
        e.preventDefault();
        cursor = Math.max(0, entries.length - 1);
        paint();
      } else if (e.key === "PageDown") {
        e.preventDefault();
        cursor = Math.min(cursor + 5, entries.length - 1);
        paint();
      } else if (e.key === "PageUp") {
        e.preventDefault();
        cursor = Math.max(cursor - 5, 0);
        paint();
      } else if (e.key === "Enter" && entries[cursor]) {
        e.preventDefault();
        go(entries[cursor].item);
      } else if (e.key === "Tab") {
        /* keep keyboard focus inside the dialog: input ⇄ close */
        e.preventDefault();
        if (e.target === paletteClose && paletteClose) paletteInput.focus();
        else if (e.shiftKey && paletteClose) paletteClose.focus();
        else paletteInput.focus();
      }
    });
    paletteInput.addEventListener("input", function () { cursor = 0; render(); });
    palette.addEventListener("click", function (e) {
      if (e.target.hasAttribute("data-close")) closePalette();
    });
    document.addEventListener("click", function (e) {
      if (!openState) return;
      if (!palette.contains(e.target) && !(paletteOpen && paletteOpen.contains(e.target))) closePalette();
    });
  }

  /* ---- mobile rail ------------------------------------------------------ */
  const rail = document.getElementById("rail");
  const toggle = document.getElementById("rail-toggle");
  const backdrop = document.getElementById("rail-backdrop");
  function setRail(open) {
    if (!rail || !toggle) return;
    rail.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (backdrop) backdrop.hidden = !open;
  }
  if (toggle) toggle.addEventListener("click", function () {
    setRail(!rail.classList.contains("open"));
  });
  if (backdrop) backdrop.addEventListener("click", function () { setRail(false); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && rail && rail.classList.contains("open")) setRail(false);
  });

  /* ---- boot ------------------------------------------------------------- */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initDeclarativeSkeletons();
      syncOverlayState();
    });
  } else {
    initDeclarativeSkeletons();
    syncOverlayState();
  }
})();
