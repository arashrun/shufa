#!/usr/bin/env python3
"""基于 IDS（表意文字描述序列）的汉字字形结构分析与 HTML 网格页生成。

用法：
  # 单字分析
  python3 scripts/structure.py 明

  # 从文本文件批处理，输出 JSON 存储结构
  python3 scripts/structure.py --file level-1.txt --json structure.json

  # 生成 HTML 网格页（列 = 结构类别，行内按文本出现顺序，表头 = 文件名）
  python3 scripts/structure.py --file level-1.txt --html structure.html

  # 多个输入文件：HTML 中每个文件一个独立表格块，页首有文件索引
  python3 scripts/structure.py --file a.txt --file b.txt --html tables.html --json tables.json

数据来源：CHISE IDS 数据文件（放在 data/ids/ 下，UTF-8 文本）。
数据文件行格式：U+660E<TAB>明<TAB>⿰日月
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import unicodedata
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IDS_DIR = ROOT / "data" / "ids"

# IDS 操作符 → 结构类别（HTML 网格的列名）。
OPERATORS = {
    "⿰": "左右结构",
    "⿱": "上下结构",
    "⿲": "左中右结构",
    "⿳": "上中下结构",
    "⿴": "全包围结构",
    "⿵": "上三包围",
    "⿶": "下三包围",
    "⿷": "左三包围",
    "⿸": "左上包围",
    "⿹": "右上包围",
    "⿺": "左下包围",
    "⿻": "重叠结构",
}

# 练字场景中习惯视作"独体"的常见字（IDS 数据可能给出拆分，这里按教学习惯归类）。
SINGLE_OVERRIDES = {
    "山", "日", "月", "水", "火", "木", "金", "土", "人", "口", "手", "心",
    "女", "子", "王", "田", "石", "禾", "目", "耳", "足", "言", "雨", "气",
    "马", "鸟", "鱼", "虫", "竹", "米", "丝", "衣", "角", "贝", "车", "门",
}

COLUMN_ORDER = [
    "左右结构", "上下结构", "左中右结构", "上中下结构",
    "全包围结构", "上三包围", "下三包围", "左三包围",
    "左上包围", "右上包围", "左下包围", "重叠结构",
    "独体字", "未知",
]

# 集字书家配置：
#   name    = 显示名
#   slug    = 资源目录名（fonts/ 与 glyph-images/ 下）
#   family  = 本机字体族名（fc-match 解析），弹窗用 Canvas 实时渲染大字
#   aliases = wikichina 书法字典的作者名（繁体），匹配 data/calligraphy/<字>/ 下的集字图
# 两种来源可同时配置，弹窗内并列展示（字体渲染 + 帖拓集字）。
CALLIGRAPHERS = [
    {"name": "欧体", "slug": "outi", "family": "欧阳询书法字体", "aliases": ["歐陽詢"]},
    {"name": "规范楷体", "slug": "kaiti", "family": "方正楷体简体", "aliases": []},
]

# 弹窗图片渲染参数
GLYPH_IMAGE_SIZE = 360      # 画布边长（像素）
GLYPH_IMAGE_FONT_SIZE = 288  # 字号
GLYPH_INK = (28, 27, 24, 255)  # 与应用主字色一致


def load_ids_data(directory: Path) -> dict[str, str]:
    """读取全部 IDS 文件，返回 {汉字: IDS 描述}。后读文件覆盖同字（按文件名顺序稳定）。"""
    mapping: dict[str, str] = {}
    if not directory.exists():
        raise SystemExit(
            f"找不到 IDS 数据目录 {directory}。\n"
            "请先下载数据，例如：\n"
            "  curl -L -o data/ids/IDS-UCS-Basic.txt \\\n"
            "    https://raw.githubusercontent.com/chise/ids/main/IDS-UCS-Basic.txt"
        )
    for path in sorted(directory.glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith(";"):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            field, character = parts[0], parts[1]
            if not field.startswith("U+") or not character:
                continue
            try:
                codepoint = int(field[2:], 16)
            except ValueError:
                continue
            descriptions = [d.strip() for d in parts[2:] if d.strip()]
            if descriptions and chr(codepoint) == character:
                mapping[character] = descriptions[0]
    return mapping


def is_hanzi(character: str) -> bool:
    if not character or not unicodedata.category(character).startswith("Lo"):
        return False
    name = unicodedata.name(character, "")
    return "CJK" in name or "IDEOGRAPH" in name


def is_hanzi_in(text: str) -> bool:
    return any(is_hanzi(char) for char in text)


# ---- 集字图片渲染 ----

def resolve_font_file(family: str) -> Path | None:
    """通过 fontconfig 把字体族名解析为本机字体文件路径。"""
    import shutil
    import subprocess

    fc_match = shutil.which("fc-match")
    if not fc_match:
        return None
    try:
        result = subprocess.run(
            [fc_match, "-f", "%{file}", family],
            capture_output=True, text=True, timeout=15, check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    path = Path(result.stdout.strip())
    return path if path.is_file() else None


def font_coverage(font_path: Path) -> set[int]:
    """返回字体覆盖的码点集合，用于跳过未收录的字。"""
    from fontTools.ttLib import TTFont

    with TTFont(font_path, fontNumber=0, lazy=True) as font:
        return set(font.getBestCmap().keys())


def render_glyph_images(
    characters: list[str],
    font_path: Path,
    output_dir: Path,
    size: int = GLYPH_IMAGE_SIZE,
    font_size: int = GLYPH_IMAGE_FONT_SIZE,
) -> dict[str, str]:
    """把每个汉字渲染为透明底 PNG，返回 {汉字: 文件名}。

    字体未收录的字跳过（弹窗中回退为提示文案）。
    """
    from PIL import Image, ImageDraw, ImageFont

    covered = font_coverage(font_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, str] = {}
    font = ImageFont.truetype(str(font_path), font_size)

    for char in characters:
        codepoint = ord(char)
        if codepoint not in covered or char in rendered:
            continue
        bbox = font.getbbox(char)
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if width <= 0 or height <= 0:
            continue
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.text(
            ((size - width) / 2 - bbox[0], (size - height) / 2 - bbox[1]),
            char, font=font, fill=GLYPH_INK,
        )
        # 量化到 64 色（书法墨色为纯色渐变边缘，视觉无损），体积约为 RGBA 的 1/4
        quantized = image.quantize(colors=64, method=Image.FASTOCTREE)
        filename = f"{hex(codepoint)[2:]}.png"
        quantized.save(output_dir / filename, optimize=True)
        rendered[char] = filename
    return rendered


def prepare_calligrapher_resources(
    characters: list[str],
    html_dir: Path,
    calligraphers: list[dict] | None = None,
    images_dirname: str = "glyph-images",
    calligraphy_dir: Path | None = None,
    pre_render: bool = False,
) -> list[dict]:
    """准备弹窗资源，返回注入 HTML 的书家配置列表。

    每个书家可带两类来源：
      - 字体实时渲染：把字体文件拷到 html_dir/fonts/<slug>.<ext>，
        弹窗用 @font-face + Canvas 现场绘制（矢量清晰，体积仅字体一份）
      - wikichina 集字图：从 calligraphy_dir/<字>/<书家别名>-*.png|.jpg
        拷到 glyph-images/<slug>/<码点>-<序号>.png
    pre_render=True 时额外用字体预渲染 PNG（离线查看的回退）。
    """
    import shutil

    if calligraphy_dir is None:
        calligraphy_dir = ROOT / "data" / "calligraphy"
    resolved: list[dict] = []
    for item in (calligraphers if calligraphers is not None else CALLIGRAPHERS):
        entry: dict = {
            "name": item["name"], "slug": item["slug"],
            "font": None, "covered": [], "images": {},
        }
        font_path = resolve_font_file(item["family"]) if item.get("family") else None
        if item.get("family") and font_path is None:
            print(
                f"警告：找不到「{item['name']}」字体（{item['family']}），"
                "弹窗将只显示集字图（如有）",
                file=sys.stderr,
            )
        if font_path is not None:
            covered = font_coverage(font_path)
            covered_chars = [ch for ch in characters if ord(ch) in covered]
            fonts_dir = html_dir / "fonts"
            fonts_dir.mkdir(parents=True, exist_ok=True)
            dest = fonts_dir / (item["slug"] + font_path.suffix.lower())
            shutil.copy2(font_path, dest)
            entry["font"] = f"fonts/{dest.name}"
            entry["covered"] = [f"{ord(ch):x}" for ch in covered_chars]
            print(
                f"已复制 {item['name']} 字体 → fonts/{dest.name}"
                f"（覆盖 {len(covered_chars)}/{len(characters)} 字）"
            )
            if pre_render:
                rendered = render_glyph_images(
                    covered_chars, font_path, html_dir / images_dirname / item["slug"],
                )
                for ch, filename in rendered.items():
                    entry["images"].setdefault(f"{ord(ch):x}", []).append(filename)
                print(f"已预渲染 {item['name']} 集字图片：{len(rendered)} 字")
        # wikichina 集字图（<字>/<别名>-*.png，回退 .jpg）
        copied = 0
        for ch in characters:
            prefix = f"{ord(ch):x}"
            files: list[Path] = []
            for alias in item.get("aliases", []):
                files.extend(sorted((calligraphy_dir / ch).glob(f"{alias}-*.png")))
            if not files:
                for alias in item.get("aliases", []):
                    files.extend(sorted((calligraphy_dir / ch).glob(f"{alias}-*.jpg")))
            for index, source in enumerate(files):
                target = html_dir / images_dirname / item["slug"] / f"{prefix}-{index}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                entry["images"].setdefault(prefix, []).append(target.name)
                copied += 1
        if copied:
            print(f"已复制 {item['name']} wikichina 集字图：{copied} 张 → {images_dirname}/{item['slug']}/")
        resolved.append(entry)
    return resolved


def structure_of(character: str, ids_data: dict[str, str]) -> str:
    """返回汉字的结构类别（列名）。"""
    if character in SINGLE_OVERRIDES:
        return "独体字"

    sequence = ids_data.get(character, "")
    if not sequence:
        return "未知"

    for operator, label in OPERATORS.items():
        if sequence.startswith(operator) or operator in sequence:
            return label
    return "独体字"


def analyze_text(text: str, ids_data: dict[str, str]) -> list[dict]:
    """按文本中首次出现的顺序分析每个汉字。

    存储结构：列表内每个元素形如
        {"char": "明", "ids": "⿰日月", "structure": "左右结构"}
    结构类别取值来自 COLUMN_ORDER。
    """
    seen: set[str] = set()
    results: list[dict] = []
    for char in text:
        if char in seen or not is_hanzi(char):
            continue
        seen.add(char)
        results.append({
            "char": char,
            "ids": ids_data.get(char, ""),
            "structure": structure_of(char, ids_data),
        })
    return results


def group_by_structure(entries: list[dict]) -> "OrderedDict[str, list[dict]]":
    """按固定列顺序分组：{结构列名: [按出现顺序的条目]}。"""
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for label in COLUMN_ORDER:
        grouped[label] = []
    for entry in entries:
        grouped.setdefault(entry["structure"], []).append(entry)
    return grouped


def to_json(entries: list[dict], source_name: str, anchor: str | None = None) -> dict:
    """HTML 友好的存储结构：列名 + 每列按文本出现顺序的汉字。"""
    grouped = group_by_structure(entries)
    columns = [label for label in COLUMN_ORDER if grouped.get(label)]
    if anchor is None:
        # 由来源名生成稳定、合法的 HTML 锚点：非 ASCII 字符转十六进制码点
        kept = "".join(
            c if c.isascii() and c.isalnum() else f"-{ord(c):x}-"
            for c in source_name
        ).strip("-")
        anchor = "s-" + (kept or "source")
    return {
        "source": source_name,
        "anchor": anchor,
        "count": len(entries),
        "columns": columns,
        "rows": {
            label: [entry["char"] for entry in grouped[label]]
            for label in columns
        },
        "entries": entries,
    }


# ---- HTML 输出 ----

HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>字形结构 — {title}</title>
  <style>
    :root {{
      --ink: #20201d;
      --ink-soft: #55544d;
      --ink-muted: #89877d;
      --paper: #fbf8f0;
      --paper-deep: #f3ecdf;
      --canvas: #f0eadf;
      --line: #dfd6c7;
      --line-strong: #cbbfa9;
      --cinnabar: #b64a37;
      --shadow: 0 28px 70px rgba(66, 52, 31, 0.11);
      --ui-font: "Noto Sans CJK SC", "Source Han Sans SC", "Microsoft YaHei",
        "PingFang SC", sans-serif;
      --serif-font: "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC",
        "SimSun", serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #eee7da;
      font-family: var(--ui-font);
      -webkit-font-smoothing: antialiased;
    }}
    .page {{
      width: min(1240px, calc(100% - 48px));
      margin: 0 auto;
      padding: 34px 0 48px;
    }}
    header.topbar {{
      display: flex;
      align-items: baseline;
      gap: 18px;
      margin-bottom: 22px;
      flex-wrap: wrap;
    }}
    header.topbar h1 {{
      margin: 0;
      font-family: var(--serif-font);
      font-size: 22px;
      font-weight: 700;
      letter-spacing: 0.1em;
    }}
    header.topbar .meta {{
      color: var(--ink-muted);
      font-size: 12px;
      letter-spacing: 0.1em;
    }}
    nav.file-index {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 26px;
    }}
    nav.file-index a {{
      padding: 6px 13px;
      color: var(--ink-soft);
      background: rgba(255, 253, 247, 0.78);
      border: 1px solid var(--line);
      border-radius: 8px;
      font-size: 12px;
      text-decoration: none;
      transition:
        border-color 150ms ease,
        color 150ms ease;
    }}
    nav.file-index a:hover {{
      color: var(--cinnabar);
      border-color: var(--line-strong);
    }}
    section.source-block {{ margin-bottom: 44px; }}
    section.source-block > h2 {{
      margin: 0 0 14px;
      font-family: var(--serif-font);
      font-size: 17px; font-weight: 600; letter-spacing: 0.08em;
    }}
    section.source-block > h2 small {{
      margin-left: 10px;
      color: var(--ink-muted);
      font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
      font-size: 10px; font-weight: 400; letter-spacing: 0;
    }}
    .table-wrap {{
      border: 1px solid var(--line-strong);
      border-radius: 14px;
      background: var(--paper);
      box-shadow: var(--shadow);
      overflow: auto;
      max-height: 78vh;
    }}
    table.structure {{ width: 100%; border-collapse: separate; border-spacing: 0; }}
    table.structure th, table.structure td {{
      border: 0;
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      padding: 14px 12px;
      vertical-align: top;
    }}
    table.structure tr > *:last-child {{ border-right: 0; }}
    table.structure tbody tr:last-child td {{ border-bottom: 0; }}
    table.structure th {{
      position: sticky; top: 0; z-index: 2;
      background: linear-gradient(115deg, #f2e7d5, var(--paper));
      color: var(--ink);
      font-family: var(--serif-font);
      font-size: 15px; font-weight: 600; letter-spacing: 0.08em;
      text-align: left;
      box-shadow: 0 2px 8px rgba(66, 52, 31, 0.08);
    }}
    table.structure th .count {{
      margin-left: 7px;
      color: var(--ink-muted);
      font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
      font-size: 10px; font-weight: 400;
    }}
    table.structure td {{
      background: var(--paper);
      line-height: 2.0;
    }}
    table.structure tr:nth-child(even) td {{ background: var(--paper-deep); }}
    .glyph {{
      display: inline-grid;
      place-items: center;
      width: 42px; height: 42px; margin: 3px 7px 3px 0;
      background: var(--canvas);
      border: 1px solid var(--line);
      border-radius: 6px;
      font-family: var(--serif-font);
      font-size: 26px; font-weight: 500;
      transition: transform 160ms ease, box-shadow 160ms ease;
      cursor: default;
    }}
    .glyph:hover {{ transform: translateY(-2px); box-shadow: 0 8px 18px rgba(66,52,31,0.13); }}
    footer {{
      margin-top: 24px;
      color: var(--ink-muted);
      font-size: 11px; letter-spacing: 0.08em;
    }}
    /* 集字弹窗 */
    .glyph-modal {{
      position: fixed; inset: 0; z-index: 40;
      display: grid; place-items: center;
      padding: 24px;
      background: rgba(35, 32, 26, 0.45);
      backdrop-filter: blur(8px);
    }}
    .glyph-modal[hidden] {{ display: none; }}
    .glyph-dialog {{
      width: min(560px, 100%);
      max-height: calc(100vh - 48px);
      overflow-y: auto;
      border: 1px solid rgba(255, 252, 244, 0.82);
      border-radius: 17px;
      background: var(--paper);
      box-shadow: 0 32px 90px rgba(27, 24, 18, 0.27);
    }}
    .glyph-dialog > header {{
      position: sticky; top: 0; z-index: 1;
      display: flex; align-items: center; justify-content: space-between;
      padding: 20px 24px 14px;
      background: var(--paper);
      border-bottom: 1px solid var(--line);
    }}
    .glyph-dialog header h2 {{
      margin: 0;
      font-family: var(--serif-font);
      font-size: 20px; font-weight: 600; letter-spacing: 0.08em;
    }}
    .glyph-dialog header h2 small {{
      margin-left: 10px;
      color: var(--ink-muted);
      font-size: 11px; font-weight: 400; letter-spacing: 0.1em;
    }}
    .glyph-modal-close {{
      display: grid; place-items: center;
      width: 34px; height: 34px;
      color: var(--ink-muted);
      border: 1px solid transparent; border-radius: 50%;
      background: transparent; cursor: pointer; font-size: 18px; line-height: 1;
    }}
    .glyph-modal-close:hover {{ color: var(--ink); border-color: var(--line); background: var(--paper-deep); }}
    .glyph-modal-body {{ padding: 18px 24px 24px; }}
    .calligrapher-figure {{ margin: 0 0 18px; }}
    .calligrapher-figure:last-child {{ margin-bottom: 0; }}
    .calligrapher-figure figcaption {{
      margin-bottom: 10px;
      color: var(--ink-muted);
      font-family: var(--serif-font);
      font-size: 11px; letter-spacing: 0.14em;
    }}
    .calligrapher-figure .glyph-stage {{
      display: flex; flex-wrap: wrap; gap: 12px;
      align-items: center; justify-content: center;
      min-height: 240px;
      border: 1px solid var(--line);
      border-radius: 11px;
      background-color: var(--canvas);
      background-image:
        linear-gradient(rgba(126, 105, 72, 0.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(126, 105, 72, 0.06) 1px, transparent 1px);
      background-size: 50% 50%;
    }}
    .calligrapher-figure img,
    .calligrapher-figure .glyph-canvas {{
      width: min(220px, 60vw); height: auto;
      user-select: none;
    }}
    .glyph-missing {{
      color: var(--ink-muted); font-size: 12px; letter-spacing: 0.1em;
    }}
    @media (max-width: 720px) {{
      .page {{ width: calc(100% - 26px); padding-top: 22px; }}
      table.structure th, table.structure td {{ padding: 10px 7px; }}
      .glyph {{ width: 36px; height: 36px; font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="topbar">
      <h1>字形结构分布</h1>
      <span class="meta">{meta}</span>
    </header>
{content}
    <footer>{footer}</footer>
  </div>
{modal}
{script}
</body>
</html>
"""

