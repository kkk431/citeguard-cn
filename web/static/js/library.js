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
  const pagerMount = document.getElementById("library-pager");
  const dupesBtn = document.getElementById("library-dupes-btn");
  const tagModal = document.getElementById("library-tag-modal");
  const tagInput = document.getElementById("tag-input");
  const tagSave = document.getElementById("tag-save");
  const tagEntryTitle = document.getElementById("tag-entry-title");
  const dupesModal = document.getElementById("library-dupes-modal");
  const dupesBody = document.getElementById("dupes-body");
  let tagTarget = null;

  let entries = [];
  let missing = 0;
  let pager = null;

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
          : "题录库为空";
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

  function filteredRows() {
    const query = (search && search.value || "").trim().toLowerCase();
    return entries.filter(function (entry) { return matches(entry, query); });
  }

  function paint() {
    if (!tableBody) return;
    const query = (search && search.value || "").trim().toLowerCase();
    const rows = filteredRows();
    const pageRows = pager ? pager.slice(rows) : rows;
    tableBody.textContent = "";
    pageRows.forEach(function (entry) {
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

      const tagsCell = document.createElement("td");
      tagsCell.className = "mono-sm lib-tags";
      tagsCell.textContent = (entry.tags || []).join("、") || "—";
      const tagBtn = document.createElement("button");
      tagBtn.type = "button";
      tagBtn.className = "btn btn-ghost btn-sm lib-tag";
      tagBtn.textContent = "标签";
      tagBtn.addEventListener("click", function () { openTagEditor(entry); });
      tagsCell.appendChild(tagBtn);
      tr.appendChild(tagsCell);

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
      td.colSpan = 8;
      td.className = "mono-sm";
      td.style.color = "var(--muted)";
      td.style.padding = "18px 12px";
      td.textContent = query ? "没有匹配的题录" : "题录库为空";
      tr.appendChild(td);
      tableBody.appendChild(tr);
    }
    if (toolbarHint && query) toolbarHint.textContent = "匹配 " + rows.length + " 条";
  }

  function render() {
    if (!tableBody) return;
    const rows = filteredRows();
    if (!pager && window.CGList && pagerMount) {
      pager = window.CGList.create({
        mount: pagerMount,
        pageSize: 20,
        param: "page",
        onChange: paint,
      });
    }
    if (pager) pager.setTotal(rows.length);
    paint();
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

  const suggInput = document.getElementById("lib-suggest-title");
  const suggRun = document.getElementById("lib-suggest-run");
  const suggHint = document.getElementById("lib-suggest-hint");
  const suggResults = document.getElementById("lib-suggest-results");

  function renderSuggest(items) {
    if (!suggResults) return;
    if (!items.length) {
      suggResults.innerHTML = '<p class="hint">没有搜到相近题名。中文期刊可先在 CNKI/万方导出 RIS 再导入。</p>';
      return;
    }
    const rows = items.map(function (c, i) {
      const meta = [c.authors && c.authors[0] ? c.authors[0] + (c.authors.length > 1 ? " 等" : "") : "",
                    c.year || "", c.venue || "", c.doi ? "DOI " + c.doi : ""].filter(Boolean).join(" · ");
      const pct = Math.round((c.sim || 0) * 100);
      const btn = c.already
        ? '<span class="hint">已在库中</span>'
        : '<button class="btn btn-sm" type="button" data-add="' + i + '">入库</button>';
      return '<div class="suggest-row"><div class="suggest-main"><b>' + (c.title || "") + '</b><span class="hint">' + meta + '</span></div><div class="suggest-side"><span class="mono-sm">' + pct + '%</span>' + btn + '</div></div>';
    }).join("");
    suggResults.innerHTML = rows;
    suggResults.querySelectorAll("button[data-add]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        const c = items[Number(btn.dataset.add)];
        btn.disabled = true;
        try {
          const data = await postJSONBody("/api/library/add", {
            title: c.title, authors: c.authors || [], year: c.year,
            venue: c.venue || "", doi: c.doi || "", url: c.url || "", abstract: c.abstract || ""
          });
          window.CiteGuard.toast(data.added ? "已加入题录库" : (data.message || "已在库中"));
          if (data.added) { await loadEntries(); }
          btn.outerHTML = '<span class="hint">' + (data.added ? "已入库" : "已在库中") + '</span>';
        } catch (err) {
          btn.disabled = false;
          window.CiteGuard.toast("入库失败：" + err.message);
        }
      });
    });
  }

  async function runSuggest() {
    const title = (suggInput && suggInput.value || "").trim();
    if (title.length < 4) { window.CiteGuard.toast("至少输入 4 个字"); return; }
    suggRun.disabled = true;
    if (suggHint) suggHint.textContent = "检索中…";
    try {
      const r = await fetch("/api/library/suggest?title=" + encodeURIComponent(title));
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "检索失败");
      renderSuggest(data.candidates || []);
      if (suggHint) suggHint.textContent = "共 " + (data.count || 0) + " 条";
    } catch (err) {
      if (suggHint) suggHint.textContent = "";
      window.CiteGuard.toast(err.message);
    } finally {
      suggRun.disabled = false;
    }
  }
  if (suggRun) suggRun.addEventListener("click", runSuggest);
  if (suggInput) suggInput.addEventListener("keydown", function (ev) { if (ev.key === "Enter") runSuggest(); });

  if (search) search.addEventListener("input", function () {
    if (pager) pager.reset();
    render();
  });
  if (enrichBtn) enrichBtn.addEventListener("click", enrichAbstracts);

  initCharts();
  loadEntries();

  function initCharts() {
    if (!window.CGCharts) return;
    var yearsEl = document.getElementById("lib-chart-years");
    var venuesEl = document.getElementById("lib-chart-venues");
    var years = [];
    var venues = [];
    try {
      years = JSON.parse(document.getElementById("library-year-data").textContent || "[]");
      venues = JSON.parse(document.getElementById("library-venue-data").textContent || "[]");
    } catch (e) { /* keep empty */ }

    if (yearsEl) {
      years = years.slice().sort(function (a, b) { return a[0] - b[0]; });
      CGCharts.mount(yearsEl, function (t) {
        if (!years.length) return null;
        return Object.assign(CGCharts.base(), {
          tooltip: Object.assign(CGCharts.base().tooltip, { trigger: "axis", axisPointer: { type: "shadow" } }),
          legend: { show: false },
          grid: { left: 8, right: 12, top: 18, bottom: 4, containLabel: true },
          xAxis: Object.assign(CGCharts.axis(), { data: years.map(function (p) { return p[0]; }) }),
          yAxis: Object.assign(CGCharts.valueAxis(), { minInterval: 1 }),
          series: [{
            type: "bar",
            data: years.map(function (p) { return p[1]; }),
            barMaxWidth: 26,
            itemStyle: { color: t.colors[0], borderRadius: [4, 4, 0, 0] },
            label: { show: true, position: "top", color: t.muted, fontSize: 10 }
          }]
        });
      });
      var note = document.getElementById("lib-year-note");
      if (note) note.textContent = years.length ? years[0][0] + "–" + years[years.length - 1][0] : "";
    }

    if (venuesEl) {
      var top = venues.slice(0, 6).reverse();
      CGCharts.mount(venuesEl, function (t) {
        if (!top.length) return null;
        return Object.assign(CGCharts.base(), {
          tooltip: Object.assign(CGCharts.base().tooltip, { trigger: "axis", axisPointer: { type: "shadow" } }),
          legend: { show: false },
          grid: { left: 8, right: 30, top: 8, bottom: 4, containLabel: true },
          xAxis: Object.assign(CGCharts.valueAxis(), { minInterval: 1 }),
          yAxis: {
            type: "category",
            data: top.map(function (p) { return String(p[0]).length > 22 ? String(p[0]).slice(0, 21) + "…" : p[0]; }),
            axisLine: { show: false }, axisTick: { show: false },
            axisLabel: { color: t.muted, fontSize: 11 }
          },
          series: [{
            type: "bar",
            data: top.map(function (p) { return p[1]; }),
            barMaxWidth: 16,
            itemStyle: { color: t.colors[1], borderRadius: [0, 4, 4, 0] },
            label: { show: true, position: "right", color: t.muted, fontSize: 11 }
          }]
        });
      });
    }
  }

  function openTagEditor(entry) {
    if (!tagModal) return;
    tagTarget = entry;
    if (tagEntryTitle) tagEntryTitle.textContent = entry.title || "";
    if (tagInput) tagInput.value = (entry.tags || []).join(", ");
    tagModal.hidden = false;
    if (tagInput) tagInput.focus();
  }

  function closeLibModal(kind) {
    if (kind === "tag" && tagModal) tagModal.hidden = true;
    if (kind === "dupes" && dupesModal) dupesModal.hidden = true;
  }

  async function saveTags() {
    if (!tagTarget) return;
    const tags = (tagInput && tagInput.value || "")
      .split(/[,，、]/)
      .map(function (t) { return t.trim(); })
      .filter(Boolean);
    tagSave.disabled = true;
    try {
      const data = await postJSONBody("/api/library/" + tagTarget.index + "/tags", {
        mode: "replace",
        tags: tags,
      });
      tagTarget.tags = data.tags || [];
      closeLibModal("tag");
      window.CiteGuard.toast("标签已保存：" + (tagTarget.tags.join("、") || "无"));
      render();
    } catch (err) {
      window.CiteGuard.toast("保存标签失败：" + err.message);
    } finally {
      tagSave.disabled = false;
    }
  }

  async function mergeGroup(keepId, dropIds, button) {
    if (!dropIds.length) return;
    if (!window.confirm("将 " + dropIds.length + " 条重复记录合并到第 1 条？\n合并后无法自动恢复。")) return;
    button.disabled = true;
    try {
      const data = await postJSONBody("/api/library/duplicates/merge", {
        keep_id: keepId,
        drop_ids: dropIds,
      });
      window.CiteGuard.toast("已合并 " + data.merged + " 条重复记录");
      closeLibModal("dupes");
      await loadEntries();
    } catch (err) {
      window.CiteGuard.toast("合并失败：" + err.message);
      button.disabled = false;
    }
  }

  async function checkDuplicates() {
    if (!dupesModal) return;
    dupesBody.textContent = "正在检查…";
    dupesModal.hidden = false;
    try {
      const data = await window.CiteGuard.getJSON("/api/library/duplicates");
      dupesBody.textContent = "";
      if (!data.count) {
        const p = document.createElement("p");
        p.className = "hint";
        p.textContent = "没有发现 DOI 或「题名 + 年份」相同的重复题录。";
        dupesBody.appendChild(p);
        return;
      }
      data.groups.forEach(function (group) {
        const box = document.createElement("div");
        box.className = "lib-dupe";
        const head = document.createElement("p");
        head.className = "hint";
        head.textContent = group.ids.length + " 条 · " + group.reason;
        box.appendChild(head);
        group.entries.forEach(function (e) {
          const row = document.createElement("p");
          row.className = "lib-dupe-row";
          row.textContent = e.title || "（无题名）";
          box.appendChild(row);
        });
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-ghost btn-sm";
        btn.textContent = "保留第 1 条并合并其余 " + (group.ids.length - 1) + " 条";
        btn.addEventListener("click", function () {
          mergeGroup(group.ids[0], group.ids.slice(1), btn);
        });
        box.appendChild(btn);
        dupesBody.appendChild(box);
      });
    } catch (err) {
      dupesBody.textContent = "检查失败：" + err.message;
    }
  }


  if (dupesBtn) dupesBtn.addEventListener("click", checkDuplicates);
  if (tagSave) tagSave.addEventListener("click", saveTags);
  if (tagInput) {
    tagInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") saveTags();
      if (e.key === "Escape") closeLibModal("tag");
    });
  }
  document.querySelectorAll("[data-close]").forEach(function (el) {
    el.addEventListener("click", function () { closeLibModal(el.getAttribute("data-close")); });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { closeLibModal("tag"); closeLibModal("dupes"); }
  });

})();
