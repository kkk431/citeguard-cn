/* Local library management: multi-file import, search, delete, abstract enrichment. */
(function () {
  const form = document.getElementById("library-form");
  if (!form) return;

  const input = document.getElementById("library-file");
  const dropzone = document.getElementById("library-dropzone");
  const nameEl = document.getElementById("library-file-name");
  const hint = document.getElementById("library-hint");
  const importBtn = document.getElementById("library-import-btn");
  const demoBtn = document.getElementById("library-demo-btn");
  const clearBtn = document.getElementById("library-clear-btn");
  const search = document.getElementById("library-search");
  const tableBody = document.getElementById("library-body");
  const panel = document.getElementById("library-panel");
  const empty = document.getElementById("library-empty");
  const countHint = document.getElementById("library-count-hint");
  const toolbarHint = document.getElementById("library-toolbar-hint");
  const enrichBtn = document.getElementById("library-enrich-btn");

  let entries = [];
  let missing = 0;

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

  async function postJSON(url) {
    const resp = await fetch(url, { method: "POST", headers: { Accept: "application/json" } });
    const data = await resp.json().catch(function () { return {}; });
    if (!resp.ok) throw new Error(data.detail || "HTTP " + resp.status);
    return data;
  }

  async function postJSONBody(url, body) {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json().catch(function () { return {}; });
    if (!resp.ok) throw new Error(data.detail || "HTTP " + resp.status);
    return data;
  }

  async function loadEntries() {
    try {
      const data = await window.CiteGuard.getJSON("/api/library?limit=2000");
      entries = data.entries || [];
      missing = data.missing_abstract || 0;
      if (countHint) {
        countHint.textContent = entries.length
          ? "共 " + data.count + " 条 · 缺摘要 " + missing + " 条"
          : "最多展示 20 条";
      }
      if (empty) empty.hidden = entries.length > 0;
      if (panel) panel.hidden = entries.length === 0;
      if (enrichBtn) {
        enrichBtn.hidden = missing === 0;
        enrichBtn.textContent = missing ? "自动补摘要（缺 " + missing + " 条）" : "自动补摘要（联网）";
      }
      if (data.truncated && toolbarHint) {
        toolbarHint.textContent = "题录超过 2000 条，只显示前 2000 条";
      }
      render();
    } catch (err) {
      if (toolbarHint) toolbarHint.textContent = "读取题录库失败：" + err.message;
    }
  }

  function matches(entry, query) {
    if (!query) return true;
    const hay = [
      entry.title,
      (entry.authors || []).join(" "),
      entry.venue,
      entry.year,
      entry.doi,
      entry.abstract,
    ].join(" ").toLowerCase();
    return hay.indexOf(query) >= 0;
  }

  function makeCell(text, className, maxWidth) {
    const td = document.createElement("td");
    if (className) td.className = className;
    if (maxWidth) td.style.maxWidth = maxWidth;
    td.textContent = text || "—";
    return td;
  }

  function render() {
    if (!tableBody) return;
    const query = (search && search.value || "").trim().toLowerCase();
    const rows = entries.filter(function (entry) { return matches(entry, query); });
    tableBody.textContent = "";
    rows.forEach(function (entry) {
      const tr = document.createElement("tr");

      const title = makeCell(entry.title, "", "380px");
      title.style.wordBreak = "break-word";
      title.title = entry.title || "";
      tr.appendChild(title);

      const authors = (entry.authors || []).slice(0, 3).join(", ");
      tr.appendChild(makeCell(authors + ((entry.authors || []).length > 3 ? " 等" : ""), "mono-sm", "200px"));
      tr.appendChild(makeCell(entry.venue, "mono-sm", "180px"));
      tr.appendChild(makeCell(entry.year ? String(entry.year) : "", "mono-sm", ""));
      tr.appendChild(makeCell(entry.doi, "mono-sm", "180px"));
      tr.appendChild(makeCell(entry.abstract ? "有" : "缺", "mono-sm", ""));

      const action = document.createElement("td");
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn btn-ghost btn-sm lib-del";
      del.textContent = "删除";
      del.addEventListener("click", function () { deleteEntry(entry); });
      action.appendChild(del);
      tr.appendChild(action);

      tableBody.appendChild(tr);
    });
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 7;
      td.className = "mono-sm";
      td.style.color = "var(--muted)";
      td.style.padding = "18px 12px";
      td.textContent = query ? "没有匹配的题录" : "题录库为空";
      tr.appendChild(td);
      tableBody.appendChild(tr);
    }
    if (toolbarHint && query) toolbarHint.textContent = "匹配 " + rows.length + " 条";
  }

  async function deleteEntry(entry) {
    if (!window.confirm("删除这条题录？\n" + (entry.title || ""))) return;
    try {
      const resp = await fetch("/api/library/" + entry.index, { method: "DELETE" });
      const data = await resp.json().catch(function () { return {}; });
      if (!resp.ok) throw new Error(data.detail || "HTTP " + resp.status);
      window.CiteGuard.toast("已删除：" + (entry.title || "").slice(0, 40));
      await loadEntries();
    } catch (err) {
      window.CiteGuard.toast("删除失败：" + err.message);
    }
  }

  async function enrichAbstracts() {
    if (!missing) return;
    const ok = window.confirm(
      "将从 OpenAlex / Crossref 拉取公开元数据，为缺少摘要的题录补摘要。\n" +
      "只接受标题高度匹配、年份兼容的记录；网络失败不会改动已有数据。\n\n继续？"
    );
    if (!ok) return;
    let enriched = 0;
    let rounds = 0;
    enrichBtn.disabled = true;
    try {
      while (missing > 0 && rounds < 50) {
        rounds += 1;
        if (toolbarHint) toolbarHint.textContent = "正在补摘要…（已补 " + enriched + " 条，还缺 " + missing + " 条）";
        const data = await postJSON("/api/library/enrich?limit=3");
        enriched += data.enriched || 0;
        missing = data.remaining || 0;
        if (!data.tried || (data.enriched === 0 && data.errors >= data.tried)) break;
      }
      window.CiteGuard.toast("补摘要完成：新增 " + enriched + " 条，剩余缺摘要 " + missing + " 条");
      await loadEntries();
    } catch (err) {
      window.CiteGuard.toast("补摘要失败：" + err.message);
    } finally {
      enrichBtn.disabled = false;
      if (toolbarHint) toolbarHint.textContent = "";
    }
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
    let added = 0;
    let noAbstract = 0;
    let failed = 0;
    for (let i = 0; i < list.length; i++) {
      if (hint) hint.textContent = "导入中 " + (i + 1) + "/" + list.length;
      try {
        const fd = new FormData();
        fd.append("file", list[i]);
        const data = await window.CiteGuard.postForm("/api/library/import", fd);
        imported += data.imported || 0;
        added += data.added || 0;
        noAbstract += data.imported_no_abstract || 0;
      } catch (err) {
        failed += 1;
      }
    }
    if (hint) hint.textContent = "";
    let msg = "解析 " + imported + " 条，新增 " + added + " 条";
    if (imported > added) msg += "，跳过重复 " + (imported - added) + " 条";
    if (failed) msg += "；" + failed + " 个文件失败";
    if (noAbstract) msg += "；" + noAbstract + " 条没有摘要（可点「自动补摘要」）";
    window.CiteGuard.toast(msg);
    await loadEntries();
  });

  if (demoBtn) {
    demoBtn.addEventListener("click", async function () {
      demoBtn.disabled = true;
      try {
        const data = await postJSON("/api/library/demo");
        const added = data.added || 0;
        const total = data.count || 0;
        window.CiteGuard.toast(
          added
            ? "已载入演示题录 " + added + " 条（库内共 " + total + " 条）"
            : "演示题录已在库中（库内共 " + total + " 条）"
        );
        await loadEntries();
      } catch (err) {
        window.CiteGuard.toast(err.message || "载入演示题录失败");
      } finally {
        demoBtn.disabled = false;
      }
    });
  }

  clearBtn.addEventListener("click", async function () {
    if (!window.confirm("确定清空本地题录库？该操作不可撤销。")) return;
    try {
      const resp = await fetch("/api/library/clear", { method: "POST" });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      window.CiteGuard.toast("已清空题录库");
      window.location.reload();
    } catch (err) {
      window.CiteGuard.toast("清空失败：" + err.message);
    }
  });

  const bulkBtn = document.getElementById("library-bulk-btn");
  const bulkText = document.getElementById("library-bulk-text");
  const bulkHint = document.getElementById("library-bulk-hint");
  if (bulkBtn && bulkText) {
    bulkBtn.addEventListener("click", async function () {
      const text = bulkText.value.trim();
      if (!text) {
        window.CiteGuard.toast("先粘一条参考文献");
        return;
      }
      bulkBtn.disabled = true;
      if (bulkHint) bulkHint.textContent = "解析中…";
      try {
        const data = await postJSONBody("/api/library/bulk", { text: text });
        let msg = "解析 " + data.parsed + " 条，新增 " + data.added + " 条";
        if (data.skipped) msg += "，跳过 " + data.skipped + " 条";
        window.CiteGuard.toast(msg);
        if (bulkHint) {
          bulkHint.textContent = data.skipped
            ? "未识别：" + (data.samples || []).join("；")
            : "已写入本地题录库";
        }
        if (data.added) bulkText.value = "";
        await loadEntries();
      } catch (err) {
        window.CiteGuard.toast("补录失败：" + err.message);
        if (bulkHint) bulkHint.textContent = "";
      } finally {
        bulkBtn.disabled = false;
      }
    });
  }

  if (search) search.addEventListener("input", render);
  if (enrichBtn) enrichBtn.addEventListener("click", enrichAbstracts);

  loadEntries();
})();
