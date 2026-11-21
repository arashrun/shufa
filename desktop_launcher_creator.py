#!/usr/bin/env python3
"""Create and install a simple per-user Linux .desktop launcher."""

import html
import os
import re
import sys
import unicodedata
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


APPLICATIONS_DIR = Path.home() / ".local" / "share" / "applications"
ICONS_DIR = Path.home() / ".local" / "share" / "icons" / "desktop-launchers"


def desktop_name(value):
    """Return a stable, filesystem-safe name for a desktop entry."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"[^\w.-]+", "-", normalized, flags=re.UNICODE).strip("-_.")
    return normalized or "application"


def desktop_quote(value):
    """Quote a value for the Exec key while preserving a complete command."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_desktop_text(name, command, workdir, comment, icon):
    lines = [
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        f"Name={name}",
        f"Exec=sh -c \"{desktop_quote(command)}\"",
        f"Icon={icon}",
        "Terminal=false",
    ]
    if comment:
        lines.insert(5, f"Comment={comment}")
    if workdir:
        lines.append(f"Path={workdir}")
    lines.append("Categories=Utility;")
    return "\n".join(lines) + "\n"


def fallback_svg(name):
    initial = html.escape((name.strip() or "A")[0].upper())
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="24" fill="#3367d6"/>
  <text x="64" y="82" text-anchor="middle" font-family="sans-serif" font-size="68" font-weight="bold" fill="white">{initial}</text>
</svg>
'''


class DesktopLauncherCreator(Gtk.Window):
    def __init__(self):
        super().__init__(title="创建 Linux 应用启动器")
        self.set_border_width(16)
        self.set_default_size(700, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.icon_button = Gtk.FileChooserButton("选择图标文件", Gtk.FileChooserAction.OPEN)
        self._build_ui()
        self._connect_signals()
        self.update_preview()

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.add(root)

        grid = Gtk.Grid(column_spacing=10, row_spacing=10)
        root.pack_start(grid, False, False, 0)
        fields = [
            ("应用名称", "name_entry", "例如：我的编辑器"),
            ("启动命令", "command_entry", "例如：gedit %U"),
            ("工作目录", "workdir_entry", "可选，例如：/home/user/project"),
            ("注释", "comment_entry", "可选，例如：打开文本编辑器"),
        ]
        for row, (label_text, attr, placeholder) in enumerate(fields):
            label = Gtk.Label(label=label_text, xalign=0)
            entry = Gtk.Entry()
            entry.set_placeholder_text(placeholder)
            setattr(self, attr, entry)
            grid.attach(label, 0, row, 1, 1)
            grid.attach(entry, 1, row, 2, 1)

        icon_label = Gtk.Label(label="图标文件", xalign=0)
        self.icon_button.set_hexpand(True)
        self.icon_button.set_title("选择 PNG、SVG 或 XPM 图标")
        image_filter = Gtk.FileFilter()
        image_filter.set_name("图标文件（PNG、SVG、XPM）")
        for pattern in ("*.png", "*.svg", "*.xpm", "*.PNG", "*.SVG", "*.XPM"):
            image_filter.add_pattern(pattern)
        self.icon_button.add_filter(image_filter)
        all_filter = Gtk.FileFilter()
        all_filter.set_name("所有文件")
        all_filter.add_pattern("*")
        self.icon_button.add_filter(all_filter)
        grid.attach(icon_label, 0, 4, 1, 1)
        grid.attach(self.icon_button, 1, 4, 2, 1)

        hint = Gtk.Label(label="未选择图标时，会在用户图标目录生成一个以内置 SVG 绘制的首字符图标。", xalign=0)
        hint.get_style_context().add_class("dim-label")
        grid.attach(hint, 1, 5, 2, 1)

        preview_label = Gtk.Label(label="Desktop 文件预览", xalign=0)
        root.pack_start(preview_label, False, False, 0)
        preview_scroll = Gtk.ScrolledWindow()
        preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.preview = Gtk.TextView()
        self.preview.set_editable(False)
        self.preview.set_monospace(True)
        self.preview.set_wrap_mode(Gtk.WrapMode.NONE)
        preview_scroll.add(self.preview)
        root.pack_start(preview_scroll, True, True, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        root.pack_start(buttons, False, False, 0)
        self.preview_button = Gtk.Button(label="更新预览")
        self.install_button = Gtk.Button(label="生成并安装")
        self.install_button.get_style_context().add_class("suggested-action")
        buttons.pack_end(self.install_button, False, False, 0)
        buttons.pack_end(self.preview_button, False, False, 0)
        self.status = Gtk.Label(xalign=0)
        root.pack_start(self.status, False, False, 0)

    def _connect_signals(self):
        for entry in (self.name_entry, self.command_entry, self.workdir_entry, self.comment_entry):
            entry.connect("changed", lambda *_args: self.update_preview())
        self.icon_button.connect("file-set", lambda *_args: self.update_preview())
        self.preview_button.connect("clicked", lambda *_args: self.update_preview())
        self.install_button.connect("clicked", self.install_launcher)
        self.connect("destroy", Gtk.main_quit)

    def values(self):
        name = self.name_entry.get_text().strip()
        command = self.command_entry.get_text().strip()
        workdir = self.workdir_entry.get_text().strip()
        comment = self.comment_entry.get_text().strip()
        selected = self.icon_button.get_filename() or ""
        return name, command, workdir, comment, selected

    def update_preview(self):
        name, command, workdir, comment, selected = self.values()
        icon = selected or str(ICONS_DIR / f"{desktop_name(name)}.svg")
        text = build_desktop_text(name or "应用名称", command or "应用命令", workdir, comment, icon)
        self.preview.get_buffer().set_text(text)

    def install_launcher(self, _button):
        name, command, workdir, comment, selected = self.values()
        if not name or not command:
            self.status.set_text("请填写应用名称和启动命令。")
            return
        if workdir and not Path(workdir).is_dir():
            self.status.set_text("工作目录不存在或不是目录，请检查后重试。")
            return
        try:
            APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
            slug = desktop_name(name)
            if selected:
                icon = selected
            else:
                ICONS_DIR.mkdir(parents=True, exist_ok=True)
                icon_path = ICONS_DIR / f"{slug}.svg"
                icon_path.write_text(fallback_svg(name), encoding="utf-8")
                icon = str(icon_path)
            desktop_path = APPLICATIONS_DIR / f"{slug}.desktop"
            desktop_path.write_text(build_desktop_text(name, command, workdir, comment, icon), encoding="utf-8")
            desktop_path.chmod(0o755)
            self.update_preview()
            self.status.set_text(f"已安装：{desktop_path}")
        except OSError as error:
            self.status.set_text(f"写入失败：{error}")


def main():
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        print("需要图形会话（DISPLAY 或 WAYLAND_DISPLAY）才能运行此工具。", file=sys.stderr)
        return 1
    DesktopLauncherCreator().show_all()
    Gtk.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
