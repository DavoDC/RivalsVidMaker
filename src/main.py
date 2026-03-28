"""
main.py — Entry point for RivalsVidMaker.

Usage:
    python src/main.py              # uses config/config.json
    python src/main.py my_cfg.json  # explicit config path
    python src/main.py --force      # re-encode even if output already exists
    python src/main.py --cleanup           # interactive cleanup mode (post-YouTube)
    python src/main.py --cleanup --dry-run # preview cleanup without moving files
"""

import logging
import sys
import time
from pathlib import Path

from cleanup import run_cleanup
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
    print(f"Log: {log_file}")

    args = sys.argv[1:]
    force_encode = "--force" in args
    cleanup_mode = "--cleanup" in args
    dry_run      = "--dry-run" in args
    config_args = [a for a in args if not a.startswith("--")]
    config_path = Path(config_args[0]) if config_args else Path("config/config.json")

    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        logging.error(str(e))
        sys.exit(1)
    except KeyError as e:
        logging.error(str(e))
        sys.exit(1)

    if cleanup_mode:
        _run_cleanup_mode(config, dry_run=dry_run)
    else:
        try:
            run(config, force_encode=force_encode)
        except KeyboardInterrupt:
            logging.info("Interrupted.")
            sys.exit(0)

    logging.info(f"Log saved to: {log_file}")


def _run_cleanup_mode(config, dry_run: bool = False) -> None:
    """Interactive cleanup: pick an output folder and run cleanup on it."""
    from pipeline import _scan_output_folder
    from state import is_youtube_confirmed, load as load_state

    output_rows = _scan_output_folder(config.output_path)
    if not output_rows:
        print("No output folders found.")
        return

    state = load_state(config.state_path)
    print("\nOutput folders:\n")
    for i, row in enumerate(output_rows, 1):
        yt = "YT" if is_youtube_confirmed(state, row["name"]) else "--"
        clips = "C" if row["has_clips"] else "-"
        print(f"  [{i}] {row['name']}  [clips:{clips}  yt:{yt}]")
    print()

    while True:
        try:
            raw = input(f"Pick a folder to clean up (1-{len(output_rows)}), or Q to quit: ").strip().lower()
            if raw in ("q", "quit", ""):
                return
            choice = int(raw)
            if 1 <= choice <= len(output_rows):
                break
        except (ValueError, EOFError):
            pass
        print(f"  Invalid - enter a number between 1 and {len(output_rows)}, or Q.")

    selected = output_rows[choice - 1]
    out_folder = config.output_path / selected["name"]
    run_cleanup(out_folder, config.archive_path, state_path=config.state_path, dry_run=dry_run)


if __name__ == "__main__":
    main()
