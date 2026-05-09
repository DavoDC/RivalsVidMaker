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
video_path = Path("C:/Users/David/Videos/MarvelRivals/Output/THOR_Mar-Apr_2026_BATCH1/THOR_Mar-Apr_2026_BATCH1.mp4")
desc_path = Path("C:/Users/David/Videos/MarvelRivals/Output/THOR_Mar-Apr_2026_BATCH1/THOR_Mar-Apr_2026_BATCH1_description.txt")

if not video_path.exists():
    print(f"ERROR: Video not found: {video_path}")
    sys.exit(1)

if not desc_path.exists():
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
    title, description = parse_description_file(desc_path)
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
