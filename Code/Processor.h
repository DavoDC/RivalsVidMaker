#pragma once

// Processor.h

// ### Headers
#include "Common.h"
#include "ClipList.h"
#include "Batcher.h"
#include "Encoder.h"
#include "DescriptionWriter.h"
#include "KillDetector.h"

/**
 * @brief Orchestrates the full pipeline:
 *        ClipList -> Batcher -> per batch: KillDetector, Encoder, DescriptionWriter
*/
class Processor {
public:
    // ### Constructor
    Processor(const std::string& clipsPath,
              const std::string& exePath,
              const std::string& outputPath,
              int minBatchSeconds = 10 * 60);

    // ### Public methods

    /**
     * @brief Run the full pipeline.
    */
    void run();

private:
    std::string clipsPath;
    std::string exePath;
    std::string outputPath;
    int minBatchSeconds;
};
