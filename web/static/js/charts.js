/* CiteGuard-CN chart layer: one ECharts entry point for every page.
 * Charts use real JSON only. Theme follows body.theme-light and re-renders
 * on the citeguard:themechange event fired by refresh.js. */
(function () {
  "use strict";

  var LIGHT = {
    text: "#1d2a27",
    muted: "#5f726d",
    line: "rgba(20, 60, 50, .14)",
    split: "rgba(20, 60, 50, .08)",
    tipBg: "#ffffff",
    colors: ["#08785f", "#0b7285", "#b26a00", "#c0392b", "#6e56cf", "#2f6f4e", "#8a6d3b"]
  };
  var DARK = {
    text: "#e8f5f1",
    muted: "#9fb5ae",
    line: "rgba(160, 220, 205, .18)",
    split: "rgba(160, 220, 205, .08)",
    tipBg: "#0b1720",
    colors: ["#3ce6b4", "#55d6ff", "#ffb84d", "#ff6b57", "#b48cff", "#7ff0cf", "#ffd27a"]
  };

  function tokens() {
    return document.body.classList.contains("theme-light") ? LIGHT : DARK;
  }

  function base() {
    var t = tokens();
    return {
      backgroundColor: "transparent",
      color: t.colors,
      textStyle: { fontFamily: '"Microsoft YaHei", "Segoe UI", sans-serif', color: t.text, fontSize: 12 },
      animationDuration: 500,
      tooltip: {
        backgroundColor: t.tipBg,
        borderColor: t.line,
        borderWidth: 1,
        padding: [8, 10],
        textStyle: { color: t.text, fontSize: 12 },
        extraCssText: "border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18)"
      },
      legend: {
        top: 0,
        left: 0,
        itemWidth: 10,
        itemHeight: 10,
        itemGap: 14,
        icon: "roundRect",
        textStyle: { color: t.muted, fontSize: 11 }
      },
      grid: { left: 6, right: 16, top: 34, bottom: 4, containLabel: true }
    };
  }

  function axis(name) {
    var t = tokens();
    var a = {
      type: "category",
      axisLine: { lineStyle: { color: t.line } },
      axisTick: { show: false },
      axisLabel: { color: t.muted, fontSize: 11, hideOverlap: true }
    };
    if (!name) delete a.name;
    return a;
  }

  function valueAxis() {
    var t = tokens();
    return {
      type: "value",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: t.split, type: "dashed" } },
      axisLabel: { color: t.muted, fontSize: 11 }
    };
  }

  function num(v, digits) {
    if (typeof v !== "number" || !isFinite(v)) return "—";
    return digits ? v.toFixed(digits) : String(Math.round(v));
  }

  var builds = new Map();
  var charts = new Map();
  var observer = null;

  // Every chart gets the same interaction defaults: a contained tooltip,
  // series focus on hover, and (for long category axes) Ctrl+wheel zoom.
  // Charts keep their own option builders; this only fills in absent keys.
  function interactions(option) {
    option.tooltip = option.tooltip || {};
    if (option.tooltip.confine === undefined) option.tooltip.confine = true;
    if (option.tooltip.enterable === undefined) option.tooltip.enterable = false;
    var series = option.series || [];
    series.forEach(function (entry) {
      if (!entry || entry.type === "gauge") return;
      entry.emphasis = entry.emphasis || {};
      if (entry.emphasis.disabled === undefined) entry.emphasis.disabled = false;
      if (entry.emphasis.focus === undefined) {
        entry.emphasis.focus = entry.type === "pie" ? "self" : "series";
      }
      if (entry.type === "pie" && entry.emphasis.scale === undefined) entry.emphasis.scale = true;
      if (entry.blur === undefined && entry.type !== "pie") {
        entry.blur = { itemStyle: { opacity: 0.35 }, lineStyle: { opacity: 0.15 } };
      }
    });
    if (option.legend) {
      if (option.legend.selectedMode === undefined) option.legend.selectedMode = "multiple";
      if (option.legend.silent === undefined) option.legend.silent = false;
    }
    var xAxis = option.xAxis || {};
    var yAxis = option.yAxis || {};
    var categories = 0;
    var zoomAxis = null;
    if (xAxis.type === "category" && Array.isArray(xAxis.data)) {
      categories = xAxis.data.length;
      zoomAxis = "xAxisIndex";
    }
    if (yAxis.type === "category" && Array.isArray(yAxis.data)) {
      if (yAxis.data.length > categories) {
        categories = yAxis.data.length;
        zoomAxis = "yAxisIndex";
      }
    }
    // Zoom is enabled for any cartesian chart with a category axis. The
    // report charts start small, but the same builder is reused for longer
    // lists; without dataZoom a long category axis would clip silently.
    if (!option.dataZoom && categories > 1 && zoomAxis) {
      var zoom = {
        type: "inside",
        filterMode: "none",
        zoomOnMouseWheel: "ctrl",
        moveOnMouseMove: false,
        start: 0,
        end: 100
      };
      zoom[zoomAxis] = 0;
      option.dataZoom = [zoom];
    }
    return option;
  }

  function hasZoom(option) {
    return !!(option.dataZoom && option.dataZoom.length);
  }

  function hintText(option) {
    var parts = ["悬停高亮"];
    if (option.legend && option.legend.show !== false) parts.push("点击图例筛选");
    if (hasZoom(option)) parts.push("Ctrl+滚轮缩放");
    parts.push("双击重置");
    return parts.join(" · ");
  }

  function ensureHint(el, option) {
    var card = el.closest(".chart-card") || el.parentElement;
    if (!card) return;
    var hint = card.querySelector(".cg-chart-hint");
    if (!hint) {
      hint = document.createElement("p");
      hint.className = "cg-chart-hint";
      hint.setAttribute("aria-hidden", "true");
      hint.style.cssText = "margin:6px 2px 0;color:var(--muted,#7c8f8a);font:11px/1.5 'Microsoft YaHei','Segoe UI',sans-serif;opacity:.82";
      card.appendChild(hint);
    }
    hint.textContent = hintText(option);
    hint.dataset.zoom = hasZoom(option) ? "1" : "0";
  }

  function resetZoom(chart, option) {
    if (!chart || !option || !hasZoom(option)) return;
    chart.dispatchAction({ type: "dataZoom", start: 0, end: 100 });
  }

  function bindInteractions(el, chart, option) {
    if (chart.__cgBound) return;
    chart.__cgBound = true;
    chart.on("dblclick", function () { resetZoom(chart, option); });
    el.addEventListener("dblclick", function () { resetZoom(chart, option); });
    if (hasZoom(option)) el.setAttribute("title", "Ctrl+滚轮缩放，双击重置；悬停查看数值");
  }

  function draw(el) {
    var builder = builds.get(el);
    if (!builder) return;
    var option = interactions(builder(tokens()));
    var old = charts.get(el);
    if (!option || !option.series || !option.series.length) {
      if (old) { old.dispose(); charts.delete(el); }
      el.innerHTML = '<div class="chart-empty">' + (el.dataset.empty || "暂无可绘制的数据") + "</div>";
      return;
    }
    if (el.firstElementChild && el.firstElementChild.className === "chart-empty") el.innerHTML = "";
    var chart = old || window.echarts.init(el, null, { renderer: "canvas" });
    chart.setOption(option, true);
    charts.set(el, chart);
    ensureHint(el, option);
    bindInteractions(el, chart, option);
  }

  function mount(el, builder) {
    if (!el || !window.echarts) return;
    el.dataset.chartReady = "1";
    builds.set(el, builder);
    draw(el);
    if (!observer && window.ResizeObserver) {
      observer = new ResizeObserver(function (entries) {
        entries.forEach(function (entry) {
          var chart = charts.get(entry.target);
          if (chart) chart.resize();
        });
      });
    }
    if (observer) {
      builds.forEach(function (_b, node) {
        if (node && node !== el) observer.observe(node);
      });
      observer.observe(el);
    }
  }

  function refresh() {
    builds.forEach(function (_builder, el) { draw(el); });
  }

  function resize() {
    charts.forEach(function (chart) {
      if (chart && !chart.isDisposed()) chart.resize();
    });
  }

  window.CGCharts = {
    mount: mount,
    refresh: refresh,
    resize: resize,
    tokens: tokens,
    base: base,
    axis: axis,
    valueAxis: valueAxis,
    num: num
  };

  document.addEventListener("citeguard:themechange", refresh);
  window.addEventListener("beforeprint", function () {
    charts.forEach(function (chart) { chart.resize(); });
  });
})();