MODAL_TEMPLATE = """<style>
{font_faces}
</style>
<div class="glyph-modal" id="glyph-modal" hidden>
  <div class="glyph-dialog" role="dialog" aria-modal="true" aria-labelledby="glyph-modal-title">
    <header>
      <h2><span id="glyph-modal-char">—</span><small id="glyph-modal-ids"></small></h2>
      <button class="glyph-modal-close" id="glyph-modal-close" type="button" aria-label="关闭集字弹窗">×</button>
    </header>
    <div class="glyph-modal-body" id="glyph-modal-body"></div>
  </div>
</div>
<script>
(function () {{
  "use strict";
  var calligraphers = {calligraphers_json};
  var modal = document.getElementById("glyph-modal");
  var charLabel = document.getElementById("glyph-modal-char");
  var idsLabel = document.getElementById("glyph-modal-ids");
  var body = document.getElementById("glyph-modal-body");
  var lastFocus = null;

  function close() {{
    modal.hidden = true;
    if (lastFocus) lastFocus.focus();
  }}

  // 用书家字体在 Canvas 上实时绘制大字（矢量，任意尺寸清晰）
  function renderFontStage(stage, c, char) {{
    var css = 220;
    var dpr = window.devicePixelRatio || 1;
    var canvas = document.createElement("canvas");
    canvas.className = "glyph-canvas";
    canvas.width = canvas.height = Math.round(css * dpr);
    canvas.style.width = canvas.style.height = css + "px";
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    function paint() {{
      ctx.clearRect(0, 0, css, css);
      // 米字格
      ctx.strokeStyle = "rgba(126, 105, 72, 0.28)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(css / 2, 0); ctx.lineTo(css / 2, css);
      ctx.moveTo(0, css / 2); ctx.lineTo(css, css / 2);
      ctx.moveTo(0, 0); ctx.lineTo(css, css);
      ctx.moveTo(css, 0); ctx.lineTo(0, css);
      ctx.stroke();
      // 大字
      ctx.fillStyle = "#1c1b18";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = Math.floor(css * 0.72) + 'px "gx-' + c.slug + '"';
      ctx.fillText(char, css / 2, css / 2 + css * 0.04);
    }}
    if (document.fonts && document.fonts.load) {{
      document.fonts.load('300px "gx-' + c.slug + '"', char).then(paint, paint);
    }} else {{
      paint();
    }}
    stage.append(canvas);
  }}

  function missingNotice(stage, c, char) {{
    stage.append(Object.assign(document.createElement("p"), {{
      className: "glyph-missing",
      textContent: "「" + char + "」暂无 " + c.name + " 集字",
    }}));
  }}

  function open(span) {{
    var char = span.getAttribute("data-char");
    var ids = span.getAttribute("data-ids") || "";
    var hex = char.codePointAt(0).toString(16);
    lastFocus = span;
    charLabel.textContent = char;
    idsLabel.textContent = ids ? "IDS " + ids : "";
    body.replaceChildren();
    calligraphers.forEach(function (c) {{
      var figure = document.createElement("figure");
      figure.className = "calligrapher-figure";
      var caption = document.createElement("figcaption");
      caption.textContent = c.name;
      var stage = document.createElement("div");
      stage.className = "glyph-stage";
      var hasFont = c.font && c.covered && c.covered.indexOf(hex) >= 0;
      var images = (c.images && c.images[hex]) || [];
      if (hasFont) renderFontStage(stage, c, char);
      images.forEach(function (filename) {{
        var image = document.createElement("img");
        image.alt = c.name + " " + char;
        image.loading = "lazy";
        image.src = "glyph-images/" + c.slug + "/" + filename;
        stage.append(image);
      }});
      if (!hasFont && !images.length) missingNotice(stage, c, char);
      figure.append(caption, stage);
      body.append(figure);
    }});
    modal.hidden = false;
    document.getElementById("glyph-modal-close").focus();
  }}

  document.querySelectorAll("span.glyph[data-char]").forEach(function (span) {{
    span.classList.add("glyph-clickable");
    span.addEventListener("click", function () {{ open(span); }});
  }});
  document.getElementById("glyph-modal-close").addEventListener("click", close);
  modal.addEventListener("click", function (event) {{
    if (event.target === modal) close();
  }});
  document.addEventListener("keydown", function (event) {{
    if (event.key === "Escape" && !modal.hidden) close();
  }});
}})();
</script>"""


