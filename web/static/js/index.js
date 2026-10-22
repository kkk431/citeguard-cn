/* Upload / paste / sample interactions for the home page. */
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

  let selectedFile = null;

  function setFile(file) {
    selectedFile = file || null;
    if (dzFile) dzFile.textContent = selectedFile ? selectedFile.name : "";
    if (hint) hint.textContent = selectedFile ? "将分析所选文件" : "";
  }

  fileInput.addEventListener("change", function () {
    setFile(fileInput.files && fileInput.files[0] ? fileInput.files[0] : null);
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
      setFile(files[0]);
      const dt = new DataTransfer();
      dt.items.add(files[0]);
      fileInput.files = dt.files;
    }
  });

  sampleBtn.addEventListener("click", async function () {
    sampleBtn.disabled = true;
    try {
      const resp = await fetch("/static/samples/sample_paper.txt");
      if (!resp.ok) throw new Error("示例文件未找到");
      paste.value = await resp.text();
      setFile(null);
      window.CiteGuard.toast("已填入示例论文，可直接点击「开始体检」");
    } catch (err) {
      window.CiteGuard.toast("示例文件不可用：" + err.message);
    } finally {
      sampleBtn.disabled = false;
    }
  });

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!selectedFile && !paste.value.trim()) {
      window.CiteGuard.toast("请先选择文件或粘贴文本");
      return;
    }
    startBtn.disabled = true;
    const original = startBtn.textContent;
    startBtn.textContent = "上传中…";
    try {
      const fd = new FormData();
      if (selectedFile) {
        fd.append("file", selectedFile);
      } else {
        fd.append("text", paste.value);
      }
      const data = await window.CiteGuard.postForm("/api/analyze", fd);
      window.location.href = "/report/" + data.job_id;
    } catch (err) {
      window.CiteGuard.toast("提交失败：" + err.message);
      startBtn.disabled = false;
      startBtn.textContent = original;
    }
  });
})();
