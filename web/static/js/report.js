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
    Unverified: { label: "未找到匹配", cls: "warn", color: "var(--warn)" },
    Unknown: { label: "无法核验", cls: "unknown", color: "var(--unknown)" },
  };
  const RISK = { Major: 3, Unverified: 2, Minor: 2, Unknown: 1, Exact: 0 };
  const SUPPORT = {
    support: { label: "支持", cls: "ok" },
    partial: { label: "部分支持", cls: "warn" },
    contradict: { label: "矛盾", cls: "bad" },
    no_evidence: { label: "无证据", cls: "unknown" },
    not_checked: { label: "未检测", cls: "unknown" },
  };
  const SUPPORT_ORDER = ["support", "partial", "contradict", "no_evidence", "not_checked"];
  const state = { filter: "all", q: "", sort: "index", view: "cards", needs: false, fmt: false, sup: "" };

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

  function renderInputMeta(data) {
    const el = document.getElementById("input-meta");
    if (!el) return;
    const meta = data.input_meta;
    if (!meta || !meta.method) {
      el.classList.add("hidden");
      return;
    }
    const methodLabels = {
      ocr: "OCR 识别（扫描件）",
      "pdf-text": "PDF 文字层",
      docx: "Word 正文",
      text: "文本",
    };
    const bits = [methodLabels[meta.method] || meta.method];
    if (meta.pages) bits.push(meta.pages + " 页");
    if (meta.chars) bits.push(meta.chars.toLocaleString() + " 字符");
    const warnings = (meta.warnings || []).filter(Boolean);
    const hasOcrWarning = warnings.some(function (w) { return String(w).indexOf("OCR") >= 0; });
    el.classList.remove("hidden");
    el.innerHTML =
      '<div class="mono-sm">文字来源：<b>' + esc(bits.join(" · ")) + "</b></div>" +
      (meta.ocr && !hasOcrWarning
        ? '<div class="mono-sm" style="margin-top:6px;color:var(--warn)">扫描件经 OCR 抽取：识别错字会传递到引文解析与核验结果，请对照原文复核后再采用本报告结论。</div>'
        : "") +
      (warnings.length
        ? '<ul class="mono-sm" style="margin:8px 0 0 18px;color:var(--muted)">' +
          warnings.map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("") +
          "</ul>"
        : "");
  }

  function renderVerdict(data) {
    const box = document.getElementById("verdict");
    if (!box) return;
    const refs = data.references || [];
    const byStatus = function (status) {
      return refs.filter(function (r) {
        return ((r.verify && r.verify.status) || "Unknown") === status;
      }).map(function (r) { return r.index; });
    };
    const major = byStatus("Major");
    const minor = byStatus("Minor");
    const unverified = byStatus("Unverified");
    const unknown = byStatus("Unknown");
    const fmtErrors = refs.filter(hasFormatError).map(function (r) { return r.index; });
    const supportRefs = refs.filter(function (r) {
      const label = (r.support && r.support.label) || "";
      return label === "contradict" || label === "partial";
    });
    const contradictRefs = supportRefs.filter(function (r) {
      return (r.support && r.support.label) === "contradict";
    });
    const items = [];
    const idx = function (list) {
      const head = list.slice(0, 5).map(function (i) { return "#" + i; }).join("、");
      return list.length > 5 ? head + " 等" : head;
    };
    if (contradictRefs.length) {
      items.push(
        "<b>" + contradictRefs.length + "</b> 条引用与被引原文矛盾（" +
        idx(contradictRefs.map(function (r) { return r.index; })) + "）——正文论点可能站不住，优先核对"
      );
    }
    if (major.length) {
      items.push("<b>" + major.length + "</b> 条疑似虚构/错配（" + idx(major) + "）——优先核对这几条");
    }
    const partialRefs = supportRefs.filter(function (r) {
      return (r.support && r.support.label) === "partial";
    });
    if (partialRefs.length) {
      items.push(
        "<b>" + partialRefs.length + "</b> 条引用仅被原文部分支持（" +
        idx(partialRefs.map(function (r) { return r.index; })) + "）——建议核对表述是否夸大"
      );
    }
    if (minor.length) {
      items.push("<b>" + minor.length + "</b> 条元数据与数据库不一致（年份/卷期/页/作者）");
    }
    if (unverified.length) {
      items.push("<b>" + unverified.length + "</b> 条在公开数据库未找到匹配（不等于造假；可导入本地题录库或人工核对）");
    }
    if (unknown.length) {
      items.push("<b>" + unknown.length + "</b> 条本次无法核验（数据源不可用）");
    }
    const retracted = refs
      .filter(function (r) { return r.verify && r.verify.retracted; })
      .map(function (r) { return r.index; });
    if (retracted.length) {
      items.push(
        "<b>" + retracted.length + "</b> 条文献在 OpenAlex 有撤稿标记（" +
        idx(retracted) + "）——引用前必须核对原文与撤稿声明"
      );
    }
    if (fmtErrors.length) {
      items.push("<b>" + fmtErrors.length + "</b> 条存在格式错误（点上方「格式错误」筛选查看）");
    }
    const cc = data.citation_consistency || {};
    if (cc.numeric_style) {
      const uncited = cc.uncited_numbers || [];
      const missingNums = cc.missing_numbers || [];
      if (uncited.length) {
        items.push(
          "<b>" + uncited.length + "</b> 条参考文献未被正文引用（" +
          idx(uncited) + "）——按顺序编码制应删除或补引"
        );
      }
      if (missingNums.length) {
        items.push(
          "<b>" + missingNums.length + "</b> 个正文引注编号在文献表中不存在（" +
          missingNums.slice(0, 5).map(function (n) { return "[" + n + "]"; }).join("、") + "）"
        );
      }
      if (cc.order_inversions) {
        items.push("正文首次引用顺序与编号有 <b>" + cc.order_inversions + "</b> 处不一致");
      }
    }
    if (!items.length) {
      items.push("未发现疑似虚构、元数据偏差或格式错误；建议仍人工抽查 1–2 条。");
    }
    box.classList.remove("hidden");
    box.innerHTML =
      '<div class="verdict-head mono-sm">体检结论</div><ul class="verdict-list">' +
      items.map(function (text) { return "<li>" + text + "</li>"; }).join("") +
      "</ul>";
  }

  function renderCitationConsistency(data) {
    var el = document.getElementById("citation-consistency");
    if (!el) return;
    var cc = data.citation_consistency || {};
    if (!cc.numeric_style) {
      if (!cc.note) {
        el.classList.add("hidden");
        return;
      }
      el.classList.remove("hidden");
      el.innerHTML =
        '<div class="mono-sm" style="margin-bottom:6px">正文引注一致性</div>' +
        '<div class="mono-sm" style="color:var(--muted)">' + esc(cc.note) + "</div>";
      return;
    }
    var items = [];
    var uncited = cc.uncited_numbers || [];
    var missing = cc.missing_numbers || [];
    if (uncited.length) {
      items.push(
        "<li>参考文献表中未被正文引用：" +
          uncited.slice(0, 20).map(function (n) { return "[" + n + "]"; }).join("、") +
          (uncited.length > 20 ? " 等 " + uncited.length + " 条" : "") +
          "</li>"
      );
    }
    if (missing.length) {
      items.push(
        "<li>正文引注编号在文献表中不存在：" +
          missing.map(function (n) { return "[" + n + "]"; }).join("、") +
          "</li>"
      );
    }
    if (cc.order_inversions) {
      items.push(
        "<li>首次引用顺序与编号不一致：" + cc.order_inversions +
          " 处（顺序编码制应按正文首次引用顺序编号）</li>"
      );
    }
    if (!items.length) {
      items.push('<li class="ok">正文引注与参考文献表一致</li>');
    }
    el.classList.remove("hidden");
    el.innerHTML =
      '<div class="mono-sm" style="margin-bottom:6px">正文引注一致性 · 数字引注 ' +
      (cc.citations || 0) + " 处 / 覆盖 " + (cc.distinct_numbers || 0) +
      ' 个编号</div><ul class="verdict-list" style="margin:0;padding-left:18px;font-size:13px;line-height:1.8">' +
      items.join("") + "</ul>";
  }

  function renderReviewSummary(data) {
    const el = document.getElementById("review-summary");
    if (!el) return;
    const r = data.review_summary;
    if (!r || !r.decision) return;
    const color = r.level === "blocker" ? "var(--bad)" : r.level === "minor" ? "var(--warn)" : "var(--ok)";
    const issues = (r.issues || []).slice(0, 8).map(function (x) {
      return "<li>" +
        (x.index == null ? "" : "<b>[" + x.index + "]</b> ") +
        "<b>" + esc(x.kind || "") + "</b>：" + esc(x.text || "") + "</li>";
    }).join("");
    el.classList.remove("hidden");
    el.innerHTML =
      '<div class="mono-sm">审稿视角 · 自动汇总（仅供参考）</div>' +
      '<div style="font-size:15px;font-weight:600;margin:6px 0 4px;color:' + color + '">' +
      esc(r.decision) + "</div>" +
      '<div class="mono-sm" style="color:var(--muted);margin-bottom:6px">' +
      "阻断级问题 " + (r.blockers || 0) + " 项 · 提示级问题 " + (r.minor_issues || 0) +
      " 项 · 已判定支持度 " + (r.support_judged || 0) + " 条" +
      (r.retracted ? " · 撤稿标记 " + r.retracted + " 条" : "") + "</div>" +
      (issues
        ? '<ul class="verdict-list" style="margin:0;padding-left:18px;font-size:13px;line-height:1.8">' + issues + "</ul>"
        : "") +
      '<div class="mono-sm" style="color:var(--muted);margin-top:6px">' + esc(r.note || "") + "</div>";
  }

  function renderFigureChecks(data) {
    const el = document.getElementById("figure-checks");
    if (!el) return;
    const blocks = data.figure_checks || [];
    if (!blocks.length) return;
    const rows = blocks.map(function (b) {
      const items = (b.items || []).map(function (it) {
        const verdict = it.verdict || (it.ok ? "supported" : "error");
        const cls = verdict === "supported" ? "ok" : verdict === "contradicted" ? "bad" : "warn";
        return '<li><span class="chip ' + cls + '">' + esc(verdict) + "</span> " +
          esc(it.claim || "") +
          (it.reason ? '<span class="mono-sm" style="color:var(--muted)"> · ' + esc(it.reason) + "</span>" : "") +
          (it.error ? '<span class="mono-sm" style="color:var(--muted)"> · ' + esc(it.error) + "</span>" : "") +
          "</li>";
      }).join("");
      return '<div style="margin-top:8px"><b>图/表 ' + esc(b.number || "") + "</b> · 第 " +
        esc(b.page == null ? "?" : b.page) + " 页" +
        (b.caption ? ' <span class="mono-sm" style="color:var(--muted)">' + esc(b.caption) + "</span>" : "") +
        (b.error ? '<div class="mono-sm" style="color:var(--warn)">' + esc(b.error) + "</div>" : "") +
        '<ul class="verdict-list" style="margin:4px 0 0;padding-left:18px">' + items + "</ul></div>";
    }).join("");
    el.classList.remove("hidden");
    el.innerHTML =
      '<div class="mono-sm">正文图表结论抽检（可选 · 视觉模型）</div>' +
      '<div class="mono-sm" style="color:var(--muted);margin:4px 0 2px">' +
      "每条结论对照自动定位的图页判断“支持 / 不支持 / 信息不足”；不替代人工读图，也不判断数据是否造假。</div>" +
      rows;
  }

  function render(data) {
  window.__reportData = data;
    renderInputMeta(data);
    renderVerdict(data);
    renderReviewSummary(data);
    renderFigureChecks(data);
    renderCitationConsistency(data);
    const s = data.stats || {};
    const total = s.total || 1;

    const stats = [
      ["参考文献", s.total || 0, ""],
      ["真实一致", s.Exact || 0, "ok"],
      ["元数据偏差", s.Minor || 0, "warn"],
      ["疑似虚构/错配", s.Major || 0, "bad"],
      ["未找到匹配", s.Unverified || 0, "warn"],
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
      ["Unverified", s.Unverified || 0, "#c9a86a"],
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
    const supportMeta = s.support_meta || {};
    const supportEl = document.getElementById("support-summary");
    if (supportEl) {
      if (supportStats) {
        supportEl.classList.remove("hidden");
        const notes = [];
        if (supportMeta.candidates != null) {
          notes.push("可判定 " + supportMeta.candidates + " 条");
        }
        if (supportMeta.judged != null) {
          notes.push("本次已判定 " + supportMeta.judged + " 条（上限 " + supportMeta.cap + "）");
        }
        if (supportMeta.skipped_by_cap) {
          notes.push("因上限跳过 " + supportMeta.skipped_by_cap + " 条");
        }
        if (supportMeta.skipped_no_abstract) {
          notes.push(
            "命中记录缺摘要 " + supportMeta.skipped_no_abstract +
            " 条（判断引用是否被支持需要摘要；导出题录时勾选摘要再导入即可）"
          );
        }
        if (supportMeta.skipped_unreliable_match) {
          notes.push(
            "题录匹配度不足 " + supportMeta.skipped_unreliable_match +
            " 条（摘要可能属于别的论文，为避免误判未做支持度判定）"
          );
        }
        if (!supportMeta.judge_available) {
          notes.push("未配置 LLM judge，全部为「未检测」");
        }
        supportEl.innerHTML =
          '<div class="mono-sm" style="margin-bottom:8px">引用支持度 · LLM judge（仅供参考）</div>' +
          '<div class="risklegend">' +
          SUPPORT_ORDER.map(function (k) {
            const label = k === "not_checked" ? "未检测" : (SUPPORT[k] ? SUPPORT[k].label : k);
            return "<span>" + label + " " + (supportStats[k] || 0) + "</span>";
          }).join("") +
          "</div>" +
          (notes.length
            ? '<div class="mono-sm" style="margin-top:8px;color:var(--muted)">' + notes.join(" · ") + "</div>"
            : "");
      } else {
        supportEl.classList.add("hidden");
      }
    }

    const libraryEl = document.getElementById("library-summary");
    if (libraryEl) {
      const entries = s.library_entries || 0;
      const hits = s.library_hits || 0;
      if (entries) {
        libraryEl.classList.remove("hidden");
        libraryEl.innerHTML =
          '<div class="mono-sm">本地题录库：<b>' + entries + "</b> 条 · 本次命中 <b>" + hits + "</b> 条" +
          (hits ? "" : "（没有命中：可到「题录库」追加对应年份的导出）") +
          " · <a href=\"/library\">管理题录库</a></div>";
      } else {
        libraryEl.classList.add("hidden");
      }
    }

    const formatErrors = (data.references || []).filter(hasFormatError).length;
    const supportCounts = s.support || null;
    const chips = [["all", "全部", s.total || 0]].concat(
      ["Exact", "Minor", "Major", "Unverified", "Unknown"].map(function (k) {
        return [k, STATUS[k].label, s[k] || 0];
      })
    );
    const chipEl = document.getElementById("chips");
    const supportChips = [];
    if (supportCounts) {
      if (supportCounts.contradict) {
        supportChips.push(
          '<button class="chip chip-sup' + (state.sup === "contradict" ? " on" : "") +
          '" data-sup="contradict" title="只显示与引用句矛盾的条目">支持度矛盾 ' + supportCounts.contradict + "</button>"
        );
      }
      if (supportCounts.partial) {
        supportChips.push(
          '<button class="chip chip-sup' + (state.sup === "partial" ? " on" : "") +
          '" data-sup="partial" title="只显示仅被部分支持的条目">部分支持 ' + supportCounts.partial + "</button>"
        );
      }
    }
    chipEl.innerHTML =
      chips
        .map(function (c) {
          return '<button class="chip' + (state.filter === c[0] && !state.needs && !state.fmt && !state.sup ? " on" : "") + '" data-filter="' + c[0] + '">' + c[1] + " " + c[2] + "</button>";
        })
        .join("") +
      supportChips.join("") +
      '<button class="chip chip-needs' + (state.needs ? " on" : "") + '" data-needs="1" title="只显示疑似虚构/元数据偏差/格式有问题/引用矛盾或部分支持的条目">仅看需处理</button>' +
      '<button class="chip' + (state.fmt ? " on" : "") + '" data-fmt="1" title="只显示存在 error 级格式问题的条目">格式错误 ' + formatErrors + "</button>";
    chipEl.querySelectorAll(".chip").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (btn.dataset.needs) {
          state.needs = !state.needs;
          state.fmt = false;
          state.sup = "";
        } else if (btn.dataset.fmt) {
          state.fmt = !state.fmt;
          state.needs = false;
          state.sup = "";
        } else if (btn.dataset.sup) {
          state.sup = state.sup === btn.dataset.sup ? "" : btn.dataset.sup;
          state.needs = false;
          state.fmt = false;
          state.filter = "all";
        } else {
          state.filter = btn.dataset.filter;
          state.needs = false;
          state.fmt = false;
          state.sup = "";
        }
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
      const tag = (document.activeElement && document.activeElement.tagName) || "";
      if (e.key === "/" && document.activeElement !== search) {
        e.preventDefault();
        search.focus();
      } else if (e.key === "Escape") {
        search.value = "";
        state.q = "";
        apply(data);
      } else if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        return;
      } else if (e.key === "f") {
        state.needs = !state.needs;
        state.sup = "";
        render(data);
        apply(data);
      } else if (e.key === "t") {
        state.view = state.view === "cards" ? "table" : "cards";
        const viewSel = document.getElementById("view");
        if (viewSel) viewSel.value = state.view;
        apply(data);
      } else if (e.key === "p") {
        window.print();
      } else if (e.key >= "1" && e.key <= "5") {
        const order = ["all", "Exact", "Minor", "Major", "Unverified"];
        state.filter = order[Number(e.key) - 1];
        state.needs = false;
        render(data);
        apply(data);
      }
    });

    const copyBtn = document.getElementById("copy-suggestions");
    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        const text = suggestionText(data);
        window.CiteGuard.copyText(text).then(function (ok) {
          window.CiteGuard.toast(ok ? "修改建议已复制到剪贴板" : "复制失败，请手动选择文本");
        });
      });
    }
    const printBtn = document.getElementById("print-report");
    if (printBtn) printBtn.addEventListener("click", function () { window.print(); });

    const copyRefsBtn = document.getElementById("copy-refs");
    if (copyRefsBtn) {
      copyRefsBtn.addEventListener("click", function () {
        const lines = (data.formatted_reference_list || [])
          .filter(function (x) { return x && x.entry; })
          .map(function (x) { return "[" + (x.index == null ? "" : x.index) + "] " + x.entry; });
        if (!lines.length) {
          window.CiteGuard.toast("本次没有可导出的参考文献表");
          return;
        }
        window.CiteGuard.copyText(lines.join("\n")).then(function (ok) {
          window.CiteGuard.toast(ok ? "参考文献表已复制（按原文重排，请核对）" : "复制失败，请手动选择文本");
        });
      });
    }

    document.addEventListener("click", function (ev) {
      const evBtn = ev.target && ev.target.closest ? ev.target.closest(".ref-evidence") : null;
      if (evBtn) {
        openEvidence(Number(evBtn.dataset.pos || 0));
        return;
      }
      if (ev.target && ev.target.closest && ev.target.closest("[data-close]")) {
        closeEvidence();
        return;
      }
      const btn = ev.target && ev.target.closest ? ev.target.closest(".ref-to-library") : null;
      if (!btn) return;
      const payload = {
        title: btn.getAttribute("data-title") || "",
        authors: btn.getAttribute("data-authors") || "",
        year: btn.getAttribute("data-year") || "",
        venue: btn.getAttribute("data-venue") || "",
        doi: btn.getAttribute("data-doi") || "",
      };
      btn.disabled = true;
      fetch("/api/library/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok) throw new Error((res.d && res.d.detail) || "加入失败");
          btn.textContent = res.d.added ? "已加入题录库" : "题录库中已有";
          window.CiteGuard.toast(res.d.added ? "已加入题录库，后续核验会自动使用" : "题录库中已有同题名记录");
        })
        .catch(function () {
          btn.disabled = false;
          window.CiteGuard.toast("加入失败，请稍后重试");
        });
    });

    apply(data);
  }

  function hasFormatError(item) {
    const issues = (item.compliance && item.compliance.issues) || [];
    return issues.some(function (i) { return i.level === "error"; });
  }

  function needsAttention(item) {
    const status = (item.verify && item.verify.status) || "Unknown";
    const sup = (item.support && item.support.label) || "";
    if (sup === "contradict" || sup === "partial") return true;
    if (status !== "Exact") return true;
    return hasFormatError(item);
  }

  function riskScore(item) {
    const status = (item.verify && item.verify.status) || "Unknown";
    const sup = (item.support && item.support.label) || "";
    let score = RISK[status] || 0;
    // A citation whose source contradicts the sentence is more urgent than a
    // metadata drift: the paper's argument, not just the entry, may be wrong.
    if (sup === "contradict") score += 4;
    else if (sup === "partial") score += 1;
    return score;
  }

  function suggestionText(data) {
    const counts = (data.stats && data.stats.support) || {};
    const lines = [
      "# 引证卫士修改建议",
      "",
      "参考文献 " + ((data.stats && data.stats.total) || 0) + " 条；支持度：" +
        ["support", "partial", "contradict", "no_evidence", "not_checked"]
          .map(function (k) { return k + " " + (counts[k] || 0); })
          .join(" / "),
      "",
    ];
    (data.references || []).forEach(function (item) {
      const p = item.parsed || {};
      const v = item.verify || {};
      const c = item.compliance || {};
      const sup = item.support || {};
      const supLabel = sup.label || "";
      const issues = (c.issues || []).filter(function (i) { return i.level === "error"; });
      const status = (v.status || "Unknown");
      const supportProblem = supLabel === "contradict" || supLabel === "partial";
      if (status === "Exact" && !issues.length && !supportProblem) return;
      const head = "[" + (item.index || "") + "] " + (p.title || item.raw || "");
      lines.push(head);
      if (status !== "Exact") {
        lines.push("  状态：" + status + (v.mismatches && v.mismatches.length ? "（" + v.mismatches.join(", ") + "）" : ""));
      }
      if (supportProblem) {
        lines.push(
          "  支持度：" + (supLabel === "contradict" ? "与引用句矛盾" : "仅部分支持") +
          (sup.reason ? " —— " + sup.reason : "")
        );
        if (sup.evidence) lines.push("  证据：" + sup.evidence);
      }
      issues.forEach(function (i) {
        lines.push("  格式：" + i.message + (i.suggestion ? " → " + i.suggestion : ""));
      });
      lines.push("");
    });
    return lines.join("\n");
  }

  function matches(item, data) {
    if (state.fmt && !hasFormatError(item)) return false;
    if (state.needs && !needsAttention(item)) return false;
    if (state.sup) {
      const label = (item.support && item.support.label) || "";
      if (label !== state.sup) return false;
    }
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
        return riskScore(b) - riskScore(a);
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

  function openEvidence(pos) {
    const items = window.__reportItems || [];
    const item = items[pos];
    if (!item) return;
    const v = item.verify || {};
    const p = item.parsed || {};
    const rows = [
      ["序号", item.index],
      ["核验状态", v.status],
      ["题名", p.title],
      ["作者", (p.authors || []).join("; ")],
      ["年份", p.year],
      ["来源", p.venue],
      ["DOI", p.doi],
      ["数据源", (v.sources || []).join(", ")],
      ["来源一致数", v.source_agreement],
      ["标题相似度", v.title_sim],
      ["作者匹配", v.author_match],
      ["比对题名", (v.best || {}).title],
      ["比对来源", [(v.best || {}).source, (v.best || {}).doi, (v.best || {}).venue].filter(Boolean).join(" · ")],
      ["备注", (v.notes || []).join("；")],
      ["字段差异", (v.mismatches || []).join("；")],
    ];
    const visible = rows
      .filter(function (r) { return r[1] !== undefined && r[1] !== null && r[1] !== ""; })
      .map(function (r) {
        return '<div class="drawer-row"><span class="drawer-key">' + esc(r[0]) + "</span><span>" + esc(String(r[1])) + "</span></div>";
      })
      .join("");
    const body = document.getElementById("drawer-body");
    const title = document.getElementById("drawer-title");
    if (title) title.textContent = "[" + (item.index || "") + "] 条目证据";
    if (body) {
      body.innerHTML =
        visible +
        (item.suggested_entry ? "<h4>建议条目</h4><pre>" + esc(item.suggested_entry) + "</pre>" : "") +
        (item.support ? "<h4>支持度判定</h4><pre>" + esc(JSON.stringify(item.support, null, 2)) + "</pre>" : "") +
        "<h4>原始条目</h4><pre>" + esc(item.raw || "") + "</pre>" +
        "<h4>完整 JSON</h4><pre>" + esc(JSON.stringify(item, null, 2)) + "</pre>";
    }
    const drawer = document.getElementById("evidence-drawer");
    if (drawer) {
      drawer.hidden = false;
      document.body.classList.add("drawer-open");
    }
  }

  function closeEvidence() {
    const drawer = document.getElementById("evidence-drawer");
    if (drawer) drawer.hidden = true;
    document.body.classList.remove("drawer-open");
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeEvidence();
  });

  function renderCards(items) {
    window.__reportItems = items;
    document.getElementById("ref-list").innerHTML = items
      .map(function (item, pos) {
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
        const unmatched = v.status === "Unverified" || v.status === "Unknown";
        const evidence = unmatched
          ? ["数据库中没有足够相似的记录，未做字段比对"]
          : [
              "标题相似度 " + (v.title_sim == null ? "—" : Number(v.title_sim).toFixed(2)),
              "年份 " + (v.year_match ? "一致" : "不一致/未知"),
              "作者匹配 " + (v.author_match == null ? "—" : Number(v.author_match).toFixed(2)),
            ];
        if (url && !unmatched) evidence.push('<a href="' + esc(url) + '" target="_blank" rel="noopener">查看证据</a>');
        if (v.doi_status === "exists_elsewhere") {
          evidence.push('<a href="https://doi.org/' + encodeURIComponent(p.doi || "") + '" target="_blank" rel="noopener">DOI 原文页</a>');
        }
        if (unmatched) {
          const query = encodeURIComponent((p.title || item.raw || "").slice(0, 80));
          evidence.push(
            '<a href="https://xueshu.baidu.com/s?wd=' + query + '" target="_blank" rel="noopener">百度学术</a>',
            '<a href="https://scholar.google.com/scholar?q=' + query + '" target="_blank" rel="noopener">Google Scholar</a>',
            '<a href="https://api.crossref.org/works?query.bibliographic=' + query + '" target="_blank" rel="noopener">Crossref</a>'
          );
        }
        const sup = item.support;
        const supInfo = sup ? SUPPORT[sup.label] : null;
        const supPill = '<span class="pill ' + (supInfo ? supInfo.cls : "unknown") + '"><i></i>支持度 ' + (supInfo ? supInfo.label : "未检测") + "</span>";
        const sources = v.sources || [];
        const isWeb = sources.some(function (x) { return x.indexOf("url:") === 0; });
        if (isWeb) {
          evidence.length = 0;
          evidence.push("网页引文：已检查链接可达性与页面标题");
          if (v.title_sim != null) evidence.push("页面标题相似度 " + Number(v.title_sim).toFixed(2));
          if (p.url) evidence.push('<a href="' + esc(p.url) + '" target="_blank" rel="noopener">打开引文链接</a>');
          if (unmatched) {
            const webQuery = encodeURIComponent((p.title || item.raw || "").slice(0, 80));
            evidence.push(
              '<a href="https://xueshu.baidu.com/s?wd=' + webQuery + '" target="_blank" rel="noopener">百度学术</a>',
              '<a href="https://scholar.google.com/scholar?q=' + webQuery + '" target="_blank" rel="noopener">Google Scholar</a>'
            );
          }
        }
        const urlPills = [];
        if (v.source_agreement >= 2) {
          urlPills.push('<span class="pill ok" title="OpenAlex / Crossref / arXiv / DataCite 等独立索引对题名与年份的结论一致"><i></i>' +
            v.source_agreement + ' 个来源一致</span>');
        }
        if (sources.indexOf("url:live") !== -1 && v.status === "Exact") {
          urlPills.push('<span class="pill ok"><i></i>网页链接已核</span>');
        }
        if (sources.indexOf("url:dead") !== -1 || sources.indexOf("url:blocked") !== -1) {
          urlPills.push('<span class="pill warn"><i></i>链接失效/受限</span>');
        }
        if (sources.indexOf("url:mismatch") !== -1) {
          urlPills.push('<span class="pill warn"><i></i>页面标题不一致</span>');
        }
        const localPill = sources.indexOf("local") !== -1
          ? '<span class="pill ok"><i></i>本地题录库</span>'
          : "";
        const retractPill = v.retracted
          ? '<span class="pill warn" title="OpenAlex 撤稿标记；引用前请核对原文与撤稿声明"><i></i>该文献已撤稿</span>'
          : "";
        const provPills = [];
        if (sources.indexOf("doi:landing") !== -1) {
          provPills.push('<span class="pill warn"><i></i>中国 DOI 平台 · 卷期页未核对</span>');
        }
        if (sources.indexOf("doi:datacite") !== -1) {
          provPills.push('<span class="pill warn"><i></i>DataCite · 卷期页未核对</span>');
        }
        if (provPills.length) {
          evidence.push("元数据来源：" + (sources.indexOf("doi:landing") !== -1 ? "中国 DOI 平台" : "DataCite") + "（题名/作者可核，卷期页可能缺）");
        }
        const supBlock = supInfo
          ? '<div class="ref-raw" style="margin-top:8px">引用句：' + esc(sup.claim || "") + "</div>" +
            '<div class="ref-evidence">判定理由：' + esc(sup.reason || "") +
            (sup.evidence ? " · 证据：" + esc(sup.evidence) : "") + "</div>"
          : "";
        const suggestBlock = item.suggested_entry
          ? '<div class="ref-suggest">' +
              '<div class="mono-sm">按数据库元数据生成的规范条目（核对后替换）</div>' +
              '<code>' + esc(item.suggested_entry) + "</code>" +
              '<button class="btn btn-sm btn-ghost ref-copy" type="button" data-copy="' + esc(item.suggested_entry) + '">复制</button>' +
            "</div>"
          : "";
        const manualTitle = (item.parsed && item.parsed.title) || "";
        const addToLibBtn = manualTitle
          ? ' <button class="btn btn-sm btn-ghost ref-to-library" type="button" data-title="' + esc(manualTitle) +
            '" data-authors="' + esc((p.authors || []).join("；")) + '" data-year="' + esc(p.year || "") +
            '" data-venue="' + esc(p.venue || "") + '" data-doi="' + esc(p.doi || "") + '">加入题录库</button>'
          : "";
        const manualLinks = (v.status === "Unverified" && manualTitle)
          ? '<div class="ref-note">人工核对入口：<a style="color:var(--accent)" target="_blank" rel="noopener" href="https://kns.cnki.net/kns8s/defaultresult/index?kw=' +
              encodeURIComponent(manualTitle) + '">知网检索</a> · <a style="color:var(--accent)" target="_blank" rel="noopener" href="https://xueshu.baidu.com/s?wd=' +
              encodeURIComponent(manualTitle) + '">百度学术</a> · <a style="color:var(--accent)" target="_blank" rel="noopener" href="https://s.wanfangdata.com.cn/paper?q=' +
              encodeURIComponent(manualTitle) + '">万方</a> · <a style="color:var(--accent)" target="_blank" rel="noopener" href="https://ss.zhizhen.com/s?sw=' +
              encodeURIComponent(manualTitle) + '">超星发现</a>' +
              (/[\u4e00-\u9fff]/.test(manualTitle)
                ? "（中文文献不在 OpenAlex/Crossref 覆盖范围，开放索引查不到属正常，需人工核对）"
                : "") +
              addToLibBtn +
            "</div>"
          : "";
        const webNote = isWeb && v.status === "Unverified"
          ? (sources.indexOf("url:dead") !== -1
              ? "引文给出的网页链接已失效（可能链接腐化或站点迁移）：请核对最新地址；链接失效不等同于伪造。"
              : sources.indexOf("url:blocked") !== -1
                ? "网页链接需要登录或拒绝访问，无法自动核验，请人工打开核对。"
                : sources.indexOf("url:mismatch") !== -1
                  ? "网页链接可访问，但页面标题与引文题名不一致，请核对是否同一页面。"
                  : "网页链接可访问，但返回内容不是可读网页（PDF/附件），请人工打开核对。")
          : "";
        const noteBlock = webNote
          ? '<div class="ref-note">' + esc(webNote) + "</div>"
          : (v.status === "Unverified" || v.status === "Unknown")
            ? '<div class="ref-note">' +
                (v.status === "Unverified"
                  ? "没有找到足够相似的数据库记录：可能是该文献未被 OpenAlex / Crossref 收录，也可能是引文本身有误。请用上面的链接人工核对后再改。"
                  : "本次核验没有拿到数据源的有效响应（网络或数据源问题），不能据此判断引文真伪。") +
              "</div>"
            : "";
        return (
          '<article class="ref ' + st.cls + '">' +
            '<div class="ref-head">' +
              '<span class="ref-idx">[' + (item.index || "") + "]</span>" +
              '<span class="pill ' + st.cls + '"><i></i>' + st.label + "</span>" +
              supPill +
              localPill +
              retractPill +
              provPills.join("") +
              urlPills.join("") +
              '<button class="btn btn-sm btn-ghost ref-evidence" type="button" data-pos="' + pos + '" title="查看该条目的全部证据字段">证据</button>' +
              '<span class="ref-title">' + esc(p.title || short(item.raw, 80)) + "</span>" +
              '<span class="mono-sm">合规 ' + (c.score == null ? "—" : c.score) + "/100</span>" +
            "</div>" +
            '<div class="ref-meta">' + esc((p.authors || []).join(", ") || "（未解析作者）") + " · " + esc(p.year || "") + " · " + esc(p.venue || "") + "</div>" +
            '<div class="ref-raw">' + esc(item.raw) + "</div>" +
            '<div class="ref-evidence">' + evidence.map(function (x) { return "<span>" + x + "</span>"; }).join("") + "</div>" +
            supBlock +
            noteBlock +
            manualLinks +
            (issues ? '<ul class="issues">' + issues + "</ul>" : '<div class="clean">本规则集未发现字段/标点问题（不覆盖页码连接号、卷期互换等排版与语义错误）</div>') +
            suggestBlock +
          "</article>"
        );
      })
      .join("");

    document.querySelectorAll(".ref-evidence").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openEvidence(Number(btn.dataset.pos || 0));
      });
    });

    document.querySelectorAll(".ref-copy").forEach(function (btn) {
      btn.addEventListener("click", function () {
        window.CiteGuard.copyText(btn.dataset.copy || "").then(function (ok) {
          window.CiteGuard.toast(ok ? "已复制规范条目" : "复制失败，请手动选择");
        });
      });
    });
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
            '<td><span class="pill ' + st.cls + '"><i></i>' + st.label + "</span>" +
              (v.retracted ? ' <span class="pill warn">撤稿</span>' : "") + "</td>" +
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

