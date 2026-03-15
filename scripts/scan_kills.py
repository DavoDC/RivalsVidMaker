"""Scan Thor batch clips for Quad+ KO timestamps."""
import subprocess, os, struct, tempfile, glob, shutil

FFMPEG = r"C:\Users\David\GitHubRepos\CompilationVidMaker\FFMPEG\ffmpeg.exe"
CLIPS  = r"C:\Users\David\Videos\MarvelRivals\Highlights\THOR"
CROP   = "fps=2,crop=iw*0.25:ih*0.20:iw*0.75:ih*0.41"
SKIP   = 4
VIVID_THRESH = 0.03
COOLDOWN = 2.0
TIERS = ["Kill","Double Kill","Triple Kill","Quad Kill","Penta Kill","Hexa Kill"]

BATCH1 = [
    "THOR_2026-02-01_23-06-24.mp4","THOR_2026-02-05_23-34-58.mp4","THOR_2026-02-05_23-35-47.mp4",
    "THOR_2026-02-06_21-25-38.mp4","THOR_2026-02-06_21-26-23.mp4","THOR_2026-02-06_21-27-07.mp4",
    "THOR_2026-02-06_21-38-51.mp4","THOR_2026-02-06_21-39-43.mp4","THOR_2026-02-06_22-38-56.mp4",
    "THOR_2026-02-06_22-39-48.mp4","THOR_2026-02-06_22-42-30.mp4","THOR_2026-02-15_22-39-21.mp4",
    "THOR_2026-02-15_23-00-22.mp4","THOR_2026-02-15_23-09-55.mp4","THOR_2026-02-15_23-21-47.mp4",
    "THOR_2026-02-15_23-36-49.mp4","THOR_2026-02-16_00-12-08.mp4","THOR_2026-02-17_23-24-35.mp4",
    "THOR_2026-02-17_23-25-25.mp4","THOR_2026-02-18_23-19-12.mp4","THOR_2026-02-18_23-20-39.mp4",
    "THOR_2026-02-20_01-02-03.mp4","THOR_2026-02-20_01-10-58.mp4","THOR_2026-02-20_01-15-20.mp4",
    "THOR_2026-02-20_01-18-26.mp4","THOR_2026-02-20_01-19-11.mp4","THOR_2026-02-20_01-20-03.mp4",
    "THOR_2026-02-20_23-50-11.mp4","THOR_2026-02-20_23-50-59.mp4","THOR_2026-02-20_23-52-42.mp4",
    "THOR_2026-02-21_00-09-43.mp4",
]
BATCH2 = [
    "THOR_2026-02-21_00-12-21.mp4","THOR_2026-02-21_19-02-00.mp4","THOR_2026-02-21_20-30-43.mp4",
    "THOR_2026-02-21_20-31-53.mp4","THOR_2026-02-21_20-46-38.mp4","THOR_2026-02-21_20-47-21.mp4",
    "THOR_2026-02-21_21-12-31.mp4","THOR_2026-02-21_22-18-09.mp4","THOR_2026-02-21_23-41-31.mp4",
    "THOR_2026-02-21_23-42-33.mp4","THOR_2026-02-21_23-43-50.mp4","THOR_2026-02-21_23-44-31.mp4",
    "THOR_2026-02-22_21-46-36.mp4","THOR_2026-02-22_23-46-11.mp4","THOR_2026-02-22_23-46-54.mp4",
    "THOR_2026-02-22_23-47-33.mp4","THOR_2026-02-22_23-48-21.mp4","THOR_2026-02-22_23-49-23.mp4",
    "THOR_2026-02-24_23-35-25.mp4","THOR_2026-02-24_23-37-54.mp4","THOR_2026-02-24_23-40-21.mp4",
    "THOR_2026-02-24_23-41-47.mp4","THOR_2026-02-24_23-42-46.mp4","THOR_2026-02-25_23-24-36.mp4",
    "THOR_2026-02-25_23-25-20.mp4","THOR_2026-02-25_23-26-43.mp4","THOR_2026-02-27_20-39-30.mp4",
    "THOR_2026-03-01_00-20-52.mp4","THOR_2026-03-01_22-38-49.mp4","THOR_2026-03-02_00-00-08.mp4",
    "THOR_2026-03-02_23-28-38.mp4","THOR_2026-03-03_22-54-23.mp4","THOR_2026-03-05_19-24-55.mp4",
]

def get_duration(path):
    r = subprocess.run([FFMPEG.replace("ffmpeg","ffprobe"),"-v","error","-show_entries",
        "format=duration","-of","default=noprint_wrappers=1:nokey=1",path],
        capture_output=True,text=True)
    try: return float(r.stdout.strip())
    except: return 0.0

def is_vivid(ppm_path):
    with open(ppm_path,"rb") as f:
        hdr = b""
        while True:
            c = f.read(1)
            if not c: return False
            hdr += c
            # read until we have magic + w + h + maxval
            parts = hdr.split()
            if len(parts) >= 4 and parts[0] == b"P6":
                try:
                    w,h,mx = int(parts[1]),int(parts[2]),int(parts[3])
                    break
                except: pass
        f.read(1)  # skip whitespace after maxval
        data = f.read(w*h*3)
    vivid = 0
    for i in range(0, len(data)-2, 3):
        r,g,b = data[i],data[i+1],data[i+2]
        mx2 = max(r,g,b); mn = min(r,g,b)
        if mx2 > 180 and (mx2-mn) > 100:
            vivid += 1
    return vivid / (w*h) > VIVID_THRESH

def scan_clip(clip_path, tmpdir):
    pat = os.path.join(tmpdir, "f_%04d.ppm")
    subprocess.run([FFMPEG,"-y","-loglevel","quiet","-ss",str(SKIP),"-i",clip_path,
        "-vf",CROP,"-f","image2",pat], capture_output=True)
    frames = sorted(glob.glob(os.path.join(tmpdir,"f_*.ppm")))
    events = []
    prev = False; cooldown = -1.0
    for fi, fp in enumerate(frames):
        t = SKIP + fi*0.5
        active = is_vivid(fp)
        if active and not prev and t >= cooldown:
            events.append(t)
            cooldown = t + COOLDOWN
        prev = active
    for f in frames: os.remove(f)
    return events

def fmt(s):
    s = int(s); return f"{s//60}:{s%60:02d}"

def process_batch(name, clips):
    print(f"\n=== {name} ===")
    tmpdir = tempfile.mkdtemp()
    running = 0.0
    results = []
    for clip in clips:
        path = os.path.join(CLIPS, clip)
        if not os.path.exists(path):
            print(f"  MISSING: {clip}"); dur = 0.0
        else:
            events = scan_clip(path, tmpdir)
            dur = get_duration(path)
            for i, t in enumerate(events):
                if i >= 3:  # index 3+ = Quad Kill+
                    tier = TIERS[i] if i < len(TIERS) else "Multi Kill"
                    ts = running + t
                    results.append((ts, tier, clip))
                    print(f"  {fmt(ts)}  {tier}  ({clip})")
            print(f"  {clip}: {len(events)} kills, dur={dur:.1f}s")
        running += dur
    shutil.rmtree(tmpdir, ignore_errors=True)
    print(f"\nQuad+ timestamps for {name}:")
    for ts, tier, clip in results:
        print(f"  {fmt(ts)} {tier}")

process_batch("BATCH1 (Thor Vid 1)", BATCH1)
process_batch("BATCH2 (Thor Vid 2)", BATCH2)
