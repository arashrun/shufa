"use strict";

const STORAGE_KEY = "xingkai-recall-state-v1";
const DEFAULT_SOURCE = "level-1.txt";
const RATING_LABELS = {
  forgot: "已标记为需重点复习",
  fuzzy: "已标记为有点模糊",
  mastered: "已标记为已掌握",
};
const SEARCH_STATUS_LABELS = {
  forgot: "需重点复习",
  fuzzy: "有点模糊",
  mastered: "已掌握",
};

const elements = {
  sourceName: document.querySelector("#source-name"),
  importButton: document.querySelector("#import-button"),
  fileInput: document.querySelector("#file-input"),
  searchTrigger: document.querySelector("#search-trigger"),
  searchOverlay: document.querySelector("#search-overlay"),
  searchClose: document.querySelector("#search-close"),
  searchInput: document.querySelector("#search-input"),
  searchPreview: document.querySelector("#search-preview"),
  positionCurrent: document.querySelector("#position-current"),
  positionTotal: document.querySelector("#position-total"),
  orderToggle: document.querySelector("#order-toggle"),
  promptEyebrow: document.querySelector("#prompt-eyebrow"),
  promptCharacter: document.querySelector("#prompt-character"),
  practiceStage: document.querySelector("#practice-stage"),
  revealButton: document.querySelector("#reveal-button"),
  revealButtonLabel: document.querySelector("#reveal-button-label"),
  ratingPanel: document.querySelector("#rating-panel"),
  previousButton: document.querySelector("#previous-button"),
  nextButton: document.querySelector("#next-button"),
  progressRing: document.querySelector("#progress-ring"),
  masteredPercent: document.querySelector("#mastered-percent"),
  newCount: document.querySelector("#new-count"),
  reviewCount: document.querySelector("#review-count"),
  masteredCount: document.querySelector("#mastered-count"),
  resetButton: document.querySelector("#reset-button"),
  dropOverlay: document.querySelector("#drop-overlay"),
  toast: document.querySelector("#toast"),
};

let state = {
  chars: [],
  order: [],
  index: 0,
  source: "",
  reveal: false,
  shuffle: false,
  ratings: {},
  finished: false,
};

let toastTimer = 0;
let dragDepth = 0;
let lastFocusedElement = null;

function parseCharacters(text) {
  const seen = new Set();
  const characters = [];
  const withoutBom = text.replace(/^\uFEFF/, "");

  for (const line of withoutBom.split(/\r?\n/)) {
    const cleanLine = line.replace(/#.*$/, "");
    const matches = cleanLine.match(/\p{Script=Han}/gu) || [];

    for (const character of matches) {
      if (!seen.has(character)) {
        seen.add(character);
        characters.push(character);
      }
    }
  }

  return characters;
}

function naturalOrder(length) {
  return Array.from({ length }, (_, index) => index);
}

function shuffledOrder(length) {
  const order = naturalOrder(length);

  for (let index = order.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [order[index], order[randomIndex]] = [order[randomIndex], order[index]];
  }

  return order;
}

function currentCharacter() {
  const characterIndex = state.order[state.index];
  return state.chars[characterIndex] ?? null;
}

function currentNaturalIndex() {
  return state.order[state.index] ?? 0;
}

function clampState() {
  if (state.chars.length === 0) {
    state.index = 0;
    state.order = [];
    state.reveal = false;
    return;
  }

  if (state.order.length !== state.chars.length) {
    state.order = naturalOrder(state.chars.length);
  }

  state.index = Math.min(Math.max(Number(state.index) || 0, 0), state.order.length - 1);
  state.reveal = false;
  state.finished = false;
}

function persistState() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        chars: state.chars,
        order: state.order,
        index: state.index,
        source: state.source,
        shuffle: state.shuffle,
        ratings: state.ratings,
      }),
    );
  } catch {
    showToast("浏览器无法保存学习记录");
  }
}