/* Export the references that still need human checking (Unverified/Unknown). */
function csvCell(value) {
  const text = String(value == null ? "" : value).replace(/"/g, '""');
  return '"' + text + '"';
}

function manualCsv() {
  const data = window.__reportData || {};
  const rows = [["序号", "状态", "题名", "作者", "年份", "期刊/来源", "引文原文", "人工检索"]];
  (data.references || []).forEach(function (item) {
    const v = item.verify || {};
    if (v.status !== "Unverified" && v.status !== "Unknown") return;
    const p = item.parsed || {};
    const title = p.title || "";
    const links = [
      "https://kns.cnki.net/kns8s/defaultresult/index?kw=" + encodeURIComponent(title),
      "https://s.wanfangdata.com.cn/paper?q=" + encodeURIComponent(title),
      "https://ss.zhizhen.com/s?sw=" + encodeURIComponent(title),
      "https://xueshu.baidu.com/s?wd=" + encodeURIComponent(title),
    ].join(" ");
    rows.push([
      item.index || "", v.status || "", title, (p.authors || []).join("; "),
      p.year || "", p.venue || "", item.raw || "", links,
    ]);
  });
  const csv = "\ufeff" + rows.map(function (row) { return row.map(csvCell).join(","); }).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "manual-check.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const manualCsvBtn = document.getElementById("manual-csv");
if (manualCsvBtn) {
  manualCsvBtn.addEventListener("click", manualCsv);
}
