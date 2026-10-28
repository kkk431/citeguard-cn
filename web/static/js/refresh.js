/* CiteGuard-CN · 2026 前端交互层
   主题切换 / 卡片聚光 / 滚动入场 / 数字滚动 / 移动端导航。
   不改变任何业务请求，只增强交互。 */
(function () {
  "use strict";
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- 主题 ---------- */
  var THEME_KEY = "citeguard-theme";
  function applyTheme(theme) {
    document.body.classList.toggle("theme-light", theme === "light");
    var btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.textContent = theme === "light" ? "☾" : "☀";
      btn.setAttribute("aria-label", theme === "light" ? "切到深色" : "切到浅色");
      btn.title = theme === "light" ? "深色模式" : "浅色模式";
    }
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* ignore */ }
  }
  var saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch (e) { /* ignore */ }
  applyTheme(saved === "light" ? "light" : "dark");

  document.addEventListener("click", function (ev) {
    var t = ev.target.closest && ev.target.closest("#theme-toggle");
    if (!t) return;
    applyTheme(document.body.classList.contains("theme-light") ? "dark" : "light");
  });

  /* ---------- 移动端导航 ---------- */
  var rail = document.getElementById("rail");
  var backdrop = document.getElementById("rail-backdrop");
  var railToggle = document.getElementById("rail-toggle");
  function closeRail() {
    if (!rail) return;
    rail.classList.remove("open");
    if (backdrop) backdrop.hidden = true;
    if (railToggle) railToggle.setAttribute("aria-expanded", "false");
  }
  if (railToggle) {
    railToggle.addEventListener("click", function () {
      var open = rail.classList.toggle("open");
      if (backdrop) backdrop.hidden = !open;
      railToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }
  if (backdrop) backdrop.addEventListener("click", closeRail);
  if (rail) rail.addEventListener("click", function (e) {
    if (e.target.closest("a") && window.innerWidth <= 860) closeRail();
  });

  /* ---------- 卡片聚光 ---------- */
  function bindSpotlight() {
    var nodes = document.querySelectorAll(".cap-card, .stats-strip a, .btn, .preview");
    nodes.forEach(function (el) {
      if (el.dataset.spot === "1") return;
      el.dataset.spot = "1";
      el.addEventListener("pointermove", function (e) {
        var r = el.getBoundingClientRect();
        el.style.setProperty("--mx", ((e.clientX - r.left) / r.width * 100).toFixed(1) + "%");
        el.style.setProperty("--my", ((e.clientY - r.top) / r.height * 100).toFixed(1) + "%");
      });
    });
  }

  /* ---------- 滚动入场 ---------- */
  function bindReveal() {
    var nodes = document.querySelectorAll(".section, .hero-copy, .preview, .cap-card, .how-card");
    if (!("IntersectionObserver" in window) || reduceMotion) {
      nodes.forEach(function (n) { n.classList.add("in"); });
      return;
    }
    nodes.forEach(function (n) { n.classList.add("reveal"); });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.06 });
    nodes.forEach(function (n) { io.observe(n); });
  }

  /* ---------- 数字滚动 ---------- */
  function countUp(el) {
    var raw = el.getAttribute("data-count");
    if (!raw) return;
    var target = parseFloat(raw);
    var decimals = (raw.split(".")[1] || "").length;
    var suffix = el.getAttribute("data-suffix") || "";
    var start = null, dur = 1100;
    if (reduceMotion || isNaN(target)) { el.textContent = el.getAttribute("data-text") || raw; return; }
    function step(ts) {
      if (!start) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      var eased = 1 - Math.pow(1 - p, 3);
      var val = target * eased;
      el.textContent = (decimals ? val.toFixed(decimals) : Math.round(val).toLocaleString("en-US")) + suffix;
      if (p < 1) requestAnimationFrame(step);
      else el.textContent = (el.getAttribute("data-text") || el.textContent);
    }
    requestAnimationFrame(step);
  }
  function bindCounts() {
    var els = document.querySelectorAll("[data-count]");
    if (!els.length) return;
    if (!("IntersectionObserver" in window)) { els.forEach(countUp); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { countUp(en.target); io.unobserve(en.target); }
      });
    }, { threshold: 0.4 });
    els.forEach(function (el) {
      if (el.dataset.counted === "1") return;
      el.dataset.counted = "1";
      var t = el.getAttribute("data-text");
      if (t) el.textContent = t;
      io.observe(el);
    });
  }

  /* ---------- 键盘：/ 聚焦命令面板 ---------- */
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "/" || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    if (/INPUT|TEXTAREA|SELECT/.test(tag)) return;
    var open = document.getElementById("palette-open");
    if (open) { ev.preventDefault(); open.click(); }
  });

  function init() {
    bindSpotlight();
    bindReveal();
    bindCounts();
    // 稍后插入的卡片（如批量结果）也接上聚光
    var mo = new MutationObserver(function () { bindSpotlight(); });
    mo.observe(document.getElementById("main") || document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
