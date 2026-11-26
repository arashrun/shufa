#!/usr/bin/env python3
"""将 content/calligraphers/*.md 生成书家谱工具页 tools/calligraphers/index.html。

每个 markdown 文件一位书家，结构固定为：
    # 书家名
    ## 简介
    段落…
    ## 作品集
    - 《作品》：说明

按文件名排序（文件名用拼音/年代前缀保证时间顺序），单页输出，页首为目录导航。
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "content" / "calligraphers"
DEFAULT_OUT = ROOT / "tools" / "calligraphers" / "index.html"


def parse_markdown(path: Path) -> dict:
    """解析单个书家 md，返回 {name, sections: [{title, kind, items|paragraphs}]}。"""
    name = ""
    sections: list[dict] = []
    current: dict | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("# ") and not line.startswith("## "):
            name = line[2:].strip()
            continue
        if line.startswith("## "):
            title = line[3:].strip()
            kind = "list" if "作品" in title else "paragraphs"
            current = {"title": title, "kind": kind, "items": [], "paragraphs": []}
            sections.append(current)
            continue
        if current is None:
            current = {"title": "简介", "kind": "paragraphs", "items": [], "paragraphs": []}
            sections.append(current)
        if line.lstrip().startswith("- "):
            current["items"].append(line.lstrip()[2:].strip())
        else:
            if current["kind"] == "list":
                # 列表段落后的续行并入上一条
                if current["items"]:
                    current["items"][-1] += line.strip()
            else:
                current["paragraphs"].append(line.strip())
    if not name:
        raise SystemExit(f"{path.name} 缺少一级标题（# 书家名）")
    return {"name": name, "sections": sections}


def render_section(section: dict) -> str:
    title = html.escape(section["title"])
    if section["kind"] == "list":
        items = "\n".join(
            f"      <li>{html.escape(item)}</li>" for item in section["items"]
        )
        return (
            f'    <section class="bio">\n'
            f"      <h3>{title}</h3>\n      <ul>\n{items}\n      </ul>\n    </section>"
        )
    paragraphs = "\n".join(
        f"      <p>{html.escape(p)}</p>" for p in section["paragraphs"]
    )
    return (
        f'    <section class="bio">\n'
        f"      <h3>{title}</h3>\n{paragraphs}\n    </section>"
    )


def render_calligrapher(entry: dict, anchor: str) -> str:
    name = html.escape(entry["name"])
    sections = "\n".join(render_section(s) for s in entry["sections"])
    return f'  <article class="calligrapher" id="{anchor}">\n    <h2>{name}</h2>\n{sections}\n  </article>'


def era_sort_key(path: Path) -> str:
    """按文件名排序；前缀数字（如 01-wangxizhi.md）可控制时间顺序。"""
    return path.name


def build(source: Path, out: Path, title: str) -> None:
    files = sorted(source.glob("*.md"), key=era_sort_key)
    if not files:
        raise SystemExit(f"目录 {source} 下没有任何 markdown 文件")
    entries = []
    for path in files:
        entry = parse_markdown(path)
        anchor = "c-" + re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
        entries.append((entry, anchor))

    toc_items = "\n".join(
        f'      <li><a href="#{anchor}">{html.escape(entry["name"])}</a></li>'
        for entry, anchor in entries
    )
    articles = "\n".join(render_calligrapher(entry, anchor) for entry, anchor in entries)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        PAGE_TEMPLATE.format(title=html.escape(title), toc=toc_items, articles=articles),
        encoding="utf-8",
    )
    print(f"已生成 {out}（{len(entries)} 位书家）")


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --ink: #2b2620;
  --paper: #f7f2e8;
  --cinnabar: #a83232;
  --muted: #7a7062;
  --line: #ddd3c0;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--paper); color: var(--ink);
  font: 16px/1.9 "Songti SC", "Noto Serif SC", "SimSun", serif;
}}
header.page {{
  padding: 28px 16px 12px; text-align: center;
  border-bottom: 3px double var(--line);
}}
header.page h1 {{
  margin: 0; font-size: 26px; letter-spacing: 0.35em; text-indent: 0.35em;
  font-weight: 700;
}}
header.page p {{ margin: 6px 0 0; color: var(--muted); font-size: 13px; }}
nav.toc {{
  position: sticky; top: 0; z-index: 5;
  background: rgba(247, 242, 232, 0.96); border-bottom: 1px solid var(--line);
  padding: 8px 12px;
}}
nav.toc ul {{
  margin: 0; padding: 0; list-style: none;
  display: flex; flex-wrap: wrap; gap: 4px 14px;
}}
nav.toc a {{ color: var(--ink); text-decoration: none; font-size: 14px; }}
nav.toc a:hover {{ color: var(--cinnabar); }}
main {{ max-width: 720px; margin: 0 auto; padding: 0 16px 64px; }}
article.calligrapher {{ border-bottom: 1px solid var(--line); padding: 28px 0 20px; }}
article.calligrapher h2 {{
  margin: 0 0 4px; font-size: 24px; letter-spacing: 0.25em; color: var(--cinnabar);
}}
article.calligrapher h2::before {{ content: "「"; color: var(--muted); }}
article.calligrapher h2::after {{ content: "」"; color: var(--muted); }}
section.bio h3 {{
  margin: 20px 0 6px; font-size: 15px; color: var(--muted);
  letter-spacing: 0.3em; font-weight: 400;
}}
section.bio p {{ margin: 8px 0; text-align: justify; }}
section.bio ul {{ margin: 8px 0; padding-left: 0; list-style: none; }}
section.bio li {{
  margin: 10px 0; padding-left: 1.2em; text-indent: -1.2em; text-align: justify;
}}
section.bio li::before {{ content: "◦ "; color: var(--cinnabar); }}
@media (prefers-reduced-motion: no-preference) {{
  html {{ scroll-behavior: smooth; }}
}}
</style>
</head>
<body>
<header class="page">
  <h1>历代书家谱</h1>
  <p>楷书 · 行书 · 按时代为序</p>
</header>
<nav class="toc">
  <ul>
{toc}
  </ul>
</nav>
<main>
{articles}
</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="书家 markdown → 工具页 HTML（tools/calligraphers/）",
    )
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="markdown 目录")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出 HTML 路径")
    parser.add_argument("--title", default="历代书家谱", help="页面标题")
    args = parser.parse_args()
    build(Path(args.source), Path(args.out), args.title)


if __name__ == "__main__":
    main()
