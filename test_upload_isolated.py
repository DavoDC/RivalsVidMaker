#!/usr/bin/env python3
"""
Isolated upload test - debug the upload without full pipeline.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

from uploader import get_authenticated_service, validate_channel_id, upload_video, parse_description_file
from config import load

config = load()

# CLI arg = video path. Default = small Instagram_2.mp4 (5.9MB) for fast iteration.
# To test the real 2.4GB workflow file: pass it as arg1.
if len(sys.argv) > 1:
    video_path = Path(sys.argv[1])
    desc_path = video_path.with_name(video_path.stem + "_description.txt")
else:
    video_path = Path("C:/Users/David/Downloads/Instagram_2.mp4")
    desc_path = None  # synthesise title/desc inline

if not video_path.exists():
    print(f"ERROR: Video not found: {video_path}")
    sys.exit(1)

if desc_path is not None and not desc_path.exists():
    print(f"ERROR: Description not found: {desc_path}")
    sys.exit(1)

print(f"Video: {video_path.name} ({video_path.stat().st_size / (1024**3):.2f} GB)")
print()

try:
    print("Step 1: Authenticate...")
    youtube = get_authenticated_service(expected_channel_id=config.youtube_channel_id)
    print("[OK] Authenticated")
    print()

    print("Step 2: Validate channel...")
    validate_channel_id(youtube, config.youtube_channel_id)
    print("[OK] Channel validated")
    print()

    print("Step 3: Parse description...")
    if desc_path is not None:
        title, description = parse_description_file(desc_path)
    else:
        title = f"TEST UPLOAD - {video_path.stem} (private, will be deleted)"
        description = "Isolated upload test. Safe to delete."
    print(f"[OK] Title: {title[:60]}...")
    print()

    print("Step 4: Upload video...")
    video_id = upload_video(youtube, video_path, title, description)
    print(f"[OK] Upload successful! Video ID: {video_id}")
    print(f"URL: https://www.youtube.com/watch?v={video_id}")

except Exception as e:
    print(f"✗ ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
