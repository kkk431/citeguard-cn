(function () {
  "use strict";

  const API = "/api/live/check";
  const PREWARM_API = "/api/live/prewarm";
  const PAGE_API = "/api/live/page";
  const MAX_CANDIDATES = 5;
  const MAX_CLAIM = 500;

  const root = document.querySelector(".live-page");
  if (!root) return;

  const els = {
    claim: document.getElementById("live-claim"),
    count: document.getElementById("live-count"),
    pageTitle: document.getElementById("live-page-title"),
    pageUrl: document.getElementById("live-page-url"),
    btn: document.getElementById("live-btn"),
    result: document.getElementById("live-result"),
    placeholder: document.getElementById("live-placeholder"),
    loading: document.getElementById("live-loading"),
    error: document.getElementById("live-error"),
    errorMsg: document.getElementById("live-error-msg"),
    retry: document.getElementById("live-retry"),
    output: document.getElementById("live-output"),
    label: document.getElementById("live-label"),
    confidenceText: document.getElementById("live-confidence-text"),
    meter: document.getElementById("live-meter"),
    bar: document.getElementById("live-confidence-bar"),
    reason: document.getElementById("live-reason"),
    evidence: document.getElementById("live-evidence"),
    evidenceLink: document.getElementById("live-evidence-link"),
    evidenceTitle: document.getElementById("live-evidence-title"),
    quote: document.getElementById("live-quote"),
    candidateCount: document.getElementById("live-candidate-count"),
    candidates: document.getElementById("live-candidates"),
    prewarm: document.getElementById("live-prewarm-status"),
    probeBtn: document.getElementById("live-page-probe-btn"),
    probeStatus: document.getElementById("live-page-probe-status"),
    probeResult: document.getElementById("live-page-probe-result"),
    probeSummary: document.getElementById("live-page-probe-summary"),
    probeList: document.getElementById("live-page-probe-list")
  };

  if (!els.claim || !els.btn || !els.result || !els.output) return;

  const LABELS = Object.freeze({
    support: { text: "支持", hint: "候选摘要直接支持这句话" },
    partial: { text: "部分支持", hint: "方向相近，但数字、范围或条件只对上一部分" },
    contradict: { text: "矛盾", hint: "候选摘要与这句话方向相反或明确否定" },
    no_evidence: { text: "无证据", hint: "没有找到可核对摘要或对应句，这不等于“假”" }
  });

  const SOURCE_LABELS = Object.freeze({
    openalex: "OpenAlex",
    crossref: "Crossref",
    arxiv: "arXiv"
  });

  const state = {
    requestId: 0,
    last: null,
    prewarmTimer: 0,
    prewarmAbort: null
  };

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function number(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function clamp01(value) {
    return Math.max(0, Math.min(1, value));
  }

  function safeHref(value) {
    const raw = String(value || "").trim();
    if (!/^https?:\/\//i.test(raw)) return "";
    return raw;
  }

  function setView(view) {
    const show = {
      placeholder: view === "placeholder",
      loading: view === "loading",
      error: view === "error",
      output: view === "output"
    };
    els.placeholder.hidden = !show.placeholder;
    els.loading.hidden = !show.loading;
    els.error.hidden = !show.error;
    els.output.hidden = !show.output;
    els.result.dataset.state = view;
    els.result.setAttribute("aria-busy", view === "loading" ? "true" : "false");
    els.btn.disabled = view === "loading";
    els.btn.setAttribute("aria-disabled", view === "loading" ? "true" : "false");
  }

  function errorMessage(body, status) {
    let message = body && (body.error || body.detail || body.message);
    if (Array.isArray(message)) {
      message = message.map(function (item) {
        if (item && typeof item === "object") return item.msg || item.message || "";
        return String(item || "");
      }).filter(Boolean).join("；");
    }
    if (message && typeof message === "object") {
      try {
        message = JSON.stringify(message);
      } catch (_err) {
        message = "";
      }
    }
    if (typeof message === "string" && message.trim()) return message.trim();

    const defaults = {
      400: "请求无效：请确认句子非空且不超过 500 字。",
      401: "接口需要访问令牌；请检查本地服务配置。",
      404: "接口或候选来源不存在；请确认本地服务版本。",
      429: "请求太频繁，请稍等几秒再试。",
      500: "服务端出错；请稍后重试。",
      502: "上游文献服务暂时不可用；请稍后重试。",
      503: "服务暂不可用（可能处于离线模式或未配置判定模型）。"
    };
    return defaults[status] || "请求失败（HTTP " + status + "）。";
  }

  function candidateUrl(candidate) {
    const direct = safeHref(candidate && candidate.url);
    if (direct) return direct;
    const doi = String((candidate && candidate.doi) || "").trim();
    if (!doi) return "";
    return "https://doi.org/" + encodeURIComponent(doi).replace(/%2F/gi, "/");
  }

  function confidencePercent(value) {
    return Math.round(clamp01(number(value, 0)) * 100);
  }

  function renderCandidates(candidates) {
    clear(els.candidates);
    const list = Array.isArray(candidates) ? candidates.slice() : [];
    list.sort(function (a, b) {
      return number(b && b.score, 0) - number(a && a.score, 0);
    });
    const shown = list.slice(0, MAX_CANDIDATES);

    if (!shown.length) {
      const empty = el("li", "live-candidates-empty");
      empty.appendChild(el("strong", "", "没有检索到可展示的候选论文。"));
      empty.appendChild(document.createTextNode("可以把页面标题 / URL 填上再试，或换一句更具体的断言；没有候选时不会硬凑证据。"));
      els.candidates.appendChild(empty);
      els.candidateCount.textContent = "0 条";
      return;
    }

    shown.forEach(function (candidate, index) {
      const item = el("li", "live-candidate");
      const head = el("div", "live-candidate-head");
      head.appendChild(el("span", "live-candidate-rank", "#" + (index + 1)));

      const title = el("span", "live-candidate-title", candidate && candidate.title ? candidate.title : "未命名候选");
      const href = candidateUrl(candidate);
      if (href) {
        const link = el("a", "live-candidate-link");
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.appendChild(title);
        head.appendChild(link);
      } else {
        head.appendChild(title);
      }
      item.appendChild(head);

      const meta = [];
      if (candidate && Array.isArray(candidate.authors) && candidate.authors.length) {
        const first = String(candidate.authors[0] || "").trim();
        if (first) meta.push(candidate.authors.length > 1 ? first + " 等" : first);
      }
      if (candidate && candidate.year) meta.push(String(candidate.year));
      if (candidate && candidate.venue) meta.push(String(candidate.venue));
      if (meta.length) item.appendChild(el("p", "live-candidate-meta", meta.join(" · ")));

      const foot = el("div", "live-candidate-foot");
      const source = String((candidate && candidate.source) || "").toLowerCase();
      foot.appendChild(el("span", "live-source", SOURCE_LABELS[source] || (source ? source : "未知来源")));

      const score = number(candidate && candidate.score, NaN);
      if (Number.isFinite(score)) {
        foot.appendChild(el("span", "live-score", "相关度 " + Math.round(clamp01(score) * 100) + "%"));
      }

      if (candidate && candidate.label && LABELS[candidate.label]) {
        const badge = el("span", "live-badge live-badge--" + candidate.label, LABELS[candidate.label].text);
        if (candidate.confidence !== undefined) {
          badge.appendChild(document.createTextNode(" " + confidencePercent(candidate.confidence) + "%"));
        }
        foot.appendChild(badge);
      }
      item.appendChild(foot);

      const abstract = candidate && candidate.abstract ? String(candidate.abstract).trim() : "";
      if (abstract) {
        const details = document.createElement("details");
        details.className = "live-candidate-abstract";
        details.appendChild(el("summary", "", "查看摘要片段"));
        details.appendChild(el("p", "", abstract));
        item.appendChild(details);
      }

      els.candidates.appendChild(item);
    });

    els.candidateCount.textContent = shown.length + " 条";
  }

  function renderEvidence(evidence) {
    const quote = evidence && evidence.quote ? String(evidence.quote).trim() : "";
    if (!quote) {
      els.evidence.hidden = true;
      els.evidenceTitle.textContent = "";
      els.quote.textContent = "";
      els.evidenceLink.removeAttribute("href");
      return;
    }

    els.evidence.hidden = false;
    els.evidenceTitle.textContent = evidence.title ? String(evidence.title) : "候选论文";
    els.quote.textContent = quote;

    const href = safeHref(evidence.url);
    if (href) {
      els.evidenceLink.href = href;
      els.evidenceLink.setAttribute("target", "_blank");
      els.evidenceLink.setAttribute("rel", "noopener noreferrer");
    } else {
      els.evidenceLink.removeAttribute("href");
      els.evidenceLink.removeAttribute("target");
    }
  }

  function renderResult(data) {
    const key = data && LABELS[data.label] ? data.label : "no_evidence";
    const label = LABELS[key];
    els.label.className = "live-badge live-badge--" + key;
    els.label.textContent = label.text;
    els.label.setAttribute("title", label.hint);

    const percent = confidencePercent(data && data.confidence);
    els.confidenceText.textContent = "置信度 " + percent + "%";
    els.bar.style.width = percent + "%";
    els.meter.setAttribute("aria-valuenow", String(percent));

    els.reason.textContent = data && data.reason ? String(data.reason) : "接口没有返回判定理由。";
    renderEvidence(data && data.evidence);
    renderCandidates(data && data.candidates);
    setView("output");
  }

  function showError(message) {
    els.errorMsg.textContent = message || "这次没有查成，请稍后重试。";
    setView("error");
  }

  function renderPending(data) {
    els.label.className = "live-badge";
    els.label.textContent = "判定中…";
    els.label.setAttribute("title", "已找到候选文献，正在判定");
    els.confidenceText.textContent = "置信度 —";
    els.bar.style.width = "0%";
    els.meter.setAttribute("aria-valuenow", "0");
    els.reason.textContent = (data && data.reason) || "已找到候选文献，正在判定…";
    renderEvidence(null);
    renderCandidates(data && data.candidates);
    setView("output");
  }

  function setPrewarm(text, ok) {
    if (!els.prewarm) return;
    els.prewarm.textContent = text;
    els.prewarm.classList.toggle("is-ok", Boolean(ok));
  }

  async function prewarmPageNow() {
    const pageTitle = String((els.pageTitle && els.pageTitle.value) || "").trim();
    const pageUrl = String((els.pageUrl && els.pageUrl.value) || "").trim();
    if (!pageUrl && !pageTitle) {
      setPrewarm("");
      return;
    }
    if (state.prewarmAbort) state.prewarmAbort.abort();
    const controller = new AbortController();
    state.prewarmAbort = controller;
    setPrewarm("正在预热页面引用…", false);
    try {
      const response = await fetch(PREWARM_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ page_url: pageUrl, page_title: pageTitle }),
        signal: controller.signal
      });
      let body = null;
      try {
        body = await response.json();
      } catch (_err) {
        body = null;
      }
      if (!response.ok || !body || body.ok === false) {
        throw new Error((body && body.detail) || "预热失败");
      }
      const count = typeof body.references === "number" ? body.references : 0;
      setPrewarm(count ? `页面已预热 · 参考文献 ${count} 条` : "页面已预热（未发现参考文献）", true);
    } catch (err) {
      if (err && err.name === "AbortError") return;
      setPrewarm("预热失败（不影响核验）", false);
    }
  }

  function schedulePrewarm() {
    window.clearTimeout(state.prewarmTimer);
    state.prewarmTimer = window.setTimeout(prewarmPageNow, 900);
  }

  function setProbeStatus(text, ok) {
    if (!els.probeStatus) return;
    els.probeStatus.textContent = text;
    els.probeStatus.classList.toggle("is-ok", Boolean(ok));
    els.probeStatus.classList.toggle("is-bad", !ok && Boolean(text));
  }

  function renderProbe(data) {
    if (!els.probeResult || !els.probeSummary || !els.probeList) return;
    const total = Number(data.markers_total) || 0;
    const mapped = Number(data.markers_mapped) || 0;
    const ratio = Math.round((Number(data.mapped_ratio) || 0) * 100);
    const title = data.page_title ? `「${String(data.page_title).slice(0, 80)}」` : "该页面";
    if (total === 0) {
      els.probeSummary.textContent =
        `${title}：没有识别到引用标记或参考文献列表。页面可能不是学术页，或使用了脚本渲染。`;
    } else {
      els.probeSummary.textContent =
        `${title}：识别 ${Number(data.reference_count) || 0} 条参考文献、${total} 个引用标记` +
        `（${Number(data.reference_sentences) || 0} 句引用句），` +
        `映射 ${mapped}/${total}（${ratio}%）。只做定位，不判真伪。`;
    }
    els.probeList.replaceChildren();
    (data.sample || []).forEach(function (ref) {
      const item = document.createElement("li");
      const titleText = document.createElement("span");
      titleText.textContent = `[${ref.index}] ${String(ref.title || "（无题名）").slice(0, 120)}`;
      item.append(titleText);
      if (ref.doi) {
        const doi = document.createElement("code");
        doi.textContent = String(ref.doi);
        item.append(document.createTextNode(" · "));
        item.append(doi);
      }
      els.probeList.append(item);
    });
    els.probeResult.hidden = false;
  }

  async function probePage() {
    if (!els.probeBtn || !els.pageUrl) return;
    const pageUrl = els.pageUrl.value.trim();
    if (!pageUrl) {
      setProbeStatus("先填页面 URL，再检查页面引用。", false);
      return;
    }
    els.probeBtn.disabled = true;
    setProbeStatus("正在读取页面引用列表…", false);
    try {
      const response = await fetch(PAGE_API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ page_url: pageUrl })
      });
      const data = await response.json().catch(function () { return {}; });
      if (!response.ok) {
        throw new Error(data.detail || "页面读取失败");
      }
      renderProbe(data);
      setProbeStatus("页面引用已读取；核验时可直接使用正文里的 [n] 标记。", true);
    } catch (error) {
      if (els.probeResult) els.probeResult.hidden = true;
      setProbeStatus(error && error.message ? error.message : "页面读取失败", false);
    } finally {
      els.probeBtn.disabled = false;
    }
  }

  async function runCheck() {
    const claim = String(els.claim.value || "").trim();
    if (!claim) {
      showError("请先输入一句要核验的话。");
      els.claim.focus();
      return;
    }
    if (claim.length > MAX_CLAIM) {
      showError("句子最多 500 字，请缩短后再试。");
      els.claim.focus();
      return;
    }

    const pageTitle = String((els.pageTitle && els.pageTitle.value) || "").trim();
    const pageUrl = String((els.pageUrl && els.pageUrl.value) || "").trim();
    state.last = { claim: claim, pageTitle: pageTitle, pageUrl: pageUrl };
    const requestId = ++state.requestId;
    setView("loading");

    async function postLive(phase) {
      const response = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          claim: claim,
          page_title: pageTitle,
          page_url: pageUrl,
          mode: "fast",
          phase: phase
        })
      });
      let body = null;
      try {
        body = await response.json();
      } catch (_err) {
        body = null;
      }
      if (!response.ok || (body && body.ok === false)) {
        throw new Error(errorMessage(body, response.status));
      }
      const data = body && body.result && typeof body.result === "object" ? body.result : body;
      if (!data || typeof data !== "object" || typeof data.label !== "string") {
        throw new Error("接口返回格式不正确：缺少 label。请确认本地服务版本。");
      }
      return data;
    }

    try {
      // Two-phase: show sources immediately; the verdict follows.
      const retrieval = await postLive("retrieve");
      if (requestId !== state.requestId) return;
      if (retrieval.pending) {
        renderPending(retrieval);
        const final = await postLive("judge");
        if (requestId !== state.requestId) return;
        renderResult(final);
      } else {
        renderResult(retrieval);
      }
    } catch (err) {
      if (requestId !== state.requestId) return;
      const message = err && err.message ? err.message : "网络请求失败，请确认本地服务已启动后重试。";
      showError(message);
    }
  }

  function updateCount() {
    const length = String(els.claim.value || "").length;
    els.count.textContent = length + " / " + MAX_CLAIM;
    els.count.classList.toggle("is-near-limit", length >= 450);
  }

  els.claim.addEventListener("input", updateCount);
  if (els.pageTitle) els.pageTitle.addEventListener("input", schedulePrewarm);
  if (els.pageUrl) els.pageUrl.addEventListener("input", schedulePrewarm);
  if (els.probeBtn) els.probeBtn.addEventListener("click", probePage);
  els.claim.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      runCheck();
    }
  });
  els.btn.addEventListener("click", runCheck);
  els.retry.addEventListener("click", function () {
    if (state.last) {
      runCheck();
    } else {
      els.claim.focus();
    }
  });

  document.querySelectorAll(".live-example").forEach(function (button) {
    button.addEventListener("click", function () {
      const claim = button.getAttribute("data-claim") || "";
      const pageTitle = button.getAttribute("data-page-title") || "";
      els.claim.value = claim;
      if (els.pageTitle) els.pageTitle.value = pageTitle;
      if (els.pageUrl) els.pageUrl.value = button.getAttribute("data-page-url") || "";
      updateCount();
      schedulePrewarm();
      els.claim.focus();
    });
  });

  updateCount();
  setView("placeholder");
})();
