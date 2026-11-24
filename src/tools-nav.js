/* 工具导航：注入底部栏与工具抽屉，数据来自 tools.json。
 * 每个页面（首页/工具页）只需引入 tools-nav.css + tools-nav.js 即可获得导航。
 * 路径解析基于当前页面位置，file:// 与 Capacitor 均可用。
 */
(function () {
  "use strict";
  var script =
    document.currentScript ||
    document.querySelector('script[src$="tools-nav.js"]');
  var attr = script ? script.getAttribute("data-root") : null;

  // 计算站点根的相对前缀：根据 data-root 属性（推荐）或脚本路径深度推断
  var base = "";
  if (attr !== null) {
    base = attr;
  } else if (script) {
    var parts = script.getAttribute("src").split("/");
    base = new Array(Math.max(0, parts.length - 1)).fill("..").join("/");
    if (base === "") base = ".";
  }
  function resolve(path) {
    return base === "." ? path : base + "/" + path;
  }

  var state = { tools: [], open: false };

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function isHome() {
    // 精确匹配首页地址，避免工具页也叫 index.html 被误判
    try {
      return location.href === new URL(resolve("index.html"), location.href).href;
    } catch {
      return location.pathname.split("/").pop() === "index.html";
    }
  }

  function buildBar() {
    var bar = el("nav", "tools-bar");
    var home = el("button", "tools-bar-btn" + (isHome() ? " active" : ""));
    home.type = "button";
    home.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11.2 12 4l8 7.2v8.05a.75.75 0 0 1-.75.75H15v-6h-6v6H4.75a.75.75 0 0 1-.75-.75z"/></svg><span>首页</span>';
    home.addEventListener("click", function () {
      location.href = resolve("index.html");
    });
    var grid = el("button", "tools-bar-btn");
    grid.type = "button";
    grid.innerHTML =
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg><span>工具</span>';
    grid.addEventListener("click", function () {
      state.open ? closeSheet() : openSheet();
    });
    grid.classList.toggle("active", state.open);
    bar.append(home, grid);
    return bar;
  }

  function openSheet() {
    state.open = true;
    renderSheet();
    sheet.hidden = false;
    requestAnimationFrame(function () {
      sheet.classList.add("open");
    });
  }
  function closeSheet() {
    state.open = false;
    sheet.classList.remove("open");
    setTimeout(function () {
      sheet.hidden = true;
    }, 180);
  }
  function renderSheet() {
    list.replaceChildren();
    state.tools.forEach(function (tool) {
      var item = el("button", "tools-item");
      item.type = "button";
      var current = location.pathname.endsWith(tool.url.split("/").pop());
      if (current && !isHome()) item.classList.add("current");
      var title = el("strong", null, tool.title);
      var desc = el("span", null, tool.desc || "");
      item.append(title, desc);
      item.addEventListener("click", function () {
        closeSheet();
        location.href = resolve(tool.url);
      });
      list.append(item);
    });
  }

  var sheet = el("div", "tools-sheet");
  sheet.hidden = true;
  var panel = el("div", "tools-sheet-panel");
  var head = el("header", "tools-sheet-head");
  head.append(el("strong", null, "工具箱"));
  var closeBtn = el("button", "tools-sheet-close", "×");
  closeBtn.type = "button";
  closeBtn.setAttribute("aria-label", "关闭工具列表");
  closeBtn.addEventListener("click", closeSheet);
  head.append(closeBtn);
  var list = el("div", "tools-list");
  panel.append(head, list);
  sheet.append(panel);
  sheet.addEventListener("click", function (event) {
    if (event.target === sheet) closeSheet();
  });

  var bar = buildBar();
  sheet.addEventListener("transitionend", function () {
    grid.classList.toggle("active", state.open);
  });

  function mount() {
    document.body.append(sheet, bar);
  }

  fetch(resolve("tools.json"))
    .then(function (response) {
      return response.json();
    })
    .then(function (tools) {
      state.tools = tools;
      if (state.open) renderSheet();
    })
    .catch(function () {
      state.tools = [];
    });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
  document.body.classList.add("has-tools-nav");
})();
