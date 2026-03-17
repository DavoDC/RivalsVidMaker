#pragma once

// Batcher.h

// ### Headers
#include "Common.h"
#include "Clip.h"
#include "ClipList.h"

// Target batch duration: 15 minutes
static constexpr int TARGET_BATCH_SECONDS = 15 * 60;

// Minimum batch duration to bother encoding — batches shorter than this are skipped
// Default: 10 minutes. Avoids generating tiny leftover batches.
static constexpr int MIN_BATCH_SECONDS = 10 * 60;

/**
 * @brief A batch of clips whose total duration is ~15 minutes.
*/
struct Batch {
    int batchNumber = 0;
    int totalDurationSeconds = 0;
    std::vector<Clip> clips;
};

/**
 * @brief Groups clips from a ClipList into ~15-minute batches.
*/
class Batcher {
public:
    // ### Constructor
    Batcher(const ClipList& clipList, int targetSeconds = TARGET_BATCH_SECONDS);

    // ### Public methods

    /**
     * @return All batches.
    */
    const std::vector<Batch>& getBatches() const;

    /**
     * @return Number of batches.
    */
    int getCount() const;

private:
    std::vector<Batch> batches;
};