function restoreState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");

    if (
      saved &&
      Array.isArray(saved.chars) &&
      saved.chars.length > 0 &&
      saved.chars.every((character) => typeof character === "string")
    ) {
      state = {
        ...state,
        chars: saved.chars,
        order: Array.isArray(saved.order) ? saved.order : [],
        index: Number(saved.index) || 0,
        source: saved.source || "上次导入的词表",
        shuffle: Boolean(saved.shuffle),
        ratings: saved.ratings && typeof saved.ratings === "object" ? saved.ratings : {},
      };
      clampState();
      return true;
    }
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }

  return false;
}

async function loadDefaultSource() {
  if (window.location.protocol === "file:") {
    renderLoadError("请通过本地启动脚本打开，或点击右上角导入词表。");
    return;
  }

  try {
    const response = await fetch(DEFAULT_SOURCE, { cache: "no-store" });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const characters = parseCharacters(await response.text());

    if (characters.length === 0) {
      throw new Error("词表中没有可用的汉字");
    }

    state.chars = characters;
    state.order = naturalOrder(characters.length);
    state.index = 0;
    state.source = DEFAULT_SOURCE;
    state.shuffle = false;
    state.ratings = {};
    state.reveal = false;
    state.finished = false;
    persistState();
    render();
  } catch (error) {
    renderLoadError(`无法读取 ${DEFAULT_SOURCE}，请导入词表。`);
    console.error(error);
  }
}

function createIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M5.25 4.5c4.15.7 6.2 3.4 6.75 8.25.4-4.2 2.45-6.85 6.75-8.1M7 15.75c2.8.1 5.1.85 6.9 2.4M12 9.2v11.05");
  svg.append(path);
  return svg;
}

function renderStage() {
  const character = currentCharacter();
  elements.practiceStage.replaceChildren();

  if (!character) {
    renderLoadError("还没有可用汉字。");
    return;
  }

  if (!state.reveal) {
    const recallState = document.createElement("div");
    recallState.className = "recall-state";

    const orbit = document.createElement("div");
    orbit.className = "recall-orbit";
    orbit.append(createIcon());

    const title = document.createElement("strong");
    title.textContent = "字形已隐藏";

    const copy = document.createElement("p");
    copy.textContent = "看一眼上面的字，在纸上写下你记得的行楷形态，再来核对。";

    recallState.append(orbit, title, copy);
    elements.practiceStage.append(recallState);
    return;
  }

  const revealState = document.createElement("div");
  revealState.className = "reveal-state";

  const calligraphy = document.createElement("span");
  calligraphy.className = "calligraphy-character";
  calligraphy.textContent = character;
  calligraphy.setAttribute("aria-label", `荆霄鹏行楷：${character}`);

  const seal = document.createElement("span");
  seal.className = "reveal-seal";
  seal.setAttribute("aria-hidden", "true");
  seal.textContent = "行楷";

  revealState.append(calligraphy, seal);
  elements.practiceStage.append(revealState);
}

function renderLoadError(message) {
  elements.practiceStage.replaceChildren();
  const loadingState = document.createElement("div");
  loadingState.className = "loading-state";

  const title = document.createElement("strong");
  title.textContent = message;
  title.style.fontSize = "13px";
  title.style.fontWeight = "500";
  title.style.maxWidth = "330px";
  title.style.lineHeight = "1.8";
  title.style.textAlign = "center";

  loadingState.append(title);
  elements.practiceStage.append(loadingState);
}

function renderStats() {
  const total = state.chars.length;
  let mastered = 0;
  let review = 0;

  for (const character of state.chars) {
    if (state.ratings[character] === "mastered") {
      mastered += 1;
    } else if (state.ratings[character]) {
      review += 1;
    }
  }

  const percentage = total === 0 ? 0 : Math.round((mastered / total) * 100);
  const angle = (percentage / 100) * 360;

  elements.masteredPercent.textContent = `${percentage}%`;
  elements.masteredCount.textContent = mastered.toLocaleString("zh-CN");
  elements.reviewCount.textContent = review.toLocaleString("zh-CN");
  elements.newCount.textContent = (total - mastered - review).toLocaleString("zh-CN");
  elements.progressRing.style.background = `conic-gradient(var(--cinnabar) ${angle}deg, var(--line) ${angle}deg)`;
}

