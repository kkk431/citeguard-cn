// 多篇文献对比页：上传 2–6 篇 -> /api/compare 后台抽取 -> 轮询 -> 渲染矩阵
(function () {
  const form = document.getElementById("compare-form");
  if (!form) return;
  const fileInput = document.getElementById("compare-files");
  const dropzone = document.getElementById("compare-dropzone");
  const fileList = document.getElementById("compare-file-list");
  const btn = document.getElementById("compare-btn");
  const hint = document.getElementById("compare-hint");
  const progress = document.getElementById("compare-progress");
  const resultSection = document.getElementById("compare-result-section");
  const table = document.getElementById("compare-table");
  const meta = document.getElementById("compare-meta");
  const exportMd = document.getElementById("compare-export-md");
  const exportCsv = document.getElementById("compare-export-csv");
  const MIN = Number(form.getAttribute("data-min") || 2);
  const MAX = Number(form.getAttribute("data-max") || 6);

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setHint(text) {
    if (hint) hint.textContent = text || "";
  }

  function showProgress(text) {
    if (!progress) return;
    progress.textContent = text;
    progress.classList.remove("hidden");
  }

  function hideProgress() {
    if (progress) progress.classList.add("hidden");
  }

  function currentFiles() {
    return Array.prototype.slice.call(fileInput.files || []);
  }

  function renderFileList() {
    const files = currentFiles();
    fileList.textContent = files.length
      ? files.map(function (f, i) { return (i + 1) + ". " + f.name; }).join("　")
      : "";
    if (files.length > MAX) {
      setHint("一次最多 " + MAX + " 篇，当前 " + files.length + " 篇");
    } else if (files.length === 1) {
      setHint("再选一篇就可以开始");
    } else {
      setHint("");
    }
  }

  fileInput.addEventListener("change", renderFileList);
  ["dragenter", "dragover"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      dropzone.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      dropzone.classList.remove("drag");
    });
  });
  dropzone.addEventListener("drop", function (e) {
    if (!e.dataTransfer || !e.dataTransfer.files.length) return;
    const dt = new DataTransfer();
    const existing = currentFiles();
    for (let i = 0; i < existing.length; i++) dt.items.add(existing[i]);
    for (let i = 0; i < e.dataTransfer.files.length; i++) dt.items.add(e.dataTransfer.files[i]);
    fileInput.files = dt.files;
    renderFileList();
  });

  function renderMatrix(result) {
    const papers = result.papers || [];
    const fields = result.fields || [];
    const head = ["<tr><th class=\"cmp-field\">维度</th>"];
    papers.forEach(function (paper) {
      head.push("<th>" + escapeHtml(paper.name) + "</th>");
    });
    head.push("</tr>");

    const statusRow = ["<tr><th class=\"cmp-field\">抽取状态</th>"];
    papers.forEach(function (paper) {
      if (paper.error) {
        statusRow.push("<td><span class=\"pill bad\">失败</span><div class=\"mono-sm cmp-note\">" + escapeHtml(paper.error) + "</div></td>");
      } else {
        const cached = paper.cached ? "缓存" : "新抽取";
        statusRow.push("<td><span class=\"pill ok\">成功</span><div class=\"mono-sm cmp-note\">" + escapeHtml(cached) + "</div></td>");
      }
    });
    statusRow.push("</tr>");

    const body = fields.map(function (field) {
      const cells = papers.map(function (paper) {
        if (paper.error) return "<td class=\"cmp-empty\">—</td>";
        const value = (paper.fields || {})[field.key] || "";
        return value
          ? "<td>" + escapeHtml(value) + "</td>"
          : "<td class=\"cmp-empty\">未提及</td>";
      });
      return "<tr><th class=\"cmp-field\">" + escapeHtml(field.label) + "</th>" + cells.join("") + "</tr>";
    });

    table.innerHTML = "<thead>" + head.join("") + "</thead><tbody>" + statusRow.join("") + body.join("") + "</tbody>";
    meta.textContent =
      "判官模型 " + (result.model || "—") +
      " · " + papers.length + " 篇 · 生成于 " + (result.generated_at || "").replace("T", " ");
    exportMd.href = "/api/compare/" + encodeURIComponent(result.job_id) + "/export?format=md";
    exportCsv.href = "/api/compare/" + encodeURIComponent(result.job_id) + "/export?format=csv";
    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function poll(jobId) {
    fetch("/api/compare/" + encodeURIComponent(jobId))
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        const job = data.job || {};
        if (job.status === "error") {
          hideProgress();
          showProgress("对比失败：" + (job.error || "未知错误"));
          btn.disabled = false;
          return;
        }
        if (job.status !== "done") {
          showProgress((job.stage || "处理中") + " · " + (job.progress || 0) + "%");
          setTimeout(function () { poll(jobId); }, 1200);
          return;
        }
        hideProgress();
        if (!data.result) {
          showProgress("结果文件缺失，请重新提交");
          btn.disabled = false;
          return;
        }
        renderMatrix(data.result);
        btn.disabled = false;
      })
      .catch(function (err) {
        hideProgress();
        showProgress("轮询失败：" + (err.message || String(err)));
        btn.disabled = false;
      });
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const files = currentFiles();
    if (files.length < MIN) { setHint("至少选择 " + MIN + " 篇文献"); return; }
    if (files.length > MAX) { setHint("一次最多 " + MAX + " 篇文献"); return; }
    const fd = new FormData();
    files.forEach(function (file) { fd.append("files", file, file.name); });
    btn.disabled = true;
    setHint("上传中…");
    resultSection.classList.add("hidden");
    try {
      const resp = await fetch("/api/compare", { method: "POST", body: fd });
      const data = await resp.json().catch(function () { return {}; });
      if (!resp.ok || !data.job_id) {
        hideProgress();
        showProgress("提交失败：" + (data.detail || data.error || ("HTTP " + resp.status)));
        btn.disabled = false;
        return;
      }
      setHint("");
      showProgress("已接收 " + files.length + " 篇，正在抽取…");
      poll(data.job_id);
    } catch (err) {
      hideProgress();
      showProgress("请求失败：" + (err.message || String(err)));
      btn.disabled = false;
    }
  });
})();
