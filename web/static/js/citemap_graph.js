(function () {
  "use strict";

  const app = document.getElementById("citemap-app");
  const panel = document.getElementById("ctm-graph-panel");
  const toggle = document.getElementById("ctm-graph-toggle");
  if (!app || !panel || !toggle) return;

  const NS = "http://www.w3.org/2000/svg";
  const svg = document.getElementById("ctm-graph-svg");
  const scroll = panel.querySelector(".ctm-graph-scroll");
  const summary = document.getElementById("ctm-graph-summary");
  const status = document.getElementById("ctm-graph-status");
  const detail = document.getElementById("ctm-graph-detail");
  const detailBody = document.getElementById("ctm-graph-detail-body");
  const detailClose = document.getElementById("ctm-graph-detail-close");

  const state = {
    open: false,
    topicId: "",
    payload: null,
    loading: false,
    graph: null
  };

  const LEVEL_LABEL = Object.freeze({
    fulltext: "全文逐字证据",
    abstract: "摘要级证据",
    none: "抽样未发现证据"
  });
  const STANCE_LABEL = Object.freeze({
    support: "支持",
    contradict: "反驳",
    neutral: "中立",
    partial: "部分支持",
    no_evidence: "无证据"
  });

  function topicFromUrl() {
    try {
      return new URLSearchParams(window.location.search).get("topic") || "";
    } catch (err) {
      return "";
    }
  }

  function currentTopic() {
    return state.topicId || topicFromUrl() || app.dataset.topic || "";
  }

  function makeSvg(tag, attrs, text) {
    const node = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (key) {
      node.setAttribute(key, attrs[key]);
    });
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function truncate(text, size) {
    const value = String(text || "").replace(/\s+/g, " ").trim();
    if (value.length <= size) return value;
    return value.slice(0, size - 1) + "…";
  }

  function setStatus(message, tone) {
    if (!status) return;
    status.textContent = message || "";
    if (tone) status.dataset.tone = tone;
    else delete status.dataset.tone;
  }

  function safeTopicId() {
    const id = currentTopic();
    return /^[a-zA-Z0-9_-]{1,80}$/.test(id) ? id : "";
  }

  async function fetchTopic() {
    const topicId = safeTopicId();
    if (!topicId) throw new Error("还没有选择主题。");
    const response = await fetch("/api/citemap/" + encodeURIComponent(topicId), {
      headers: { Accept: "application/json" },
      credentials: "same-origin"
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      data = null;
    }
    if (!response.ok) {
      const message = data && (data.error || data.detail);
      throw new Error(typeof message === "string" ? message : "图数据加载失败（HTTP " + response.status + "）。");
    }
    if (!data) throw new Error("图数据为空或无法解析。");
    return data;
  }

  function buildGraph(payload) {
    const claims = (Array.isArray(payload.claims) ? payload.claims : []).filter(function (claim) {
      return claim && claim.claim_id;
    });
    const papers = (Array.isArray(payload.papers) ? payload.papers : []).filter(function (paper) {
      return paper && paper.paper_id;
    });
    const claimIndex = new Map();
    const paperIndex = new Map();
    claims.forEach(function (claim, index) {
      claimIndex.set(claim.claim_id, index);
    });
    papers.forEach(function (paper, index) {
      paperIndex.set(paper.paper_id, index);
    });

    const edges = [];
    const byPair = new Map();

    function pairKey(claimId, paperId) {
      return String(claimId) + "::" + String(paperId);
    }

    function stronger(left, right) {
      const rank = { none: 0, abstract: 1, fulltext: 2 };
      return rank[right] > rank[left] ? right : left;
    }

    function addEdge(claimId, paperId, level, evidence, cell) {
      if (!claimIndex.has(claimId) || !paperIndex.has(paperId)) return;
      const key = pairKey(claimId, paperId);
      const existing = byPair.get(key);
      if (existing) {
        existing.level = stronger(existing.level, level);
        if (evidence) existing.evidence.push(evidence);
        if (cell) existing.cells.push(cell);
        return;
      }
      const edge = {
        claimId: claimId,
        paperId: paperId,
        level: level,
        evidence: evidence ? [evidence] : [],
        cells: cell ? [cell] : []
      };
      byPair.set(key, edge);
      edges.push(edge);
    }

    (Array.isArray(payload.evidence) ? payload.evidence : []).forEach(function (ev) {
      if (!ev || !ev.claim_id || !ev.paper_id) return;
      const level = ev.fulltext ? "fulltext" : "abstract";
      addEdge(ev.claim_id, ev.paper_id, level, ev, null);
    });

    // Machine evidence lives in a separate list (human examples are in
    // payload.evidence). Both belong on the map; collapsing by pair keeps the
    // strongest level instead of drawing two lines for the same relationship.
    (Array.isArray(payload.auto_evidence) ? payload.auto_evidence : []).forEach(function (ev) {
      if (!ev || !ev.claim_id || !ev.paper_id) return;
      const level = ev.fulltext ? "fulltext" : "abstract";
      addEdge(ev.claim_id, ev.paper_id, level, ev, null);
    });

    // Only sampled "no evidence" cells are drawn; showing every possible pair
    // would turn the map into a hairball and imply more than we checked.
    (Array.isArray(payload.verification_cells) ? payload.verification_cells : []).forEach(function (cell) {
      if (!cell || !cell.claim_id || !cell.paper_id) return;
      if (cell.evidence_id) return;
      addEdge(cell.claim_id, cell.paper_id, "none", null, cell);
    });

    const claimIds = new Set(edges.map(function (edge) { return edge.claimId; }));
    const paperIds = new Set(edges.map(function (edge) { return edge.paperId; }));
    const visibleClaims = claims.filter(function (claim) { return claimIds.has(claim.claim_id); });
    const visiblePapers = papers.filter(function (paper) { return paperIds.has(paper.paper_id); });

    return {
      claims: visibleClaims,
      papers: visiblePapers,
      allClaims: claims,
      allPapers: papers,
      edges: edges,
      byPair: byPair,
      counts: countLevels(edges)
    };
  }

  function countLevels(edges) {
    const counts = { fulltext: 0, abstract: 0, none: 0 };
    edges.forEach(function (edge) {
      if (Object.prototype.hasOwnProperty.call(counts, edge.level)) counts[edge.level] += 1;
    });
    return counts;
  }

  function render() {
    if (!state.payload) return;
    const graph = buildGraph(state.payload);
    state.graph = graph;
    svg.replaceChildren();

    if (!graph.claims.length || !graph.papers.length) {
      summary.textContent = "这个主题还没有可画成图的断言与论文。";
      setStatus("没有画出关系：主题数据里没有同时带 claim 和 paper 的证据。", "warn");
      return;
    }

    const rowHeight = 42;
    const top = 74;
    const width = 1240;
    const height = Math.max(560, top + Math.max(graph.claims.length, graph.papers.length) * rowHeight + 36);
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    svg.setAttribute("width", String(width));
    svg.setAttribute("height", String(height));

    const claimsX = 24;
    const claimWidth = 332;
    const edgeStart = claimsX + claimWidth;
    const papersX = 814;
    const paperLabelX = papersX + 18;
    const claimY = new Map();
    const paperY = new Map();

    graph.claims.forEach(function (claim, index) {
      claimY.set(claim.claim_id, top + index * rowHeight);
    });
    graph.papers.forEach(function (paper, index) {
      paperY.set(paper.paper_id, top + index * rowHeight);
    });

    svg.append(makeSvg("text", { x: claimsX, y: 36, class: "ctm-graph-col" }, "断言"));
    svg.append(makeSvg("text", { x: papersX, y: 36, class: "ctm-graph-col" }, "论文"));
    svg.append(makeSvg("line", {
      x1: claimsX, y1: 52, x2: width - 24, y2: 52, class: "ctm-graph-rule"
    }));

    const edgeLayer = makeSvg("g", { class: "ctm-graph-edges" });
    const nodeLayer = makeSvg("g", { class: "ctm-graph-nodes" });
    svg.append(edgeLayer, nodeLayer);

    graph.edges.forEach(function (edge) {
      const y1 = claimY.get(edge.claimId) + 16;
      const y2 = paperY.get(edge.paperId) + 16;
      if (y1 === undefined || y2 === undefined) return;
      const mid = (edgeStart + papersX) / 2;
      const path = makeSvg("path", {
        d: "M " + edgeStart + " " + y1 + " C " + mid + " " + y1 + ", " + mid + " " + y2 + ", " + papersX + " " + y2,
        class: "ctm-edge ctm-edge--" + edge.level,
        "data-claim-id": edge.claimId,
        "data-paper-id": edge.paperId
      });
      const claim = graph.allClaims.find(function (item) { return item.claim_id === edge.claimId; });
      const paper = graph.allPapers.find(function (item) { return item.paper_id === edge.paperId; });
      const title = makeSvg("title", {}, LEVEL_LABEL[edge.level] + " · " +
        (claim && claim.text ? truncate(claim.text, 34) : edge.claimId) + " · " +
        (paper && paper.title ? truncate(paper.title, 34) : edge.paperId));
      path.append(title);
      path.addEventListener("click", function () {
        selectEdge(edge);
      });
      edgeLayer.append(path);
    });

    graph.claims.forEach(function (claim) {
      const y = claimY.get(claim.claim_id);
      const group = makeSvg("g", {
        class: "ctm-node ctm-node--claim",
        tabindex: "0",
        role: "button",
        "data-claim-id": claim.claim_id,
        "aria-label": "断言：" + (claim.text || claim.claim_id)
      });
      group.append(makeSvg("rect", {
        x: claimsX, y: y, width: claimWidth, height: 32, rx: 8, class: "ctm-node-box"
      }));
      const text = makeSvg("text", { x: claimsX + 12, y: y + 21, class: "ctm-node-text" },
        truncate(claim.text || claim.claim_id, 30));
      const title = makeSvg("title", {}, claim.text || claim.claim_id);
      text.append(title);
      group.append(text);
      bindNode(group, function () { selectClaim(claim); });
      nodeLayer.append(group);
    });

    graph.papers.forEach(function (paper) {
      const y = paperY.get(paper.paper_id);
      const group = makeSvg("g", {
        class: "ctm-node ctm-node--paper",
        tabindex: "0",
        role: "button",
        "data-paper-id": paper.paper_id,
        "aria-label": "论文：" + (paper.title || paper.paper_id)
      });
      group.append(makeSvg("circle", {
        cx: papersX, cy: y + 16, r: 7, class: "ctm-node-dot"
      }));
      const text = makeSvg("text", { x: paperLabelX, y: y + 12, class: "ctm-node-text" },
        truncate(paper.title || paper.paper_id, 34));
      const meta = makeSvg("text", { x: paperLabelX, y: y + 28, class: "ctm-node-meta" },
        [paper.year, paper.venue].filter(Boolean).join(" · "));
      const title = makeSvg("title", {}, paper.title || paper.paper_id);
      text.append(title);
      group.append(text, meta);
      bindNode(group, function () { selectPaper(paper); });
      nodeLayer.append(group);
    });

    const counts = graph.counts;
    summary.textContent = graph.claims.length + " 条断言 · " + graph.papers.length + " 篇论文 · 全文 " +
      counts.fulltext + " 条 · 摘要 " + counts.abstract + " 条 · 抽样未发现 " + counts.none + " 条";
    setStatus("已画出 " + graph.edges.length + " 条关系；点击节点或连线看证据原文。", "ok");
    closeDetail();
  }

  function bindNode(group, handler) {
    group.addEventListener("click", handler);
    group.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handler();
      }
    });
  }

  function openDetail() {
    if (!detail) return;
    detail.hidden = false;
    if (scroll) scroll.classList.add("has-detail");
  }

  function closeDetail() {
    if (!detailBody) return;
    detail.hidden = true;
    detailBody.replaceChildren();
    if (scroll) scroll.classList.remove("has-detail");
    svg.querySelectorAll(".ctm-node.is-active").forEach(function (node) {
      node.classList.remove("is-active");
    });
  }

  function selectClaim(claim) {
    if (!detailBody) return;
    detailBody.replaceChildren();
    detailBody.append(make("p", "ctm-graph-detail-kicker", "断言 · " + claim.claim_id));
    detailBody.append(make("h3", "ctm-graph-detail-title", claim.text || "（无断言文本）"));
    const edges = state.graph.edges.filter(function (edge) { return edge.claimId === claim.claim_id; });
    detailBody.append(renderEdgeList(edges, "paper"));
    markNode("[data-claim-id]", claim.claim_id);
    openDetail();
  }

  function selectPaper(paper) {
    if (!detailBody) return;
    detailBody.replaceChildren();
    detailBody.append(make("p", "ctm-graph-detail-kicker", "论文"));
    detailBody.append(make("h3", "ctm-graph-detail-title", paper.title || paper.paper_id));
    const meta = [paper.year, paper.venue].filter(Boolean).join(" · ");
    if (meta) detailBody.append(make("p", "ctm-graph-detail-meta", meta));
    if (paper.doi) {
      const link = make("a", "ctm-graph-doi", "DOI " + paper.doi);
      link.href = "https://doi.org/" + String(paper.doi).replace(/^https?:\/\/doi\.org\//i, "");
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      detailBody.append(link);
    }
    const edges = state.graph.edges.filter(function (edge) { return edge.paperId === paper.paper_id; });
    detailBody.append(renderEdgeList(edges, "claim"));
    markNode("[data-paper-id]", paper.paper_id);
    openDetail();
  }

  function selectEdge(edge) {
    if (!detailBody) return;
    detailBody.replaceChildren();
    const claim = state.graph.allClaims.find(function (item) { return item.claim_id === edge.claimId; });
    const paper = state.graph.allPapers.find(function (item) { return item.paper_id === edge.paperId; });
    detailBody.append(make("p", "ctm-graph-detail-kicker", LEVEL_LABEL[edge.level]));
    detailBody.append(make("h3", "ctm-graph-detail-title", "断言 ↔ 论文"));
    const pair = make("div", "ctm-graph-pair");
    pair.append(make("span", "ctm-graph-pair-label", "断言"));
    pair.append(make("p", "", claim ? claim.text : edge.claimId));
    pair.append(make("span", "ctm-graph-pair-label", "论文"));
    pair.append(make("p", "", paper ? paper.title : edge.paperId));
    detailBody.append(pair);
    if (edge.level === "none") {
      detailBody.append(make("p", "ctm-graph-detail-note",
        "这次抽样没有发现逐字证据；没有发现不等于不存在，只表示当前摘要/全文里没找到。"));
    } else {
      edge.evidence.slice(0, 5).forEach(function (ev) {
        detailBody.append(renderEvidenceMini(ev));
      });
      if (edge.evidence.length > 5) {
        detailBody.append(make("p", "ctm-graph-detail-note", "还有 " + (edge.evidence.length - 5) + " 条证据未展开。"));
      }
    }
    markNode("[data-claim-id]", edge.claimId);
    markNode("[data-paper-id]", edge.paperId);
    openDetail();
  }

  function markNode(selector, id) {
    svg.querySelectorAll(".ctm-node.is-active").forEach(function (node) {
      node.classList.remove("is-active");
    });
    svg.querySelectorAll(selector).forEach(function (node) {
      if (node.getAttribute(selector.replace(/[\[\]]/g, "").split("=")[0]) === id) {
        node.classList.add("is-active");
      }
    });
  }

  function renderEdgeList(edges, otherSide) {
    const list = make("div", "ctm-graph-edges-list");
    if (!edges.length) {
      list.append(make("p", "ctm-graph-detail-note", "没有可展示的证据关系。"));
      return list;
    }
    const order = { fulltext: 0, abstract: 1, none: 2 };
    edges.slice().sort(function (a, b) { return order[a.level] - order[b.level]; }).forEach(function (edge) {
      const item = make("button", "ctm-graph-edge-item ctm-graph-edge-item--" + edge.level);
      item.type = "button";
      const id = otherSide === "paper" ? edge.paperId : edge.claimId;
      const source = otherSide === "paper"
        ? state.graph.allPapers.find(function (paper) { return paper.paper_id === id; })
        : state.graph.allClaims.find(function (claim) { return claim.claim_id === id; });
      item.append(make("span", "ctm-graph-edge-level", LEVEL_LABEL[edge.level]));
      item.append(make("span", "ctm-graph-edge-name",
        otherSide === "paper" ? (source && source.title) || id : (source && source.text) || id));
      if (edge.evidence.length) {
        const stance = edge.evidence[0] && edge.evidence[0].stance;
        if (stance) item.append(make("span", "ctm-graph-stance", STANCE_LABEL[stance] || stance));
      }
      item.addEventListener("click", function () {
        selectEdge(edge);
      });
      list.append(item);
    });
    return list;
  }

  function renderEvidenceMini(ev) {
    const box = make("div", "ctm-graph-evidence");
    const head = make("div", "ctm-graph-evidence-head");
    if (ev.stance) head.append(make("span", "ctm-graph-stance", STANCE_LABEL[ev.stance] || ev.stance));
    head.append(make("span", "ctm-graph-edge-level", ev.fulltext ? "全文" : "摘要"));
    if (ev.evidence_id) head.append(make("span", "ctm-graph-evidence-id", ev.evidence_id));
    box.append(head);
    if (ev.quote) box.append(make("blockquote", "ctm-graph-quote", ev.quote));
    if (ev.locator) box.append(make("p", "ctm-graph-detail-meta", "定位：" + ev.locator));
    if (ev.summary) box.append(make("p", "ctm-graph-detail-note", ev.summary));
    return box;
  }

  function make(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function setOpen(open) {
    state.open = open;
    toggle.setAttribute("aria-pressed", open ? "true" : "false");
    toggle.classList.toggle("is-active", open);
    panel.hidden = !open;
    const layout = document.getElementById("ctm-layout");
    if (open) {
      if (layout) layout.hidden = true;
      ensureGraph();
      panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } else {
      closeDetail();
      if (layout && state.payload) layout.hidden = false;
    }
  }

  async function ensureGraph() {
    if (state.loading) return;
    if (state.payload) {
      render();
      return;
    }
    state.loading = true;
    summary.textContent = "正在读取主题数据…";
    setStatus("正在加载图数据…");
    try {
      const payload = await fetchTopic();
      state.topicId = payload.topic && payload.topic.topic_id ? payload.topic.topic_id : currentTopic();
      state.payload = payload;
      render();
    } catch (err) {
      summary.textContent = "图数据加载失败。";
      setStatus(err && err.message ? err.message : "图数据加载失败。", "bad");
    } finally {
      state.loading = false;
    }
  }

  toggle.addEventListener("click", function () {
    setOpen(!state.open);
  });

  if (detailClose) detailClose.addEventListener("click", closeDetail);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && state.open) {
      if (detail && !detail.hidden) closeDetail();
      else setOpen(false);
    }
  });

  document.addEventListener("ctm:topic", function (event) {
    const detailData = event.detail || {};
    state.topicId = detailData.topicId || currentTopic();
    state.payload = detailData.payload || null;
    if (state.open) {
      if (state.payload) {
        const layout = document.getElementById("ctm-layout");
        if (layout) layout.hidden = true;
        render();
      } else {
        ensureGraph();
      }
    }
  });

  // The page may already have loaded before this script runs; keep the topic
  // id in sync without issuing a second API request.
  state.topicId = app.dataset.topic || topicFromUrl();
})();
