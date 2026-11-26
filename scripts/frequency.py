#!/usr/bin/env python3
"""把字频表生成为按频序排列的汉字网格工具页。

每个汉字可点击，弹窗用本机书家字体实时渲染行楷/楷书大字
（复用 structure.py 的弹窗与字体资源逻辑，书家在 structure.CALLIGRAPHERS 配置）。

用法：
  .venv/bin/python scripts/frequency.py --file 2亿语料字频.txt \
      --html tools/frequency/index.html
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import structure  # noqa: E402  复用弹窗模板与资源准备逻辑
import search_widget  # noqa: E402  共享搜索定位组件

# 字频表弹窗书家配置（独立于 structure.py 的 CALLIGRAPHERS，按需增删）：
#   name    = 弹窗显示名
#   slug    = 资源目录名（fonts/ 下）
#   family  = 本机字体族名（fc-match 解析），留空 family 则跳过该字体
#   aliases = wikichina 集字图作者名（繁体），匹配 data/calligraphy/<字>/ 下的图
CALLIGRAPHERS = [
    {"name": "行楷", "slug": "xingkai", "family": "绿木屐JXP行楷", "aliases": []},
    # {"name": "欧体", "slug": "outi", "family": "欧阳询书法字体", "aliases": ["歐陽詢"]},
    # {"name": "规范楷体", "slug": "kaiti", "family": "方正楷体简体", "aliases": []},
]

GRID_COLUMNS = 20  # 每行字数（CSS 网格会自适应，仅用于占位提示）

PAGE_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>字频总表 — {total} 字</title>
  <style>
    :root {{
      --ink: #20201d; --ink-muted: #89877d;
      --paper: #fbf8f0; --paper-deep: #f3ecdf; --canvas: #f0eadf;
      --line: #dfd6c7; --cinnabar: #b64a37;
      --ui-font: "Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei",
        "PingFang SC", sans-serif;
      --serif-font: "Noto Serif CJK SC", "Source Han Serif SC", "SimSun", serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 26px 0 80px;
      background: var(--paper); color: var(--ink);
      font-family: var(--ui-font);
    }}
    .page {{ width: min(1180px, calc(100% - 36px)); margin: 0 auto; }}
    header.page-head h1 {{
      margin: 0; font-family: var(--serif-font);
      font-size: 24px; letter-spacing: 0.1em;
    }}
    header.page-head .meta {{
      color: var(--ink-muted); font-size: 12px; letter-spacing: 0.12em;
    }}
    .freq-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(52px, 1fr));
      gap: 7px; margin-top: 22px;
    }}
    span.freq {{
      position: relative;
      display: grid; place-items: center;
      aspect-ratio: 1;
      border: 1px solid var(--line); border-radius: 9px;
      background: #fffdf7;
      font-family: var(--serif-font); font-size: 24px;
      user-select: none;
    }}
    span.freq small {{
      position: absolute; top: 2px; right: 4px;
      color: var(--ink-muted); font-size: 8px;
      font-family: var(--ui-font); line-height: 1;
    }}
    span.glyph-clickable {{ cursor: pointer; }}
    span.glyph-clickable:hover {{
      border-color: var(--cinnabar); color: var(--cinnabar);
    }}
{modal_css}
{search_css}
  </style>
</head>
<body>
  <div class="page">
    <header class="page-head">
      <h1>字频总表</h1>
      <span class="meta">{meta}</span>
{search_html}
    </header>
    <div class="freq-grid">
{grid}
    </div>
  </div>
{modal}
{search_js}
</body>
</html>
"""

# 弹窗 CSS（从 structure.py 的 HTML_TEMPLATE 中截取 .glyph-modal 起的样式段）
MODAL_CSS_ANCHOR_START = "    .glyph-modal {"
MODAL_CSS_ANCHOR_END = "  </style>"