TABLE_TEMPLATE = """<section class="source-block" id="{anchor}">
  <h2>{title}<small>{summary}</small></h2>
  <div class="table-wrap">
    <table class="structure">
      <thead>
        <tr>
{header_cells}
        </tr>
      </thead>
      <tbody>
{body_rows}
      </tbody>
    </table>
  </div>
</section>"""


def render_table(data: dict) -> str:
    """渲染单个来源文件的独立表格块。"""
    columns = data["columns"]
    header_cells = "\n".join(
        f'        <th>{html.escape(label)}'
        f'<span class="count">{len(data["rows"][label])}</span></th>'
        for label in columns
    )

    # 真正的网格：第 N 行 = 每个结构列的第 N 个字（按文本出现顺序），空位占位对齐
    max_rows = max((len(data["rows"][label]) for label in columns), default=0)
    ids_by_char = {entry["char"]: entry["ids"] for entry in data.get("entries", [])}
    body_rows = []
    for row_index in range(max(max_rows, 1)):
        cells = []
        for label in columns:
            characters = data["rows"][label]
            if row_index < len(characters):
                char = characters[row_index]
                ids_sequence = html.escape(ids_by_char.get(char, ""), quote=True)
                cells.append(
                    "        <td>"
                    f'<span class="glyph" role="button" tabindex="0"'
                    f' data-char="{html.escape(char, quote=True)}"'
                    f' data-ids="{ids_sequence}"'
                    f' title="{html.escape(label)}：{html.escape(char)}（点击查看集字）">'
                    f'{html.escape(char)}</span>'
                    "</td>"
                )
            else:
                # 无内容的格子保持占位，保证表格行对齐
                cells.append("        <td></td>")
        body_rows.append("      <tr>\n" + "\n".join(cells) + "\n      </tr>")
    return TABLE_TEMPLATE.format(
        anchor=html.escape(data["anchor"], quote=True),
        title=html.escape(data["source"]),
        summary=html.escape(f'{data["count"]} 字 · {len(columns)} 类结构'),
        header_cells=header_cells,
        body_rows="\n".join(body_rows),
    )


