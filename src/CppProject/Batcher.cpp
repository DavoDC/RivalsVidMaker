// Batcher.cpp

#include "Batcher.h"

using namespace std;

Batcher::Batcher(const ClipList& clipList, int targetSeconds) {

    Batch current;
    current.batchNumber = 1;

    for (const Clip& clip : clipList.getClips()) {
        int clipDur = clip.getDuration();

        // If adding this clip would exceed target AND current batch is non-empty, seal it
        if (!current.clips.empty()
            && (current.totalDurationSeconds + clipDur) > targetSeconds) {
            batches.push_back(current);
            current = Batch{};
            current.batchNumber = static_cast<int>(batches.size()) + 1;
        }

        current.clips.push_back(clip);
        current.totalDurationSeconds += clipDur;
    }

    // Add last batch if non-empty
    if (!current.clips.empty()) {
        batches.push_back(current);
    }

    // Print summary
    print("\nBatching complete: " + to_string(batches.size()) + " batch(es)");
    for (const Batch& b : batches) {
        int mins = b.totalDurationSeconds / 60;
        int secs = b.totalDurationSeconds % 60;
        print("  Batch " + to_string(b.batchNumber) + ": "
            + to_string(b.clips.size()) + " clips, "
            + to_string(mins) + "m " + to_string(secs) + "s");
    }
}

const vector<Batch>& Batcher::getBatches() const {
    return batches;
}

int Batcher::getCount() const {
    return static_cast<int>(batches.size());
}
