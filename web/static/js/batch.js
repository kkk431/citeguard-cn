/* Batch claim-evidence check page. */
(function () {
  "use strict";
  const form = document.getElementById("bt-form");
  const claimsEl = document.getElementById("bt-claims");
  const evEl = document.getElementById("bt-evidence");
  const runBtn = document.getElementById("bt-run");
  const sampleBtn = document.getElementById("bt-sample");
  const countEl = document.getElementById("bt-count");
  const errEl = document.getElementById("bt-err");
  const resultEl = document.getElementById("bt-result");
  const metaEl = document.getElementById("bt-result-meta");
  if (!form || !claimsEl || !evEl) return;

  const LABELS = {
    support: "支持",
    partial: "部分支持",
    contradict: "矛盾",
    no_evidence: "无证据",
    not_checked: "未判定",
  };
  const SAMPLE_CLAIMS = [
    "图中 2025 年的发文量最高，为 195 篇。",
    "该方法在中文任务上优于基线模型。",
    "作者认为样本量不足是主要局限。"
  ];
  const SAMPLE_EVIDENCE = [
    "2025 年的发文量为 195 篇，是 2016–2025 年间最高的一年。",
    "在中文任务上，该方法的 F1 为 0.72，基线为 0.65。",
    "作者指出，样本量偏小，结论仍需更大规模验证。"
  ];

  function lines(el) {
    return el.value.split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean);
  }
  function refreshCount() {
    const a = lines(claimsEl).length, b = lines(evEl).length;
    countEl.textContent = a + " 条引用 · " + b + " 条证据";
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function labelChip(label) {
    const key = label || "not_checked";
    return '<span class="bt-chip ' + key + '">' + esc(LABELS[key] || key) + "</span>";
  }
  function confText(c) {
    return typeof c === "number" ? Math.round(c * 100) + "%" : "—";
  }

  claimsEl.addEventListener("input", refreshCount);
  evEl.addEventListener("input", refreshCount);

  sampleBtn.addEventListener("click", function () {
    claimsEl.value = SAMPLE_CLAIMS.join("\n");
    evEl.value = SAMPLE_EVIDENCE.join("\n");
    refreshCount();
    errEl.textContent = "";
  });

  let lastRows = [];

  const VERDICT_COLORS = {
    support: "#3ce6b4", partial: "#ffb84d", contradict: "#ff6b57", no_evidence: "#9fb5ae", not_checked: "#5b6b70"
  };

  function mountVerdictChart(rows) {
    const el = document.getElementById("bt-chart");
    if (!el || !window.echarts || !window.CGCharts) return;
    const counts = {};
    rows.forEach(function (r) {
      const k = r.label || "not_checked";
      counts[k] = (counts[k] || 0) + 1;
    });
    const order = ["support", "partial", "contradict", "no_evidence", "not_checked"];
    const data = order.filter(function (k) { return counts[k]; }).map(function (k) {
      return { name: LABELS[k], value: counts[k], itemStyle: { color: VERDICT_COLORS[k] } };
    });
    const total = rows.length;
    CGCharts.mount(el, function (t) {
      const opt = CGCharts.base();
      opt.tooltip = Object.assign(opt.tooltip, { trigger: "item", formatter: "{b}：{c} 条（{d}%）" });
      opt.legend = { show: false };
      opt.series = [{
        type: "pie", radius: ["58%", "80%"], center: ["50%", "50%"],
        avoidLabelOverlap: true, label: { show: false }, data: data
      }];
      opt.graphic = [
        { type: "text", left: "center", top: "40%", style: { text: String(total), fill: t.text, fontSize: 24, fontWeight: 700, textAlign: "center" } },
        { type: "text", left: "center", top: "56%", style: { text: "条判定", fill: t.muted, fontSize: 11, textAlign: "center" } }
      ];
      return opt;
    });
  }

  function renderRows(rows) {
    lastRows = rows;
    const counts = {};
    rows.forEach(function (r) { const k = r.label || "not_checked"; counts[k] = (counts[k] || 0) + 1; });
    const legend = ["support", "partial", "contradict", "no_evidence", "not_checked"].filter(function (k) {
      return counts[k];
    }).map(function (k) {
      return '<span class="bt-sum-item"><i style="background:' + VERDICT_COLORS[k] + '"></i>' + LABELS[k] + " <b>" + counts[k] + "</b></span>";
    }).join("");
    let html = '<div class="bt-summary"><div class="bt-chart" id="bt-chart"></div><div class="bt-sum-legend">' + legend + "</div></div>";
    html += '<table class="bt-table"><thead><tr><th>#</th><th>引用句</th><th>判定</th><th>置信度</th><th>理由</th></tr></thead><tbody>';
    rows.forEach(function (r) {
      html += "<tr><td>" + (r.index + 1) + "</td><td class='claim'>" + esc(r.claim) +
        "</td><td>" + labelChip(r.label) + "</td><td class='bt-conf'>" + confText(r.confidence) +
        "</td><td class='reason'>" + esc(r.reason || "") + "</td></tr>";
    });
    html += "</tbody></table>";
    resultEl.innerHTML = html;
    metaEl.textContent = rows.length + " 条 · 可导出 CSV";
    mountVerdictChart(rows);
  }

  function csvCell(v) {
    return '"' + String(v == null ? "" : v).replace(/"/g, '""') + '"';
  }
  function downloadCsv() {
    if (!lastRows.length) return;
    const rows = [["序号", "引用句", "判定", "置信度", "理由", "证据原句"]];
    lastRows.forEach(function (r) {
      rows.push([r.index + 1, r.claim, LABELS[r.label] || r.label || "", confText(r.confidence), r.reason || "", r.evidence || ""]);
    });
    const csv = "\ufeff" + rows.map(function (row) { return row.map(csvCell).join(","); }).join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "batch-check.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const claims = lines(claimsEl);
    const evidences = lines(evEl);
    errEl.textContent = "";
    if (!claims.length) { errEl.textContent = "至少填一条引用句。"; return; }
    if (claims.length !== evidences.length) {
      errEl.textContent = "引用句 " + claims.length + " 条、证据 " + evidences.length + " 条，行数必须一致。";
      return;
    }
    if (claims.length > 50) { errEl.textContent = "一次最多 50 条（当前 " + claims.length + " 条）。"; return; }
    const items = claims.map(function (c, i) { return { claim: c, evidence: evidences[i] }; });
    runBtn.disabled = true;
    runBtn.textContent = "核验中…";
    resultEl.innerHTML = '<div class="bt-empty">判定服务正在逐条核验（4 并发），请稍候…</div>';
    try {
      const res = await fetch("/api/support/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: items }),
      });
      const data = await res.json().catch(function () { return {}; });
      if (!res.ok) throw new Error(data.detail || data.error || ("HTTP " + res.status));
      const out = (data.items || []).map(function (it, i) {
        return {
          index: i,
          claim: claims[i],
          label: it.label,
          confidence: it.confidence,
          reason: it.reason,
          evidence: it.evidence,
        };
      });
      renderRows(out);
      const btn = document.createElement("button");
      btn.className = "btn ghost sm";
      btn.type = "button";
      btn.textContent = "下载 CSV";
      btn.style.marginTop = "12px";
      btn.addEventListener("click", downloadCsv);
      resultEl.appendChild(btn);
    } catch (e) {
      resultEl.innerHTML = '<div class="bt-empty">核验失败：' + esc(e.message) + "</div>";
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = "开始批量核验";
    }
  });

  refreshCount();
})();
