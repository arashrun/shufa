import { build } from "esbuild";
import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
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
html = html.replace("</body>", '  <script src="mobile.js"></script>\n  </body>');
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
