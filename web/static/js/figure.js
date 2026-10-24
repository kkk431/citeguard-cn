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

  function setFile(file) {
    if (!file) return;
    if (!/^image\/(png|jpeg|webp)$/.test(file.type)) {
      setHint("只支持 PNG / JPEG / WebP");
      window.showToast && window.showToast("只支持 PNG / JPEG / WebP");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setHint("图片超过 8 MB");
      window.showToast && window.showToast("图片超过 8 MB");
      return;
    }
    const dt = new DataTransfer();
    dt.items.add(file);
    fileInput.files = dt.files;
    fileName.textContent = file.name + " · " + (file.size / 1024).toFixed(0) + " KB";
    preview.src = URL.createObjectURL(file);
    previewWrap.hidden = false;
    setHint("");
  }

  fileInput.addEventListener("change", function () {
    setFile(fileInput.files && fileInput.files[0]);
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
    if (e.dataTransfer && e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
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
        setFile(new File([blob], "example.png", { type: blob.type || "image/png" }));
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
    const meta = [
      data.model ? "模型 " + escapeHtml(data.model) : "",
      data.latency_ms != null ? (data.latency_ms / 1000).toFixed(1) + " 秒" : "",
      source,
    ].filter(Boolean).join(" · ");
    return (
      "<div class=\"fig-verdict\">" +
      "<span class=\"pill " + info.cls + "\"><i></i>" + info.text + " · " + escapeHtml(data.verdict) + "</span>" +
      reason +
      "<div class=\"mono-sm\" style=\"color:var(--muted);margin-top:8px\">" + meta + " · 自动判断，请人工复核</div>" +
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
    const file = fileInput.files && fileInput.files[0];
    const claim = (claimInput.value || "").trim();
    if (!file) { setHint("请先选择图表截图"); return; }
    if (claim.length < 5) { setHint("结论至少写 5 个字"); return; }
    const fd = new FormData();
    fd.append("image", file);
    fd.append("claim", claim);
    const context = contextInput ? (contextInput.value || "").trim() : "";
    if (context) fd.append("context", context);
    const paper = paperInput && paperInput.files && paperInput.files[0];
    if (paper) {
      fd.append("paper", paper);
      const pageValue = pageInput && pageInput.value.trim();
      if (pageValue) fd.append("page", pageValue);
    }
    btn.disabled = true;
    setHint(paper ? "正在读取 PDF 正文并核验…" : "核验中…首次请求需要加载模型，可能等十几秒");
    result.classList.add("hidden");
    try {
      const resp = await fetch("/api/figure-check", { method: "POST", body: fd });
      const data = await resp.json().catch(function () { return {}; });
      if (!resp.ok || !data.ok) {
        setHint("");
        result.innerHTML =
          "<div class=\"fig-error\">核验失败：" + escapeHtml(data.error || ("HTTP " + resp.status)) + "</div>";
        result.classList.remove("hidden");
        return;
      }
      setHint("");
      result.innerHTML = verdictHtml(data);
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
