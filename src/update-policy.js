export function validateRepository(value) {
  return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9.-]*\/[A-Za-z0-9_.-]+$/.test(value);
}

export function selectUpdate(release, currentCode) {
  if (!release || release.draft || release.prerelease || !Array.isArray(release.assets)) return null;
  const apk = release.assets.find((asset) => /^xingkai-recall-(\d+)\.apk$/.test(asset.name));
  if (!apk) return null;
  const versionCode = Number(apk.name.match(/-(\d+)\.apk$/)[1]);
  if (!Number.isSafeInteger(versionCode) || versionCode <= currentCode || versionCode > 2100000000) return null;
  const checksum = release.assets.find((asset) => asset.name === `${apk.name}.sha256`);
  if (!checksum) throw new Error("新版本缺少 SHA-256 校验文件");
  return {
    versionCode,
    name: release.name || release.tag_name,
    url: apk.browser_download_url,
    checksumUrl: checksum.browser_download_url,
    size: apk.size,
  };
}

export function releaseAssetUrl(value, repository) {
  let url;
  try { url = new URL(value); } catch { throw new Error("无效的更新地址"); }
  if (url.protocol !== "https:" || url.hostname !== "github.com" || url.username || url.password ||
      url.search || url.hash ||
      !url.pathname.startsWith(`/${repository}/releases/download/`) ||
      decodeURIComponent(url.pathname).includes("..") ||
      !/\.apk(\.sha256)?$/.test(url.pathname)) {
    throw new Error("更新资源必须来自所配置 GitHub 仓库的 HTTPS Release");
  }
  return url.href;
}
