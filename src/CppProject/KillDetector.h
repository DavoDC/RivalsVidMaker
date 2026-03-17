#pragma once

// KillDetector.h
// Detects KO banner events in video frames using a saturation-based heuristic.
// The KO banner appears at a fixed screen position (right ~25%, y 41-61%) and is
// always vivid/saturated regardless of character (Thor=cyan, Squirrel Girl=gold, etc.).
// Results are cached per-clip in ClipCache/ to avoid re-scanning.

#include "Common.h"
#include "Batcher.h"
#include "ClipCache.h"

/**
 * @brief A detected multi-kill event within a batch.
*/
struct KillEvent {
    std::string tier;           // e.g. "Quad Kill"
    int timestampSeconds = 0;   // Offset from start of the batch
    std::string clipName;       // Filename of the clip it was found in
};

/**
 * @brief Scans clip video frames for KO banner events and records timestamps.
 *        Uses ClipCache to skip re-scanning already-processed clips.
 *        Only emits KillEvents for Quad Kill and above.
*/
class KillDetector {
public:
    /**
     * @brief Scan a batch and return all Quad+ kill events with batch-relative timestamps.
     * @param batch The batch to scan.
     * @param ffmpegPath Full path to ffmpeg.exe.
    */
    static std::vector<KillEvent> detect(const Batch& batch, const std::string& ffmpegPath);

private:
    /**
     * @brief Scan a single clip's frames for KO events. Uses cache if available.
    */
    static ClipScanResult scanClip(const Clip& clip, const std::string& ffmpegPath);

    /**
     * @brief Analyse one PPM frame: returns true if the KO banner appears active.
     *        Heuristic: vivid/saturated pixels (max channel > 180, max-min > 100)
     *        exceed 3% of the crop frame area.
    */
    static bool isFrameBannerActive(const std::string& ppmPath);

    /**
     * @brief Map 0-based kill index to tier label (0=Kill, 1=Double Kill, ..., 3=Quad Kill).
    */
    static std::string tierName(int killIndex);
};
