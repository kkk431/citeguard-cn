/* Report rendering: stats, filters, search, sort, cards/table, evidence. */
(function () {
  const root = document.getElementById("report-root");
  if (!root) return;

  const jobId = root.dataset.jobId;
  const dataEl = document.getElementById("report-data");
  let report = null;
  try {
    report = JSON.parse((dataEl && dataEl.textContent) || "null");
  } catch (e) {
    report = null;
  }

  const STATUS = {
    Exact: { label: "真实一致", cls: "ok", color: "var(--ok)" },
    Minor: { label: "元数据偏差", cls: "warn", color: "var(--warn)" },
    Major: { label: "疑似虚构或错配", cls: "bad", color: "var(--bad)" },
    Unknown: { label: "无法核验", cls: "unknown", color: "var(--unknown)" },
  };
  const RISK = { Major: 3, Minor: 2, Unknown: 1, Exact: 0 };
  const SUPPORT = {
    support: { label: "支持", cls: "ok" },
    partial: { label: "部分支持", cls: "warn" },
    contradict: { label: "矛盾", cls: "bad" },
    no_evidence: { label: "无证据", cls: "unknown" },
    not_checked: { label: "未检测", cls: "unknown" },
  };
  const SUPPORT_ORDER = ["support", "partial", "contradict", "no_evidence", "not_checked"];
  const state = { filter: "all", q: "", sort: "index", view: "cards" };

  if (!report) {
    pollJob();
    return;
  }
  render(report);

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function short(value, n) {
    const s = String(value == null ? "" : value);
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  function pollJob() {
    const stageEl = document.getElementById("loading-stage");
    const progEl = document.getElementById("loading-progress");
    const barEl = document.getElementById("loading-bar");
    const timer = setInterval(async function () {
      try {
        const job = await window.CiteGuard.getJSON("/api/jobs/" + jobId);
        if (stageEl) stageEl.textContent = job.stage || "分析中…";
        if (progEl) progEl.textContent = (job.progress || 0) + "%";
        if (barEl) barEl.style.width = (job.progress || 0) + "%";
        if (job.status === "done") {
          clearInterval(timer);
          window.location.reload();
        } else if (job.status === "error") {
          clearInterval(timer);
          if (stageEl) stageEl.textContent = "分析失败：" + (job.error || "未知错误");
        }
      } catch (err) {
        /* keep polling; a transient 404 is normal while the report is written */
      }
    }, 1400);
  }

  function render(data) {
    const s = data.stats || {};
    const total = s.total || 1;

    const stats = [
      ["参考文献", s.total || 0, ""],
      ["真实一致", s.Exact || 0, "ok"],
      ["元数据偏差", s.Minor || 0, "warn"],
      ["疑似虚构/错配", s.Major || 0, "bad"],
      ["无法核验", s.Unknown || 0, ""],
    ];
    document.getElementById("stats").innerHTML = stats
      .map(function (x) {
        return '<div class="stat ' + x[2] + '"><b>' + x[1] + "</b><span>" + x[0] + "</span></div>";
      })
      .join("");
    document.getElementById("compliance").textContent =
      s.avg_compliance == null ? "—" : s.avg_compliance;

    const parts = [
      ["Exact", s.Exact || 0, "var(--ok)"],
      ["Minor", s.Minor || 0, "var(--warn)"],
      ["Major", s.Major || 0, "var(--bad)"],
      ["Unknown", s.Unknown || 0, "var(--unknown)"],
    ];
    document.getElementById("riskbar").innerHTML = parts
      .map(function (p) {
        return '<i style="width:' + (100 * p[1]) / total + "%;background:" + p[2] + '"></i>';
      })
      .join("");
    document.getElementById("risklegend").innerHTML = parts
      .map(function (p) {
        return "<span><i style='display:inline-block;width:7px;height:7px;border-radius:50%;background:" + p[2] + ";margin-right:5px'></i>" + STATUS[p[0]].label + " " + p[1] + "</span>";
      })
      .join("");

    const supportStats = s.support || null;
    const supportEl = document.getElementById("support-summary");
    if (supportEl) {
      if (supportStats) {
        supportEl.classList.remove("hidden");
        supportEl.innerHTML =
          '<div class="mono-sm" style="margin-bottom:8px">引用支持度 · LLM judge（仅供参考）</div>' +
          '<div class="risklegend">' +
          SUPPORT_ORDER.map(function (k) {
            const label = k === "not_checked" ? "未检测" : (SUPPORT[k] ? SUPPORT[k].label : k);
            return "<span>" + label + " " + (supportStats[k] || 0) + "</span>";
          }).join("") +
          "</div>";
      } else {
        supportEl.classList.add("hidden");
      }
    }

    const chips = [["all", "全部", s.total || 0]].concat(
      ["Exact", "Minor", "Major", "Unknown"].map(function (k) {
        return [k, STATUS[k].label, s[k] || 0];
      })
    );
    const chipEl = document.getElementById("chips");
    chipEl.innerHTML = chips
      .map(function (c) {
        return '<button class="chip' + (state.filter === c[0] ? " on" : "") + '" data-filter="' + c[0] + '">' + c[1] + " " + c[2] + "</button>";
      })
      .join("");
    chipEl.querySelectorAll(".chip").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.filter = btn.dataset.filter;
        render(data);
        apply(data);
      });
    });

    const search = document.getElementById("search");
    search.addEventListener("input", function () {
      state.q = search.value.trim().toLowerCase();
      apply(data);
    });
    document.getElementById("sort").addEventListener("change", function (e) {
      state.sort = e.target.value;
      apply(data);
    });
    document.getElementById("view").addEventListener("change", function (e) {
      state.view = e.target.value;
      apply(data);
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && document.activeElement !== search) {
        e.preventDefault();
        search.focus();
      } else if (e.key === "Escape") {
        search.value = "";
        state.q = "";
        apply(data);
      }
    });

    apply(data);
  }

  function matches(item, data) {
    if (state.filter !== "all") {
      const st = (item.verify && item.verify.status) || "Unknown";
      if (st !== state.filter) return false;
    }
    if (!state.q) return true;
    const p = item.parsed || {};
    const hay = [
      p.title,
      (p.authors || []).join(" "),
      p.venue,
      p.year,
      item.raw,
    ]
      .join(" ")
      .toLowerCase();
    return hay.indexOf(state.q) !== -1;
  }

  function apply(data) {
    const items = (data.references || []).filter(function (it) {
      return matches(it, data);
    });
    if (state.sort === "risk") {
      items.sort(function (a, b) {
        return (RISK[(b.verify && b.verify.status) || "Unknown"] || 0) - (RISK[(a.verify && a.verify.status) || "Unknown"] || 0);
      });
    } else if (state.sort === "compliance") {
      items.sort(function (a, b) {
        return ((a.compliance && a.compliance.score) || 0) - ((b.compliance && b.compliance.score) || 0);
      });
    } else {
      items.sort(function (a, b) {
        return (a.index || 0) - (b.index || 0);
      });
    }

    document.getElementById("ref-empty").classList.toggle("hidden", items.length > 0);
    document.getElementById("ref-list").classList.toggle("hidden", state.view !== "cards" || items.length === 0);
    document.getElementById("ref-table-wrap").classList.toggle("hidden", state.view !== "table" || items.length === 0);

    if (state.view === "cards") renderCards(items);
    else renderTable(items);
  }

  function renderCards(items) {
    document.getElementById("ref-list").innerHTML = items
      .map(function (item) {
        const p = item.parsed || {};
        const v = item.verify || {};
        const c = item.compliance || {};
        const st = STATUS[v.status] || STATUS.Unknown;
        const best = v.best || {};
        const url = best.url || (best.doi ? "https://doi.org/" + best.doi : "");
        const issues = (c.issues || [])
          .map(function (i) {
            return '<li class="' + esc(i.level) + '">' + esc(i.message) + (i.suggestion ? '<span class="sugg">建议：' + esc(i.suggestion) + "</span>" : "") + "</li>";
          })
          .join("");
        const evidence = [
          "标题相似度 " + (v.title_sim == null ? "—" : Number(v.title_sim).toFixed(2)),
          "年份 " + (v.year_match ? "一致" : "不一致/未知"),
          "作者匹配 " + (v.author_match == null ? "—" : Number(v.author_match).toFixed(2)),
        ];
        if (url) evidence.push('<a href="' + esc(url) + '" target="_blank" rel="noopener">查看证据</a>');
        const sup = item.support;
        const supInfo = sup ? SUPPORT[sup.label] : null;
        const supPill = '<span class="pill ' + (supInfo ? supInfo.cls : "unknown") + '"><i></i>支持度 ' + (supInfo ? supInfo.label : "未检测") + "</span>";
        const supBlock = supInfo
          ? '<div class="ref-raw" style="margin-top:8px">引用句：' + esc(sup.claim || "") + "</div>" +
            '<div class="ref-evidence">判定理由：' + esc(sup.reason || "") +
            (sup.evidence ? " · 证据：" + esc(sup.evidence) : "") + "</div>"
          : "";
        return (
          '<article class="ref ' + st.cls + '">' +
            '<div class="ref-head">' +
              '<span class="ref-idx">[' + (item.index || "") + "]</span>" +
              '<span class="pill ' + st.cls + '"><i></i>' + st.label + "</span>" +
              supPill +
              '<span class="ref-title">' + esc(p.title || short(item.raw, 80)) + "</span>" +
              '<span class="mono-sm">合规 ' + (c.score == null ? "—" : c.score) + "/100</span>" +
            "</div>" +
            '<div class="ref-meta">' + esc((p.authors || []).join(", ") || "（未解析作者）") + " · " + esc(p.year || "") + " · " + esc(p.venue || "") + "</div>" +
            '<div class="ref-raw">' + esc(item.raw) + "</div>" +
            '<div class="ref-evidence">' + evidence.map(function (x) { return "<span>" + x + "</span>"; }).join("") + "</div>" +
            supBlock +
            (issues ? '<ul class="issues">' + issues + "</ul>" : '<div class="clean">新国标字段检查未发现问题</div>') +
          "</article>"
        );
      })
      .join("");
  }

  function renderTable(items) {
    const tbody = document.querySelector("#ref-table tbody");
    if (!tbody) return;
    tbody.innerHTML = items
      .map(function (item) {
        const p = item.parsed || {};
        const v = item.verify || {};
        const c = item.compliance || {};
        const st = STATUS[v.status] || STATUS.Unknown;
        const sup = item.support;
        const supInfo = sup ? SUPPORT[sup.label] : null;
        return (
          "<tr>" +
            "<td class='mono-sm'>" + (item.index || "") + "</td>" +
            '<td><span class="pill ' + st.cls + '"><i></i>' + st.label + "</span></td>" +
            '<td><span class="pill ' + (supInfo ? supInfo.cls : "unknown") + '">' + (supInfo ? supInfo.label : "—") + "</span></td>" +
            "<td>" + esc(short(p.title || item.raw, 60)) + "</td>" +
            "<td class='mono-sm'>" + esc(p.year || "") + "</td>" +
            "<td class='mono-sm'>" + esc(short(p.venue || "", 24)) + "</td>" +
            "<td class='mono-sm'>" + (c.score == null ? "—" : c.score) + "</td>" +
          "</tr>"
        );
      })
      .join("");
  }
})();
