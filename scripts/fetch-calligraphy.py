#!/usr/bin/env python3
"""从 wikichina 书法字典批量下载指定汉字的楷书集字图。

数据源：https://tool.wikichina.com/shufa/index.asp?zhi=<GBK编码汉字>
返回两类资源：
  1. images/sl/...jpg  — 历代书法矢量字的 JPG 预览（附 WMF 矢量原图）
  2. dict/...gif       — 毛笔字典扫描图（含书体与作者信息）

楷书筛选：按条目"作者"字段匹配楷书大家名单（歐陽詢/顏真卿/柳公權…），
因为该站不提供书体筛选参数，sl 图混合各书体。

用法：
  # 从词表文件批量下载（默认只下载 JPG 预览图，流量小）
  python3 scripts/fetch-calligraphy.py --file level-1.txt --out data/calligraphy

  # 同时下载 WMF 矢量原图（体积更大，可离线转高清 PNG）
  python3 scripts/fetch-calligraphy.py --file level-1.txt --out data/calligraphy --wmf

  # 限定书家（默认全部楷书大家）
  python3 scripts/fetch-calligraphy.py --file level-1.txt --authors 歐陽詢,顏真卿

限速：默认每次请求间隔 1.5 秒 + 随机抖动；服务端实测无频率限制，
但作为礼貌爬虫仍保持低速。支持断点续传（已存在的文件跳过）。
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://tool.wikichina.com/shufa/"
INDEX_URL = BASE + "index.asp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Referer": INDEX_URL,
}

# 楷书大家名单（站内使用繁体）
DEFAULT_MASTERS = [
    "歐陽詢", "歐陽通",  # 欧体父子
    "顏真卿",            # 颜体
    "柳公權",            # 柳体
    "趙子昂", "趙孟頫",   # 赵体
    "褚遂良", "虞世南", "智永", "鍾紹京", "王羲之",
]


def fetch(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def query_character(character: str) -> str:
    """查询单字，返回解码后的 HTML。参数用 GBK 编码（服务端是老 ASP）。"""
    encoded = urllib.parse.quote(character.encode("gbk"))
    raw = fetch(f"{INDEX_URL}?zhi={encoded}")
    return raw.decode("gbk", errors="replace")


def parse_entries(html: str) -> list[dict]:
    """解析查询结果，返回矢量字条目 [{image, wmf, author, dynasty, source}]。"""
    entries: list[dict] = []
    # 条目结构：<a href="down.asp?url=images/sl\7\7-83.WMF&zhi=山"><img src=images/sl\7\7-83.jpg title=...>
    pattern = re.compile(
        r'href="?down\.asp\?url=(?P<wmf>[^"&> ]+)'
        r'[^>]*>\s*<img src=?"?(?P<image>images/sl[^" >]+\.jpg)"?'
        r'[^>]*title=[^>]*>.*?作者：(?P<author>[^<\s]*)',
        re.S,
    )
    for match in pattern.finditer(html):
        entries.append({
            "image": match.group("image").replace("\\", "/"),
            "wmf": match.group("wmf").replace("\\", "/"),
            "author": match.group("author").strip(),
        })
    return entries


def filter_masters(entries: list[dict], masters: list[str]) -> list[dict]:
    return [e for e in entries if e["author"] in masters]


def download(url: str, target: Path, delay: float, jitter: float) -> bool:
    if target.exists() and target.stat().st_size > 0:
        return False  # 断点续传：跳过已下载
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = fetch(url)
    except Exception as error:
        print(f"    下载失败 {url}: {error}", file=sys.stderr)
        return False
    target.write_bytes(data)
    time.sleep(delay + random.uniform(0, jitter))
    return True


def convert_wmf(wmf_path: Path, png_path: Path, size: int = 512) -> bool:
    """用 libwmf 的 wmf2gd 把 WMF 矢量渲染成 PNG（--maxpect 保持比例放大）。"""
    if png_path.exists() and png_path.stat().st_size > 0:
        return False
    import subprocess
    result = subprocess.run(
        ["wmf2gd", f"--maxwidth={size}", f"--maxheight={size}", "--maxpect",
         "-t", "png", "-o", str(png_path), str(wmf_path)],
        capture_output=True,
    )
    if result.returncode != 0 or not png_path.exists():
        print(f"    WMF 转换失败: {wmf_path.name}", file=sys.stderr)
        return False
    return True


def fetch_character(
    character: str,
    out_dir: Path,
    masters: list[str],
    delay: float,
    jitter: float,
    with_wmf: bool,
    png_size: int = 0,
) -> dict:
    """下载单字的全部楷书集字图，返回统计。"""
    character_dir = out_dir / character
    html = query_character(character)
    entries = filter_masters(parse_entries(html), masters)

    stats = {"character": character, "downloaded": 0, "skipped": 0, "total": len(entries)}
    for index, entry in enumerate(entries):
        author = entry["author"]
        image_path = character_dir / f"{author}-{index}.jpg"
        url = BASE + entry["image"]
        if download(url, image_path, delay, jitter):
            stats["downloaded"] += 1
        else:
            stats["skipped"] += 1
        if with_wmf:
            wmf_path = character_dir / f"{author}-{index}.wmf"
            wmf_url = BASE + entry["wmf"]
            if download(wmf_url, wmf_path, delay, jitter):
                stats["downloaded"] += 1
            else:
                stats["skipped"] += 1
            if png_size and wmf_path.exists():
                if convert_wmf(wmf_path, wmf_path.with_suffix(".png"), png_size):
                    stats["converted"] = stats.get("converted", 0) + 1
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="批量下载 wikichina 楷书集字图")
    parser.add_argument("characters", nargs="*", help="要下载的汉字")
    parser.add_argument("--file", help="从文本文件读取汉字（去重）")
    parser.add_argument("--out", default="data/calligraphy", help="输出目录")
    parser.add_argument("--authors", help="限定书家（逗号分隔，默认全部楷书大家）")
    parser.add_argument("--wmf", action="store_true", help="同时下载 WMF 矢量原图")
    parser.add_argument(
        "--convert", action="store_true",
        help="下载 WMF 后自动用 wmf2gd 转成 PNG（需已安装 libwmf-bin，隐含 --wmf）",
    )
    parser.add_argument("--png-size", type=int, default=512, help="PNG 渲染尺寸（默认 512）")
    parser.add_argument("--delay", type=float, default=1.5, help="请求间隔秒数（默认 1.5）")
    parser.add_argument("--jitter", type=float, default=1.0, help="随机抖动秒数（默认 1.0）")
    parser.add_argument("--limit", type=int, help="最多处理多少个字（调试用）")
    args = parser.parse_args()

    if args.characters:
        characters = [c for c in "".join(args.characters) if "\u4e00" <= c <= "\u9fff"]
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8")
        characters = sorted({c for c in text if "\u4e00" <= c <= "\u9fff"})
    else:
        parser.error("请提供汉字或 --file 词表")

    if args.limit:
        characters = characters[: args.limit]

    masters = (
        [a.strip() for a in args.authors.split(",")]
        if args.authors else DEFAULT_MASTERS
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"准备下载 {len(characters)} 个字 · 书家 {len(masters)} 位 · 输出 {out_dir}")
    manifest_path = out_dir / "manifest.json"
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    with_wmf = args.wmf or args.convert
    for index, character in enumerate(characters, 1):
        stats = fetch_character(
            character, out_dir, masters, args.delay, args.jitter, with_wmf,
            args.png_size if args.convert else 0,
        )
        manifest[character] = stats
        print(f"[{index}/{len(characters)}] {character}: "
              f"找到 {stats['total']} 张 · 新下载 {stats['downloaded']} · 已有 {stats['skipped']}")
        if index % 20 == 0:
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
            )

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"完成。清单已写入 {manifest_path}")


if __name__ == "__main__":
    main()
