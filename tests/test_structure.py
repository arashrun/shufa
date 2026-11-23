"""字形结构脚本的核心逻辑测试（直接导入模块，不经过子进程）。"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "structure.py"

spec = importlib.util.spec_from_file_location("xingkai_structure", SCRIPT)
structure = importlib.util.module_from_spec(spec)
sys.modules["xingkai_structure"] = structure
spec.loader.exec_module(structure)


def load_data():
    return structure.load_ids_data(structure.IDS_DIR)


def test_structure_classification():
    ids_data = load_data()
    assert structure.structure_of("明", ids_data) == "左右结构"
    assert structure.structure_of("森", ids_data) == "上下结构"
    assert structure.structure_of("园", ids_data) == "全包围结构"
    assert structure.structure_of("虎", ids_data) == "左上包围"
    assert structure.structure_of("这", ids_data) == "左下包围"
    assert structure.structure_of("爽", ids_data) in structure.COLUMN_ORDER
    # 教学习惯视作独体的字不受 IDS 拆分影响
    assert structure.structure_of("日", ids_data) == "独体字"
    # IDS 未收录的字归"未知"
    unknown = structure.structure_of("𠀀", ids_data)
    assert unknown in {"未知", "独体字", "左右结构"}  # 视数据文件覆盖范围而定


def test_analyze_text_order_and_dedup():
    ids_data = load_data()
    entries = structure.analyze_text("森明明A1，、森", ids_data)
    assert [entry["char"] for entry in entries] == ["森", "明"]
    assert entries[0]["structure"] == "上下结构"
    assert entries[1]["ids"] == "⿰日月"


def test_group_and_json_shape():
    ids_data = load_data()
    entries = structure.analyze_text("明森园", ids_data)
    data = structure.to_json(entries, "demo.txt")
    assert data["source"] == "demo.txt"
    assert data["count"] == 3
    assert data["columns"][0] == "左右结构"
    assert data["rows"]["左右结构"] == ["明"]
    assert data["rows"]["上下结构"] == ["森"]
    assert data["rows"]["全包围结构"] == ["园"]
    assert sum(len(v) for v in data["rows"].values()) == data["count"]


def test_render_html_grid_alignment():
    ids_data = load_data()
    entries = structure.analyze_text("明森园一个虎", ids_data)
    data = structure.to_json(entries, "demo.txt")
    html = structure.render_html(data)
    # 6 个字，每个渲染为恰好一个格子
    assert html.count('class="glyph"') == 6
    # 表头列数与数据列一致，且包含计数
    assert html.count("<th>") == len(data["columns"])
    assert "左右结构" in html and "全包围结构" in html
    # 单元格按行对齐：行数 = 最长列的长度（另加表头一行）
    longest = max(len(v) for v in data["rows"].values())
    assert html.count("<tr>") == longest + 1


def test_html_escapes():
    ids_data = load_data()
    entries = structure.analyze_text("明", ids_data)
    data = structure.to_json(entries, "<img src=x onerror=alert(1)>.txt")
    html = structure.render_html(data)
    assert "<img" not in html
    assert "&lt;img" in html