def extract_modal_css() -> str:
    """从 structure.py 的 HTML_TEMPLATE 源码中提取弹窗样式段，避免两处维护。

    源码里是 format 模板（花括号写成双写），插入本页模板前需还原为单花括号。
    """
    source = (ROOT / "scripts" / "structure.py").read_text(encoding="utf-8")
    start = source.index(MODAL_CSS_ANCHOR_START)
    end = source.index(MODAL_CSS_ANCHOR_END, start)
    return source[start:end].replace("{{", "{").replace("}}", "}")


def read_frequency(path: Path) -> list[str]:
    """按文件顺序读取去重后的汉字（文件顺序即字频序）。"""
    seen: set[str] = set()
    characters: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        for char in line:
            if not structure.is_hanzi(char) or char in seen:
                continue
            seen.add(char)
            characters.append(char)
    return characters


def render_grid(characters: list[str]) -> str:
    cells = []
    for rank, char in enumerate(characters, 1):
        cells.append(
            f'      <span class="freq glyph" data-char="{html.escape(char)}" '
            f'data-ids="频序 第{rank} 位">{html.escape(char)}<small>{rank}</small></span>'
        )
    return "\n".join(cells)


def render_page(characters: list[str], calligraphers: list[dict]) -> str:
    total = len(characters)
    font_faces = "\n".join(
        f"@font-face {{ font-family: 'gx-{html.escape(c['slug'], quote=True)}';"
        f" src: url('{html.escape(c['font'])}'); }}"
        for c in calligraphers if c.get("font")
    )
    modal = ""
    if calligraphers:
        modal = structure.MODAL_TEMPLATE.format(
            font_faces=font_faces,
            calligraphers_json=json.dumps(
                [{
                    "name": c["name"],
                    "slug": c["slug"],
                    "font": c.get("font"),
                    "covered": c.get("covered") or [],
                    "images": c.get("images") or {},
                } for c in calligraphers],
                ensure_ascii=False,
            ),
        )
    return PAGE_TEMPLATE.format(
        total=total,
        meta=f"共 {total} 字 · 顺序为语料字频序 · 点击查看集字",
        grid=render_grid(characters),
        modal_css=extract_modal_css(),
        modal=modal,
        search_css=search_widget.SEARCH_CSS,
        search_html=search_widget.SEARCH_HTML,
        search_js=search_widget.SEARCH_JS,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="字频表 → 频序网格工具页")
    parser.add_argument(
        "--file", action="append", dest="files", metavar="FILE",
        help="字频文件（每行一个字或普通文本，首次出现顺序即频序），可重复",
    )
    parser.add_argument(
        "--html", default="tools/frequency/index.html", help="输出 HTML 路径",
    )
    parser.add_argument("--ids-dir", default=str(structure.IDS_DIR))
    parser.add_argument(
        "--calligrapher", action="append", dest="calligraphers", metavar="NAME",
        help="只启用指定书家（按 name 匹配，可重复）；默认用脚本内 CALLIGRAPHERS 全部",
    )
    args = parser.parse_args()

    if not args.files:
        parser.error("请用 --file 指定字频文件")

    characters: list[str] = []
    seen: set[str] = set()
    for name in args.files:
        for char in read_frequency(Path(name)):
            if char not in seen:
                seen.add(char)
                characters.append(char)
    if not characters:
        raise SystemExit("字频文件中没有发现汉字")

    html_path = Path(args.html)
    html_dir = html_path.resolve().parent
    calligraphers = CALLIGRAPHERS
    if args.calligraphers:
        wanted = set(args.calligraphers)
        calligraphers = [c for c in CALLIGRAPHERS if c["name"] in wanted]
        missing = wanted - {c["name"] for c in calligraphers}
        if missing:
            raise SystemExit(f"未找到书家：{'、'.join(sorted(missing))}（可选：{'、'.join(c['name'] for c in CALLIGRAPHERS)}）")
    calligraphers = structure.prepare_calligrapher_resources(
        characters, html_dir, calligraphers=calligraphers,
        calligraphy_dir=ROOT / "data" / "calligraphy",
    )
    html_path.write_text(render_page(characters, calligraphers), encoding="utf-8")
    print(f"已写出 {html_path}（{len(characters)} 字，频序）")


if __name__ == "__main__":
    main()
