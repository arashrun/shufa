import { Capacitor, registerPlugin } from "@capacitor/core";
import { releaseAssetUrl, selectUpdate, validateRepository } from "./update-policy.js";

const Updater = registerPlugin("AppUpdater");
const native = Capacitor.getPlatform() === "android";
const repositoryKey = "xingkai-update-repository";
const autoKey = "xingkai-update-auto-download";
let busy = false;
let ready = false;

const panel = document.createElement("section");
panel.className = "device-settings";
panel.innerHTML = `
  <details>
    <summary>应用与离线设置</summary>
    <div class="device-settings-body">
      <p id="app-version">本地应用</p>
      <label>离线行楷字体 <input id="font-import" type="file" accept=".ttf,.otf,.woff,.woff2"></label>
      <p id="font-status" role="status">正在检查字体…</p>
      <div id="android-updates" hidden>
        <label>GitHub 更新仓库 <input id="update-repository" placeholder="owner/repository" autocomplete="off" spellcheck="false"></label>
        <p>填写公开的 Release 仓库；源码仓库可以另设为私有。</p>
        <label><input id="auto-download" type="checkbox">发现更新后自动下载（可能使用移动流量）</label>
        <div class="update-actions">
          <button class="button" id="check-update" type="button">检查更新</button>
          <button class="button" id="install-update" type="button" hidden>安装已下载更新</button>
        </div>
        <p id="update-status" role="status" aria-live="polite">启动时自动检查更新，离线时仍可学习。</p>
      </div>
    </div>
  </details>`;
document.querySelector(".app-shell").append(panel);
const find = (id) => panel.querySelector(`#${id}`);
const status = (text) => { find("update-status").textContent = text; };

function fontDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("xingkai-offline-assets", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("assets");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function fontStorage(value) {
  const db = await fontDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("assets", value === undefined ? "readonly" : "readwrite");
      const store = tx.objectStore("assets");
      const request = value === undefined ? store.get("font") : store.put(value, "font");
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}

async function activateFont(bytes) {
  const face = new FontFace("XingkaiOffline", bytes);
  await face.load();
  document.fonts.add(face);
  document.documentElement.style.setProperty("--jxp-font", '"XingkaiOffline", serif');
}

async function initFont() {
  try {
    const saved = await fontStorage();
    if (saved) {
      await activateFont(saved);
      find("font-status").textContent = "已加载导入的离线字体";
      return;
    }
    const response = await fetch("fonts/jxp.ttf");
    if (!response.ok) throw new Error("字体未打包");
    await activateFont(await response.arrayBuffer());
    find("font-status").textContent = "已加载安装包内的离线字体";
  } catch {
    find("font-status").textContent = "正在使用系统字体；若字形不正确，请导入 JXP 行楷字体。导入后可离线使用。";
  }
}

find("font-import").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 40 * 1024 * 1024) throw new Error("字体文件不能超过 40 MB");
    const bytes = await file.arrayBuffer();
    await activateFont(bytes);
    await fontStorage(bytes);
    find("font-status").textContent = `已保存离线字体：${file.name}`;
  } catch (error) {
    find("font-status").textContent = `字体导入失败：${error.message}`;
  } finally { event.target.value = ""; }
});

let installed = { versionCode: 0, versionName: "" };

function setRepositoryInput(value) {
  find("update-repository").value =
    value || localStorage.getItem(repositoryKey) || __UPDATE_REPOSITORY__ || "";
}

async function checkUpdate(manual = false) {
  if (busy) return;
  const repository = find("update-repository").value.trim();
  if (!validateRepository(repository)) {
    status(repository ? "仓库格式应为 owner/repository" : "请填写 GitHub 更新仓库后检查更新。");
    return;
  }
  busy = true;
  find("check-update").disabled = true;
  try {
    localStorage.setItem(repositoryKey, repository);
    status("正在检查更新…");
    const { release } = await Updater.fetchRelease({ repository });
    // release is a JSON string produced on the native side; validate before use.
    const parsed = JSON.parse(release);
    const update = selectUpdate(parsed, installed.versionCode);
    if (!update) { status("当前已是最新版本。"); return; }
    if (!find("auto-download").checked && !manual) {
      status(`发现新版本 ${update.name}，点击“检查更新”确认下载。`);
      return;
    }
    if (!find("auto-download").checked && !window.confirm(`发现 ${update.name}，下载更新包（约 ${Math.ceil(update.size / 1048576)} MB）？`)) {
      status("已取消下载，下次可再次检查更新。");
      return;
    }
    status(`正在下载 ${update.name}…`);
    await Updater.downloadUpdate({
      repository,
      url: releaseAssetUrl(update.url, repository),
      checksumUrl: releaseAssetUrl(update.checksumUrl, repository),
      versionCode: update.versionCode,
    });
    ready = true;
    find("install-update").hidden = false;
    status("更新已下载并通过校验，点击“安装已下载更新”继续。学习记录会保留。");
  } catch (error) {
    status(`更新未完成：${error.message || "请检查网络后重试"}。可继续离线学习。`);
  } finally {
    busy = false;
    find("check-update").disabled = false;
  }
}

async function initUpdater() {
  if (!native) return;
  find("android-updates").hidden = false;
  installed = await Updater.getInfo();
  find("app-version").textContent = `Android ${installed.versionName}（${installed.versionCode}）`;
  setRepositoryInput();
  find("auto-download").checked = localStorage.getItem(autoKey) === "true";
  find("auto-download").addEventListener("change", () => {
    localStorage.setItem(autoKey, String(find("auto-download").checked));
  });
  find("check-update").addEventListener("click", () => checkUpdate(true));
  find("install-update").addEventListener("click", () => installDownloadedUpdate());
  await Updater.addListener("downloadProgress", ({ percent }) => {
    if (busy) status(`正在下载更新：${percent}%`);
  });
  const pending = await Updater.getPendingUpdate();
  ready = pending.available;
  find("install-update").hidden = !ready;
  if (ready) status("已有下载并校验完成的更新，可点击安装。");
  else await checkUpdate();
}

async function installDownloadedUpdate() {
  if (!ready) return;
  try {
    const result = await Updater.installUpdate();
    status(result.permissionRequired
      ? "请允许此应用安装更新，返回后再次点击安装。"
      : "请在 Android 系统安装界面确认更新；取消后可再次点击安装。学习记录会保留。");
  } catch (error) {
    status(`无法安装：${error.message}`);
  }
}

initFont();
initUpdater().catch((error) => status(`更新功能初始化失败：${error.message}`));
