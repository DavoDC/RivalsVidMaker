"""
main.py — Entry point for CompilationVidMaker.

Usage:
    python src/main.py              # uses config.txt in the current directory
    python src/main.py my_cfg.txt   # explicit config path
"""

import logging
import sys
import time
from pathlib import Path

from config import load as load_config
from pipeline import run


def setup_logging() -> Path:
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return log_file


def main() -> None:
    log_file = setup_logging()

    print("=" * 50)
    print("  CompilationVidMaker")
    print("  Marvel Rivals clip compiler")
    print("=" * 50)
    print(f"  Log: {log_file}\n")

    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.json")

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    try:
        run(config)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)

    print(f"\nLog saved to: {log_file}")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