function render() {
  const character = currentCharacter();
  const total = state.chars.length;

  elements.sourceName.textContent = state.source || "未载入词表";
  elements.positionCurrent.textContent = total === 0 ? "—" : String(state.index + 1);
  elements.positionTotal.textContent = total === 0 ? "—" : total.toLocaleString("zh-CN");
  elements.promptCharacter.textContent = character || "—";
  elements.promptEyebrow.textContent = state.reveal ? "对照行楷，修正笔意" : "先在纸上写一遍";
  elements.orderToggle.setAttribute("aria-pressed", String(state.shuffle));
  elements.orderToggle.querySelector("span").textContent = state.shuffle ? "随机学习" : "顺序学习";
  elements.previousButton.disabled = state.index <= 0 || total === 0;
  elements.nextButton.disabled = state.index >= total - 1 || total === 0;
  elements.revealButton.hidden = state.reveal;
  elements.ratingPanel.hidden = !state.reveal;
  elements.revealButtonLabel.textContent = "揭晓 JXP 行楷";

  renderStage();
  renderStats();
}

function revealCharacter() {
  if (!currentCharacter() || state.reveal) {
    return;
  }

  state.reveal = true;
  render();
  elements.ratingPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function navigate(direction) {
  if (state.chars.length === 0) {
    return;
  }

  const targetIndex = state.index + direction;

  if (targetIndex < 0 || targetIndex >= state.order.length) {
    return;
  }

  state.index = targetIndex;
  state.reveal = false;
  state.finished = false;
  persistState();
  render();
}

function rateCurrent(rating) {
  const character = currentCharacter();

  if (!character || !state.reveal || !RATING_LABELS[rating]) {
    return;
  }

  state.ratings[character] = rating;
  showToast(RATING_LABELS[rating]);

  if (state.index < state.order.length - 1) {
    state.index += 1;
    state.reveal = false;
  } else {
    state.finished = true;
    state.reveal = true;
    showToast("本轮最后一个字已完成");
  }

  persistState();
  render();
}

function toggleOrder() {
  if (state.chars.length === 0) {
    return;
  }

  const character = currentCharacter();
  state.shuffle = !state.shuffle;
  state.order = state.shuffle
    ? shuffledOrder(state.chars.length)
    : naturalOrder(state.chars.length);

  if (state.shuffle) {
    state.index = 0;
  } else {
    state.index = Math.max(0, state.chars.indexOf(character));
  }

  state.reveal = false;
  state.finished = false;
  persistState();
  render();
}

async function importFile(file) {
  if (!file) {
    return;
  }

  if (!file.name.toLowerCase().endsWith(".txt")) {
    showToast("请选择 .txt 文本文件");
    return;
  }

  try {
    const characters = parseCharacters(await file.text());

    if (characters.length === 0) {
      showToast("文件中没有找到汉字");
      return;
    }

    state.chars = characters;
    state.order = naturalOrder(characters.length);
    state.index = 0;
    state.source = file.name;
    state.reveal = false;
    state.shuffle = false;
    state.ratings = {};
    state.finished = false;
    persistState();
    render();
    showToast(`已载入 ${characters.length.toLocaleString("zh-CN")} 个字`);
  } catch (error) {
    showToast("读取文件失败，请检查文件编码");
    console.error(error);
  } finally {
    elements.fileInput.value = "";
  }
}

function resetProgress() {
  if (!window.confirm("清空全部学习标记？汉字词表会保留。")) {
    return;
  }

  state.ratings = {};
  persistState();
  render();
  showToast("学习记录已清空");
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.classList.add("visible");
  toastTimer = window.setTimeout(() => {
    elements.toast.classList.remove("visible");
  }, 2200);
}

function searchCharacterFromInput() {
  return parseCharacters(elements.searchInput.value)[0] || "";
}

function renderSearchEmpty() {
  const empty = document.createElement("div");
  empty.className = "search-empty";

  const mark = document.createElement("span");
  mark.className = "search-empty-mark";
  mark.textContent = "字";

  const title = document.createElement("strong");
  title.textContent = "输入一个汉字";

  const copy = document.createElement("p");
  copy.textContent = "立即查看它在本机 JXP 行楷字体中的写法，也可定位到当前词表里的学习位置。";

  empty.append(mark, title, copy);
  elements.searchPreview.replaceChildren(empty);
}

function renderSearch() {
  const enteredCharacters = parseCharacters(elements.searchInput.value);

  if (enteredCharacters.length === 0) {
    renderSearchEmpty();
    return;
  }

  const character = enteredCharacters[0];
  const naturalIndex = state.chars.indexOf(character);
  const isInWordList = naturalIndex >= 0;
  const orderIndex = isInWordList ? state.order.indexOf(naturalIndex) : -1;
  const rating = state.ratings[character];

  const result = document.createElement("div");
  result.className = "search-result";

  const glyphWrap = document.createElement("div");
  glyphWrap.className = "search-glyph-wrap";

  const glyph = document.createElement("span");
  glyph.className = "search-glyph";
  glyph.textContent = character;
  glyph.setAttribute("aria-label", `荆霄鹏行楷：${character}`);

  const fontLabel = document.createElement("small");
  fontLabel.textContent = "JXP 行楷";
  glyphWrap.append(glyph, fontLabel);

  const info = document.createElement("div");
  info.className = "search-result-info";

  const status = document.createElement("span");
  status.className = `search-status${isInWordList ? "" : " is-absent"}`;
  status.textContent = isInWordList
    ? SEARCH_STATUS_LABELS[rating] || "尚未学习"
    : "不在当前词表";

  const title = document.createElement("h3");
  title.textContent = `「${character}」的行楷`;

  const description = document.createElement("p");
  description.textContent = isInWordList
    ? `当前词表第 ${(orderIndex >= 0 ? orderIndex : naturalIndex) + 1} 位，共 ${state.chars.length.toLocaleString("zh-CN")} 字。`
    : "当前词表中没有这个字，但可以预览本机字体中的对应字形。";

  info.append(status, title, description);

  if (isInWordList) {
    const locateButton = document.createElement("button");
    locateButton.className = "locate-button";
    locateButton.type = "button";
    locateButton.textContent = "定位并揭晓";
    locateButton.addEventListener("click", () => locateCharacter(character));
    info.append(locateButton);
  }

  result.append(glyphWrap, info);
  elements.searchPreview.replaceChildren(result);

  if (enteredCharacters.length > 1) {
    const chips = document.createElement("div");
    chips.className = "search-chips";

    for (const enteredCharacter of enteredCharacters) {
      const chip = document.createElement("button");
      chip.className = "search-chip";
      chip.type = "button";
      chip.textContent = enteredCharacter;
      chip.title = `查看「${enteredCharacter}」`;
      chip.addEventListener("click", () => {
        elements.searchInput.value = enteredCharacter;
        renderSearch();
        elements.searchInput.focus();
      });
      chips.append(chip);
    }

    elements.searchPreview.append(chips);
  }
}

function openSearch(initialCharacter = "") {
  if (initialCharacter) {
    elements.searchInput.value = initialCharacter;
  }

  if (elements.searchOverlay.hidden) {
    lastFocusedElement = document.activeElement;
    elements.searchOverlay.hidden = false;
    document.body.classList.add("modal-open");
    renderSearch();
  }

  window.requestAnimationFrame(() => {
    elements.searchInput.focus();
    elements.searchInput.select();
  });
}

function closeSearch() {
  if (elements.searchOverlay.hidden) {
    return;
  }

  elements.searchOverlay.hidden = true;
  document.body.classList.remove("modal-open");

  const focusTarget =
    lastFocusedElement instanceof HTMLElement && document.contains(lastFocusedElement)
      ? lastFocusedElement
      : elements.searchTrigger;
  focusTarget.focus();
}

function locateCharacter(character) {
  const naturalIndex = state.chars.indexOf(character);

  if (naturalIndex < 0) {
    showToast("这个字不在当前词表中");
    return;
  }

  let orderIndex = state.order.indexOf(naturalIndex);

  if (orderIndex < 0) {
    state.order = naturalOrder(state.chars.length);
    orderIndex = naturalIndex;
  }

  state.index = orderIndex;
  state.reveal = true;
  state.finished = false;
  persistState();
  closeSearch();
  render();
  showToast(`已定位到「${character}」`);

  window.requestAnimationFrame(() => {
    elements.practiceStage.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

function isTypingTarget(target) {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;
}

function bindEvents() {
  elements.revealButton.addEventListener("click", revealCharacter);
  elements.previousButton.addEventListener("click", () => navigate(-1));
  elements.nextButton.addEventListener("click", () => navigate(1));
  elements.orderToggle.addEventListener("click", toggleOrder);
  elements.resetButton.addEventListener("click", resetProgress);
  elements.searchTrigger.addEventListener("click", () => openSearch());
  elements.searchClose.addEventListener("click", closeSearch);
  elements.searchInput.addEventListener("input", renderSearch);
  elements.searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeSearch();
    } else if (event.key === "Enter") {
      event.preventDefault();
      const character = searchCharacterFromInput();

      if (character) {
        locateCharacter(character);
      }
    }
  });
  elements.searchOverlay.addEventListener("click", (event) => {
    if (event.target === elements.searchOverlay) {
      closeSearch();
    }
  });

  elements.importButton.addEventListener("click", () => elements.fileInput.click());
  elements.fileInput.addEventListener("change", (event) => {
    importFile(event.target.files?.[0]);
  });

  for (const button of document.querySelectorAll("[data-rating]")) {
    button.addEventListener("click", () => rateCurrent(button.dataset.rating));
  }

  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openSearch();
      return;
    }

    if (event.key === "Escape" && !elements.searchOverlay.hidden) {
      event.preventDefault();
      closeSearch();
      return;
    }

    if (isTypingTarget(event.target) || event.altKey || event.metaKey || event.ctrlKey) {
      return;
    }

    if (event.key === "/" && elements.searchOverlay.hidden) {
      event.preventDefault();
      openSearch();
      return;
    }

    if (!elements.searchOverlay.hidden) {
      return;
    }

    if ((event.code === "Space" || event.key === "Enter") && !state.reveal) {
      event.preventDefault();
      revealCharacter();
      return;
    }

    if (state.reveal && ["1", "2", "3"].includes(event.key)) {
      event.preventDefault();
      rateCurrent({ 1: "forgot", 2: "fuzzy", 3: "mastered" }[event.key]);
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      navigate(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      navigate(1);
    }
  });

  window.addEventListener("dragenter", (event) => {
    event.preventDefault();
    dragDepth += 1;
    elements.dropOverlay.hidden = false;
  });

  window.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = "copy";
    }
  });

  window.addEventListener("dragleave", (event) => {
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);

    if (dragDepth === 0) {
      elements.dropOverlay.hidden = true;
    }
  });

  window.addEventListener("drop", (event) => {
    event.preventDefault();
    dragDepth = 0;
    elements.dropOverlay.hidden = true;
    importFile(event.dataTransfer?.files?.[0]);
  });
}

async function init() {
  bindEvents();

  if (restoreState()) {
    render();
  } else {
    await loadDefaultSource();
  }
}

init();
