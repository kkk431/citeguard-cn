// 图表结论核验页：上传截图 + 结论 -> /api/figure-check
(function () {
  const form = document.getElementById("figure-form");
  if (!form) return;
  const fileInput = document.getElementById("figure-file");
  const dropzone = document.getElementById("figure-dropzone");
  const fileName = document.getElementById("figure-file-name");
  const previewWrap = document.getElementById("figure-preview-wrap");
  const preview = document.getElementById("figure-preview");
  const claimInput = document.getElementById("figure-claim");
  const contextInput = document.getElementById("figure-context");
  const paperInput = document.getElementById("figure-paper");
  const pageInput = document.getElementById("figure-page");
  const btn = document.getElementById("figure-check-btn");
  const hint = document.getElementById("figure-hint");
  const result = document.getElementById("figure-result");

  const LABELS = {
    supported: { text: "结论与图表一致", cls: "ok" },
    contradicted: { text: "结论与图表矛盾", cls: "bad" },
    insufficient: { text: "图表信息不足", cls: "unknown" },
  };

  function setHint(text) {
    if (hint) hint.textContent = text || "";
  }

  function setFiles(files) {
    const list = Array.prototype.slice.call(files || []).filter(Boolean);
    if (!list.length) return;
    if (list.length > 5) {
      setHint("一次最多上传 5 张图");
      window.showToast && window.showToast("一次最多上传 5 张图");
      return;
    }
    for (let i = 0; i < list.length; i++) {
      const file = list[i];
      if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
        setHint("只支持 PNG / JPEG / WebP");
        window.showToast && window.showToast("只支持 PNG / JPEG / WebP");
        return;
      }
      if (file.size > 8 * 1024 * 1024) {
        setHint("单张图片超过 8 MB");
        window.showToast && window.showToast("单张图片超过 8 MB");
        return;
      }
    }
    const dt = new DataTransfer();
    list.forEach(function (file) { dt.items.add(file); });
    fileInput.files = dt.files;
    fileName.textContent = list.length === 1
      ? list[0].name + " · " + (list[0].size / 1024).toFixed(0) + " KB"
      : list.length + " 张图：" + list.map(function (f) { return f.name; }).join("、");
    preview.src = URL.createObjectURL(list[0]);
    previewWrap.hidden = false;
    setHint(list.length > 1 ? "将逐张核验，结果按图片分组显示" : "");
  }

  fileInput.addEventListener("change", function () {
    setFiles(fileInput.files);
  });
  if (paperInput) {
    paperInput.addEventListener("change", function () {
      const paper = paperInput.files && paperInput.files[0];
      if (paper) {
        setHint("已选择论文 PDF，提交时按页读取正文（页码留空则自动定位图注页）");
      }
    });
  }
  ["dragenter", "dragover"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      dropzone.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    dropzone.addEventListener(ev, function (e) {
      e.preventDefault();
      dropzone.classList.remove("drag");
    });
  });
  dropzone.addEventListener("drop", function (e) {
    if (e.dataTransfer && e.dataTransfer.files.length) setFiles(e.dataTransfer.files);
  });

  document.querySelectorAll(".fig-example-use").forEach(function (button) {
    button.addEventListener("click", async function () {
      const card = button.closest(".fig-example");
      if (!card) return;
      const imgUrl = card.getAttribute("data-img");
      const claim = card.getAttribute("data-claim") || "";
      claimInput.value = claim;
      setHint("正在载入示例图片…");
      try {
        const resp = await fetch(imgUrl);
        const blob = await resp.blob();
        setFiles([new File([blob], "example.png", { type: blob.type || "image/png" })]);
      } catch (err) {
        setHint("示例图片载入失败");
      }
    });
  });

  function verdictHtml(data) {
    const info = LABELS[data.verdict] || { text: "未知判定", cls: "unknown" };
    const reason = data.reason ? "<p class=\"fig-reason\">" + escapeHtml(data.reason) + "</p>" : "";
    let source = "";
    if (data.context_source) {
      const raw = String(data.context_source);
      if (raw.indexOf("pdf_auto:") === 0) {
        source = "正文取自 PDF 第 " + escapeHtml(raw.slice(9)) + " 页（按图注自动定位）";
      } else {
        source = "正文取自 PDF 第 " + escapeHtml(raw.replace("pdf_page:", "")) + " 页";
      }
    }
    const pageInfo = data.page_rendered && data.page_no
      ? "第 " + escapeHtml(data.page_no) + " 页（PDF 自动渲染）" : "";
    const meta = [
      data.model ? "模型 " + escapeHtml(data.model) : "",
      data.latency_ms != null ? (data.latency_ms / 1000).toFixed(1) + " 秒" : "",
      pageInfo || source,
    ].filter(Boolean).join(" · ");
    return (
      "<div class=\"fig-verdict\">" +
      "<span class=\"pill " + info.cls + "\"><i></i>" + info.text + " · " + escapeHtml(data.verdict) + "</span>" +
      reason +
      "<div class=\"mono-sm\" style=\"color:var(--muted);margin-top:8px\">" + meta + " · 自动判断，请人工复核</div>" +
      "</div>"
    );
  }

  function itemsHtml(data) {
    let source = "";
    if (data.context_source) {
      const raw = String(data.context_source);
      source = raw.indexOf("pdf_auto:") === 0
        ? "正文取自 PDF 第 " + escapeHtml(raw.slice(9)) + " 页（按图注自动定位）"
        : "正文取自 PDF 第 " + escapeHtml(raw.replace("pdf_page:", "")) + " 页";
    }
    const rows = (data.items || []).map(function (item) {
      const info = LABELS[item.verdict] || { text: "未判定", cls: "unknown" };
      const reason = item.ok && item.reason ? escapeHtml(item.reason) : escapeHtml(item.error || "未判定");
      const pageTag = item.page ? "<span class=\"mono-sm\" style=\"color:var(--muted)\">第 " + escapeHtml(item.page) + " 页 · </span>" : "";
      return (
        "<tr>" +
        "<td class=\"fig-claim-cell\">" + pageTag + escapeHtml(item.claim) + "</td>" +
        "<td><span class=\"pill " + info.cls + "\"><i></i>" + info.text + "</span></td>" +
        "<td class=\"fig-reason-cell\">" + reason + "</td>" +
        "</tr>"
      );
    }).join("");
    const pages = data.page_rendered && data.context_source && String(data.context_source).indexOf("pdf_pages:") === 0
      ? "第 " + escapeHtml(String(data.context_source).slice(10)) + " 页（PDF 自动渲染）" : source;
    const meta = [
      data.model ? "模型 " + escapeHtml(data.model) : "",
      pages,
      "自动判断，请人工复核",
    ].filter(Boolean).join(" · ");
    return (
      "<div class=\"fig-verdict\">" +
      "<table class=\"fig-claim-table\"><thead><tr><th>结论</th><th>判断</th><th>理由</th></tr></thead>" +
      "<tbody>" + rows + "</tbody></table>" +
      "<div class=\"mono-sm\" style=\"color:var(--muted);margin-top:8px\">" + meta + "</div>" +
      "</div>"
    );
  }

  function escapeHtml(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const files = fileInput.files ? Array.prototype.slice.call(fileInput.files) : [];
    const rawClaim = (claimInput.value || "").trim();
    const claimLines = rawClaim.split(/\r?\n/).map(function (line) { return line.trim(); }).filter(Boolean);
    const paper = paperInput && paperInput.files && paperInput.files[0];
    if (!files.length && !paper) { setHint("请上传图表截图，或上传论文 PDF 自动定位并渲染图/表页"); return; }
    if (!claimLines.length) { setHint("请写一条结论"); return; }
    if (claimLines.length > 5) { setHint("一次最多核验 5 条结论"); return; }
    if (claimLines.some(function (line) { return line.length < 5; })) {
      setHint("每条结论至少写 5 个字");
      return;
    }
    const context = contextInput ? (contextInput.value || "").trim() : "";
    const pageValue = pageInput && pageInput.value.trim();

    function buildForm(file) {
      const fd = new FormData();
      if (file) fd.append("image", file);
      fd.append("claim", claimLines[0]);
      if (claimLines.length > 1) fd.append("claims", rawClaim);
      if (context) fd.append("context", context);
      if (paper) {
        fd.append("paper", paper);
        if (pageValue) fd.append("page", pageValue);
      }
      return fd;
    }

    async function post(file) {
      const resp = await fetch("/api/figure-check", { method: "POST", body: buildForm(file) });
      const data = await resp.json().catch(function () { return {}; });
      return { resp: resp, data: data };
    }

    btn.disabled = true;
    setHint(paper ? (files.length ? "正在读取 PDF 正文并核验…" : "正在定位图/表页并渲染，随后核验…")
      : "核验中…首次请求需要加载模型，可能等十几秒");
    result.classList.add("hidden");
    try {
      if (files.length > 1) {
        const blocks = [];
        for (let i = 0; i < files.length; i++) {
          setHint("正在核验第 " + (i + 1) + " / " + files.length + " 张…");
          const out = await post(files[i]);
          const head = '<div class="fig-batch-item"><div class="mono-sm" style="margin:10px 0 4px">' +
            escapeHtml(files[i].name) + "</div>";
          if (!out.resp.ok || !out.data.ok) {
            blocks.push(head + '<div class="fig-error">核验失败：' +
              escapeHtml(out.data.error || ("HTTP " + out.resp.status)) + "</div></div>");
            continue;
          }
          blocks.push(head + (out.data.items ? itemsHtml(out.data) : verdictHtml(out.data)) + "</div>");
        }
        setHint("");
        result.innerHTML = blocks.join("");
        result.classList.remove("hidden");
        return;
      }
      const out = await post(files[0]);
      if (!out.resp.ok || !out.data.ok) {
        setHint("");
        result.innerHTML =
          "<div class=\"fig-error\">核验失败：" + escapeHtml(out.data.error || ("HTTP " + out.resp.status)) + "</div>";
        result.classList.remove("hidden");
        return;
      }
      setHint("");
      result.innerHTML = out.data.items ? itemsHtml(out.data) : verdictHtml(out.data);
      result.classList.remove("hidden");
    } catch (err) {
      setHint("");
      result.innerHTML = "<div class=\"fig-error\">请求失败：" + escapeHtml(err.message || String(err)) + "</div>";
      result.classList.remove("hidden");
    } finally {
      btn.disabled = false;
    }
  });
})();
