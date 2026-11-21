#!/usr/bin/env python3
"""Serve the local handwriting study app and open it in a browser."""

from __future__ import annotations

import argparse
import fcntl
import functools
import http.server
import os
import socket
import threading
import webbrowser
from pathlib import Path


class LocalRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serve files from the app directory without long-lived browser caches."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def acquire_singleton_lock() -> object | None:
    """Keep only one study-app server running for the current user."""
    lock_dir = Path.home() / ".cache" / "xingkai-recall"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "serve.lock"
    lock_file = lock_path.open("a+")

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_file.close()
        return None

    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(f"{os.getpid()}\n")
    lock_file.flush()
    return lock_file


def find_available_port(start: int) -> int:
    for port in range(start, start + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("找不到可用的本地端口")


def main() -> None:
    parser = argparse.ArgumentParser(description="启动行楷忆写学习工具")
    parser.add_argument("--port", type=int, default=8765, help="起始端口，默认 8765")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    lock_file = acquire_singleton_lock()
    if lock_file is None:
        print("行楷忆写已经在运行，退出本次启动。")
        return

    app_root = Path(__file__).resolve().parent
    try:
        port = find_available_port(args.port)
        handler = functools.partial(LocalRequestHandler, directory=app_root)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        url = f"http://127.0.0.1:{port}/"

        print(f"行楷忆写已启动：{url}")
        print("按 Ctrl+C 停止。")

        if not args.no_browser:
            threading.Timer(0.45, lambda: webbrowser.open(url)).start()

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n已停止。")
        finally:
            server.server_close()
    finally:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


if __name__ == "__main__":
    main()
