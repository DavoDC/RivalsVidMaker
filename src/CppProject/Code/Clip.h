#pragma once

// Clip.h

// ### Headers
#include "Common.h"

/**
 * @brief Represents a single video clip file.
*/
class Clip {
public:
    // ### Constructor
    Clip(const std::string& filePath, int durationSeconds);

    // ### Public methods

    /**
     * @return Full file path.
    */
    const std::string& getFilePath() const;

    /**
     * @return Just the filename (no directory).
    */
    const std::string& getFileName() const;

    /**
     * @return Duration in seconds.
    */
    int getDuration() const;

private:
    std::string filePath;
    std::string fileName;
    int durationSeconds;
};
