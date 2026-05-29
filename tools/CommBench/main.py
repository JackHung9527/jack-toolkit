"""CommBench host UI 入口。

直接執行：
    python main.py

打包後（PyInstaller）也由本檔當入口。
"""

from __future__ import annotations

import os
import sys


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
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
