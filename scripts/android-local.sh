#!/usr/bin/env bash
# 本地编译签名 Release APK（与 CI 相同的签名密钥，产物可互相覆盖安装）。
# 用法：npm run android:local
# 依赖：ANDROID_HOME 指向 Android SDK（默认 ~/android-sdk），
#       签名信息从 .signing/ci-secrets.txt 的 KEY=VALUE 行读取。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS="$ROOT/.signing/ci-secrets.txt"

if [[ ! -f "$SECRETS" ]]; then
  echo "缺少 $SECRETS（先运行 npm run android:keystore 生成）" >&2
  exit 1
fi
if [[ ! -f "$ROOT/.signing/release.jks" ]]; then
  echo "缺少 $ROOT/.signing/release.jks" >&2
  exit 1
fi

export ANDROID_HOME="${ANDROID_HOME:-$HOME/android-sdk}"
if [[ ! -d "$ANDROID_HOME" ]]; then
  echo "ANDROID_HOME 不存在：$ANDROID_HOME（请安装 Android SDK 或设置环境变量）" >&2
  exit 1
fi

# 只取 KEY=VALUE 行，忽略说明文字与 base64 块
while IFS='=' read -r key value; do
  case "$key" in
    ANDROID_KEYSTORE_PASSWORD) export ANDROID_KEYSTORE_PASSWORD="$value" ;;
    ANDROID_KEY_ALIAS)         export ANDROID_KEY_ALIAS="$value" ;;
    ANDROID_KEY_PASSWORD)      export ANDROID_KEY_PASSWORD="$value" ;;
  esac
done < <(grep '^ANDROID_[A-Z_]*=' "$SECRETS")

: "${ANDROID_KEYSTORE_PASSWORD:?ci-secrets.txt 缺少 ANDROID_KEYSTORE_PASSWORD}"
: "${ANDROID_KEY_ALIAS:?ci-secrets.txt 缺少 ANDROID_KEY_ALIAS}"
: "${ANDROID_KEY_PASSWORD:?ci-secrets.txt 缺少 ANDROID_KEY_PASSWORD}"
export ANDROID_KEYSTORE_PATH="$ROOT/.signing/release.jks"

cd "$ROOT/android"
./gradlew assembleRelease "$@"
echo
echo "APK 输出：$ROOT/android/app/build/outputs/apk/release/app-release.apk"
echo "注意：本地包 versionCode 固定为 1，正式发版请推代码走 CI。"
