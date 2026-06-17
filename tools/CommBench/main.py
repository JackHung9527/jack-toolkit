"""CommBench host UI 入口。

直接執行：
    python main.py

打包後（PyInstaller）也由本檔當入口。
"""

from __future__ import annotations

import os
import sys


def _center_window(win) -> None:
    win.update_idletasks()
    w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
    h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
    x = max(0, (win.winfo_screenwidth() - w) // 2)
    y = max(0, (win.winfo_screenheight() - h) // 2)
    win.geometry(f"+{x}+{y}")


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    # 讓子模組能 import common.*
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from host.ui.main_window import MainWindow

    app = MainWindow()
    try:
        app.iconbitmap(default=os.path.join(here, "commbench.ico"))
    except Exception:
        pass
    _center_window(app)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
