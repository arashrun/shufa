#!/usr/bin/env python3
"""生成 Android 签名密钥库，并输出配置 GitHub Secrets 需要的内容。

密钥库写入 .signing/release.jks（已被 Git 忽略）。
"""

from __future__ import annotations

import argparse
import base64
import getpass
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYSTORE = ROOT / ".signing" / "release.jks"
ALIAS = "xingkai"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 Android 签名密钥库")
    parser.add_argument("--force", action="store_true", help="覆盖已有密钥库（旧安装包将无法直接升级）")
    args = parser.parse_args()

    if KEYSTORE.exists() and not args.force:
        print(f"已存在 {KEYSTORE}；使用 --force 覆盖。")
        return 1

    password = os.environ.get("ANDROID_KEYSTORE_PASSWORD") or getpass.getpass("设置密钥库口令: ")
    if not password:
        print("口令不能为空", file=sys.stderr)
        return 1

    KEYSTORE.parent.mkdir(parents=True, exist_ok=True)
    keytool = os.environ.get("KEYTOOL", "keytool")
    subprocess.run(
        [
            keytool, "-genkeypair",
            "-storetype", "PKCS12",
            "-keystore", str(KEYSTORE),
            "-alias", ALIAS,
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10950",
            "-storepass", password,
            "-keypass", password,
            "-dname", "CN=Xingkai Recall, OU=Personal, O=xingkai, C=CN",
        ],
        check=True,
    )

    encoded = base64.b64encode(KEYSTORE.read_bytes()).decode()
    secrets_path = ROOT / ".signing" / "ci-secrets.txt"
    secrets_path.write_text(
        "在 GitHub 仓库 Settings → Secrets and variables → Actions 配置以下 Secrets：\n\n"
        f"ANDROID_KEYSTORE_PASSWORD={password}\n"
        f"ANDROID_KEY_ALIAS={ALIAS}\n"
        f"ANDROID_KEY_PASSWORD={password}\n"
        "ANDROID_KEYSTORE_BASE64=（下面这一整行 Base64）\n\n"
        + encoded + "\n",
        encoding="utf-8",
    )
    print(f"密钥库已生成：{KEYSTORE}")
    print(f"Secrets 配置说明已写入：{secrets_path}（该目录已被 Git 忽略，请勿提交）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
