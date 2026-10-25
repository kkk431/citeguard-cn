/* Shared helpers: toast + fetch wrappers. */
(function () {
  const toastEl = document.getElementById("toast");
  let toastTimer = null;

  function toast(message, ms) {
    if (!toastEl) return;
    toastEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.classList.remove("show");
    }, ms || 2600);
  }

  async function getJSON(url) {
    const resp = await fetch(url, { headers: { Accept: "application/json" } });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return resp.json();
  }

  async function postForm(url, formData) {
    const resp = await fetch(url, { method: "POST", body: formData });
    const data = await resp.json().catch(function () { return {}; });
    if (!resp.ok) throw new Error(data.detail || "HTTP " + resp.status);
    return data;
  }

  async function copyText(text) {
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (err) {
      /* fall through to the textarea fallback */
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (err) {
      return false;
    }
  }

  window.CiteGuard = {
    toast: toast,
    getJSON: getJSON,
    postForm: postForm,
    copyText: copyText,
  };

  /* ---- command palette ---- */
  const palette = document.getElementById("palette");
  const paletteInput = document.getElementById("palette-input");
  const paletteList = document.getElementById("palette-list");
  const paletteOpen = document.getElementById("palette-open");
  if (palette && paletteInput && paletteList) {
    const items = [
      { kind: "page", label: "工作台", sub: "上传论文，逐条核验", url: "/" },
      { kind: "page", label: "图表核验", sub: "图中结论是否成立", url: "/figure" },
      { kind: "page", label: "文献对比", sub: "多篇论文横向矩阵", url: "/compare" },
      { kind: "page", label: "文献发现", sub: "选题检索与排序", url: "/discover" },
      { kind: "page", label: "题录库", sub: "导入本地中文元数据", url: "/library" },
      { kind: "page", label: "历史", sub: "最近的体检任务", url: "/history" },
      { kind: "page", label: "评测", sub: "可复核的数字与证据", url: "/benchmark" },
      { kind: "page", label: "关于", sub: "方法与边界", url: "/about" },
      { kind: "action", label: "开始一次新体检", sub: "回到工作台并选择文件", url: "/#upload-card" },
      { kind: "action", label: "用示例论文试试", sub: "工作台内置示例", url: "/?sample=1" },
      { kind: "link", label: "GitHub 仓库", sub: "kkk431/citeguard-cn", url: "https://github.com/kkk431/citeguard-cn" },
    ];
    let filtered = items.slice();
    let cursor = 0;
    let lastFocus = null;

    function render() {
      paletteList.innerHTML = "";
      if (!filtered.length) {
        const empty = document.createElement("div");
        empty.className = "palette-empty";
        empty.textContent = "没有匹配的页面或动作";
        paletteList.appendChild(empty);
        return;
      }
      filtered.forEach(function (item, i) {
        const row = document.createElement("div");
        row.className = "palette-item" + (i === cursor ? " on" : "");
        row.setAttribute("role", "option");
        row.innerHTML = '<span class="p-kind">' + item.kind + "</span><span>" +
          item.label + '</span><span class="p-sub">' + item.sub + "</span>";
        row.addEventListener("mouseenter", function () { cursor = i; paint(); });
        row.addEventListener("click", function () { go(item); });
        paletteList.appendChild(row);
      });
    }

    function paint() {
      Array.prototype.forEach.call(paletteList.children, function (row, i) {
        if (!row.classList) return;
        row.classList.toggle("on", i === cursor);
      });
      const active = paletteList.children[cursor];
      if (active && active.scrollIntoView) active.scrollIntoView({ block: "nearest" });
    }

    function filter() {
      const q = paletteInput.value.trim().toLowerCase();
      filtered = items.filter(function (item) {
        return !q || (item.label + " " + item.sub + " " + item.url).toLowerCase().indexOf(q) >= 0;
      });
      cursor = 0;
      render();
    }

    function open() {
      lastFocus = document.activeElement;
      palette.hidden = false;
      paletteInput.value = "";
      filter();
      paletteInput.focus();
    }

    function close() {
      palette.hidden = true;
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }

    function go(item) {
      close();
      if (item.url.indexOf("http") === 0) window.open(item.url, "_blank", "noopener");
      else window.location.href = item.url;
    }

    if (paletteOpen) paletteOpen.addEventListener("click", open);
    if (window.location.hash === "#palette") open();
    document.addEventListener("keydown", function (e) {
      const isOpen = !palette.hidden;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (isOpen) close(); else open();
        return;
      }
      if (!isOpen) return;
      if (e.key === "Escape") { e.preventDefault(); close(); }
      else if (e.key === "ArrowDown") { e.preventDefault(); cursor = Math.min(cursor + 1, filtered.length - 1); paint(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); cursor = Math.max(cursor - 1, 0); paint(); }
      else if (e.key === "Enter" && filtered[cursor]) { e.preventDefault(); go(filtered[cursor]); }
    });
    paletteInput.addEventListener("input", filter);
    palette.addEventListener("click", function (e) {
      if (e.target.hasAttribute("data-close")) close();
    });
  }

  /* ---- mobile rail ---- */
  const rail = document.getElementById("rail");
  const toggle = document.getElementById("rail-toggle");
  const backdrop = document.getElementById("rail-backdrop");
  function setRail(open) {
    if (!rail || !toggle) return;
    rail.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (backdrop) backdrop.hidden = !open;
  }
  if (toggle) toggle.addEventListener("click", function () {
    setRail(!rail.classList.contains("open"));
  });
  if (backdrop) backdrop.addEventListener("click", function () { setRail(false); });
})();
