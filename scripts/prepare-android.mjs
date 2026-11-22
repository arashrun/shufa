#!/usr/bin/env node
/**
 * 构建应用内更新所需的版本配置。
 *
 * 必需环境变量：
 *   APP_VERSION_NAME   例如 1.2.0
 *   ANDROID_KEYSTORE_PATH / ANDROID_KEYSTORE_PASSWORD / ANDROID_KEY_ALIAS / ANDROID_KEY_PASSWORD
 * 可选环境变量：
 *   UPDATE_REPOSITORY  owner/repository，公开 Release 仓库；未设置时用户可在应用内填写
 */
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { validateRepository } from "../src/update-policy.js";

const root = resolve(import.meta.dirname, "..");
const env = process.env;

// 签名口令不在这里校验：release 构建时由 Gradle 的 validateSigningRelease 强制要求。
const repository = env.UPDATE_REPOSITORY || "";
if (repository && !validateRepository(repository)) {
  console.error("UPDATE_REPOSITORY 必须是 GitHub 公开 Release 仓库，格式 owner/repository");
  process.exit(1);
}

const version = env.APP_VERSION_NAME || null;
await mkdir(resolve(root, "android/app/src/main/assets"), { recursive: true });
await writeFile(
  resolve(root, "android/app/src/main/assets/capacitor.config.json"),
  JSON.stringify(
    {
      appId: "io.github.xingkai.recall",
      appName: "行楷忆写",
      webDir: "dist",
      android: { allowMixedContent: false, updateRepository: repository },
    },
    null,
    2,
  ),
);
try {
  await mkdir(resolve(root, "android/app/src/main/assets/public"), { recursive: true });
  await writeFile(
    resolve(root, "android/app/src/main/assets/public/version.json"),
    JSON.stringify({ version }, null, 2),
  );
} catch {
  // assets/public may not exist yet; cap sync will create it.
}
console.log("构建配置已生成；Release 仓库：" + (repository || "未设置，由用户在应用内填写"));
