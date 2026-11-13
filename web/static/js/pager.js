/* Shared client-side pager for long lists.
 *
 * Usage:
 *   const pager = CGList.create({
 *     mount: document.getElementById("x-pager"),
 *     pageSize: 20,
 *     param: "page",            // optional URL query key
 *     sizeParam: "size",        // optional URL query key for page size
 *     onChange: function (page, size) { paint(page, size); }
 *   });
 *   pager.setTotal(rows.length); // renders controls; caller paints once
 *   pager.slice(rows);           // current page slice
 *
 * The control never renders a second pagination bar: a list shorter than the
 * page size shows only the total count. URL state uses replaceState, so it
 * does not spam browser history.
 */
(function () {
  "use strict";

  function readInt(params, key, fallback) {
    if (!key) return fallback;
    const raw = params.get(key);
    const n = raw === null ? NaN : parseInt(raw, 10);
    return isFinite(n) && n > 0 ? n : fallback;
  }

  function pageList(current, total) {
    const wanted = new Set([1, total, current - 2, current - 1, current, current + 1, current + 2]);
    const pages = Array.from(wanted).filter(function (n) { return n >= 1 && n <= total; }).sort(function (a, b) { return a - b; });
    const out = [];
    let prev = 0;
    pages.forEach(function (n) {
      if (prev && n - prev > 1) out.push(null);
      out.push(n);
      prev = n;
    });
    return out;
  }

  function create(opts) {
    const mount = opts.mount;
    const sizes = opts.sizes || [10, 20, 50];
    const param = opts.param || null;
    const sizeParam = opts.sizeParam || null;
    const onChange = typeof opts.onChange === "function" ? opts.onChange : function () {};
    const params = param ? new URLSearchParams(window.location.search) : null;
    let size = readInt(params, sizeParam, opts.pageSize || 20);
    if (sizes.indexOf(size) < 0) size = opts.pageSize || sizes[0];
    let page = readInt(params, param, 1);
    let total = 0;

    function pages() {
      return Math.max(1, Math.ceil(total / size));
    }

    function clamp() {
      page = Math.max(1, Math.min(page, pages()));
    }

    function writeURL() {
      if (!param) return;
      const url = new URL(window.location.href);
      if (page <= 1) url.searchParams.delete(param); else url.searchParams.set(param, String(page));
      if (sizeParam) {
        if (size === (opts.pageSize || 20)) url.searchParams.delete(sizeParam);
        else url.searchParams.set(sizeParam, String(size));
      }
      window.history.replaceState(null, "", url);
    }

    function button(label, target, extra) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "pager-btn" + (extra || "");
      btn.textContent = label;
      btn.addEventListener("click", function () {
        page = target;
        render();
        writeURL();
        onChange(page, size);
      });
      return btn;
    }

    function render() {
      if (!mount) return;
      mount.textContent = "";
      mount.classList.toggle("pager-simple", total <= size);
      const shownStart = total ? (page - 1) * size + 1 : 0;
      const shownEnd = Math.min(total, page * size);
      const info = document.createElement("span");
      info.className = "pager-info";
      info.textContent = total
        ? "第 " + shownStart + "–" + shownEnd + " 条 / 共 " + total + " 条"
        : "共 0 条";
      mount.appendChild(info);

      if (total > size) {
        const bar = document.createElement("div");
        bar.className = "pager-btns";
        const prev = button("‹", Math.max(1, page - 1), " pager-step");
        prev.setAttribute("aria-label", "上一页");
        prev.disabled = page <= 1;
        bar.appendChild(prev);
        pageList(page, pages()).forEach(function (n) {
          if (n === null) {
            const gap = document.createElement("span");
            gap.className = "pager-gap";
            gap.textContent = "…";
            bar.appendChild(gap);
            return;
          }
          const btn = button(String(n), n, n === page ? " on" : "");
          if (n === page) btn.setAttribute("aria-current", "page");
          bar.appendChild(btn);
        });
        const next = button("›", Math.min(pages(), page + 1), " pager-step");
        next.setAttribute("aria-label", "下一页");
        next.disabled = page >= pages();
        bar.appendChild(next);
        mount.appendChild(bar);

        const sizeWrap = document.createElement("label");
        sizeWrap.className = "pager-size";
        sizeWrap.appendChild(document.createTextNode("每页 "));
        const select = document.createElement("select");
        select.setAttribute("aria-label", "每页条数");
        sizes.forEach(function (n) {
          const opt = document.createElement("option");
          opt.value = String(n);
          opt.textContent = String(n);
          if (n === size) opt.selected = true;
          select.appendChild(opt);
        });
        select.addEventListener("change", function () {
          size = parseInt(select.value, 10) || size;
          page = 1;
          render();
          writeURL();
          onChange(page, size);
        });
        sizeWrap.appendChild(select);
        mount.appendChild(sizeWrap);
      }
    }

    const pager = {
      get page() { return page; },
      get size() { return size; },
      get total() { return total; },
      setTotal: function (n, options) {
        total = Math.max(0, parseInt(n, 10) || 0);
        if (options && options.reset) page = 1;
        clamp();
        render();
        writeURL();
      },
      reset: function () {
        page = 1;
        clamp();
        render();
        writeURL();
        onChange(page, size);
      },
      slice: function (items) {
        const start = (page - 1) * size;
        return (items || []).slice(start, start + size);
      },
      refresh: render,
    };

    render();
    return pager;
  }

  window.CGList = { create: create };
})();
