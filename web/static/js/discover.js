(function () {
  "use strict";

  const form = document.getElementById("discover-form");
  if (!form) return;
  const queryInput = document.getElementById("discover-query");
  const limitSelect = document.getElementById("discover-limit");
  const yearInput = document.getElementById("discover-year");
  const oaInput = document.getElementById("discover-oa");
  const retractedInput = document.getElementById("discover-retracted");
  const sortSelect = document.getElementById("discover-sort");
  const langSelect = document.getElementById("discover-lang");
  const expandInput = document.getElementById("discover-expand");
  const btn = document.getElementById("discover-btn");
  const hint = document.getElementById("discover-hint");
  const status = document.getElementById("discover-status");
  const section = document.getElementById("discover-result-section");
  const expansionBox = document.getElementById("discover-expansion");
  const list = document.getElementById("discover-list");
  const meta = document.getElementById("discover-meta");
  const selectedLabel = document.getElementById("discover-selected");
  const selectAll = document.getElementById("discover-select-all");
  const importBtn = document.getElementById("discover-import-btn");
  const exportLink = document.getElementById("discover-export");
  const moreBtn = document.getElementById("discover-more");
  const empty = document.getElementById("discover-empty");

  const state = { query: "", page: 1, results: [], seen: new Set(), selected: new Set(), lastPayload: null };

  const esc = (value) =>
    String(value == null ? "" : value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));

  function setStatus(message, kind) {
    status.textContent = message || "";
    status.classList.toggle("hidden", !message);
    status.classList.toggle("lib-banner-error", kind === "error");
  }

  function itemKey(item) {
    return (item.doi || "").toLowerCase() || item.openalex_id || item.title;
  }

  function linkFor(item) {
    if (item.doi) return "https://doi.org/" + encodeURIComponent(item.doi);
    if (item.oa_url) return item.oa_url;
    if (item.openalex_id) return "https://openalex.org/" + encodeURIComponent(item.openalex_id);
    return "";
  }

  function langLabel(code) {
    if (!code) return "";
    if (code === "zh") return "中文";
    if (code === "en") return "英文";
    return String(code).toUpperCase();
  }

  function buildParams() {
    return {
      query: state.query,
      limit: Number(limitSelect.value),
      sort: sortSelect.value,
      year_from: yearInput.value ? Number(yearInput.value) : null,
      oa_only: oaInput.checked,
      include_retracted: retractedInput.checked,
      expand: expandInput.checked ? "auto" : "off",
      page: state.page,
    };
  }

  function updateExport() {
    const params = new URLSearchParams();
    const source = buildParams();
    Object.entries(source).forEach(([key, value]) => {
      if (value !== null && value !== "" && value !== false) params.set(key, String(value));
    });
    exportLink.href = "/api/discover/export?" + params.toString();
  }

  function renderExpansion(payload) {
    const expansion = payload.expansion;
    const isCjk = /[\u4e00-\u9fff]/.test(payload.query || "");
    if (payload.expand === "off") {
      expansionBox.classList.add("hidden");
      return;
    }
    if (expansion && expansion.en) {
      expansionBox.innerHTML =
        '<span class="pill pill-ok">已扩展英文检索</span> <b>' + esc(expansion.en) + "</b>" +
        (expansion.keywords && expansion.keywords.length
          ? '<span class="discover-kw">关键词：' + esc(expansion.keywords.join(" · ")) + "</span>"
          : "") +
        '<span class="mono-sm">扩充词只用于检索，不写入题录</span>';
      expansionBox.classList.remove("hidden");
    } else if (isCjk) {
      expansionBox.innerHTML =
        '<span class="pill">未扩展英文检索</span> 未配置判词模型（或调用失败），本次只用中文主题检索；' +
        "英文文献可能因此漏召回。";
      expansionBox.classList.remove("hidden");
    } else {
      expansionBox.classList.add("hidden");
    }
  }

  function renderList() {
    const lang = langSelect ? langSelect.value : "";
    const visible = lang
      ? state.results.filter((item) => (item.language || "") === lang)
      : state.results;
    list.innerHTML = visible.map((item, index) => {
      const url = linkFor(item);
      const title = url
        ? '<a href="' + esc(url) + '" target="_blank" rel="noopener">' + esc(item.title) + "</a>"
        : esc(item.title);
      const authors = (item.authors || []).join("、");
      const authorsShown = authors.length > 60 ? authors.slice(0, 60) + "…" : authors;
      const badges = [];
      if (item.is_oa) badges.push('<span class="pill pill-ok">OA</span>');
      if (item.via === "expansion") badges.push('<span class="pill">英文扩展</span>');
      if (item.retracted) badges.push('<span class="pill pill-bad">已撤稿</span>');
      if (item.language) badges.push('<span class="pill">' + esc(langLabel(item.language)) + "</span>");
      const abstract = item.abstract
        ? '<p class="paper-abstract">' + esc(item.abstract) + "</p>"
        : "";
      const reason = item.reason
        ? '<div class="paper-reason">' + esc(item.reason) + "</div>"
        : "";
      const key = itemKey(item);
      const checked = state.selected.has(key) ? " checked" : "";
      return (
        '<article class="paper-card" data-index="' + index + '" data-key="' + esc(key) + '">' +
          '<label class="paper-check"><input type="checkbox" class="discover-pick"' + checked + '></label>' +
          '<div class="paper-main">' +
            '<h3 class="paper-title">' + title + "</h3>" +
            '<div class="paper-meta">' +
              esc(authorsShown || "作者未知") +
              (item.venue ? " · " + esc(item.venue) : "") +
              (item.year ? " · " + esc(item.year) : "") +
              " · 被引 " + esc(item.cited_by || 0) +
              " " + badges.join(" ") +
            "</div>" +
            abstract +
            reason +
            (item.doi ? '<div class="mono-sm">' + esc(item.doi) + "</div>" : "") +
          "</div>" +
          '<div class="paper-side"><span class="paper-score">' + esc(item.match_score != null ? item.match_score : "") + "</span>" +
          (url ? '<a href="' + esc(url) + '" target="_blank" rel="noopener">打开</a>' : "") + "</div>" +
        "</article>"
      );
    }).join("");
    empty.classList.toggle("hidden", visible.length > 0);
    if (!visible.length && state.results.length) {
      empty.textContent = "当前语言筛选下没有结果，切换「全部语言」或调整主题再看看。";
    } else {
      empty.textContent = "没有找到候选文献。换一组关键词、放宽年份，或勾选「包含撤稿文献」再试。";
    }
    moreBtn.classList.toggle("hidden", !(state.lastPayload && state.lastPayload.has_more) || state.page >= 5);
    updateSelection();
  }

  function selectedItems() {
    return state.results.filter((item) => state.selected.has(itemKey(item)));
  }

  function updateSelection() {
    const count = selectedItems().length;
    selectedLabel.textContent = "已选 " + count + " 条";
    importBtn.disabled = count === 0;
    importBtn.textContent = count ? "加入题录库（" + count + "）" : "加入题录库";
    selectAll.checked = state.results.length > 0 && state.results.every((item) => state.selected.has(itemKey(item)));
  }

  async function runSearch(append) {
    if (!append) {
      state.page = 1;
      state.results = [];
      state.seen = new Set();
      state.selected = new Set();
      state.lastPayload = null;
      section.classList.add("hidden");
    }
    btn.disabled = true;
    moreBtn.disabled = true;
    setStatus(append ? "正在加载下一页…" : "正在查询 OpenAlex，中文主题会尝试扩成英文检索，首次可能需要几秒。");
    hint.textContent = "检索中…";
    try {
      const resp = await fetch("/api/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildParams()),
      });
      const payload = await resp.json();
      if (!resp.ok) throw new Error(payload.detail || "检索失败");
      state.lastPayload = payload;
      const fresh = [];
      (payload.results || []).forEach((item) => {
        const key = itemKey(item);
        if (!state.seen.has(key)) {
          state.seen.add(key);
          fresh.push(item);
        }
      });
      state.results = append ? state.results.concat(fresh) : fresh;
      section.classList.remove("hidden");
      renderExpansion(payload);
      renderList();
      updateExport();
      meta.textContent =
        "主题「" + payload.query + "」· OpenAlex 匹配 " + payload.matched + " 条" +
        (payload.expansion && payload.expansion.en ? "（含英文扩展检索）" : "") +
        " · 本页 " + fresh.length + " 条 · 排序为规则启发式" +
        (payload.retracted_filtered ? " · 已过滤 " + payload.retracted_filtered + " 条撤稿文献" : "");
      setStatus("");
      if (!state.results.length) setStatus("没有找到候选文献，换一组关键词试试。");
    } catch (error) {
      setStatus("检索失败：" + (error.message || error), "error");
    } finally {
      btn.disabled = false;
      moreBtn.disabled = false;
      hint.textContent = "";
      updateSelection();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = queryInput.value.trim();
    if (query.length < 2) {
      setStatus("请输入至少两个字符的研究主题", "error");
      return;
    }
    state.query = query;
    runSearch(false);
  });

  list.addEventListener("change", (event) => {
    if (!event.target.classList.contains("discover-pick")) return;
    const card = event.target.closest(".paper-card");
    const key = card && card.dataset.key;
    if (!key) return;
    if (event.target.checked) state.selected.add(key);
    else state.selected.delete(key);
    updateSelection();
  });

  selectAll.addEventListener("change", () => {
    state.results.forEach((item) => {
      const key = itemKey(item);
      if (selectAll.checked) state.selected.add(key);
      else state.selected.delete(key);
    });
    document.querySelectorAll(".discover-pick").forEach((box) => {
      box.checked = selectAll.checked;
    });
    updateSelection();
  });

  sortSelect.addEventListener("change", () => {
    if (!state.query) return;
    runSearch(false);
  });

  if (langSelect) {
    langSelect.addEventListener("change", renderList);
  }

  moreBtn.addEventListener("click", () => {
    if (!state.lastPayload || !state.lastPayload.has_more) return;
    state.page += 1;
    runSearch(true);
  });

  importBtn.addEventListener("click", async () => {
    const items = selectedItems();
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
      updateSelection();
    }
  });
})();
