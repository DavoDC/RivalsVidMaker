#pragma once

// ClipList.h

// ### Headers
#include "Common.h"
#include "Clip.h"

/**
 * @brief Scans the clips folder and builds a list of Clip objects with durations.
*/
class ClipList {
public:
    // ### Constructor
    ClipList(const std::string& clipsPath, const std::string& ffprobePath);

    // ### Public methods

    /**
     * @return All loaded clips.
    */
    const std::vector<Clip>& getClips() const;

    /**
     * @return Number of clips loaded.
    */
    int getCount() const;

private:
    std::vector<Clip> clips;

    /**
     * @brief Query a clip's duration in seconds via ffprobe.
    */
    int getDurationSeconds(const std::string& filePath, const std::string& ffprobePath);
};
