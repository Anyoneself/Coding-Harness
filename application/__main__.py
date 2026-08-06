"""支持通过 python -m application 启动命令行。"""

from .cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
