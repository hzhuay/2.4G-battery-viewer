# -*- coding: utf-8 -*-
"""拆 Electron app.asar（标准库实现），只读。

用法：
    python tools/asar_ls.py <app.asar>            # 列出文件
    python tools/asar_ls.py <app.asar> --grep battery   # 在 js/json 里搜关键字
"""
from __future__ import annotations

import json
import struct
import sys


def load_asar(path: str):
    with open(path, "rb") as f:
        head = struct.unpack("<4I", f.read(16))
        json_size = head[3]
        header = json.loads(f.read(json_size))
        base = 16 + (json_size + (4 - json_size % 4) % 4) - 4
        base = 8 + json_size if json_size % 4 == 0 else 16 + json_size
        # 统一按官方实现：文件数据起点 = 8 + header_size(对齐后)
        base = 8 + json_size + ((4 - json_size % 4) % 4)
        f.seek(base)
        blob = f.read()
    return header, blob


def walk(node, prefix=""):
    for name, info in node.get("files", {}).items():
        p = f"{prefix}/{name}" if prefix else name
        if "files" in info:
            yield from walk(info, p)
        else:
            yield p, info


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    path = sys.argv[1]
    header, blob = load_asar(path)
    files = list(walk(header))
    print(f"{len(files)} 个文件，blob {len(blob)} 字节")
    if len(sys.argv) > 2 and sys.argv[2] == "--grep":
        kw = sys.argv[3].lower().encode()
        for p, info in files:
            if not p.lower().endswith((".js", ".json", ".cjs", ".mjs")):
                continue
            off = int(info.get("offset", 0))
            data = blob[off: off + int(info["size"])]
            if kw in data.lower():
                print("HIT", p, info["size"])
    else:
        for p, info in files:
            print(f"{int(info['size']):10d}  {p}")


if __name__ == "__main__":
    main()
