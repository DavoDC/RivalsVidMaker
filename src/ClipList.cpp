// ClipList.cpp

#include "ClipList.h"
#include "Command.h"
#include <algorithm>
#include <future>
#include <chrono>

using namespace std;

// Supported video extensions
static const StringV VIDEO_EXTS = { ".mp4", ".mov", ".mkv", ".avi", ".webm" };

ClipList::ClipList(const string& clipsPath, const string& ffprobePath) {

    if (!isPathValid(clipsPath)) {
        printErr("Clips folder not found: " + clipsPath, true);
    }

    print("Scanning clips folder: " + clipsPath);

    // Collect and sort clip files alphabetically
    vector<fs::path> clipPaths;
    for (const auto& entry : fs::directory_iterator(clipsPath)) {
        if (!entry.is_regular_file()) continue;
        string ext = entry.path().extension().string();
        transform(ext.begin(), ext.end(), ext.begin(), [](unsigned char c) { return (char)::tolower(c); });
        if (find(VIDEO_EXTS.begin(), VIDEO_EXTS.end(), ext) != VIDEO_EXTS.end()) {
            clipPaths.push_back(entry.path());
        }
    }
    sort(clipPaths.begin(), clipPaths.end());

    print("Found " + to_string(clipPaths.size()) + " video files. Probing durations in parallel...");
    logRaw("[SCAN] " + to_string(clipPaths.size()) + " files found in " + clipsPath);

    auto scanStart = chrono::high_resolution_clock::now();

    // Launch all ffprobe calls in parallel
    vector<future<int>> futures;
    futures.reserve(clipPaths.size());
    for (const auto& path : clipPaths) {
        futures.push_back(async(launch::async, &ClipList::getDurationSeconds,
            this, path.string(), ffprobePath));
    }

    // Collect results in order
    for (int i = 0; i < (int)clipPaths.size(); i++) {
        int dur = futures[i].get();
        string fp = clipPaths[i].string();
        string name = clipPaths[i].filename().string();
        if (dur > 0) {
            clips.emplace_back(fp, dur);
            logRaw("  [" + to_string(dur) + "s] " + name);
        } else {
            printErr("Could not read duration, skipping: " + name);
        }
    }

    auto scanEnd = chrono::high_resolution_clock::now();
    double scanSecs = chrono::duration_cast<chrono::milliseconds>(scanEnd - scanStart).count() / 1000.0;

    print("Loaded " + to_string(clips.size()) + " clips in " + to_string(scanSecs).substr(0, 4) + "s.");
    logRaw("[SCAN] Duration probe complete in " + to_string(scanSecs) + "s");
}

const vector<Clip>& ClipList::getClips() const {
    return clips;
}

int ClipList::getCount() const {
    return static_cast<int>(clips.size());
}

int ClipList::getDurationSeconds(const string& filePath, const string& ffprobePath) {
    Command cmd(ffprobePath, {
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        quoteD(filePath)
    });
    cmd.run();
    string output = cmd.getOutput();
    try {
        return static_cast<int>(stod(output));
    } catch (...) {
        return -1;
    }
}
