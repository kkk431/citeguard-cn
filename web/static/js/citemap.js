(function () {
  "use strict";

  const app = document.getElementById("citemap-app");
  if (!app) return;

  const els = {
    topicSwitch: document.getElementById("ctm-topic-switch"),
    status: document.getElementById("ctm-status"),
    loading: document.getElementById("ctm-loading"),
    error: document.getElementById("ctm-error"),
    errorMsg: document.getElementById("ctm-error-msg"),
    retry: document.getElementById("ctm-retry"),
    empty: document.getElementById("ctm-empty"),
    emptyMsg: document.getElementById("ctm-empty-msg"),
    layout: document.getElementById("ctm-layout"),
    topicTitle: document.getElementById("ctm-topic-title"),
    topicQuestion: document.getElementById("ctm-topic-question"),
    topicStats: document.getElementById("ctm-topic-stats"),
    paperList: document.getElementById("ctm-paper-list"),
    paperCount: document.getElementById("ctm-paper-count"),
    detail: document.getElementById("ctm-detail"),
    detailEmpty: document.getElementById("ctm-detail-empty"),
    detailBody: document.getElementById("ctm-detail-body"),
    verifyToggle: document.getElementById("ctm-verify-toggle"),
    verifyCount: document.getElementById("ctm-verify-count")
  };

  if (!els.paperList || !els.detailBody) return;

  const TOPIC_LABELS = Object.freeze({
    ai_education: "AI 教育",
    medical_imaging: "医学影像"
  });
  const STANCE_LABELS = Object.freeze({
    support: "支持",
    contradict: "反驳",
    neutral: "中立"
  });
  const RISK_LABELS = Object.freeze({
    low: "低",
    some: "有一些",
    high: "高",
    unclear: "不明确"
  });
  const GAP_KIND_LABELS = Object.freeze({
    evidence: "证据缺口",
    method: "方法缺口",
    sample: "样本缺口",
    outcome: "结局缺口",
    theory: "理论缺口"
  });
  const SEVERITY_LABELS = Object.freeze({
    low: "低",
    medium: "中",
    high: "高"
  });
  const DIRECTION_LABELS = Object.freeze({
    positive: "正向",
    negative: "负向",
    no_effect: "无显著差异",
    mixed: "混合",
    unclear: "不明确"
  });

  const state = {
    topics: [],
    topicId: "",
    payload: null,
    selectedPaperId: "",
    verifyMode: false,
    requestId: 0
  };

  function setView(view) {
    const views = {
      loading: els.loading,
      error: els.error,
      empty: els.empty,
      layout: els.layout
    };
    Object.keys(views).forEach(function (key) {
      const node = views[key];
      if (node) node.hidden = key !== view;
    });
    app.dataset.state = view;
  }

  function setBusy(busy) {
    app.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function setStatus(text, tone) {
    if (!els.status) return;
    els.status.textContent = text || "";
    if (tone) {
      els.status.dataset.tone = tone;
    } else {
      delete els.status.dataset.tone;
    }
  }

  function showError(message) {
    if (els.errorMsg) els.errorMsg.textContent = message || "加载失败，请稍后重试。";
    setView("error");
    setBusy(false);
    setStatus("加载失败", "bad");
  }

  function showEmpty(message) {
    if (els.emptyMsg) els.emptyMsg.textContent = message || "暂无数据。";
    setView("empty");
    setBusy(false);
    setStatus("暂无数据");
  }

  function readTopicFromUrl() {
    try {
      return new URLSearchParams(window.location.search).get("topic") || "";
    } catch (err) {
      return "";
    }
  }

  function syncUrl(topicId) {
    try {
      const url = new URL(window.location.href);
      if (url.searchParams.get("topic") !== topicId) {
        url.searchParams.set("topic", topicId);
        window.history.replaceState({ topic: topicId }, "", url.toString());
      }
    } catch (err) {
      /* 地址栏同步失败不应阻断内容渲染 */
    }
  }

  function topicLabel(topicId) {
    if (TOPIC_LABELS[topicId]) return TOPIC_LABELS[topicId];
    const meta = state.topics.find(function (topic) { return topic.topic_id === topicId; });
    return (meta && (meta.name_zh || meta.name_en)) || topicId;
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function makeTag(text, className) {
    return make("span", "ctm-tag" + (className ? " " + className : ""), text);
  }

  function safeHref(value) {
    if (!value) return "";
    try {
      const url = new URL(String(value), window.location.origin);
      if (url.protocol === "http:" || url.protocol === "https:") return url.href;
    } catch (err) {
      return "";
    }
    return "";
  }

  function doiHref(doi) {
    const value = String(doi || "").trim().replace(/^(?:https?:\/\/(?:dx\.)?doi\.org\/|doi:\s*)/i, "");
    if (!value) return "";
    return "https://doi.org/" + encodeURIComponent(value).replace(/%2F/gi, "/");
  }

  function errorMessage(data, status) {
    if (data && typeof data.error === "string" && data.error.trim()) return data.error;
    if (data && data.error && typeof data.error.message === "string") return data.error.message;
    if (data && typeof data.detail === "string" && data.detail.trim()) return data.detail;
    if (status === 404) return "未找到该主题（HTTP 404）。";
    if (status === 500) return "CiteMap 数据校验失败（HTTP 500），请检查服务端日志。";
    return "CiteMap 接口请求失败（HTTP " + status + "）。";
  }

  async function fetchJSON(url) {
    return requestJSON(url, "GET", null);
  }

  async function requestJSON(url, method, body) {
    let response;
    try {
      response = await fetch(url, {
        method: method,
        headers: body
          ? { "Accept": "application/json", "Content-Type": "application/json" }
          : { "Accept": "application/json" },
        credentials: "same-origin",
        body: body ? JSON.stringify(body) : undefined
      });
    } catch (err) {
      throw new Error("无法连接 CiteMap 接口，请检查服务是否在线。");
    }

    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      data = null;
    }

    if (!response.ok) throw new Error(errorMessage(data, response.status));
    if (data === null) throw new Error("接口返回了空响应或无法解析的数据。");
    return data;
  }

  async function init() {
    state.requestId += 1;
    state.topicId = "";
    state.payload = null;
    state.selectedPaperId = "";
    setView("loading");
    setBusy(true);
    setStatus("正在加载主题…");

    try {
      const data = await fetchJSON("/api/citemap/topics");
      const topics = Array.isArray(data) ? data : (data && Array.isArray(data.topics) ? data.topics : []);
      state.topics = topics.filter(function (topic) {
        return topic && typeof topic.topic_id === "string" && topic.topic_id;
      });

      if (!state.topics.length) {
        showEmpty("暂无 CiteMap 主题，数据层可能尚未生成。");
        return;
      }

      renderTopicSwitch();
      const requested = readTopicFromUrl() || (app.dataset.topic || "").trim();
      const known = state.topics.some(function (topic) { return topic.topic_id === requested; });
      const topicId = known ? requested : state.topics[0].topic_id;
      await selectTopic(topicId, { syncUrl: true });
    } catch (err) {
      showError(err && err.message ? err.message : "主题列表加载失败。");
    }
  }

  function renderTopicSwitch() {
    if (!els.topicSwitch) return;
    els.topicSwitch.replaceChildren();
    state.topics.forEach(function (topic) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ctm-topic-btn";
      button.dataset.topicId = topic.topic_id;
      button.textContent = topicLabel(topic.topic_id);
      button.setAttribute("aria-pressed", "false");
      button.addEventListener("click", function () {
        if (topic.topic_id !== state.topicId) {
          selectTopic(topic.topic_id, { syncUrl: true });
        }
      });
      els.topicSwitch.append(button);
    });
    syncTopicButtons();
  }

  function syncTopicButtons() {
    if (!els.topicSwitch) return;
    els.topicSwitch.querySelectorAll("[data-topic-id]").forEach(function (button) {
      const active = button.dataset.topicId === state.topicId;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  async function selectTopic(topicId, options) {
    const opts = options || {};
    const seq = state.requestId + 1;
    state.requestId = seq;
    state.topicId = topicId;
    state.payload = null;
    app.dataset.topic = topicId;
    syncTopicButtons();
    setView("loading");
    setBusy(true);
    setStatus("正在加载「" + topicLabel(topicId) + "」…");

    try {
      const payload = await fetchJSON("/api/citemap/" + encodeURIComponent(topicId));
      if (seq !== state.requestId) return;

      state.payload = payload && typeof payload === "object" ? payload : {};
      const papers = Array.isArray(state.payload.papers) ? state.payload.papers : [];
      if (!papers.length) {
        showEmpty("该主题暂无已登记的论文。");
        return;
      }

      renderPayload();
      setView("layout");
      setBusy(false);
      setStatus("已加载 " + papers.length + " 篇论文", "ok");
      if (opts.syncUrl) syncUrl(topicId);
    } catch (err) {
      if (seq !== state.requestId) return;
      showError(err && err.message ? err.message : "主题数据加载失败。");
    }
  }

  function renderPayload() {
    const payload = state.payload || {};
    const topic = payload.topic && typeof payload.topic === "object" ? payload.topic : {};
    const papers = Array.isArray(payload.papers) ? payload.papers : [];
    const claims = Array.isArray(payload.claims) ? payload.claims : [];
    const evidence = Array.isArray(payload.evidence) ? payload.evidence : [];
    const gaps = Array.isArray(payload.gaps) ? payload.gaps : [];

    if (els.topicTitle) {
      els.topicTitle.textContent = topic.name_zh || topicLabel(state.topicId);
    }
    if (els.topicQuestion) {
      els.topicQuestion.textContent = topic.question || "";
      els.topicQuestion.hidden = !topic.question;
    }
    renderTopicStats(payload, papers, claims, evidence, gaps);
    updateVerifyCount();
    if (els.verifyToggle) {
      els.verifyToggle.setAttribute("aria-pressed", state.verifyMode ? "true" : "false");
      els.verifyToggle.classList.toggle("is-active", state.verifyMode);
    }

    if (els.paperCount) {
      els.paperCount.textContent = "共 " + papers.length + " 篇 · 点击查看证据";
    }

    renderPaperList(papers);
    const keep = papers.some(function (paper) { return paper.paper_id === state.selectedPaperId; })
      ? state.selectedPaperId
      : (papers[0] && papers[0].paper_id) || "";
    selectPaper(keep, false);
  }

  function numberOr(value, fallback) {
    return typeof value === "number" && Number.isFinite(value) ? value : fallback;
  }

  function autoForTopic() {
    return state.payload && Array.isArray(state.payload.auto_evidence) ? state.payload.auto_evidence : [];
  }

  function autoForPaper(paperId) {
    return autoForTopic().filter(function (ev) { return ev && ev.paper_id === paperId; });
  }

  function normQuote(value) {
    return String(value || "").normalize("NFKC").toLowerCase().replace(/\s+/g, "");
  }

  function sameQuote(left, right) {
    const a = normQuote(left);
    const b = normQuote(right);
    if (!a || !b) return false;
    if (a === b) return true;
    const shorter = a.length <= b.length ? a : b;
    const longer = a.length <= b.length ? b : a;
    return shorter.length >= 40 && longer.indexOf(shorter) !== -1;
  }

  function autoMatchesHuman(autoEv, humanEv) {
    return Boolean(autoEv && humanEv)
      && autoEv.claim_id === humanEv.claim_id
      && sameQuote(autoEv.quote, humanEv.quote);
  }

  function autoDuplicatesForPaper(paperId) {
    const human = evidenceForPaper(paperId);
    return autoForPaper(paperId).filter(function (autoEv) {
      return human.some(function (humanEv) { return autoMatchesHuman(autoEv, humanEv); });
    });
  }

  function autoUniqueForPaper(paperId) {
    const human = evidenceForPaper(paperId);
    return autoForPaper(paperId).filter(function (autoEv) {
      return !human.some(function (humanEv) { return autoMatchesHuman(autoEv, humanEv); });
    });
  }

  function autoUniqueForTopic() {
    return autoForTopic().filter(function (autoEv) {
      return !evidenceForPaper(autoEv.paper_id).some(function (humanEv) {
        return autoMatchesHuman(autoEv, humanEv);
      });
    });
  }

  function cellsForPaper(paperId) {
    const cells = state.payload && Array.isArray(state.payload.verification_cells)
      ? state.payload.verification_cells
      : [];
    return cells.filter(function (cell) { return cell && cell.paper_id === paperId; });
  }

  function cellForEvidence(evidenceId) {
    const cells = state.payload && Array.isArray(state.payload.verification_cells)
      ? state.payload.verification_cells
      : [];
    return cells.find(function (cell) { return cell.evidence_id === evidenceId; }) || null;
  }

  function updateVerifyCount() {
    if (!els.verifyCount) return;
    const progress = (state.payload && state.payload.verification_progress) || {};
    if (!progress.packet) {
      els.verifyCount.textContent = "";
      return;
    }
    els.verifyCount.textContent = "抽样 " + progress.packet + " 格 · 已核对 " + (progress.checked || 0) +
      " · 通过 " + (progress.verified || 0);
  }

  function renderTopicStats(payload, papers, claims, evidence, gaps) {
    if (!els.topicStats) return;
    els.topicStats.replaceChildren();
    const counts = payload.counts && typeof payload.counts === "object" ? payload.counts : {};

    addStat("篇论文", numberOr(counts.papers, papers.length));
    addStat("条断言", numberOr(counts.claims, claims.length));
    addStat("条示例证据", numberOr(counts.evidence, evidence.length));
    addStat("条机器证据", autoUniqueForTopic().length);
    const mergedTotal = papers.reduce(function (total, paper) {
      return total + autoDuplicatesForPaper(paper.paper_id).length;
    }, 0);
    if (mergedTotal) addStat("已合并重合", mergedTotal);
    addStat("个证据缺口", numberOr(counts.gaps, gaps.length));

    const summary = payload.verification && payload.verification.summary;
    if (summary && typeof summary.crossref_ok === "number" && typeof summary.papers === "number") {
      addStat("全库 DOI 校验", summary.crossref_ok + "/" + summary.papers);
    }
    const progress = payload.verification_progress || {};
    if (progress.packet) {
      addStat("抽样核对", (progress.checked || 0) + "/" + progress.packet);
    }
  }

  function addStat(label, value) {
    if (!els.topicStats) return;
    const item = make("span", "ctm-topic-stat");
    item.append(make("strong", "", String(value)));
    item.append(make("span", "", label));
    els.topicStats.append(item);
  }

  function renderPaperList(papers) {
    els.paperList.replaceChildren();
    const visible = state.verifyMode
      ? papers.filter(function (paper) { return cellsForPaper(paper.paper_id).length > 0; })
      : papers;
    visible.forEach(function (paper) {
      const item = make("li", "ctm-paper-item");
      item.dataset.paperId = paper.paper_id || "";

      const button = document.createElement("button");
      button.type = "button";
      button.className = "ctm-paper-select";
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-controls", "ctm-detail-body");
      button.append(make("span", "ctm-paper-title", paper.title || "（无标题）"));

      const metaBits = [];
      if (paper.year) metaBits.push(String(paper.year));
      if (paper.venue) metaBits.push(paper.venue);
      if (metaBits.length) {
        button.append(make("span", "ctm-paper-venue", metaBits.join(" · ")));
      }

      const tags = make("span", "ctm-paper-tags");
      if (paper.cn_affiliated) tags.append(makeTag("中国机构参与", "ctm-tag--cn"));
      if (paper.license) tags.append(makeTag(paper.license, "ctm-tag--license"));
      if (paper.is_oa) tags.append(makeTag("OA", "ctm-tag--oa"));
      const autoCount = autoUniqueForPaper(paper.paper_id).length;
      const autoMerged = autoDuplicatesForPaper(paper.paper_id).length;
      if (autoCount) tags.append(makeTag("机器证据 " + autoCount, "ctm-tag--auto"));
      const cells = cellsForPaper(paper.paper_id);
      if (cells.length) {
        const pending = cells.filter(function (cell) { return !cell.check; }).length;
        tags.append(makeTag(
          pending ? "待核对 " + pending : "已核对",
          pending ? "ctm-tag--todo" : "ctm-tag--done"
        ));
      }
      if (tags.childElementCount) button.append(tags);

      item.append(button);

      const foot = make("div", "ctm-paper-foot");
      appendDoi(foot, paper.doi);
      if (paper.oa_url) {
        const href = safeHref(paper.oa_url);
        if (href) {
          const link = make("a", "ctm-paper-link", "开放全文");
          link.href = href;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          foot.append(link);
        }
      }
      item.append(foot);
      els.paperList.append(item);
    });
  }

  function appendDoi(container, doi) {
    if (!doi) {
      container.append(make("span", "ctm-doi ctm-doi--none", "无 DOI"));
      return;
    }
    const href = doiHref(doi);
    if (!href) {
      container.append(make("span", "ctm-doi ctm-doi--none", "DOI " + doi));
      return;
    }
    const link = make("a", "ctm-doi", "DOI " + doi);
    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    container.append(link);
  }

  function selectPaper(paperId, scroll) {
    const papers = state.payload && Array.isArray(state.payload.papers) ? state.payload.papers : [];
    if (!papers.length) {
      if (els.detailBody) els.detailBody.hidden = true;
      if (els.detailEmpty) els.detailEmpty.hidden = false;
      return;
    }

    const paper = papers.find(function (item) { return item.paper_id === paperId; }) || papers[0];
    state.selectedPaperId = paper.paper_id || "";
    let selectedItem = null;

    els.paperList.querySelectorAll(".ctm-paper-item").forEach(function (item) {
      const active = item.dataset.paperId === state.selectedPaperId;
      item.classList.toggle("is-selected", active);
      const button = item.querySelector(".ctm-paper-select");
      if (button) button.setAttribute("aria-expanded", active ? "true" : "false");
      if (active) selectedItem = item;
    });

    if (scroll && selectedItem) {
      try {
        selectedItem.scrollIntoView({ block: "nearest" });
      } catch (err) {
        /* 旧浏览器忽略滚动即可 */
      }
    }

    renderDetail(paper);
    if (els.detailEmpty) els.detailEmpty.hidden = true;
    if (els.detailBody) els.detailBody.hidden = false;
  }

  function evidenceForPaper(paperId) {
    const items = state.payload && Array.isArray(state.payload.evidence) ? state.payload.evidence : [];
    return items.filter(function (ev) { return ev && ev.paper_id === paperId; });
  }

  function claimById(claimId) {
    const claims = state.payload && Array.isArray(state.payload.claims) ? state.payload.claims : [];
    return claims.find(function (claim) { return claim.claim_id === claimId; }) || null;
  }

  function renderDetail(paper) {
    const body = els.detailBody;
    if (state.detailPaper !== paper.paper_id && els.detail) {
      els.detail.scrollTop = 0;
    }
    state.detailPaper = paper.paper_id;
    body.replaceChildren();

    const evidence = evidenceForPaper(paper.paper_id);
    const head = make("header", "ctm-detail-head");
    const titleRow = make("div", "ctm-detail-title-row");
    titleRow.append(make("h2", "ctm-detail-title", paper.title || "（无标题）"));
    if (evidence.length) {
      titleRow.append(makeTag("证据 " + evidence.length + " 条", "ctm-detail-count"));
    }
    head.append(titleRow);

    const authors = Array.isArray(paper.authors)
      ? paper.authors.slice(0, 4).join("、") + (paper.authors.length > 4 ? " 等" : "")
      : String(paper.authors || "");
    const metaBits = [];
    if (authors) metaBits.push(authors);
    if (paper.year) metaBits.push(String(paper.year));
    if (paper.venue) metaBits.push(paper.venue);
    if (metaBits.length) head.append(make("p", "ctm-detail-meta", metaBits.join(" · ")));

    const tags = make("div", "ctm-detail-tags");
    if (paper.cn_affiliated) tags.append(makeTag("中国机构参与", "ctm-tag--cn"));
    if (paper.license) tags.append(makeTag("许可 " + paper.license, "ctm-tag--license"));
    if (paper.oa_status) tags.append(makeTag("OA 状态 " + paper.oa_status, "ctm-tag--oa"));
    if (paper.fulltext_available) tags.append(makeTag("可获取全文", "ctm-tag--fulltext"));
    if (Number(paper.cited_by) > 0) tags.append(makeTag("被引 " + paper.cited_by, "ctm-tag--cite"));
    if (tags.childElementCount) head.append(tags);

    const links = make("div", "ctm-detail-links");
    if (paper.doi) {
      const href = doiHref(paper.doi);
      if (href) {
        const link = make("a", "", "DOI · " + paper.doi);
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        links.append(link);
      }
    }
    if (paper.oa_url) {
      const href = safeHref(paper.oa_url);
      if (href) {
        const link = make("a", "", "开放全文");
        link.href = href;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        links.append(link);
      }
    }
    if (paper.openalex_id && /^W\d{6,}$/.test(paper.openalex_id)) {
      const link = make("a", "", "OpenAlex · " + paper.openalex_id);
      link.href = "https://openalex.org/" + paper.openalex_id;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      links.append(link);
    }
    if (links.childElementCount) head.append(links);
    body.append(head);

    if (paper.notes) body.append(make("p", "ctm-paper-note", paper.notes));

    if (!evidence.length) {
      body.append(make("p", "ctm-detail-empty-note", "该论文暂无人工示例证据；本页只展示清单元数据。"));
    } else {
      const section = make("section", "ctm-evidence-section");
      section.append(make("h3", "", "断言与证据"));
      evidence.forEach(function (ev) {
        const duplicate = autoDuplicatesForPaper(paper.paper_id).find(function (autoEv) {
          return autoMatchesHuman(autoEv, ev);
        });
        const cell = duplicate ? cellForEvidence(duplicate.evidence_id) : null;
        section.append(renderEvidence(ev, claimById(ev.claim_id), cell));
      });
      body.append(section);
    }

    const autoSection = renderAutoSection(paper);
    if (autoSection) body.append(autoSection);

    const relatedClaims = [];
    evidence.forEach(function (ev) {
      if (ev.claim_id && relatedClaims.indexOf(ev.claim_id) === -1) relatedClaims.push(ev.claim_id);
    });
    body.append(renderGaps(relatedClaims));
  }

  function normalizeStance(value) {
    const stance = String(value || "neutral");
    return Object.prototype.hasOwnProperty.call(STANCE_LABELS, stance) ? stance : "neutral";
  }

  function normalizeSeverity(value) {
    const severity = String(value || "medium");
    return Object.prototype.hasOwnProperty.call(SEVERITY_LABELS, severity) ? severity : "medium";
  }

  function renderEvidence(ev, claim, cell) {
    const card = make("article", "ctm-evidence");
    const top = make("div", "ctm-evidence-top");
    const stance = normalizeStance(ev.stance);
    top.append(makeTag(STANCE_LABELS[stance], "ctm-stance ctm-stance--" + stance));

    if (ev.extracted_by === "human") {
      top.append(makeTag("人工示例", "ctm-extractor"));
    }
    top.append(makeTag(
      ev.verified ? "已核对全文" : "仅摘要 · verified=false",
      ev.verified ? "ctm-verified" : "ctm-verified ctm-verified--no"
    ));
    top.append(renderConfidence(ev.confidence));
    if (ev.evidence_id) top.append(make("span", "ctm-evidence-id", ev.evidence_id));
    card.append(top);

    if (claim) {
      const claimBox = make("div", "ctm-claim");
      claimBox.append(make("span", "ctm-claim-label", "对应断言 · " + claim.claim_id));
      claimBox.append(make("p", "ctm-claim-text", claim.text || ""));
      if (claim.direction) {
        claimBox.append(make("span", "ctm-claim-dir", "断言方向：" + (DIRECTION_LABELS[claim.direction] || claim.direction)));
      }
      card.append(claimBox);
    } else if (ev.claim_id) {
      card.append(make("p", "ctm-muted", "对应断言 " + ev.claim_id + " 未在本主题登记。"));
    }

    if (ev.summary) card.append(make("p", "ctm-evidence-summary", ev.summary));

    if (ev.quote) {
      const quote = make("blockquote", "ctm-quote");
      quote.append(make("p", "ctm-quote-text", ev.quote));
      const meta = make("footer", "ctm-quote-meta");
      meta.append(make("span", "ctm-locator", "定位：" + (ev.locator || "未标注")));
      if (ev.quote_lang) meta.append(make("span", "ctm-lang", "原文语言：" + String(ev.quote_lang).toUpperCase()));
      quote.append(meta);
      card.append(quote);
    } else {
      card.append(make("p", "ctm-muted", "该条证据没有登记逐字引用。"));
    }

    const method = ev.method ? renderMethod(ev.method) : null;
    const sample = ev.sample ? renderSample(ev.sample) : null;
    if (method || sample) {
      const grid = make("div", "ctm-facts-grid");
      if (method) grid.append(method);
      if (sample) grid.append(sample);
      card.append(grid);
    } else {
      card.append(make("p", "ctm-muted", "未提供结构化方法 / 样本字段。"));
    }

    if (ev.notes) card.append(make("p", "ctm-evidence-note", ev.notes));
    if (cell) card.append(renderVerifyRow(cell));
    return card;
  }

  function renderAutoSection(paper) {
    const cells = cellsForPaper(paper.paper_id);
    const allAuto = autoUniqueForPaper(paper.paper_id);
    const mergedAuto = autoDuplicatesForPaper(paper.paper_id).length;
    const auto = state.verifyMode
      ? allAuto.filter(function (ev) { return Boolean(cellForEvidence(ev.evidence_id)); })
      : allAuto;
    const emptyCells = cells.filter(function (cell) { return !cell.evidence_id; });
    if (!auto.length && !emptyCells.length) return null;

    const section = make("section", "ctm-evidence-section ctm-auto-section");
    const head = make("div", "ctm-auto-head");
    head.append(make("h3", "", "机器抽取 · 仅摘要"));
    head.append(make("span", "ctm-auto-note",
      "由模型从摘要抽取，尚未逐条人工核对；引用为逐字摘录。" +
      (mergedAuto ? " 与人工示例重合 " + mergedAuto + " 条，已合并到人工卡片。" : "")));
    section.append(head);

    auto.forEach(function (ev) {
      section.append(renderAutoEvidence(ev, claimById(ev.claim_id), cellForEvidence(ev.evidence_id)));
    });
    emptyCells.forEach(function (cell) {
      section.append(renderNoEvidenceCell(cell, claimById(cell.claim_id)));
    });
    return section;
  }

  function renderAutoEvidence(ev, claim, cell) {
    const card = make("article", "ctm-evidence ctm-evidence--auto");
    const top = make("div", "ctm-evidence-top");
    const stance = normalizeStance(ev.stance);
    top.append(makeTag(STANCE_LABELS[stance], "ctm-stance ctm-stance--" + stance));
    top.append(makeTag("机器抽取 · 仅摘要", "ctm-extractor ctm-extractor--auto"));
    if (cell) top.append(makeTag("抽样格", "ctm-cell-tag"));
    top.append(renderConfidence(ev.confidence));
    card.append(top);

    if (claim) {
      const claimBox = make("div", "ctm-claim");
      claimBox.append(make("span", "ctm-claim-label", "对应断言 · " + claim.claim_id));
      claimBox.append(make("p", "ctm-claim-text", claim.text || ""));
      card.append(claimBox);
    }
    if (ev.summary) card.append(make("p", "ctm-evidence-summary", ev.summary));
    if (ev.quote) {
      const quote = make("blockquote", "ctm-quote");
      quote.append(make("p", "ctm-quote-text", ev.quote));
      const meta = make("footer", "ctm-quote-meta");
      meta.append(make("span", "ctm-locator", "定位：摘要"));
      quote.append(meta);
      card.append(quote);
    }
    const facts = [];
    if (ev.method) facts.push("方法：" + ev.method);
    if (ev.sample) facts.push("样本：" + ev.sample);
    if (facts.length) card.append(make("p", "ctm-muted", facts.join(" · ")));
    if (cell) card.append(renderVerifyRow(cell));
    return card;
  }

  function renderNoEvidenceCell(cell, claim) {
    const card = make("article", "ctm-evidence ctm-evidence--auto ctm-evidence--empty");
    const top = make("div", "ctm-evidence-top");
    top.append(makeTag("未发现证据", "ctm-stance ctm-stance--neutral"));
    top.append(makeTag("抽样格", "ctm-cell-tag"));
    card.append(top);
    if (claim) {
      const claimBox = make("div", "ctm-claim");
      claimBox.append(make("span", "ctm-claim-label", "对应断言 · " + claim.claim_id));
      claimBox.append(make("p", "ctm-claim-text", claim.text || ""));
      card.append(claimBox);
    }
    card.append(make("p", "ctm-muted", "机器没有从摘要中找到逐字支持/反驳句。请核对是否确实无证据。"));
    card.append(renderVerifyRow(cell));
    return card;
  }

  function renderVerifyRow(cell) {
    const row = make("div", "ctm-verify-row");
    if (cell.check) {
      const label = cell.check.status === "ok" ? "已核对：通过" : cell.check.status === "issue" ? "已核对：有问题" : "已跳过";
      row.append(make("span", "ctm-verify-done", label));
      return row;
    }
    ["ok", "issue", "skip"].forEach(function (status) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-ghost ctm-verify-btn";
      button.dataset.verify = "1";
      button.dataset.cellId = cell.cell_id;
      button.dataset.status = status;
      button.textContent = status === "ok" ? "✓ 正确" : status === "issue" ? "✗ 有问题" : "跳过";
      row.append(button);
    });
    return row;
  }

  async function verifyCell(button) {
    const cellId = button.dataset.cellId;
    const status = button.dataset.status;
    if (!cellId || !status) return;
    button.disabled = true;
    try {
      const result = await requestJSON(
        "/api/citemap/" + encodeURIComponent(state.topicId) + "/verify",
        "POST",
        { cell_id: cellId, status: status }
      );
      const cells = state.payload && Array.isArray(state.payload.verification_cells)
        ? state.payload.verification_cells
        : [];
      const cell = cells.find(function (item) { return item.cell_id === cellId; });
      if (cell) cell.check = result.cell;
      if (state.payload) state.payload.verification_progress = result;
      updateVerifyCount();
      const papers = state.payload && Array.isArray(state.payload.papers) ? state.payload.papers : [];
      renderPaperList(papers);
      const current = papers.find(function (paper) { return paper.paper_id === state.selectedPaperId; });
      if (current) renderDetail(current);
    } catch (err) {
      button.disabled = false;
      setStatus(err && err.message ? err.message : "核对保存失败。", "warn");
    }
  }

  function renderConfidence(value) {
    const raw = Number(value);
    const confidence = Number.isFinite(raw) ? Math.min(1, Math.max(0, raw)) : 0;
    const box = make("div", "ctm-confidence");
    box.append(make("span", "ctm-confidence-label", "置信度 " + confidence.toFixed(2)));

    const track = make("div", "ctm-confidence-track");
    track.setAttribute("role", "meter");
    track.setAttribute("aria-label", "人工抽取置信度");
    track.setAttribute("aria-valuemin", "0");
    track.setAttribute("aria-valuemax", "1");
    track.setAttribute("aria-valuenow", confidence.toFixed(2));

    const fill = make("span", "ctm-confidence-fill");
    fill.style.width = (confidence * 100).toFixed(0) + "%";
    if (confidence < 0.6) {
      fill.classList.add("is-low");
    } else if (confidence < 0.8) {
      fill.classList.add("is-mid");
    }
    track.append(fill);
    box.append(track);
    return box;
  }

  function addFact(list, label, value) {
    if (value === undefined || value === null) return;
    const text = String(value).trim();
    if (!text) return;
    const row = make("div", "ctm-fact");
    row.append(make("dt", "", label));
    row.append(make("dd", "", text));
    list.append(row);
  }

  function renderMethod(method) {
    const card = make("section", "ctm-fact-card");
    card.append(make("h4", "ctm-fact-title", "研究方法"));
    const list = make("dl", "ctm-facts");
    addFact(list, "设计", method.design);
    addFact(list, "样本量", method.sample_size !== null && method.sample_size !== undefined ? String(method.sample_size) : "");
    addFact(list, "研究总体", method.population);
    addFact(list, "场景", method.setting);
    addFact(list, "工具 / 数据", Array.isArray(method.instruments) ? method.instruments.join("、") : "");
    addFact(list, "分析", method.analysis);
    addFact(list, "偏倚风险", RISK_LABELS[method.risk_of_bias] || method.risk_of_bias);
    if (list.childElementCount) {
      card.append(list);
    } else {
      card.append(make("p", "ctm-muted", "摘要未给出可抽取的方法信息。"));
    }
    return card;
  }

  function renderSample(sample) {
    const card = make("section", "ctm-fact-card");
    card.append(make("h4", "ctm-fact-title", "研究样本"));
    const list = make("dl", "ctm-facts");
    const size = sample.size !== null && sample.size !== undefined
      ? String(sample.size) + (sample.unit ? " " + sample.unit : "")
      : "";
    addFact(list, "样本量", size);
    addFact(list, "对象 / 人群", sample.population);
    addFact(list, "场景", sample.setting);
    addFact(list, "国家 / 地区", sample.country);
    addFact(list, "招募方式", sample.recruitment);
    if (list.childElementCount) {
      card.append(list);
    } else {
      card.append(make("p", "ctm-muted", "摘要未给出可抽取的样本信息。"));
    }
    return card;
  }

  function renderGaps(relatedClaimIds) {
    const gaps = state.payload && Array.isArray(state.payload.gaps) ? state.payload.gaps : [];
    const section = make("section", "ctm-gaps-section");
    section.append(make("h3", "", "证据缺口（gap）"));

    if (!gaps.length) {
      section.append(make("p", "ctm-muted", "当前主题尚未登记证据缺口。"));
      return section;
    }

    const list = make("div", "ctm-gap-list");
    gaps.forEach(function (gap) {
      const severity = normalizeSeverity(gap.severity);
      const card = make("article", "ctm-gap ctm-gap--" + severity);
      const top = make("div", "ctm-gap-top");
      top.append(makeTag(GAP_KIND_LABELS[gap.kind] || gap.kind || "缺口", "ctm-gap-kind"));
      top.append(makeTag("严重度：" + (SEVERITY_LABELS[severity] || severity), "ctm-gap-sev ctm-gap-sev--" + severity));

      const related = Array.isArray(gap.related_claim_ids) ? gap.related_claim_ids : [];
      const isRelated = related.some(function (claimId) {
        return relatedClaimIds.indexOf(claimId) !== -1;
      });
      if (isRelated) {
        card.classList.add("is-related");
        top.append(makeTag("与当前论文相关", "ctm-gap-related"));
      }
      card.append(top);
      if (gap.description) card.append(make("p", "ctm-gap-desc", gap.description));
      if (gap.rationale) card.append(make("p", "ctm-gap-rationale", "依据：" + gap.rationale));
      if (related.length) card.append(make("p", "ctm-gap-refs", "关联断言：" + related.join("、")));
      list.append(card);
    });
    section.append(list);
    return section;
  }

  function onPaperClick(event) {
    const target = event.target;
    if (!target || typeof target.closest !== "function") return;
    const button = target.closest(".ctm-paper-select");
    if (!button || !els.paperList.contains(button)) return;
    const item = button.closest(".ctm-paper-item");
    if (!item) return;
    selectPaper(item.dataset.paperId, true);
  }

  function onPopState() {
    if (!state.topics.length) return;
    const topicId = readTopicFromUrl() || state.topics[0].topic_id;
    if (!topicId || topicId === state.topicId) return;
    const known = state.topics.some(function (topic) { return topic.topic_id === topicId; });
    if (!known) return;
    selectTopic(topicId, { syncUrl: false });
  }

  function onVerifyToggle() {
    state.verifyMode = !state.verifyMode;
    if (els.verifyToggle) {
      els.verifyToggle.setAttribute("aria-pressed", state.verifyMode ? "true" : "false");
      els.verifyToggle.classList.toggle("is-active", state.verifyMode);
    }
    const papers = state.payload && Array.isArray(state.payload.papers) ? state.payload.papers : [];
    renderPaperList(papers);
    const first = state.verifyMode
      ? papers.find(function (paper) { return cellsForPaper(paper.paper_id).length > 0; })
      : papers.find(function (paper) { return paper.paper_id === state.selectedPaperId; });
    selectPaper((first && first.paper_id) || (papers[0] && papers[0].paper_id) || "", false);
  }

  if (els.retry) els.retry.addEventListener("click", init);
  els.paperList.addEventListener("click", onPaperClick);
  if (els.verifyToggle) els.verifyToggle.addEventListener("click", onVerifyToggle);
  if (els.detailBody) {
    els.detailBody.addEventListener("click", function (event) {
      const target = event.target;
      if (!target || typeof target.closest !== "function") return;
      const button = target.closest("[data-verify]");
      if (!button) return;
      verifyCell(button);
    });
  }
  window.addEventListener("popstate", onPopState);
  init();
})();
