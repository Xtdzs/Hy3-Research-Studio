"""允许 `python -m scholarbench <sub>` 直接调用各子命令。"""
import sys

from .run import main as run_main

SUBCOMMANDS = {
    "run": run_main,
    "build_dataset": lambda: __import__("scholarbench.build_dataset", fromlist=["main"]).main(),
    "annotate": lambda: __import__("scholarbench.annotate", fromlist=["main"]).main(),
    "agreement": lambda: __import__("scholarbench.agreement", fromlist=["main"]).main(),
    "report": lambda: __import__("scholarbench.report_cmd", fromlist=["main"]).main(),
    "stats": lambda: __import__("scholarbench.stats_cmd", fromlist=["main"]).main(),
    "download_papers": lambda: __import__(
        "scholarbench.download_papers", fromlist=["main"]).main(),
}


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print("用法：python -m scholarbench <子命令> [参数]\n")
        print("子命令：" + ", ".join(SUBCOMMANDS))
        return
    cmd, rest = args[0], args[1:]
    if cmd not in SUBCOMMANDS:
        print(f"未知子命令：{cmd}（可选：{', '.join(SUBCOMMANDS)}）")
        return
    sys.argv = [f"scholarbench {cmd}"] + rest
    SUBCOMMANDS[cmd]()


if __name__ == "__main__":
    main()
