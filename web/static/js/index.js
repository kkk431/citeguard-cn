/* Upload / paste / sample / batch interactions for the home page. */
(function () {
  const form = document.getElementById("upload-form");
  if (!form) return;

  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const dzFile = document.getElementById("dz-file");
  const paste = document.getElementById("paste-text");
  const startBtn = document.getElementById("start-btn");
  const sampleBtn = document.getElementById("sample-btn");
  const hint = document.getElementById("upload-hint");
  const batchBox = document.getElementById("batch-results");

  let selectedFiles = [];

  function setFiles(files) {
    selectedFiles = Array.from(files || []);
    if (dzFile) {
      if (!selectedFiles.length) {
        dzFile.textContent = "";
      } else if (selectedFiles.length === 1) {
        dzFile.textContent = selectedFiles[0].name;
      } else {
        dzFile.textContent = "已选 " + selectedFiles.length + " 个文件：" +
          selectedFiles.slice(0, 2).map(function (f) { return f.name; }).join("、") +
          (selectedFiles.length > 2 ? " 等" : "");
      }
    }
    if (hint) hint.textContent = selectedFiles.length > 1 ? "将批量体检 " + selectedFiles.length + " 篇" : "";
  }

  fileInput.addEventListener("change", function () {
    setFiles(fileInput.files);
  });

  ["dragenter", "dragover"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      dropzone.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach(function (evt) {
    dropzone.addEventListener(evt, function (e) {
      e.preventDefault();
      dropzone.classList.remove("drag");
    });
  });
  dropzone.addEventListener("drop", function (e) {
    const files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) {
      const dt = new DataTransfer();
      Array.from(files).forEach(function (f) { dt.items.add(f); });
      fileInput.files = dt.files;
      setFiles(dt.files);
    }
  });

  sampleBtn.addEventListener("click", async function () {
    sampleBtn.disabled = true;
    try {
      const resp = await fetch("/static/samples/sample_paper.txt");
      if (!resp.ok) throw new Error("示例文件未找到");
      paste.value = await resp.text();
      setFiles([]);
      window.CiteGuard.toast("已填入示例论文，可直接点击「开始体检」");
    } catch (err) {
      window.CiteGuard.toast("示例文件不可用：" + err.message);
    } finally {
      sampleBtn.disabled = false;
    }
  });

  function supportMaxValue() {
    const el = document.getElementById("support-max");
    return el ? el.value : "30";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  const STATUS_LABEL = {
    Exact: "真实一致",
    Minor: "元数据偏差",
    Major: "疑似虚构",
    Unverified: "未找到",
    Unknown: "无法核验",
  };

  function normalizeStats(report) {
    const s = (report && report.stats) || {};
    return {
      total: s.total || 0,
      exact: s.Exact || 0,
      minor: s.Minor || 0,
      major: s.Major || 0,
      unverified: s.Unverified || 0,
      unknown: s.Unknown || 0,
      avg: typeof s.avg_compliance === "number" ? s.avg_compliance : null,
      risk: s.risk_index == null ? null : s.risk_index,
    };
  }

  function aggregate(rows) {
    const total = {
      files: 0, failed: 0, refs: 0, exact: 0, minor: 0, major: 0,
      unverified: 0, unknown: 0, scoreSum: 0, scored: 0,
    };
    rows.forEach(function (r) {
      if (r.report) {
        total.files += 1;
        const s = normalizeStats(r.report);
        total.refs += s.total;
        total.exact += s.exact;
        total.minor += s.minor;
        total.major += s.major;
        total.unverified += s.unverified;
        total.unknown += s.unknown;
        if (s.avg != null && s.total > 0) {
          total.scoreSum += s.avg * s.total;
          total.scored += s.total;
        }
      } else if (r.error) {
        total.failed += 1;
      }
    });
    total.avgScore = total.scored ? total.scoreSum / total.scored : null;
    total.needAttention = total.minor + total.major;
    return total;
  }

  function summaryHtml(sum) {
    if (!sum || !sum.files) return "";
    const cells = [
      ["篇数", sum.files, ""],
      ["参考文献", sum.refs, ""],
      ["真实一致", sum.exact, "ok"],
      ["元数据偏差", sum.minor, "warn"],
      ["疑似虚构/错配", sum.major, sum.major ? "bad" : ""],
      ["未找到匹配", sum.unverified, "muted"],
      ["格式均分", sum.avgScore == null ? "—" : Number(sum.avgScore).toFixed(1), ""],
    ];
    const cellsHtml = cells.map(function (c) {
      return '<div class="batch-stat"><b class="' + c[2] + '">' + escapeHtml(c[1]) + "</b><span>" + c[0] + "</span></div>";
    }).join("");
    let verdict;
    if (sum.major) {
      verdict = "<b>" + sum.major + "</b> 条疑似虚构或错配，建议优先核对。";
    } else if (sum.needAttention) {
      verdict = "没有疑似虚构条目；<b>" + sum.needAttention + "</b> 条元数据偏差，可逐篇查看。";
    } else if (sum.unverified) {
      verdict = "没有疑似虚构或偏差条目；<b>" + sum.unverified + "</b> 条未找到匹配（不等于造假，建议人工核对）。";
    } else {
      verdict = "本批未发现疑似虚构、元数据偏差条目，建议仍抽查 1–2 条。";
    }
    return (
      '<div class="batch-summary">' +
        '<div class="batch-summary-head"><span>批量汇总</span>' +
          '<button type="button" class="btn btn-sm btn-ghost" id="batch-csv">导出汇总 CSV</button>' +
        "</div>" +
        '<div class="batch-grid">' + cellsHtml + "</div>" +
        '<div class="batch-verdict">' + verdict + "</div>" +
        (sum.failed ? '<div class="batch-verdict muted">有 ' + sum.failed + " 篇提交或分析失败，见下方列表。</div>" : "") +
      "</div>"
    );
  }

  function renderBatchResults(rows, summary) {
    if (!batchBox) return;
    batchBox.classList.remove("hidden");
    if (!rows || !rows.length) {
      batchBox.innerHTML = "";
      return;
    }
    const sum = summary || null;
    const rowHtml = rows.map(function (r) {
      let state = "";
      if (r.error) {
        state = '<span class="pill bad"><i></i>' + escapeHtml(r.error) + "</span>";
      } else if (r.report) {
        const s = normalizeStats(r.report);
        state =
          '<span class="pill ok"><i></i>完成 · ' + s.total + " 条</span>" +
          (s.major ? '<span class="mono-sm" style="color:var(--bad)">' + s.major + " 疑似虚构</span>" : "") +
          (s.minor ? '<span class="mono-sm" style="color:var(--warn)">' + s.minor + " 偏差</span>" : "") +
          (s.avg != null ? '<span class="mono-sm">格式 ' + Number(s.avg).toFixed(0) + "/100</span>" : "");
      } else if (r.jobId) {
        state = '<span class="pill unknown"><i></i>' + escapeHtml(r.state || "核验中") + "</span>";
      } else {
        state = '<span class="pill unknown"><i></i>等待提交</span>';
      }
      return (
        '<div class="batch-row">' +
          '<span class="batch-name">' + escapeHtml(r.name) + "</span>" +
          state +
          (r.jobId ? '<a class="btn btn-sm btn-ghost" href="/report/' + r.jobId + '">查看报告</a>' : "") +
        "</div>"
      );
    }).join("");
    batchBox.innerHTML =
      (sum ? summaryHtml(sum) : '<div class="mono-sm" style="margin-bottom:8px">批量任务进行中：分析进度会实时更新，全部完成后给出汇总。</div>') +
      rowHtml;
    const csvBtn = document.getElementById("batch-csv");
    if (csvBtn) {
      csvBtn.addEventListener("click", function () {
        downloadSummaryCsv(rows);
      });
    }
  }

  function downloadSummaryCsv(rows) {
    const lines = [["文件", "参考文献", "真实一致", "元数据偏差", "疑似虚构", "未找到匹配", "无法核验", "格式均分", "备注"]];
    rows.forEach(function (r) {
      if (!r.report) {
        lines.push([r.name, 0, 0, 0, 0, 0, 0, "", r.error ? "失败：" + r.error : "未完成"]);
        return;
      }
      const s = normalizeStats(r.report);
      lines.push([
        r.name, s.total, s.exact, s.minor, s.major, s.unverified, s.unknown,
        s.avg == null ? "" : Number(s.avg).toFixed(1), "",
      ]);
    });
    const csv = lines.map(function (cols) {
      return cols.map(function (c) {
        const text = String(c == null ? "" : c);
        return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
      }).join(",");
    }).join("\r\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "citeguard-批量汇总.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 2000);
    window.CiteGuard.toast("汇总 CSV 已下载（可用 Excel 打开）");
  }

  async function submitOne(file) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("support_max", supportMaxValue());
    const data = await window.CiteGuard.postForm("/api/analyze", fd);
    return data.job_id;
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  async function pollJob(jobId, onUpdate) {
    for (;;) {
      const resp = await fetch("/api/jobs/" + encodeURIComponent(jobId));
      if (!resp.ok) throw new Error("任务状态读取失败");
      const job = await resp.json();
      if (onUpdate) onUpdate(job);
      if (job.status === "done" || job.status === "error") return job;
      await sleep(1200);
    }
  }

  async function fetchReport(jobId) {
    const resp = await fetch("/api/report/" + encodeURIComponent(jobId));
    if (!resp.ok) throw new Error("报告读取失败");
    return resp.json();
  }

  async function runBatch() {
    const rows = selectedFiles.map(function (f) {
      return { name: f.name, jobId: "", error: "", state: "等待提交", report: null };
    });
    renderBatchResults(rows, null);

    for (let i = 0; i < selectedFiles.length; i++) {
      startBtn.textContent = "提交中 " + (i + 1) + "/" + selectedFiles.length;
      rows[i].state = "提交中";
      renderBatchResults(rows, null);
      try {
        rows[i].jobId = await submitOne(selectedFiles[i]);
        rows[i].state = "排队中";
      } catch (err) {
        rows[i].error = err.message || "提交失败";
      }
      renderBatchResults(rows, null);
    }

    let finished = 0;
    await Promise.all(rows.filter(function (r) { return r.jobId; }).map(async function (r) {
      try {
        const job = await pollJob(r.jobId, function (j) {
          r.state = (j.stage || "核验中") + (j.progress != null ? " " + j.progress + "%" : "");
          renderBatchResults(rows, null);
        });
        if (job.status === "error") {
          r.error = job.error || "分析失败";
        } else {
          r.report = await fetchReport(r.jobId);
        }
      } catch (err) {
        r.error = err.message || "读取报告失败";
      } finally {
        finished += 1;
        startBtn.textContent = "汇总中 " + finished + "/" + rows.filter(function (x) { return x.jobId; }).length;
        renderBatchResults(rows, null);
      }
    }));

    if (hint) hint.textContent = "";
    startBtn.textContent = "开始体检";
    startBtn.disabled = false;
    const summary = aggregate(rows);
    renderBatchResults(rows, summary);
    if (summary.files) {
      window.CiteGuard.toast("已完成 " + summary.files + " 篇 · " + summary.refs + " 条参考文献");
    } else {
      window.CiteGuard.toast("批量任务未完成，请检查下方错误信息");
    }
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!selectedFiles.length && !paste.value.trim()) {
      window.CiteGuard.toast("请先选择文件或粘贴文本");
      return;
    }
    startBtn.disabled = true;
    const original = startBtn.textContent;

    if (selectedFiles.length > 1) {
      await runBatch();
      return;
    }

    startBtn.textContent = "上传中…";
    try {
      const fd = new FormData();
      if (selectedFiles.length === 1) {
        fd.append("file", selectedFiles[0]);
      } else {
        fd.append("text", paste.value);
      }
      fd.append("support_max", supportMaxValue());
      const data = await window.CiteGuard.postForm("/api/analyze", fd);
      window.location.href = "/report/" + data.job_id;
    } catch (err) {
      window.CiteGuard.toast("提交失败：" + err.message);
      startBtn.disabled = false;
      startBtn.textContent = original;
    }
  });
})();
