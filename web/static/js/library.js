/* Local library management: import / clear. */
(function () {
  const form = document.getElementById("library-form");
  if (!form) return;

  const input = document.getElementById("library-file");
  const dropzone = document.getElementById("library-dropzone");
  const nameEl = document.getElementById("library-file-name");
  const hint = document.getElementById("library-hint");
  const importBtn = document.getElementById("library-import-btn");
  const clearBtn = document.getElementById("library-clear-btn");

  function setName() {
    const file = input.files && input.files[0];
    if (nameEl) nameEl.textContent = file ? file.name : "";
  }

  input.addEventListener("change", setName);
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
      dt.items.add(files[0]);
      input.files = dt.files;
      setName();
    }
  });

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const file = input.files && input.files[0];
    if (!file) {
      window.CiteGuard.toast("请先选择一个题录导出文件");
      return;
    }
    importBtn.disabled = true;
    if (hint) hint.textContent = "导入中…";
    try {
      const fd = new FormData();
      fd.append("file", file);
      const data = await window.CiteGuard.postForm("/api/library/import", fd);
      if (hint) hint.textContent = "";
      window.CiteGuard.toast("导入 " + data.imported + " 条，库内共 " + data.count + " 条");
      setTimeout(function () { window.location.reload(); }, 700);
    } catch (err) {
      if (hint) hint.textContent = "";
      window.CiteGuard.toast("导入失败：" + err.message);
      importBtn.disabled = false;
    }
  });

  clearBtn.addEventListener("click", async function () {
    if (!window.confirm("确定清空本地题录库？该操作不可撤销。")) return;
    try {
      const resp = await fetch("/api/library/clear", { method: "POST" });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      window.CiteGuard.toast("已清空题录库");
      setTimeout(function () { window.location.reload(); }, 600);
    } catch (err) {
      window.CiteGuard.toast("清空失败：" + err.message);
    }
  });
})();
