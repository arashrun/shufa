import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { execFileSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const dist = resolve(root, "dist");

test("tools.json 注册表包含首页与工具", async () => {
  const registry = JSON.parse(await readFile(resolve(dist, "tools.json"), "utf8"));
  assert.equal(registry[0].title, "行楷忆写");
  assert.ok(registry.some((tool) => tool.url.startsWith("tools/")));
});

test("工具页注入了导航与弹窗资源", async () => {
  const html = await readFile(resolve(dist, "tools/structure/index.html"), "utf8");
  assert.match(html, /tools-nav\.css/);
  assert.match(html, /tools-nav\.js.*data-root="\.\.\/\.\."/);
  assert.match(html, /glyph-modal/);
  assert.match(html, /@font-face/);
  assert.match(html, /fonts\/outi\.ttf/);
});

test("首页注入了导航并保留更新脚本", async () => {
  const html = await readFile(resolve(dist, "index.html"), "utf8");
  assert.match(html, /tools-nav\.js.*data-root="\."/);
  assert.match(html, /mobile\.js/);
});

test("共享导航组件已拷贝", async () => {
  await readFile(resolve(dist, "tools-nav.js"));
  await readFile(resolve(dist, "tools-nav.css"));
});

test("build.mjs 拷贝产物与源一致（工具目录完整性）", () => {
  const files = execFileSync("find", [resolve(dist, "tools/structure"), "-type", "f"], {
    encoding: "utf8",
  }).trim().split("\n");
  assert.ok(files.some((f) => f.endsWith("tool.json")));
  assert.ok(files.some((f) => f.endsWith(".ttf")));
});
