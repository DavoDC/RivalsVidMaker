#ifndef NOMINMAX
#define NOMINMAX
#endif

#include "KillDetector.h"
#include "Command.h"
#include <fstream>
#include <algorithm>

using namespace std;

// --- Banner crop region (as fraction of video dimensions) ---
// The KO prompt sits in the right portion of the screen, vertically centred-upper.
// These values were calibrated from example screenshots (see examples/ko_frames/).
//   X start : 75% of width
//   Width   : 25% of width  (covers to right edge)
//   Y start : 41% of height
//   Height  : 20% of height (41% -> 61%)
static const char* BANNER_CROP = "fps=2,crop=iw*0.25:ih*0.20:iw*0.75:ih*0.41";

// Minimum fraction of crop pixels that must be vivid/saturated to count as banner active
static constexpr double VIVID_THRESHOLD = 0.03;

// Minimum gap (seconds) between two distinct KO events — prevents double-counting
// a sustained banner as multiple events
static constexpr double EVENT_COOLDOWN_SECS = 2.0;

// Skip the first N seconds of each clip — the KO banner never appears this early
// (clips typically start 4-5s before the first kill)
static constexpr double SCAN_START_SECS = 4.0;

// Temp directory for extracted PPM frames (cleaned after each clip scan)
static const string TEMP_DIR = "data\\cache\\temp";

// ---

vector<KillEvent> KillDetector::detect(const Batch& batch, const string& ffmpegPath) {
    vector<KillEvent> events;
    int runningSeconds = 0;

    for (const Clip& clip : batch.clips) {
        ClipScanResult scan;

        if (ClipCache::exists(clip.getFilePath())) {
            scan = ClipCache::load(clip.getFilePath());
            logRaw("[CACHE HIT] " + clip.getFileName()
                + " — " + to_string(scan.killCount) + " kills");
        } else {
            print("  Scanning: " + clip.getFileName() + "...");
            scan = scanClip(clip, ffmpegPath);
            ClipCache::save(clip.getFilePath(), scan);
            logRaw("[SCANNED] " + clip.getFileName()
                + " — " + to_string(scan.killCount) + " kills");
        }

        // Emit a KillEvent for each event at Quad Kill (index 3) and above
        for (int i = 3; i < scan.killCount && i < (int)scan.killTimestamps.size(); i++) {
            KillEvent ev;
            ev.tier = tierName(i);
            ev.timestampSeconds = runningSeconds + static_cast<int>(scan.killTimestamps[i]);
            ev.clipName = clip.getFileName();
            events.push_back(ev);
        }

        runningSeconds += clip.getDuration();
    }

    return events;
}

ClipScanResult KillDetector::scanClip(const Clip& clip, const string& ffmpegPath) {
    ClipScanResult result;

    // Ensure temp dir exists and is clean
    if (!isPathValid(TEMP_DIR)) {
        fs::create_directories(TEMP_DIR);
    } else {
        for (const auto& entry : fs::directory_iterator(TEMP_DIR)) {
            fs::remove(entry.path());
        }
    }

    // Extract frames: skip first ~4s (no banner there), 2fps, banner crop, output as PPM
    string framePat = TEMP_DIR + "\\frame_%04d.ppm";
    Command cmd(ffmpegPath, {
        "-y",
        "-loglevel", "quiet",
        "-ss",       to_string(static_cast<int>(SCAN_START_SECS)),
        "-i",        quoteD(clip.getFilePath()),
        "-vf",       quoteD(string(BANNER_CROP)),
        "-f",        "image2",
        quoteD(framePat)
    });
    cmd.run();

    // Collect and sort extracted frame paths
    vector<fs::path> frames;
    if (isPathValid(TEMP_DIR)) {
        for (const auto& entry : fs::directory_iterator(TEMP_DIR)) {
            if (entry.path().extension() == ".ppm") {
                frames.push_back(entry.path());
            }
        }
    }
    sort(frames.begin(), frames.end());

    if (frames.empty()) {
        logRaw("[SCAN] No frames extracted for: " + clip.getFileName());
        return result;
    }

    // Detect rising edges (banner inactive -> active) = distinct KO events
    bool prevActive = false;
    double cooldownEnd = -1.0;

    for (int fi = 0; fi < (int)frames.size(); fi++) {
        double t = SCAN_START_SECS + fi * 0.5;  // 2fps → 0.5s per frame; offset by skip
        bool active = isFrameBannerActive(frames[fi].string());

        if (active && !prevActive && t >= cooldownEnd) {
            result.killTimestamps.push_back(t);
            cooldownEnd = t + EVENT_COOLDOWN_SECS;
        }
        prevActive = active;
    }
    result.killCount = static_cast<int>(result.killTimestamps.size());

    // Clean up temp frames
    for (const auto& entry : fs::directory_iterator(TEMP_DIR)) {
        fs::remove(entry.path());
    }

    return result;
}

bool KillDetector::isFrameBannerActive(const string& ppmPath) {
    ifstream file(ppmPath, ios::binary);
    if (!file.is_open()) return false;

    // Parse PPM P6 header: magic, width, height, maxval (skip comment lines)
    string magic;
    file >> magic;
    if (magic != "P6") return false;

    // Skip comment lines (start with #)
    int w = 0, h = 0, maxVal = 0;
    string token;
    while (file >> token) {
        if (token[0] == '#') {
            // skip rest of comment line
            file.ignore(4096, '\n');
            continue;
        }
        w = stoi(token);
        break;
    }
    file >> h >> maxVal;
    file.ignore(1);  // skip single whitespace after maxval

    if (w <= 0 || h <= 0 || maxVal <= 0) return false;

    int total = w * h;
    int vivid = 0;

    uint8_t rgb[3];
    for (int i = 0; i < total; i++) {
        if (!file.read(reinterpret_cast<char*>(rgb), 3)) break;
        int r = rgb[0], g = rgb[1], b = rgb[2];
        int mx = std::max(r, std::max(g, b));
        int mn = std::min(r, std::min(g, b));
        // Vivid/saturated pixel: bright (mx > 180) with high colour spread (mx-mn > 100)
        // Captures vivid cyan (Thor), vivid gold (Squirrel Girl), etc.
        // Rejects grey walls, muted backgrounds.
        if (mx > 180 && (mx - mn) > 100) {
            vivid++;
        }
    }

    double ratio = static_cast<double>(vivid) / total;
    return ratio > VIVID_THRESHOLD;
}

string KillDetector::tierName(int killIndex) {
    static const string names[] = {
        "Kill", "Double Kill", "Triple Kill",
        "Quad Kill", "Penta Kill", "Hexa Kill"
    };
    if (killIndex >= 0 && killIndex < 6) return names[killIndex];
    return "Multi Kill";
}
