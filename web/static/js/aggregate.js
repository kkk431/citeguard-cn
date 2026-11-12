(function () {
  "use strict";

  const root = document.getElementById("aggregate-root");
  if (!root) return;
  const ids = (root.dataset.ids || "").trim();
  const statsEl = document.getElementById("ag-stats");
  const errorEl = document.getElementById("ag-error");
  const loadingEl = document.getElementById("ag-loading");
  const overviewEl = document.getElementById("ag-overview");
  const tableCardEl = document.getElementById("ag-table-card");
  const bodyEl = document.getElementById("ag-body");
  const csvBtn = document.getElementById("ag-csv");

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function num(value, digits) {
    if (typeof value !== "number" || !isFinite(value)) return "—";
    return digits ? value.toFixed(digits) : String(value);
  }

  function showError(message) {
    if (loadingEl) loadingEl.hidden = true;
    errorEl.hidden = false;
    errorEl.textContent = message;
    if (overviewEl) overviewEl.hidden = true;
    if (tableCardEl) tableCardEl.hidden = true;
  }

  function renderStats(data) {
    const s = data.summary || {};
    statsEl.innerHTML = [
      '<div class="ag-stat"><b>' + num(s.papers) + "</b><span>篇有报告的论文</span></div>",
      '<div class="ag-stat"><b>' + num(s.avg_health, 1) + "</b><span>平均健康分 · 已评 " + num(s.scored) + " 篇</span></div>",
      '<div class="ag-stat"><b>' + num(s.refs) + "</b><span>参考文献 · 平均 " + num(s.avg_refs, 1) + " 条/篇</span></div>",
      '<div class="ag-stat"><b>' + num(s.major) + "</b><span>疑似错配/虚构（Major）</span></div>",
    ].join("");
  }

  function renderGrades(data) {
    const box = document.getElementById("ag-grades");
    box.innerHTML = (data.grades || [])
      .filter(function (g) { return g.count > 0; })
      .map(function (g) {
        const cls = g.grade === "未评" ? "N" : g.grade;
        return '<span class="ag-grade"><b class="ag-grade-chip ' + cls + '">' + esc(g.grade) +
          "</b>" + num(g.count) + " 篇</span>";
      })
      .join("") || '<span class="ag-note">暂无可评分的报告。</span>';
  }

  function renderDims(data) {
    const box = document.getElementById("ag-dims");
    box.innerHTML = (data.dimensions || []).map(function (d) {
      const has = typeof d.average === "number";
      const pct = has ? Math.max(0, Math.min(100, d.average)) : 0;
      return '<div class="ag-dim"><div class="ag-dim-top"><strong>' + esc(d.label) +
        "</strong><span>" + (has ? num(d.average, 1) + " 分 · " + num(d.papers) + " 篇" : "本次未检测") +
        '</span></div><div class="ag-bar"><i style="width:' + pct + '%"></i></div></div>';
    }).join("");
  }

  function renderIssues(data) {
    const box = document.getElementById("ag-issues");
    const issues = data.top_issues || [];
    box.innerHTML = issues.length
      ? issues.map(function (it) {
          return '<div class="ag-issue"><span>' + esc(it.label) + "</span><b>" + num(it.count) + " 篇</b></div>";
        }).join("")
      : '<p class="ag-note">这批报告里没有出现可归类的问题。</p>';
  }

  function renderTable(data) {
    const tbody = document.getElementById("ag-rows");
    tbody.innerHTML = (data.papers || []).map(function (p) {
      const grade = p.grade || "未评";
      const cls = grade === "未评" ? "N" : grade;
      return "<tr>" +
        '<td class="name"><a href="/report/' + encodeURIComponent(p.job_id) + '">' + esc(p.name) + "</a></td>" +
        "<td>" + num(p.health, 1) + "</td>" +
        '<td><span class="ag-grade-chip ' + cls + '">' + esc(grade) + "</span></td>" +
        "<td>" + num(p.refs) + "</td>" +
        "<td>" + num(p.exact) + "</td>" +
        "<td>" + num(p.minor) + "</td>" +
        "<td>" + num(p.unverified + p.unknown) + "</td>" +
        "<td>" + num(p.major) + "</td>" +
        "<td>" + num(p.format_issues) + "</td>" +
        "<td>" + num(p.contradict) + "</td>" +
        "<td>" + num(p.retracted) + "</td>" +
        '<td><a href="/report/' + encodeURIComponent(p.job_id) + '">查看</a></td>' +
        "</tr>";
    }).join("");
    const note = document.getElementById("ag-note");
    const missing = (data.missing || []).length;
    const dup = (data.duplicates || []).length;
    note.textContent = (data.note || "") +
      (dup ? " 同一文件的 " + dup + " 份重复报告已合并（只保留第一份）。" : "") +
      (missing ? " 另有 " + missing + " 个所选任务没有已完成报告，未计入。" : "");
  }

  function render(data) {
    if (loadingEl) loadingEl.hidden = true;
    errorEl.hidden = true;
    renderStats(data);
    renderGrades(data);
    renderDims(data);
    renderIssues(data);
    renderTable(data);
    overviewEl.hidden = false;
    tableCardEl.hidden = false;
    const missing = (data.missing || []).length;
    const dup = (data.duplicates || []).length;
    document.getElementById("ag-scope").textContent =
      "本次汇总 " + (data.summary ? data.summary.papers : 0) + " 篇" +
      (dup ? " · 合并同一文件重复报告 " + dup + " 份" : "") +
      (missing ? " · 跳过 " + missing + " 个无报告任务" : "");
  }

  function load() {
    if (!ids) {
      showError("没有选择报告。请先到「历史报告」勾选几篇，再点「聚合健康画像」。");
      return;
    }
    fetch("/api/aggregate?ids=" + encodeURIComponent(ids), { headers: { Accept: "application/json" } })
      .then(function (resp) {
        return resp.json().then(function (body) {
          if (!resp.ok) throw new Error(body.detail || ("HTTP " + resp.status));
          return body;
        });
      })
      .then(render)
      .catch(function (err) {
        showError("汇总失败：" + err.message);
      });
  }

  if (csvBtn) {
    csvBtn.addEventListener("click", function () {
      if (!ids) return;
      window.location.href = "/api/aggregate.csv?ids=" + encodeURIComponent(ids);
    });
  }

  load();
})();
