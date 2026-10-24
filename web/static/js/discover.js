(function () {
  "use strict";

  const form = document.getElementById("discover-form");
  if (!form) return;
  const queryInput = document.getElementById("discover-query");
  const limitSelect = document.getElementById("discover-limit");
  const yearInput = document.getElementById("discover-year");
  const oaInput = document.getElementById("discover-oa");
  const btn = document.getElementById("discover-btn");
  const hint = document.getElementById("discover-hint");
  const status = document.getElementById("discover-status");
  const section = document.getElementById("discover-result-section");
  const body = document.getElementById("discover-body");
  const meta = document.getElementById("discover-meta");
  const selectAll = document.getElementById("discover-select-all");
  const importBtn = document.getElementById("discover-import-btn");
  const exportLink = document.getElementById("discover-export");

  let results = [];
  let lastParams = null;

  const esc = (value) =>
    String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));

  function setStatus(message, kind) {
    status.textContent = message || "";
    status.classList.toggle("hidden", !message);
    status.classList.toggle("lib-banner-error", kind === "error");
  }

  function linkFor(item) {
    if (item.doi) return "https://doi.org/" + encodeURIComponent(item.doi);
    if (item.oa_url) return item.oa_url;
    if (item.openalex_id) return "https://openalex.org/" + encodeURIComponent(item.openalex_id);
    return "";
  }

  function render(payload) {
    results = payload.results || [];
    lastParams = {
      query: payload.query,
      limit: limitSelect.value,
      year_from: yearInput.value,
      oa_only: oaInput.checked ? "true" : "",
    };
    const params = new URLSearchParams();
    Object.entries(lastParams).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    exportLink.href = "/api/discover/export?" + params.toString();

    body.innerHTML = results.map((item, index) => {
      const url = linkFor(item);
      const title = url
        ? '<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(item.title) + "</a>"
        : esc(item.title);
      const authors = (item.authors || []).join("、");
      const authorsShown = authors.length > 48 ? authors.slice(0, 48) + "…" : authors;
      const oa = item.is_oa
        ? '<span class="pill pill-ok">OA</span>'
        : '<span class="pill">未开放</span>';
      return (
        "<tr>" +
        '<td><input type="checkbox" class="discover-pick" data-index="' + index + '"></td>' +
        '<td class="discover-title">' + title + (item.doi ? '<div class="mono-sm">' + esc(item.doi) + "</div>" : "") + "</td>" +
        '<td class="discover-authors">' + esc(authorsShown || "—") + "</td>" +
        "<td>" + esc(item.year || "—") + "</td>" +
        '<td class="discover-venue">' + esc(item.venue || "—") + "</td>" +
        "<td>" + esc(item.cited_by || 0) + "</td>" +
        "<td>" + oa + "</td>" +
        "</tr>"
      );
    }).join("");
    section.classList.remove("hidden");
    meta.textContent =
      "主题「" + payload.query + "」· OpenAlex 匹配 " + payload.matched +
      " 条，展示 " + results.length + " 条 · 排序为规则启发式";
    selectAll.checked = false;
    updateImportButton();
  }

  function picked() {
    return Array.from(document.querySelectorAll(".discover-pick:checked"))
      .map((box) => results[Number(box.dataset.index)])
      .filter(Boolean);
  }

  function updateImportButton() {
    const count = picked().length;
    importBtn.disabled = count === 0;
    importBtn.textContent = count ? "加入题录库（" + count + "）" : "加入题录库";
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = queryInput.value.trim();
    if (query.length < 2) {
      setStatus("请输入至少两个字符的研究主题", "error");
      return;
    }
    btn.disabled = true;
    hint.textContent = "检索中…";
    setStatus("正在查询 OpenAlex，首次请求可能需要几秒。");
    try {
      const resp = await fetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query,
          limit: Number(limitSelect.value),
          year_from: yearInput.value ? Number(yearInput.value) : null,
          oa_only: oaInput.checked,
        }),
      });
      const payload = await resp.json();
      if (!resp.ok) throw new Error(payload.detail || "检索失败");
      render(payload);
      setStatus("");
      if (!payload.results.length) setStatus("没有找到候选文献，换一组关键词试试。");
    } catch (error) {
      setStatus("检索失败：" + (error.message || error), "error");
    } finally {
      btn.disabled = false;
      hint.textContent = "";
    }
  });

  body.addEventListener("change", (event) => {
    if (event.target.classList.contains("discover-pick")) updateImportButton();
  });

  selectAll.addEventListener("change", () => {
    document.querySelectorAll(".discover-pick").forEach((box) => {
      box.checked = selectAll.checked;
    });
    updateImportButton();
  });

  importBtn.addEventListener("click", async () => {
    const items = picked();
    if (!items.length) return;
    importBtn.disabled = true;
    setStatus("正在写入本地题录库…");
    try {
      const resp = await fetch("/api/discover/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: items }),
      });
      const payload = await resp.json();
      if (!resp.ok) throw new Error(payload.detail || "导入失败");
      setStatus(
        "已加入题录库 " + payload.added + " 条" +
        (payload.skipped ? "，跳过重复 " + payload.skipped + " 条" : "") +
        "；当前题录库共 " + payload.count + " 条。"
      );
    } catch (error) {
      setStatus("导入失败：" + (error.message || error), "error");
    } finally {
      importBtn.disabled = false;
      updateImportButton();
    }
  });
})();
