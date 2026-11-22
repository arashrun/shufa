import assert from "node:assert/strict";
import { test } from "node:test";
import { releaseAssetUrl, selectUpdate, validateRepository } from "../src/update-policy.js";

const asset = (name, size = 1024) => ({ name, size, browser_download_url: `https://github.com/me/app/releases/download/v1/${name}` });

test("仓库格式校验", () => {
  assert.equal(validateRepository("me/app"), true);
  assert.equal(validateRepository("me.app/app.name"), true);
  assert.equal(validateRepository("/app"), false);
  assert.equal(validateRepository("me/"), false);
  assert.equal(validateRepository("me app"), false);
  assert.equal(validateRepository(42), false);
});

test("选择更新：仅接受更高版本Code的非预览Release", () => {
  const release = {
    name: "v2",
    tag_name: "v2",
    draft: false,
    prerelease: false,
    assets: [asset("xingkai-recall-3.apk"), asset("xingkai-recall-3.apk.sha256")],
  };
  const update = selectUpdate(release, 2);
  assert.equal(update.versionCode, 3);
  assert.equal(update.url, "https://github.com/me/app/releases/download/v1/xingkai-recall-3.apk");

  assert.equal(selectUpdate(release, 3), null);
  assert.equal(selectUpdate({ ...release, draft: true }, 2), null);
  assert.equal(selectUpdate({ ...release, prerelease: true }, 2), null);
  assert.equal(selectUpdate({ ...release, assets: [asset("other.apk")] }, 2), null);
});

test("更新包缺少校验文件时拒绝", () => {
  const release = {
    tag_name: "v2",
    assets: [asset("xingkai-recall-3.apk")],
  };
  assert.throws(() => selectUpdate(release, 2), /SHA-256/);
});

test("更新地址必须来自配置仓库的HTTPS Release", () => {
  const repo = "me/app";
  assert.equal(
    releaseAssetUrl("https://github.com/me/app/releases/download/v1/x.apk", repo),
    "https://github.com/me/app/releases/download/v1/x.apk",
  );
  assert.throws(() => releaseAssetUrl("http://github.com/me/app/releases/download/v1/x.apk", repo), /GitHub/);
  assert.throws(() => releaseAssetUrl("https://evil.com/releases/download/v1/x.apk", repo), /GitHub/);
  assert.throws(() => releaseAssetUrl("https://github.com/me/other/releases/download/v1/x.apk", repo), /GitHub/);
  assert.throws(() => releaseAssetUrl("https://user@github.com/me/app/releases/download/v1/x.apk", repo), /GitHub/);
  assert.throws(() => releaseAssetUrl("https://github.com/me/app/releases/download/v1/x.apk?x=1", repo), /GitHub/);
  assert.throws(() => releaseAssetUrl("ftp://github.com/me/app/releases/download/v1/x.apk", repo), /GitHub/);
});
