"""Thin CLI for the OldCompilations archive run. Logic lives in src/oldcomp_scan.py."""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ko_detect  # noqa: E402
import oldcomp_guard  # noqa: E402
import oldcomp_scan  # noqa: E402

DEFAULT_ROOT = r"C:\Users\David\Videos\MarvelRivals\OldCompilations"
DEFAULT_META = r"C:\Users\David\Videos\MarvelRivals\OldCompilationsMeta"
DEFAULT_STATE = (r"C:\Users\David\GitHubRepos\Claude_Workspace\ClaudeOnly\memory\project"
                 r"\rvm-oldcompilations\STATE.json")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="scan videos with the NCC scanner")
    sc.add_argument("--root", default=DEFAULT_ROOT)
    sc.add_argument("--meta", default=DEFAULT_META)
    sc.add_argument("--state", default=DEFAULT_STATE)
    sc.add_argument("--only", help="substring of the video stem")
    sc.add_argument("--max-videos", type=int)
    sc.add_argument("--order", default="shortest-first", choices=["shortest-first"])
    sc.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    run_log = None
    if not a.dry_run:
        log_path = Path(a.meta) / "_scan_run.log"
        oldcomp_guard.assert_outside_oldcomp(log_path, a.root)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        run_log = open(log_path, "a", encoding="utf-8", buffering=1)  # append: runs never clobber each other

    def emit(m):
        print(m, flush=True)
        if run_log:
            run_log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {m}\n")

    try:
        res = oldcomp_scan.scan_all(
            root=a.root, meta=a.meta, state_path=a.state, only=a.only, max_videos=a.max_videos,
            dry_run=a.dry_run, version=ko_detect.SCANNER_VERSION, duration_fn=ko_detect.get_duration,
            scan_fn=lambda p, checkpoint_dir: ko_detect.scan_video(p, checkpoint_dir=checkpoint_dir),
            log=emit)
    except oldcomp_scan.ScanLocked as e:
        emit(str(e))
        return 2
    finally:
        if run_log:
            run_log.close()
    if a.dry_run:
        for r in res["plan"]:
            print(f"{r['duration'] / 60:8.1f} min  {r['stem']}")
    emit(f"done: scanned={res['scanned']} skipped={res['skipped']} failed={res['failed']}")
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
