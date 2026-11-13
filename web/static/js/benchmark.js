/* CiteBench-CN v2 charts: detection by class, decision confusion, retractions. */
(function () {
  "use strict";
  var node = document.getElementById("cb2-data");
  if (!node || !window.CGCharts) return;
  var data;
  try { data = JSON.parse(node.textContent || "{}"); } catch (e) { return; }
  var meta = (data && data.metadata) || {};
  var special = (data && data.special) || {};

  var LABELS = {
    author_swap: "作者替换",
    year_shift: "年份偏移",
    venue_swap: "期刊/会议替换",
    doi_swap: "DOI 替换",
    paraphrase: "改写转述",
    fabricated: "纯编造"
  };

  function detectionChart(t) {
    var rows = [];
    var per = meta.per_class || {};
    Object.keys(LABELS).forEach(function (key) {
      if (per[key]) rows.push({ key: key, label: LABELS[key], rate: per[key].detection_rate, n: per[key].n });
    });
    var retracted = special.retracted;
    if (retracted && retracted.n) {
      rows.push({ key: "retracted", label: "撤稿（外部真值）", rate: retracted.detected / retracted.n, n: retracted.n });
    }
    if (!rows.length) return null;
    rows = rows.slice().reverse();
    return Object.assign(CGCharts.base(), {
      tooltip: Object.assign(CGCharts.base().tooltip, {
        trigger: "axis", axisPointer: { type: "shadow" },
        formatter: function (params) {
          var p = params[0];
          var row = rows[p.dataIndex];
          return row.label + "<br/>检出率 " + (row.rate * 100).toFixed(1) + "% · n=" + row.n;
        }
      }),
      legend: { show: false },
      grid: { left: 8, right: 54, top: 8, bottom: 4, containLabel: true },
      xAxis: Object.assign(CGCharts.valueAxis(), {
        min: 0, max: 100,
        axisLabel: { color: t.muted, fontSize: 11, formatter: "{value}%" }
      }),
      yAxis: {
        type: "category",
        data: rows.map(function (r) { return r.label; }),
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: t.muted, fontSize: 11.5 }
      },
      series: [{
        type: "bar",
        barMaxWidth: 22,
        data: rows.map(function (r) {
          var color = r.rate >= 0.9 ? t.colors[0] : (r.rate >= 0.5 ? t.colors[2] : t.colors[3]);
          return { value: Math.round(r.rate * 1000) / 10, itemStyle: { color: color, borderRadius: [0, 4, 4, 0] } };
        }),
        label: {
          show: true, position: "right", color: t.muted, fontSize: 11,
          formatter: function (p) { return p.value.toFixed(1) + "%"; }
        }
      }]
    });
  }

  function confusionChart(t) {
    var tn = Number(meta.tn || 0), fp = Number(meta.fp || 0);
    var fn = Number(meta.fn || 0), tp = Number(meta.tp || 0);
    if (!(tn + fp + fn + tp)) return null;
    var max = Math.max(tn, fp, fn, tp) || 1;
    return Object.assign(CGCharts.base(), {
      tooltip: Object.assign(CGCharts.base().tooltip, {
        position: "top",
        formatter: function (p) { return p.value[2] + " 条"; }
      }),
      legend: { show: false },
      grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
      xAxis: {
        type: "category", data: ["判为干净", "判为有问题"],
        axisLine: { lineStyle: { color: t.line } }, axisTick: { show: false },
        axisLabel: { color: t.muted, fontSize: 11 }
      },
      yAxis: {
        type: "category", data: ["标签=非Exact", "标签=Exact"],
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: t.muted, fontSize: 11 }
      },
      visualMap: {
        show: false, min: 0, max: max,
        inRange: { color: [t.colors[0] + "33", t.colors[0]] }
      },
      series: [{
        type: "heatmap",
        data: [
          [0, 0, tn], [1, 0, fp],
          [0, 1, fn], [1, 1, tp]
        ],
        label: { show: true, color: t.text, fontSize: 14, fontWeight: 600 },
        itemStyle: { borderColor: t.tipBg, borderWidth: 3 }
      }]
    });
  }

  function retractedChart(t) {
    var r = special.retracted;
    if (!r || !r.n) return null;
    var missed = Math.max(0, r.n - r.detected);
    return Object.assign(CGCharts.base(), {
      tooltip: Object.assign(CGCharts.base().tooltip, { trigger: "item", formatter: "{b}: {c} 条（{d}%）" }),
      legend: Object.assign(CGCharts.base().legend, { top: "auto", bottom: 0, left: "center" }),
      series: [{
        type: "pie",
        radius: ["52%", "74%"],
        center: ["50%", "44%"],
        label: { color: t.text, fontSize: 11, formatter: "{b}\n{c} 条" },
        labelLine: { lineStyle: { color: t.line } },
        itemStyle: { borderColor: t.tipBg, borderWidth: 2 },
        data: [
          { name: "已识别", value: r.detected, itemStyle: { color: t.colors[0] } },
          { name: "未识别", value: missed, itemStyle: { color: t.colors[3] } }
        ]
      }],
      graphic: [{
        type: "text", left: "center", top: "35%",
        style: { text: Math.round(100 * r.detected / r.n) + "%", fill: t.text, fontSize: 20, fontWeight: 700, textAlign: "center" }
      }]
    });
  }

  CGCharts.mount(document.getElementById("cb2-detection"), detectionChart);
  CGCharts.mount(document.getElementById("cb2-confusion"), confusionChart);
  CGCharts.mount(document.getElementById("cb2-retracted"), retractedChart);
})();
