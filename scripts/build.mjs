import { build } from "esbuild";
import { copyFile, cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { validateRepository } from "../src/update-policy.js";

const root = resolve(import.meta.dirname, "..");
const output = resolve(root, "dist");
const repository = process.env.UPDATE_REPOSITORY || process.env.GITHUB_REPOSITORY || "";
if (repository && !validateRepository(repository)) {
  throw new Error("UPDATE_REPOSITORY 必须为 owner/repository 格式");
}
await mkdir(output, { recursive: true });
for (const file of ["app.js", "styles.css", "level-1.txt"]) {
  await copyFile(resolve(root, file), resolve(output, file));
}

// ---- 工具页：每个工具一个子目录，拷贝自 tools/ 源目录（脚本生成产物放这里）----
const toolsSource = resolve(root, "tools");
const toolsOutput = resolve(output, "tools");
const tools = [];
await mkdir(toolsSource, { recursive: true });
for (const entry of await readdir(toolsSource, { withFileTypes: true })) {
  if (!entry.isDirectory()) continue;
  const manifestPath = resolve(toolsSource, entry.name, "tool.json");
  let manifest;
  try {
    manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  } catch {
    console.warn(`跳过工具目录 ${entry.name}（缺少或非法的 tool.json）`);
    continue;
  }
  // 工具页深度为 tools/<name>/，导航脚本用 data-root 指回站点根
  let html = await readFile(resolve(toolsSource, entry.name, manifest.entry), "utf8");
  html = html.replace(
    "</head>",
    '  <link rel="stylesheet" href="../../tools-nav.css" />\n  </head>',
  );
  html = html.replace(
    "</body>",
    '  <script src="../../tools-nav.js" data-root="../.."></script>\n  </body>',
  );
  await cp(resolve(toolsSource, entry.name), resolve(toolsOutput, entry.name), {
    recursive: true,
  });
  await writeFile(resolve(toolsOutput, entry.name, manifest.entry), html);
  tools.push({
    title: manifest.title,
    url: `tools/${entry.name}/${manifest.entry}`,
    desc: manifest.desc || "",
  });
}
// 工具注册表：导航抽屉的数据源
await writeFile(
  resolve(output, "tools.json"),
  JSON.stringify(
    [{ title: "行楷忆写", url: "index.html", desc: "先想字形，再看笔意" }, ...tools],
    null,
    2,
  ),
);
// 共享导航组件
await copyFile(resolve(root, "src/tools-nav.js"), resolve(output, "tools-nav.js"));
await copyFile(resolve(root, "src/tools-nav.css"), resolve(output, "tools-nav.css"));
// Only ship explicitly selected app resources, never the whole working tree.
const fonts = resolve(output, "fonts");
await mkdir(fonts, { recursive: true });
const fontSource = process.env.APP_FONT_PATH;
if (fontSource) {
  await copyFile(resolve(fontSource), resolve(fonts, "jxp.ttf"));
} else {
  const localFonts = await readdir(resolve(root, "assets/fonts"));
  if (localFonts.includes("jxp.ttf")) {
    await copyFile(resolve(root, "assets/fonts/jxp.ttf"), resolve(fonts, "jxp.ttf"));
  } else {
    // Remove a previous build's optional font without touching any source files.
    const { rm } = await import("node:fs/promises");
    await rm(resolve(fonts, "jxp.ttf"), { force: true });
  }
}
let html = await readFile(resolve(root, "index.html"), "utf8");
html = html.replace(
  "</head>",
  '  <link rel="stylesheet" href="tools-nav.css" />\n  </head>',
);
html = html.replace(
  "</body>",
  '  <script src="tools-nav.js" data-root="."></script>\n  <script src="mobile.js"></script>\n  </body>',
);
await writeFile(resolve(output, "index.html"), html);
await build({
  entryPoints: [resolve(root, "src/mobile.js")],
  outfile: resolve(output, "mobile.js"),
  bundle: true,
  format: "iife",
  target: ["chrome109"],
  define: { __UPDATE_REPOSITORY__: JSON.stringify(repository) },
});
console.log(`已构建离线资源；更新仓库：${repository || "未配置（可在应用内填写）"}`);
