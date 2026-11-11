(function () {
  "use strict";
  var grid = document.getElementById("judge-grid");
  var current = document.getElementById("judge-current-body");
  var SOURCE = { hosted: ["云端", "badge-amber"], local: ["本地开源", "badge-mint"], adapter: ["本地 adapter", "badge-cyan"] };

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; }); }

  function render(data) {
    var cur = data.current || {};
    current.innerHTML = "判定端点 <code>" + esc(cur.base_url || "") + "</code> · 模型 <code>" + esc(cur.model || "") + "</code> · 来源 <b>" + esc(cur.label || "环境变量") + "</b>";
    grid.innerHTML = "";
    (data.models || []).forEach(function (m) {
      var src = SOURCE[m.source] || [m.source, "badge-mint"];
      var card = document.createElement("div");
      card.className = "panel judge-card" + (m.id === data.active ? " on" : "");
      card.innerHTML =
        '<div class="judge-head"><b>' + esc(m.label) + '</b><span class="badge ' + src[1] + '">' + esc(src[0]) + "</span></div>" +
        '<div class="mono-sm" style="color:var(--muted)">' + esc(m.base_url) + " · " + esc(m.model) + "</div>" +
        '<div class="hint" style="margin-top:8px">' + esc(m.note || "") + " · 许可 " + esc(m.license || "?") + "</div>" +
        '<div class="judge-actions"><button class="btn btn-sm" data-test="' + esc(m.id) + '">测连接</button>' +
        (m.id === data.active ? '<span class="badge badge-mint">当前</span>' : '<button class="btn btn-primary btn-sm" data-use="' + esc(m.id) + '">设为当前</button>') +
        '<span class="mono-sm" data-result="' + esc(m.id) + '"></span></div>';
      grid.appendChild(card);
    });
    grid.querySelectorAll("[data-use]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        btn.disabled = true;
        try {
          var r = await fetch("/api/models/active", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: btn.getAttribute("data-use") }) });
          var d = await r.json();
          if (!r.ok) throw new Error(d.detail || "切换失败");
          window.CiteGuard.toast("已切换判定模型");
          load();
        } catch (e) { btn.disabled = false; window.CiteGuard.toast(e.message); }
      });
    });
    grid.querySelectorAll("[data-test]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var id = btn.getAttribute("data-test");
        var out = grid.querySelector('[data-result="' + id + '"]');
        btn.disabled = true; out.textContent = "测试中…";
        try {
          var r = await fetch("/api/models/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: id }) });
          var d = await r.json();
          out.textContent = d.ok ? ("连通 " + d.latency_ms + " ms") : ("不通：" + d.error);
        } catch (e) { out.textContent = "不通：" + e.message; }
        btn.disabled = false;
      });
    });
  }

  async function load() {
    try {
      var r = await fetch("/api/models");
      render(await r.json());
    } catch (e) { current.textContent = "读取失败：" + e.message; }
  }
  load();
})();
