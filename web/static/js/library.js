/* Local library management: import (multi-file) / clear. */
(function () {
  const form = document.getElementById("library-form");
  if (!form) return;

  const input = document.getElementById("library-file");
  const dropzone = document.getElementById("library-dropzone");
  const nameEl = document.getElementById("library-file-name");
  const hint = document.getElementById("library-hint");
  const importBtn = document.getElementById("library-import-btn");
  const clearBtn = document.getElementById("library-clear-btn");

  function files() {
    return Array.from((input && input.files) || []);
  }

  function setName() {
    const list = files();
    if (!nameEl) return;
    if (!list.length) nameEl.textContent = "";
    else if (list.length === 1) nameEl.textContent = list[0].name;
    else nameEl.textContent = "已选 " + list.length + " 个文件";
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
    const dropped = e.dataTransfer && e.dataTransfer.files;
    if (dropped && dropped.length) {
      const dt = new DataTransfer();
      Array.from(dropped).forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
      setName();
    }
  });

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const list = files();
    if (!list.length) {
      window.CiteGuard.toast("请先选择题录导出文件");
      return;
    }
    importBtn.disabled = true;
    let imported = 0;
    let noAbstract = 0;
    let failed = 0;
    for (let i = 0; i < list.length; i++) {
      if (hint) hint.textContent = "导入中 " + (i + 1) + "/" + list.length;
      try {
        const fd = new FormData();
        fd.append("file", list[i]);
        const data = await window.CiteGuard.postForm("/api/library/import", fd);
        imported += data.imported || 0;
        noAbstract += data.imported_no_abstract || 0;
      } catch (err) {
        failed += 1;
      }
    }
    if (hint) hint.textContent = "";
    let msg = "导入 " + imported + " 条" + (failed ? "，" + failed + " 个文件失败" : "");
    if (noAbstract) msg += "；" + noAbstract + " 条没有摘要（元数据核验可用，支持度判定需要摘要）";
    window.CiteGuard.toast(msg);
    setTimeout(function () { window.location.reload(); }, 1200);
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
