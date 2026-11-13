(function () {
  "use strict";

  const API = "/api/live/check";
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
    candidates: document.getElementById("live-candidates")
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
    last: null
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

    try {
      const response = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          claim: claim,
          page_title: pageTitle,
          page_url: pageUrl
        })
      });

      let body = null;
      try {
        body = await response.json();
      } catch (_err) {
        body = null;
      }
      if (requestId !== state.requestId) return;

      if (!response.ok) {
        throw new Error(errorMessage(body, response.status));
      }
      if (body && body.ok === false) {
        throw new Error(errorMessage(body, response.status));
      }

      const data = body && body.result && typeof body.result === "object" ? body.result : body;
      if (!data || typeof data !== "object" || typeof data.label !== "string") {
        throw new Error("接口返回格式不正确：缺少 label。请确认本地服务版本。");
      }
      renderResult(data);
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
      updateCount();
      els.claim.focus();
    });
  });

  updateCount();
  setView("placeholder");
})();