def render_html(datasets: list[dict], calligraphers: list[dict] | None = None) -> str:
    """渲染整页。多个文件时每个文件一个独立表格块，页首提供文件索引。

    calligraphers 非空时注入集字弹窗（每个字点击后显示各书家大图）。
    """
    sections = "\n".join(render_table(data) for data in datasets)
    multi = len(datasets) > 1

    nav = ""
    if multi:
        links = "\n".join(
            f'      <a href="#{html.escape(data["anchor"], quote=True)}">'
            f'{html.escape(data["source"])}</a>'
            for data in datasets
        )
        nav = f'    <nav class="file-index">\n{links}\n    </nav>'

    total = sum(data["count"] for data in datasets)
    if multi:
        title = f"字形结构 — {len(datasets)} 个文件"
        meta = f"{len(datasets)} 个文件 · 共 {total} 字"
    else:
        only = datasets[0]
        title = f"字形结构 — {html.escape(only['source'])}"
        meta = f'{html.escape(only["source"])} · 共 {only["count"]} 字 · {len(only["columns"])} 类结构'

    sources = "、".join(data["source"] for data in datasets)
    modal = ""
    if calligraphers:
        font_faces = "\n".join(
            f"@font-face {{ font-family: 'gx-{html.escape(c['slug'], quote=True)}';"
            f" src: url('{html.escape(c['font'])}'); }}"
            for c in calligraphers if c.get("font")
        )
        modal = MODAL_TEMPLATE.format(
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
    return HTML_TEMPLATE.format(
        title=title,
        meta=meta,
        content=nav + "\n" + sections if nav else sections,
        footer=f"数据来源：CHISE IDS · 来源文件：{html.escape(sources)}",
        modal=modal,
        script="",
    )


# ---- 命令行 ----

def main() -> None:
    parser = argparse.ArgumentParser(
        description="基于 IDS 输出汉字字形结构，支持单字或文本文件 → JSON / HTML 网格页",
    )
    parser.add_argument("characters", nargs="*", help="要分析的汉字（可多个）")
    parser.add_argument(
        "--file", action="append", dest="files", metavar="FILE",
        help="输入文本文件（按其中汉字首次出现顺序处理），可重复传入多个文件；"
        "HTML 中每个文件生成一个独立表格",
    )
    parser.add_argument("--json", help="输出 JSON 存储结构到指定文件（多文件时输出数组）")
    parser.add_argument("--html", help="输出 HTML 网格页到指定文件")
    parser.add_argument(
        "--no-images", action="store_true",
        help="不准备弹窗集字资源（字体与集字图都不拷贝）",
    )
    parser.add_argument(
        "--pre-render", action="store_true",
        help="额外用书家字体预渲染 PNG（默认只拷字体文件由弹窗实时渲染）",
    )
    parser.add_argument(
        "--calligraphy-dir", default=str(ROOT / "data" / "calligraphy"),
        help="wikichina 集字图目录（默认 data/calligraphy/）",
    )
    parser.add_argument("--ids-dir", default=str(IDS_DIR), help="IDS 数据目录（默认 data/ids/）")
    args = parser.parse_args()

    files = args.files or []
    if not args.characters and not files:
        parser.error("请提供要分析的汉字，或使用 --file 指定文本文件")
    ids_data = load_ids_data(Path(args.ids_dir))

    if not args.json and not args.html and args.characters:
        # 单字模式直接打印
        for character in args.characters:
            for ch in character:
                if is_hanzi(ch):
                    sequence = ids_data.get(ch, "")
                    print(f"{ch}  {structure_of(ch, ids_data)}  {sequence or '（IDS 未收录）'}")
        return
    if not args.json and not args.html:
        parser.error("批处理模式需要 --json 或 --html 至少指定一个输出")

    # 每个输入文件独立分析（不合并、不跨文件去重）
    datasets: list[dict] = []
    if files:
        for name in files:
            path = Path(name)
            if not path.exists():
                raise SystemExit(f"输入文件不存在：{path}")
            entries = analyze_text(path.read_text(encoding="utf-8"), ids_data)
            if entries:
                datasets.append(to_json(entries, path.name))
            else:
                print(f"跳过 {path.name}（未发现汉字）", file=sys.stderr)
    else:
        combined = "".join(args.characters)
        if is_hanzi_in(combined):
            datasets.append(to_json(analyze_text(combined, ids_data), "命令行输入"))

    if not datasets:
        raise SystemExit("所有输入都没有发现汉字，未生成任何输出")

    if args.json:
        payload = datasets if files and len(datasets) > 1 else datasets[0]
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已写出 {args.json}")
    if args.html:
        html_path = Path(args.html)
        # 弹窗资源：字体拷贝 + 集字图收集，输出到 HTML 同目录
        resolved_calligraphers: list[dict] = []
        if not args.no_images:
            all_chars = sorted({e["char"] for d in datasets for e in d["entries"]})
            resolved_calligraphers = prepare_calligrapher_resources(
                all_chars, html_path.resolve().parent,
                calligraphy_dir=Path(args.calligraphy_dir),
                pre_render=args.pre_render,
            )
        html_path.write_text(
            render_html(datasets, resolved_calligraphers),
            encoding="utf-8",
        )
        print(f"已写出 {args.html}（{len(datasets)} 个表格）" if len(datasets) > 1 else f"已写出 {args.html}")


if __name__ == "__main__":
    main()

