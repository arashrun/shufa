#!/usr/bin/env python3
"""基于 IDS（表意文字描述序列）的汉字字形结构分析与 HTML 网格页生成。

用法：
  # 单字分析
  python3 scripts/structure.py 明

  # 从文本文件批处理，输出 JSON 存储结构
  python3 scripts/structure.py --file level-1.txt --json structure.json

  # 生成 HTML 网格页（列 = 结构类别，行内按文本出现顺序，表头 = 文件名）
  python3 scripts/structure.py --file level-1.txt --html structure.html

数据来源：CHISE IDS 数据文件（放在 data/ids/ 下，UTF-8 文本）。
数据文件行格式：U+660E<TAB>明<TAB>⿰日月
"""

from __future__ import annotations

import argparse
import html
import json
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


def to_json(entries: list[dict], source_name: str) -> dict:
    """HTML 友好的存储结构：列名 + 每列按文本出现顺序的汉字。"""
    grouped = group_by_structure(entries)
    columns = [label for label in COLUMN_ORDER if grouped.get(label)]
    return {
        "source": source_name,
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
    <footer>{footer}</footer>
  </div>
</body>
</html>
"""


def render_html(data: dict) -> str:
    columns = data["columns"]
    header_cells = "\n".join(
        f'          <th>{html.escape(label)}'
        f'<span class="count">{len(data["rows"][label])}</span></th>'
        for label in columns
    )

    # 真正的网格：第 N 行 = 每个结构列的第 N 个字（按文本出现顺序），空位占位对齐
    max_rows = max((len(data["rows"][label]) for label in columns), default=0)
    body_rows = []
    for row_index in range(max(max_rows, 1)):
        cells = []
        for label in columns:
            characters = data["rows"][label]
            if row_index < len(characters):
                char = characters[row_index]
                cells.append(
                    "          <td>"
                    f'<span class="glyph" title="{html.escape(label)}：{html.escape(char)}">'
                    f'{html.escape(char)}</span>'
                    "</td>"
                )
            else:
                # 无内容的格子保持占位，保证表格行对齐
                cells.append("          <td></td>")
        body_rows.append("        <tr>\n" + "\n".join(cells) + "\n        </tr>")
    return HTML_TEMPLATE.format(
        title=html.escape(data["source"]),
        meta=f'{html.escape(data["source"])} · 共 {data["count"]} 字 · {len(columns)} 类结构',
        header_cells=header_cells,
        body_rows="\n".join(body_rows),
        footer=f"数据来源：CHISE IDS · 生成于 {html.escape(Path(data['source']).name)}",
    )


# ---- 命令行 ----

def main() -> None:
    parser = argparse.ArgumentParser(
        description="基于 IDS 输出汉字字形结构，支持单字或文本文件 → JSON / HTML 网格页",
    )
    parser.add_argument("characters", nargs="*", help="要分析的汉字（可多个）")
    parser.add_argument("--file", help="输入文本文件（按其中汉字首次出现顺序处理）")
    parser.add_argument("--json", help="输出 JSON 存储结构到指定文件")
    parser.add_argument("--html", help="输出 HTML 网格页到指定文件")
    parser.add_argument("--ids-dir", default=str(IDS_DIR), help="IDS 数据目录（默认 data/ids/）")
    args = parser.parse_args()

    if not args.characters and not args.file:
        parser.error("请提供要分析的汉字，或使用 --file 指定文本文件")
    if not args.json and not args.html and args.characters:
        # 单字模式直接打印
        ids_data = load_ids_data(Path(args.ids_dir))
        for character in args.characters:
            for ch in character:
                if is_hanzi(ch):
                    sequence = ids_data.get(ch, "")
                    print(f"{ch}  {structure_of(ch, ids_data)}  {sequence or '（IDS 未收录）'}")
        return
    if not args.json and not args.html:
        parser.error("批处理模式需要 --json 或 --html 至少指定一个输出")

    ids_data = load_ids_data(Path(args.ids_dir))
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
        source_name = Path(args.file).name
    else:
        text = "".join(args.characters)
        source_name = "命令行输入"

    entries = analyze_text(text, ids_data)
    if args.json:
        Path(args.json).write_text(
            json.dumps(to_json(entries, source_name), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已写出 {args.json}")
    if args.html:
        Path(args.html).write_text(
            render_html(to_json(entries, source_name)),
            encoding="utf-8",
        )
        print(f"已写出 {args.html}")


if __name__ == "__main__":
    main()

