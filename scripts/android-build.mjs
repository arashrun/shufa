#!/usr/bin/env node
/** 本机构建 release APK（需要本机 JDK 21 + Android SDK）。 */
import { spawnSync } from "node:child_process";

const env = process.env;
for (const key of ["ANDROID_KEYSTORE_PATH", "ANDROID_KEYSTORE_PASSWORD", "ANDROID_KEY_ALIAS", "ANDROID_KEY_PASSWORD"]) {
  if (!env[key]) {
    console.error(`缺少环境变量 ${key}`);
    process.exit(1);
  }
}

const result = spawnSync("./gradlew", ["assembleRelease", "--no-daemon"], {
  cwd: new URL("../android/", import.meta.url).pathname,
  stdio: "inherit",
});
process.exit(result.status ?? 1);
