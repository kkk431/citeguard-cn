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

  const GRAPH_WIDTH = 1240;
  const ROW_HEIGHT = 42;
  const TOP = 74;
  const ZOOM_MIN = 0.55;
  const ZOOM_MAX = 2.5;
  const ZOOM_STEP = 0.22;
  const LEVELS = ["fulltext", "abstract", "none"];

  const state = {
    open: false,
    topicId: "",
    payload: null,
    loading: false,
    graph: null,
    viewport: null,
    adjacency: null,
    renderMs: 0,
    view: { scale: 1, x: 0, y: 0 },
    filters: { fulltext: true, abstract: true, none: true },
    pan: null,
    toolsReady: false,
    legendReady: false
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
      throw new Error(typeof message === "string" ? message : window.humanHttpError(response.status, null, "图数据加载失败，请稍后重试。"));
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
    const claimById = new Map();
    const paperById = new Map();
    claims.forEach(function (claim, index) {
      claimIndex.set(claim.claim_id, index);
      claimById.set(claim.claim_id, claim);
    });
    papers.forEach(function (paper, index) {
      paperIndex.set(paper.paper_id, index);
      paperById.set(paper.paper_id, paper);
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
      claimById: claimById,
      paperById: paperById,
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

  function layout(graph) {
    const top = TOP;
    const rowHeight = ROW_HEIGHT;
    const width = GRAPH_WIDTH;
    const height = Math.max(560, top + Math.max(graph.claims.length, graph.papers.length) * rowHeight + 36);
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
    return { top, width, height, claimsX, claimWidth, edgeStart, papersX, paperLabelX, claimY, paperY };
  }

  // Draws a graph into any SVG element. The main render passes the visible
  // SVG; the 105-node benchmark passes an offscreen SVG so it never fakes
  // page data. Returns the adjacency index used by hover/filter interactions.
  function paint(target, graph, options) {
    const opts = options || {};
    const box = layout(graph);
    target.replaceChildren();
    target.setAttribute("viewBox", "0 0 " + box.width + " " + box.height);
    target.setAttribute("width", String(box.width));
    target.setAttribute("height", String(box.height));

    const boundary = makeSvg("g", { class: "ctm-graph-frame" });
    const viewport = makeSvg("g", { class: "ctm-graph-viewport" });
    boundary.append(
      makeSvg("text", { x: box.claimsX, y: 36, class: "ctm-graph-col" }, "断言"),
      makeSvg("text", { x: box.papersX, y: 36, class: "ctm-graph-col" }, "论文"),
      makeSvg("line", { x1: box.claimsX, y1: 52, x2: box.width - 24, y2: 52, class: "ctm-graph-rule" })
    );

    const edgeLayer = makeSvg("g", { class: "ctm-graph-edges" });
    const nodeLayer = makeSvg("g", { class: "ctm-graph-nodes" });
    const edgeFragment = document.createDocumentFragment();
    const nodeFragment = document.createDocumentFragment();

    const adjacency = {
      claims: new Map(),
      papers: new Map(),
      edges: new Map()
    };

    graph.edges.forEach(function (edge) {
      const y1 = box.claimY.get(edge.claimId) + 16;
      const y2 = box.paperY.get(edge.paperId) + 16;
      if (y1 === undefined || y2 === undefined) return;
      const mid = (box.edgeStart + box.papersX) / 2;
      const path = makeSvg("path", {
        d: "M " + box.edgeStart + " " + y1 + " C " + mid + " " + y1 + ", " + mid + " " + y2 + ", " + box.papersX + " " + y2,
        class: "ctm-edge ctm-edge--" + edge.level + (state.filters[edge.level] === false ? " is-filtered" : ""),
        "data-claim-id": edge.claimId,
        "data-paper-id": edge.paperId,
        "data-level": edge.level
      });
      const claim = graph.claimById.get(edge.claimId);
      const paper = graph.paperById.get(edge.paperId);
      const title = makeSvg("title", {}, LEVEL_LABEL[edge.level] + " · " +
        (claim && claim.text ? truncate(claim.text, 34) : edge.claimId) + " · " +
        (paper && paper.title ? truncate(paper.title, 34) : edge.paperId));
      path.append(title);
      if (opts.interactive !== false) {
        path.addEventListener("click", function () { selectEdge(edge); });
      }
      path.__cg = { claimId: edge.claimId, paperId: edge.paperId, level: edge.level };
      edgeFragment.append(path);
      adjacency.edges.set(edge.claimId + "::" + edge.paperId, path);
      if (!adjacency.claims.has(edge.claimId)) adjacency.claims.set(edge.claimId, []);
      if (!adjacency.papers.has(edge.paperId)) adjacency.papers.set(edge.paperId, []);
      adjacency.claims.get(edge.claimId).push(path);
      adjacency.papers.get(edge.paperId).push(path);
    });

    graph.claims.forEach(function (claim) {
      const y = box.claimY.get(claim.claim_id);
      const group = makeSvg("g", {
        class: "ctm-node ctm-node--claim",
        tabindex: opts.interactive === false ? "-1" : "0",
        role: "button",
        "data-claim-id": claim.claim_id,
        "data-node-kind": "claim",
        "data-node-id": claim.claim_id,
        "aria-label": "断言：" + (claim.text || claim.claim_id)
      });
      group.append(makeSvg("rect", {
        x: box.claimsX, y: y, width: box.claimWidth, height: 32, rx: 8, class: "ctm-node-box"
      }));
      const text = makeSvg("text", { x: box.claimsX + 12, y: y + 21, class: "ctm-node-text" },
        truncate(claim.text || claim.claim_id, 30));
      const title = makeSvg("title", {}, claim.text || claim.claim_id);
      text.append(title);
      group.append(text);
      if (opts.interactive !== false) bindNode(group, function () { selectClaim(claim); });
      nodeFragment.append(group);
    });

    graph.papers.forEach(function (paper) {
      const y = box.paperY.get(paper.paper_id);
      const group = makeSvg("g", {
        class: "ctm-node ctm-node--paper",
        tabindex: opts.interactive === false ? "-1" : "0",
        role: "button",
        "data-paper-id": paper.paper_id,
        "data-node-kind": "paper",
        "data-node-id": paper.paper_id,
        "aria-label": "论文：" + (paper.title || paper.paper_id)
      });
      group.append(makeSvg("circle", {
        cx: box.papersX, cy: y + 16, r: 7, class: "ctm-node-dot"
      }));
      const text = makeSvg("text", { x: box.paperLabelX, y: y + 12, class: "ctm-node-text" },
        truncate(paper.title || paper.paper_id, 34));
      const meta = makeSvg("text", { x: box.paperLabelX, y: y + 28, class: "ctm-node-meta" },
        [paper.year, paper.venue].filter(Boolean).join(" · "));
      const title = makeSvg("title", {}, paper.title || paper.paper_id);
      text.append(title);
      group.append(text, meta);
      if (opts.interactive !== false) bindNode(group, function () { selectPaper(paper); });
      nodeFragment.append(group);
    });

    edgeLayer.append(edgeFragment);
    nodeLayer.append(nodeFragment);
    viewport.append(boundary, edgeLayer, nodeLayer);
    target.append(viewport);
    return { viewport: viewport, edgeLayer: edgeLayer, nodeLayer: nodeLayer, adjacency: adjacency, box: box };
  }

  function render() {
    if (!state.payload) return;
    const graph = buildGraph(state.payload);
    state.graph = graph;
    if (!graph.claims.length || !graph.papers.length) {
      svg.replaceChildren();
      summary.textContent = "这个主题还没有可画成图的断言与论文。";
      setStatus("没有画出关系：主题数据里没有同时带 claim 和 paper 的证据。", "warn");
      return;
    }
    const started = (window.performance && performance.now) ? performance.now() : Date.now();
    const painted = paint(svg, graph, { interactive: true });
    const ended = (window.performance && performance.now) ? performance.now() : Date.now();
    state.viewport = painted.viewport;
    state.adjacency = painted.adjacency;
    state.renderMs = Math.max(0, ended - started);
    panel.dataset.renderMs = state.renderMs.toFixed(2);
    svg.dataset.renderMs = state.renderMs.toFixed(2);
    ensureTools();
    wireLegend();
    applyView();
    applyFilters();
    clearHover();
    const counts = graph.counts;
    summary.textContent = graph.claims.length + " 条断言 · " + graph.papers.length + " 篇论文 · 全文 " +
      counts.fulltext + " 条 · 摘要 " + counts.abstract + " 条 · 抽样未发现 " + counts.none + " 条";
    setStatus("已画出 " + graph.edges.length + " 条关系，用时 " + state.renderMs.toFixed(1) + " ms；点击节点或连线看证据原文。", "ok");
    closeDetail();
  }

  function ensureTools() {
    if (state.toolsReady) return;
    const head = panel.querySelector(".ctm-graph-head");
    if (!head) return;
    const tools = document.createElement("div");
    tools.className = "ctm-graph-tools";
    tools.id = "ctm-graph-tools";
    tools.setAttribute("role", "group");
    tools.setAttribute("aria-label", "图缩放与重置");

    const out = document.createElement("button");
    out.type = "button";
    out.className = "ctm-graph-tool";
    out.textContent = "−";
    out.title = "缩小";
    out.setAttribute("aria-label", "缩小证据图");
    out.addEventListener("click", function () { zoomBy(1 / (1 + ZOOM_STEP)); });

    const value = document.createElement("span");
    value.className = "ctm-graph-zoom";
    value.id = "ctm-graph-zoom";
    value.textContent = "100%";
    value.setAttribute("aria-live", "polite");
    value.title = "当前缩放；双击画布或点右侧按钮恢复 100%";

    const into = document.createElement("button");
    into.type = "button";
    into.className = "ctm-graph-tool";
    into.textContent = "+";
    into.title = "放大";
    into.setAttribute("aria-label", "放大证据图");
    into.addEventListener("click", function () { zoomBy(1 + ZOOM_STEP); });

    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "ctm-graph-tool ctm-graph-tool--wide";
    reset.textContent = "重置";
    reset.title = "恢复 100% 并回到左上角（也可双击画布）";
    reset.setAttribute("aria-label", "重置证据图缩放与平移");
    reset.addEventListener("click", resetView);

    tools.append(out, value, into, reset);
    head.appendChild(tools);

    const hint = document.createElement("p");
    hint.className = "ctm-graph-hint";
    hint.id = "ctm-graph-hint";
    hint.textContent = "Ctrl / ⌘ + 滚轮缩放 · 拖拽画布平移 · 双击重置 · 点击图例可隐藏或显示某类连线";
    head.appendChild(hint);

    svg.addEventListener("wheel", onWheel, { passive: false });
    svg.addEventListener("dblclick", onDoubleClick);
    svg.addEventListener("pointerdown", onPointerDown);
    svg.addEventListener("pointermove", onPointerMove);
    svg.addEventListener("pointerup", onPointerUp);
    svg.addEventListener("pointercancel", onPointerUp);
    svg.addEventListener("pointerover", onPointerOver);
    svg.addEventListener("pointerleave", clearHover);
    state.toolsReady = true;
  }

  function wireLegend() {
    if (state.legendReady) return;
    const keys = panel.querySelectorAll(".ctm-graph-key");
    keys.forEach(function (key) {
      const level = LEVELS.find(function (name) { return key.classList.contains("ctm-graph-key--" + name); });
      if (!level) return;
      key.setAttribute("role", "button");
      key.setAttribute("tabindex", "0");
      key.setAttribute("aria-pressed", state.filters[level] ? "true" : "false");
      key.title = "点击显示或隐藏" + LEVEL_LABEL[level];
      const activate = function () { toggleFilter(level); };
      key.addEventListener("click", activate);
      key.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activate();
        }
      });
    });
    state.legendReady = true;
  }

  function toggleFilter(level) {
    state.filters[level] = !state.filters[level];
    applyFilters();
    const visible = LEVELS.filter(function (name) { return state.filters[name]; }).length;
    if (!visible) setStatus("三类连线都已隐藏；点击任一图例恢复显示。", "warn");
    else if (!state.filters[level]) setStatus("已隐藏「" + LEVEL_LABEL[level] + "」连线，其余关系保持原样。", "ok");
    else setStatus("已显示「" + LEVEL_LABEL[level] + "」连线。", "ok");
  }

  function applyFilters() {
    if (!svg) return;
    svg.querySelectorAll(".ctm-edge[data-level]").forEach(function (path) {
      const level = path.getAttribute("data-level");
      path.classList.toggle("is-filtered", state.filters[level] === false);
    });
    const keys = panel.querySelectorAll(".ctm-graph-key");
    keys.forEach(function (key) {
      const level = LEVELS.find(function (name) { return key.classList.contains("ctm-graph-key--" + name); });
      if (!level) return;
      key.setAttribute("aria-pressed", state.filters[level] ? "true" : "false");
      key.classList.toggle("is-off", state.filters[level] === false);
    });
    panel.dataset.visibleLevels = LEVELS.filter(function (name) { return state.filters[name]; }).join(",");
  }

  function applyView() {
    if (!state.viewport) return;
    state.viewport.setAttribute(
      "transform",
      "translate(" + state.view.x.toFixed(2) + " " + state.view.y.toFixed(2) + ") scale(" + state.view.scale.toFixed(3) + ")"
    );
    const label = document.getElementById("ctm-graph-zoom");
    if (label) label.textContent = Math.round(state.view.scale * 100) + "%";
    panel.dataset.zoom = String(Math.round(state.view.scale * 100));
    svg.classList.toggle("is-zoomed", Math.abs(state.view.scale - 1) > 0.01 || Math.abs(state.view.x) > 1 || Math.abs(state.view.y) > 1);
  }

  function resetView() {
    state.view = { scale: 1, x: 0, y: 0 };
    applyView();
    setStatus("已恢复 100% 缩放与原始位置。", "ok");
  }

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function clientToSvg(clientX, clientY) {
    const rect = svg.getBoundingClientRect();
    const width = rect.width || GRAPH_WIDTH;
    const height = rect.height || 560;
    const view = svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width ? svg.viewBox.baseVal : null;
    const vbWidth = view && view.width ? view.width : GRAPH_WIDTH;
    const vbHeight = view && view.height ? view.height : height;
    return {
      x: (clientX - rect.left) * (vbWidth / width),
      y: (clientY - rect.top) * (vbHeight / height)
    };
  }

  function zoomAt(factor, clientX, clientY) {
    const oldScale = state.view.scale;
    const nextScale = clamp(oldScale * factor, ZOOM_MIN, ZOOM_MAX);
    if (Math.abs(nextScale - oldScale) < 0.001) return;
    const point = clientToSvg(clientX, clientY);
    const ratio = nextScale / oldScale;
    state.view.x = point.x - (point.x - state.view.x) * ratio;
    state.view.y = point.y - (point.y - state.view.y) * ratio;
    state.view.scale = nextScale;
    applyView();
  }

  function zoomBy(factor) {
    const rect = svg.getBoundingClientRect();
    zoomAt(factor, rect.left + rect.width / 2, rect.top + rect.height / 2);
  }

  function onWheel(event) {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const factor = Math.exp(-event.deltaY * 0.0016);
    zoomAt(factor, event.clientX, event.clientY);
  }

  function onDoubleClick(event) {
    if (event.target.closest(".ctm-node, .ctm-edge")) return;
    event.preventDefault();
    resetView();
  }

  function onPointerDown(event) {
    if (event.button !== 0) return;
    if (event.target.closest(".ctm-node, .ctm-edge")) return;
    state.pan = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: state.view.x,
      originY: state.view.y,
      moved: false
    };
    svg.classList.add("is-panning");
    if (svg.setPointerCapture) svg.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event) {
    if (!state.pan || state.pan.pointerId !== event.pointerId) return;
    const dx = event.clientX - state.pan.startX;
    const dy = event.clientY - state.pan.startY;
    if (Math.abs(dx) + Math.abs(dy) > 3) state.pan.moved = true;
    if (!state.pan.moved) return;
    state.view.x = state.pan.originX + dx;
    state.view.y = state.pan.originY + dy;
    applyView();
  }

  function onPointerUp(event) {
    if (!state.pan || state.pan.pointerId !== event.pointerId) return;
    if (svg.releasePointerCapture) {
      try { svg.releasePointerCapture(event.pointerId); } catch (err) { /* already released */ }
    }
    state.pan = null;
    svg.classList.remove("is-panning");
  }

  function setHot(node, on) {
    if (!node) return;
    node.classList.toggle("is-hot", !!on);
  }

  function clearHover() {
    if (!svg) return;
    svg.classList.remove("is-hovering");
    svg.querySelectorAll(".is-hot").forEach(function (node) { node.classList.remove("is-hot"); });
  }

  function nodeFor(kind, id) {
    return svg.querySelector('.ctm-node[data-node-kind="' + kind + '"][data-node-id="' + String(id).replace(/"/g, '\\"') + '"]');
  }

  function hoverNode(node) {
    const kind = node.getAttribute("data-node-kind");
    const id = node.getAttribute("data-node-id");
    const map = kind === "claim" ? state.adjacency.claims : state.adjacency.papers;
    const edges = (map && map.get(id)) || [];
    clearHover();
    svg.classList.add("is-hovering");
    setHot(node, true);
    edges.forEach(function (path) {
      setHot(path, true);
      if (path.__cg) {
        if (kind === "claim") setHot(nodeFor("paper", path.__cg.paperId), true);
        else setHot(nodeFor("claim", path.__cg.claimId), true);
      }
    });
    const level = edges[0] && edges[0].getAttribute("data-level");
    setStatus("「" + truncate(node.getAttribute("aria-label") || id, 40) + "」连接 " + edges.length + " 条关系" +
      (level ? "（悬停仅高亮，点击打开详情）" : "。"), "ok");
  }

  function hoverEdge(path) {
    clearHover();
    svg.classList.add("is-hovering");
    setHot(path, true);
    if (path.__cg) {
      setHot(nodeFor("claim", path.__cg.claimId), true);
      setHot(nodeFor("paper", path.__cg.paperId), true);
      setStatus(LEVEL_LABEL[path.__cg.level] + "：点击连线查看断言与论文原文。", "ok");
    }
  }

  function onPointerOver(event) {
    const node = event.target.closest(".ctm-node");
    if (node) {
      if (node.classList.contains("is-hot")) return;
      hoverNode(node);
      return;
    }
    const edge = event.target.closest(".ctm-edge");
    if (edge) {
      if (edge.classList.contains("is-hot")) return;
      hoverEdge(edge);
      return;
    }
    clearHover();
  }

  function buildSyntheticGraph(count) {
    const total = Math.max(10, Math.floor(count || 105));
    const claimCount = Math.ceil(total * 0.55);
    const paperCount = total - claimCount;
    const claims = [];
    const papers = [];
    const claimById = new Map();
    const paperById = new Map();
    for (let i = 0; i < claimCount; i += 1) {
      const claim = { claim_id: "bench_claim_" + i, text: "基准断言 " + (i + 1) + "：用于测量 105 节点渲染耗时的合成文本。" };
      claims.push(claim);
      claimById.set(claim.claim_id, claim);
    }
    for (let i = 0; i < paperCount; i += 1) {
      const paper = { paper_id: "bench_paper_" + i, title: "基准论文 " + (i + 1), year: 2026, venue: "benchmark" };
      papers.push(paper);
      paperById.set(paper.paper_id, paper);
    }
    const edges = [];
    const byPair = new Map();
    claims.forEach(function (claim, index) {
      for (let step = 0; step < 2; step += 1) {
        const paper = papers[(index * 2 + step) % papers.length];
        const key = claim.claim_id + "::" + paper.paper_id;
        if (byPair.has(key)) continue;
        const level = LEVELS[(index + step) % LEVELS.length];
        const edge = { claimId: claim.claim_id, paperId: paper.paper_id, level: level, evidence: [], cells: [] };
        byPair.set(key, edge);
        edges.push(edge);
      }
    });
    return {
      claims: claims,
      papers: papers,
      allClaims: claims,
      allPapers: papers,
      claimById: claimById,
      paperById: paperById,
      edges: edges,
      byPair: byPair,
      counts: countLevels(edges)
    };
  }

  // Explicit, labelled stress measurement. It draws into an offscreen SVG and
  // never touches the visible graph or its data; callers must report it as
  // synthetic. Used once in the G3 evidence run for 105 nodes.
  function benchmark(count) {
    const graph = buildSyntheticGraph(count || 105);
    const host = makeSvg("svg", {
      viewBox: "0 0 " + GRAPH_WIDTH + " 1000",
      width: String(GRAPH_WIDTH),
      height: "1000",
      "aria-hidden": "true"
    });
    host.style.cssText = "position:absolute;left:-99999px;top:0;width:" + GRAPH_WIDTH + "px;height:1000px;visibility:hidden";
    panel.appendChild(host);
    const started = (window.performance && performance.now) ? performance.now() : Date.now();
    paint(host, graph, { interactive: false });
    const ended = (window.performance && performance.now) ? performance.now() : Date.now();
    host.remove();
    return {
      synthetic: true,
      nodes: graph.claims.length + graph.papers.length,
      edges: graph.edges.length,
      render_ms: Number(Math.max(0, ended - started).toFixed(2))
    };
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
    const claim = state.graph.claimById.get(edge.claimId) || state.graph.allClaims.find(function (item) { return item.claim_id === edge.claimId; });
    const paper = state.graph.paperById.get(edge.paperId) || state.graph.allPapers.find(function (item) { return item.paper_id === edge.paperId; });
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
        ? (state.graph.paperById.get(id) || state.graph.allPapers.find(function (paper) { return paper.paper_id === id; }))
        : (state.graph.claimById.get(id) || state.graph.allClaims.find(function (claim) { return claim.claim_id === id; }));
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
    const layoutEl = document.getElementById("ctm-layout");
    if (open) {
      if (layoutEl) layoutEl.hidden = true;
      ensureGraph();
      panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
    } else {
      closeDetail();
      if (layoutEl && state.payload) layoutEl.hidden = false;
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
        const layoutEl = document.getElementById("ctm-layout");
        if (layoutEl) layoutEl.hidden = true;
        render();
      } else {
        ensureGraph();
      }
    }
  });

  // Public hooks used by the G3 evidence script. They only expose view state
  // and an explicitly synthetic stress measurement; no page data is changed.
  window.CGMapGraph = {
    render: render,
    stats: function () {
      return {
        nodes: state.graph ? state.graph.claims.length + state.graph.papers.length : 0,
        edges: state.graph ? state.graph.edges.length : 0,
        render_ms: Number(state.renderMs.toFixed(2)),
        zoom: Number(state.view.scale.toFixed(2)),
        filters: Object.assign({}, state.filters)
      };
    },
    benchmark: benchmark,
    resetView: resetView
  };

  // The page may already have loaded before this script runs; keep the topic
  // id in sync without issuing a second API request.
  state.topicId = app.dataset.topic || topicFromUrl();
})();
