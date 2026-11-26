#!/usr/bin/env python3
"""书家谱生成脚本。

输入：
- content/calligraphers/*.md  每位书家一个文件（# 名 / ## 简介 / ## 作品集）
  文件名数字前缀控制时代顺序。
- content/works/*.md          作品原文语料（# 标题 / ## 原文 / ## 译文），
  frontmatter 中 authors 列出书写者（逗号分隔）。

输出：
- tools/calligraphers/index.html     书家谱主页（目录按时代分组，作品名链接到作品页）
- tools/calligraphers/works/<id>.html 每篇作品一个页面（原文 + 译文）

原文渲染时逐字做简→繁转换，凡与简体不同的字在简体后括号内标注繁体。

依赖：pip install opencc-python-reimplemented（未安装时原文不标注繁体）
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CALLIGRAPHERS = ROOT / "content" / "calligraphers"
DEFAULT_WORKS = ROOT / "content" / "works"
DEFAULT_OUT = ROOT / "tools" / "calligraphers"

try:
    from opencc import OpenCC

    _s2t = OpenCC("s2t")
except ImportError:  # pragma: no cover
    _s2t = None

# 逐字转换会失去上下文的多音多义字：繁体对应不止一个（如 松→鬆/松、
# 咸→鹹/咸），标错反而误导，宁可不标注。
AMBIGUOUS = set("咸松云后里面谷斗几表制才岩游只台冲须准志征余干发复系")


def annotate_traditional(text: str) -> str:
    """简体正文中凡有不同繁体的字，在后面括号标注繁体。"""
    if _s2t is None:
        return html.escape(text)
    parts: list[str] = []
    for ch in text:
        if not re.match(r"[\u4e00-\u9fff]", ch) or ch in AMBIGUOUS:
            parts.append(html.escape(ch))
            continue
        traditional = _s2t.convert(ch)
        if traditional != ch and len(traditional) == 1:
            parts.append(f"{html.escape(ch)}<small>（{html.escape(traditional)}）</small>")
        else:
            parts.append(html.escape(ch))
    return "".join(parts)


# ---- markdown 解析 ----------------------------------------------------------

def parse_frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    """支持 `key: value` 行的简易 frontmatter，返回 (meta, 剩余行)。"""
    meta: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0].strip() == "---":
        end = next(
            (i for i in range(1, len(lines)) if lines[i].strip() == "---"), None
        )
        if end is not None:
            for line in lines[1:end]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    meta[key.strip()] = value.strip()
            return meta, lines[end + 1 :]
    return meta, lines


def parse_markdown(path: Path) -> dict:
    """解析 {name, sections}；sections 元素 {title, kind, items, paragraphs}。"""
    _meta, lines = parse_frontmatter(path)
    name = ""
    sections: list[dict] = []
    current: dict | None = None
    for raw in lines:
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
        elif current["kind"] == "list":
            if current["items"]:
                current["items"][-1] += line.strip()
        else:
            current["paragraphs"].append(line.strip())
    if not name:
        raise SystemExit(f"{path.name} 缺少一级标题（# 标题）")
    return {"name": name, "sections": sections}


# ---- 时代分组 ---------------------------------------------------------------

ERAS: list[tuple[str, range]] = [
    ("魏晋", range(1, 6)),
    ("隋", range(6, 7)),
    ("唐 · 五代", range(7, 16)),
    ("两宋", range(16, 21)),
    ("元", range(21, 25)),
    ("明", range(25, 32)),
    ("明清之际", range(32, 34)),
    ("清 · 近代", range(34, 40)),
]


def era_of(stem: str) -> str:
    try:
        prefix = int(stem.split("-", 1)[0])
    except ValueError:
        return "其他"
    for name, span in ERAS:
        if prefix in span:
            return name
    return "其他"


# ---- HTML 片段 --------------------------------------------------------------

def render_section(section: dict, annotate: bool) -> str:
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
        f"      <p>{annotate_traditional(p) if annotate else html.escape(p)}</p>"
        for p in section["paragraphs"]
    )
    return (
        f'    <section class="bio">\n'
        f"      <h3>{title}</h3>\n{paragraphs}\n    </section>"
    )


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# ---- 作品页 -----------------------------------------------------------------

def render_work_page(work: dict, work_id: str) -> str:
    title = html.escape(work["name"])
    sections = "\n".join(
        render_section(s, annotate=s["title"] == "原文") for s in work["sections"]
    )
    authors = html.escape("、".join(work.get("authors", [])))
    return PAGE_TEMPLATE.format(
        title=f"{work['name']} · 历代书家谱",
        header=f"<h1>{title}</h1>\n  <p>{authors}</p>",
        extra_css="",
        body=f'<main class="work">\n{sections}\n</main>\n<p class="back"><a href="../index.html">← 返回书家谱</a></p>',
    )


# ---- 主页 -------------------------------------------------------------------

def render_index(calligraphers: list[dict], works: dict[str, dict]) -> str:
    # 按时代分组
    grouped: dict[str, list[dict]] = {}
    for entry in calligraphers:
        grouped.setdefault(entry["era"], []).append(entry)
    era_order = [name for name, _ in ERAS] + [
        e for e in grouped if e not in {n for n, _ in ERAS}
    ]

    toc_parts: list[str] = []
    for era in era_order:
        entries = grouped.get(era)
        if not entries:
            continue
        links = "\n".join(
            f'      <li><a href="#{entry["anchor"]}">{html.escape(entry["name"])}</a></li>'
            for entry in entries
        )
        toc_parts.append(
            f'    <li><details class="era">\n'
            f'      <summary>{html.escape(era)}</summary>\n'
            f"      <ul>\n{links}\n      </ul>\n    </details></li>"
        )
    toc = "\n".join(toc_parts)

    articles: list[str] = []
    for entry in calligraphers:
        name = entry["name"]
        sections_html: list[str] = []
        for section in entry["sections"]:
            if section["kind"] == "list":
                # 作品集：标题能对应作品语料的加链接
                items = []
                for item in section["items"]:
                    match = re.match(r"^《([^》]+)》", item)
                    linked = item
                    if match:
                        book_title = match.group(1)
                        for work_id, work in works.items():
                            work_title = work["name"]
                            if name in work.get("authors", []) and (
                                book_title in work_title or work_title in book_title
                            ):
                                linked = (
                                    f'<a href="works/{work_id}.html">'
                                    f"《{html.escape(book_title)}》</a>"
                                    + item[match.end() :]
                                )
                                break
                    items.append(f"      <li>{linked}</li>")
                sections_html.append(
                    f'    <section class="bio">\n      <h3>{html.escape(section["title"])}</h3>\n'
                    f"      <ul>\n" + "\n".join(items) + "\n      </ul>\n    </section>"
                )
            else:
                sections_html.append(render_section(section, annotate=False))
        articles.append(
            f'  <article class="calligrapher" id="{entry["anchor"]}">\n'
            f'    <h2>{html.escape(name)}</h2>\n' + "\n".join(sections_html) + "\n  </article>"
        )
    return INDEX_TEMPLATE.format(
        title="历代书家谱",
        toc=toc,
        articles="\n".join(articles),
    )


# ---- 构建 -------------------------------------------------------------------

def build(calligraphers_dir: Path, works_dir: Path, out_dir: Path, page_title: str) -> None:
    works: dict[str, dict] = {}
    if works_dir.is_dir():
        for path in sorted(works_dir.glob("*.md")):
            work = parse_markdown(path)
            _meta, _ = parse_frontmatter(path)
            work["authors"] = [
                a.strip() for a in _meta.get("authors", "").split(",") if a.strip()
            ]
            works[path.stem] = work

    calligraphers = []
    for path in sorted(calligraphers_dir.glob("*.md")):
        entry = parse_markdown(path)
        calligraphers.append(
            {
                "name": entry["name"],
                "sections": entry["sections"],
                "anchor": "c-" + slugify(path.stem),
                "era": era_of(path.stem),
            }
        )
    if not calligraphers:
        raise SystemExit(f"目录 {calligraphers_dir} 下没有任何 markdown 文件")

    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.html"
    index_path.write_text(
        render_index(calligraphers, works), encoding="utf-8"
    )
    works_out = out_dir / "works"
    works_out.mkdir(exist_ok=True)
    for work_id, work in works.items():
        (works_out / f"{work_id}.html").write_text(
            render_work_page(work, work_id), encoding="utf-8"
        )
    print(
        f"已生成 {index_path}（{len(calligraphers)} 位书家，{len(works)} 篇作品页）"
    )


INDEX_TEMPLATE = """<!DOCTYPE html>
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
  padding: 6px 16px; max-height: 46vh; overflow-y: auto;
}}
nav.toc > ul {{ margin: 0; padding: 0; list-style: none; }}
nav.toc details.era > summary {{
  display: inline-block; cursor: pointer; color: var(--cinnabar);
  font-size: 14px; letter-spacing: 0.2em; list-style: none;
  padding: 2px 0; user-select: none;
}}
nav.toc details.era > summary::-webkit-details-marker {{ display: none; }}
nav.toc details.era > summary::after {{ content: " ▸"; font-size: 11px; }}
nav.toc details.era[open] > summary::after {{ content: " ▾"; }}
nav.toc details.era > ul {{
  display: flex; flex-wrap: wrap; gap: 2px 12px; margin: 2px 0 6px;
  padding: 0; list-style: none;
}}
nav.toc a {{ color: var(--ink); text-decoration: none; font-size: 14px; }}
nav.toc a:hover {{ color: var(--cinnabar); }}
main {{
  max-width: 720px; margin: 0 auto;
  padding: 0 clamp(20px, 6vw, 40px) calc(76px + env(safe-area-inset-bottom, 0));
}}
main.work {{
  max-width: 720px; margin: 0 auto;
  padding: 24px clamp(20px, 6vw, 40px) calc(76px + env(safe-area-inset-bottom, 0));
}}
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
section.bio a {{ color: var(--cinnabar); text-decoration: none; border-bottom: 1px dotted var(--cinnabar); }}
main.work section.bio p {{ font-size: 18px; }}
small {{ color: var(--muted); font-size: 0.62em; }}
p.back {{ text-align: center; }}
p.back a {{ color: var(--muted); text-decoration: none; }}
@media (max-width: 600px) {{
  header.page {{ padding: 18px 12px 8px; }}
  header.page h1 {{ font-size: 21px; letter-spacing: 0.25em; text-indent: 0.25em; }}
  nav.toc {{ padding: 4px 14px; max-height: 40vh; }}
  nav.toc details.era > summary {{ font-size: 13px; }}
  nav.toc a {{ font-size: 13px; }}
  article.calligrapher {{ padding: 20px 0 14px; }}
  article.calligrapher h2 {{ font-size: 20px; }}
}}
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
{articles}
</body>
</html>
"""

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
  padding: 24px 16px 12px; text-align: center;
  border-bottom: 3px double var(--line);
}}
header.page h1 {{
  margin: 0; font-size: 24px; letter-spacing: 0.3em; text-indent: 0.3em;
}}
header.page p {{ margin: 6px 0 0; color: var(--muted); font-size: 13px; }}
main.work {{
  max-width: 720px; margin: 0 auto;
  padding: 20px clamp(20px, 6vw, 40px) calc(76px + env(safe-area-inset-bottom, 0));
}}
main.work section.bio h3 {{
  margin: 18px 0 6px; font-size: 15px; color: var(--muted);
  letter-spacing: 0.3em; font-weight: 400;
}}
main.work section.bio p {{
  margin: 8px 0; font-size: 18px; text-align: justify;
}}
small {{ color: var(--muted); font-size: 0.62em; }}
p.back {{ text-align: center; padding-bottom: 8px; }}
p.back a {{ color: var(--muted); text-decoration: none; }}
@media (max-width: 600px) {{
  header.page {{ padding: 16px 12px 8px; }}
  header.page h1 {{ font-size: 20px; letter-spacing: 0.25em; text-indent: 0.25em; }}
  main.work section.bio p {{ font-size: 17px; }}
}}
{extra_css}
</style>
</head>
<body>
<header class="page">
{header}
</header>
{body}
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="书家 markdown + 作品语料 → 工具页 HTML（tools/calligraphers/）",
    )
    parser.add_argument("--calligraphers", default=str(DEFAULT_CALLIGRAPHERS))
    parser.add_argument("--works", default=str(DEFAULT_WORKS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--title", default="历代书家谱")
    args = parser.parse_args()
    build(Path(args.calligraphers), Path(args.works), Path(args.out), args.title)


if __name__ == "__main__":
    main()
