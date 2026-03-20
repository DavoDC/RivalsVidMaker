"""
main.py — Entry point for RivalsVidMaker.

Usage:
    python src/main.py              # uses config/config.json
    python src/main.py my_cfg.json  # explicit config path
"""

import logging
import sys
import time
from pathlib import Path

from config import load as load_config
from pipeline import run


_WIDTH = 50


class _TerminalFormatter(logging.Formatter):
    """Plain message for INFO in terminal; adds [LEVEL] prefix for WARNING+."""
    def format(self, record: logging.LogRecord) -> str:
        if record.levelno >= logging.WARNING:
            return f"[{record.levelname}] {record.getMessage()}"
        return record.getMessage()


def setup_logging() -> Path:
    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8", delay=True)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s")
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(_TerminalFormatter())

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    return log_file


def main() -> None:
    log_file = setup_logging()

    print("=" * _WIDTH)
    print("RivalsVidMaker".center(_WIDTH))
    print("=" * _WIDTH)
    print(f"Log: {log_file}\n")

    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/config.json")

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        logging.error(str(e))
        sys.exit(1)

    try:
        run(config)
    except KeyboardInterrupt:
        logging.info("Interrupted.")
        sys.exit(0)

    logging.info(f"Log saved to: {log_file}")
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
