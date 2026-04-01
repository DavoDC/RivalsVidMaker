"""
rescan_and_report.py - Force-rescan all clips then regenerate the KO analysis report.

Steps:
  1. Set force_rescan_cache: true AND use_pass2_scanner: true in config/config.json
  2. Run src/preprocess.py  (scans every clip with both passes, overwrites cache)
  3. Restore both flags to false (always, even on failure)
  4. Run scripts/once_off/analyse_ko_data.py  (new report with scan_pass + updated scan_time)

Usage (from repo root):
    python scripts/once_off/rescan_and_report.py

Purpose: data collection run. Uses pass 2 so all clips are scanned exhaustively,
giving complete scan_pass and scan_time data for the analysis report. No delete
prompts fire during this run (force_rescan suppresses them in preprocess.py).
"""

import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parent.parent.parent
CONFIG     = REPO_ROOT / "config" / "config.json"
PREPROCESS = REPO_ROOT / "src" / "preprocess.py"
ANALYSE    = REPO_ROOT / "scripts" / "once_off" / "analyse_ko_data.py"


def _set_config(key: str, value) -> None:
    with open(CONFIG) as f:
        cfg = json.load(f)
    cfg[key] = value
    with open(CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"  [config] {key} = {value}")


def _run(label: str, script: Path) -> float:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    t0 = time.perf_counter()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO_ROOT),
    )
    elapsed = time.perf_counter() - t0
    if result.returncode != 0:
        raise RuntimeError(f"{script.name} exited with code {result.returncode}")
    return elapsed


def main():
    t_total = time.perf_counter()
    print("\nrescan_and_report.py")
    print(f"Repo root: {REPO_ROOT}")

    # Step 1: enable force rescan + pass 2
    print("\n[1/4] Enabling force_rescan_cache + use_pass2_scanner ...")
    _set_config("force_rescan_cache", True)
    _set_config("use_pass2_scanner", True)

    preprocess_time = 0.0
    try:
        # Step 2: rescan all clips
        print("\n[2/4] Running preprocess (force rescan, pass 2 enabled) ...")
        preprocess_time = _run("Pre-process: KO scan all clips", PREPROCESS)
    finally:
        # Step 3: always restore config
        print("\n[3/4] Restoring force_rescan_cache + use_pass2_scanner ...")
        _set_config("force_rescan_cache", False)
        _set_config("use_pass2_scanner", False)

    # Step 4: regenerate report
    print("\n[4/4] Generating analysis report ...")
    report_time = _run("analyse_ko_data.py", ANALYSE)

    total = time.perf_counter() - t_total
    print(f"\n{'=' * 60}")
    print("  Done.")
    print(f"  Pre-process:  {preprocess_time:.1f}s")
    print(f"  Report:       {report_time:.1f}s")
    print(f"  Total:        {total:.1f}s")
    print(f"{'=' * 60}")
    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
