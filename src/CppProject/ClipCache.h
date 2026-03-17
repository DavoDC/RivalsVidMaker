#pragma once

// ClipCache.h
// Saves and loads per-clip KO scan results to avoid re-scanning videos.
// Cache files live in ClipCache/<stem>.cache next to the executable root.

#include "Common.h"

/**
 * @brief Result of scanning a clip's video frames for KO banner events.
*/
struct ClipScanResult {
    int killCount = 0;                      // Total KO events detected (1=Kill, 2=Double, ..., 4=Quad)
    std::vector<double> killTimestamps;     // Seconds within clip of each event (rising edge)
};

/**
 * @brief Reads and writes per-clip scan cache files.
 *        Format: ClipCache/<filename_stem>.cache
*/
class ClipCache {
public:
    static const std::string CACHE_DIR;

    /**
     * @return True if a valid cache file exists for this clip.
    */
    static bool exists(const std::string& clipFilePath);

    /**
     * @brief Load cached scan result for a clip.
    */
    static ClipScanResult load(const std::string& clipFilePath);

    /**
     * @brief Save scan result to cache for a clip.
    */
    static void save(const std::string& clipFilePath, const ClipScanResult& result);

private:
    static std::string getCachePath(const std::string& clipFilePath);
};
