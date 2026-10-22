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

  function renderBatchResults(rows) {
    if (!batchBox) return;
    batchBox.classList.remove("hidden");
    batchBox.innerHTML =
      '<div class="mono-sm" style="margin-bottom:8px">批量任务（点击查看报告，分析进度在报告页显示）</div>' +
      rows.map(function (r) {
        return (
          '<div class="batch-row">' +
            '<span class="batch-name">' + escapeHtml(r.name) + "</span>" +
            (r.jobId
              ? '<a class="btn btn-sm btn-ghost" href="/report/' + r.jobId + '">查看报告</a>'
              : '<span class="pill bad"><i></i>' + escapeHtml(r.error || "提交失败") + "</span>") +
          "</div>"
        );
      }).join("");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  async function submitOne(file) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("support_max", supportMaxValue());
    const data = await window.CiteGuard.postForm("/api/analyze", fd);
    return data.job_id;
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
      // Batch mode: submit sequentially, list the report links.
      const rows = selectedFiles.map(function (f) { return { name: f.name, jobId: "" }; });
      if (batchBox) batchBox.classList.add("hidden");
      for (let i = 0; i < selectedFiles.length; i++) {
        startBtn.textContent = "提交中 " + (i + 1) + "/" + selectedFiles.length;
        if (hint) hint.textContent = "已提交 " + i + "/" + selectedFiles.length;
        try {
          rows[i].jobId = await submitOne(selectedFiles[i]);
        } catch (err) {
          rows[i].error = err.message;
        }
      }
      if (hint) hint.textContent = "";
      startBtn.textContent = original;
      startBtn.disabled = false;
      renderBatchResults(rows);
      window.CiteGuard.toast("已提交 " + rows.filter(function (r) { return r.jobId; }).length + " 篇");
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
