"""字格工具页共享的「搜索定位」组件。

两个生成器（structure.py / frequency.py）都通过占位符注入同一份
CSS / HTML / JS，避免两处维护。行为：

- 输入框内输入或粘贴一个或多个汉字，页面中所有匹配的字格
  （span[data-char]）加高亮并滚动定位到第一处；
- 回车 / 「下一个」循环跳到下一处命中；
- 清空输入或按 Esc 取消高亮。
"""

SEARCH_CSS = """    /* 搜索定位 */
    .char-search {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-left: auto;
    }
    .char-search input {
      width: 150px;
      padding: 7px 12px;
      border: 1px solid var(--line-strong);
      border-radius: 9px;
      background: #fffdf7;
      color: var(--ink);
      font-family: var(--ui-font);
      font-size: 14px;
      outline: none;
    }
    .char-search input:focus { border-color: var(--cinnabar); }
    .char-search button {
      padding: 7px 14px;
      border: 1px solid var(--line-strong);
      border-radius: 9px;
      background: var(--paper-deep);
      color: var(--ink);
      font-family: var(--ui-font);
      font-size: 13px;
      cursor: pointer;
    }
    .char-search button:hover { border-color: var(--cinnabar); color: var(--cinnabar); }
    .char-search .char-search-count {
      min-width: 4em;
      color: var(--ink-muted);
      font-size: 12px;
    }
    span.search-hit {
      outline: 2px solid var(--cinnabar) !important;
      outline-offset: 1px;
      border-color: var(--cinnabar) !important;
    }
    span.search-hit-current {
      background: var(--cinnabar) !important;
      color: #fffdf7 !important;
    }
"""

SEARCH_HTML = """      <div class="char-search">
        <input id="char-search-input" type="text" placeholder="输入汉字定位"
          autocomplete="off" spellcheck="false">
        <button id="char-search-next" type="button">下一个</button>
        <span class="char-search-count" id="char-search-count"></span>
      </div>"""

SEARCH_JS = """<script>
(function () {
  "use strict";
  var input = document.getElementById("char-search-input");
  var countLabel = document.getElementById("char-search-count");
  var nextButton = document.getElementById("char-search-next");
  var hits = [];
  var current = 0;

  function clear() {
    hits.forEach(function (span) {
      span.classList.remove("search-hit", "search-hit-current");
    });
    hits = [];
    current = 0;
    countLabel.textContent = "";
  }

  function focusHit(index) {
    if (!hits.length) return;
    hits.forEach(function (span) { span.classList.remove("search-hit-current"); });
    current = ((index % hits.length) + hits.length) % hits.length;
    var span = hits[current];
    span.classList.add("search-hit-current");
    span.scrollIntoView({ block: "center", behavior: "smooth" });
    countLabel.textContent = (current + 1) + " / " + hits.length;
  }

  function run() {
    clear();
    var text = input.value.replace(/\\s+/g, "");
    if (!text) return;
    var wanted = {};
    Array.prototype.forEach.call(text, function (ch) { wanted[ch] = true; });
    document.querySelectorAll("span[data-char]").forEach(function (span) {
      if (wanted[span.getAttribute("data-char")]) {
        span.classList.add("search-hit");
        hits.push(span);
      }
    });
    if (!hits.length) {
      countLabel.textContent = "未找到";
      return;
    }
    focusHit(0);
  }

  input.addEventListener("input", run);
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter") { event.preventDefault(); focusHit(current + 1); }
    if (event.key === "Escape") { input.value = ""; clear(); }
  });
  nextButton.addEventListener("click", function () { focusHit(current + 1); });
})();
</script>"""
