// DescriptionWriter.cpp

#include "DescriptionWriter.h"
#include <fstream>
#include <iomanip>
#include <sstream>
#include <algorithm>

using namespace std;

DescriptionWriter::DescriptionWriter(const string& outputPath)
    : outputPath(outputPath)
{
}

void DescriptionWriter::write(const Batch& batch, const vector<KillEvent>& kills, const string& charName) {

    string outFile = outputPath + "\\" + charName + "_batch" + to_string(batch.batchNumber) + "_description.txt";
    ofstream file(outFile);

    if (!file.is_open()) {
        printErr("Could not write description file: " + outFile);
        return;
    }

    // Capitalise character name for display
    string displayName = charName;
    transform(displayName.begin(), displayName.end(), displayName.begin(), [](unsigned char c) { return (char)::toupper(c); });

    int totalMins = batch.totalDurationSeconds / 60;
    int totalSecs = batch.totalDurationSeconds % 60;

    // --- Title suggestion (ready to paste as YouTube title) ---
    file << "=== TITLE ===\n";
    file << "Marvel Rivals " << displayName << " Highlights Part " << batch.batchNumber << "\n\n";

    // --- Description body ---
    file << "=== DESCRIPTION ===\n";
    file << "Marvel Rivals " << displayName << " highlights compilation — Part " << batch.batchNumber << "\n";
    file << "Duration: " << totalMins << "m " << totalSecs << "s\n\n";

    // --- Timestamps (only if kills detected) ---
    if (!kills.empty()) {
        file << "Timestamps:\n";
        for (const KillEvent& ev : kills) {
            file << formatTimestamp(ev.timestampSeconds) << " " << ev.tier << "\n";
        }
        file << "\n";
    }

    // --- Clip list ---
    file << "Clips (" << batch.clips.size() << "):\n";
    for (size_t i = 0; i < batch.clips.size(); i++) {
        file << (i + 1) << ". " << batch.clips[i].getFileName() << "\n";
    }

    file.close();
    printSuccess("Description written: " + outFile);
}

string DescriptionWriter::formatTimestamp(int seconds) {
    int h = seconds / 3600;
    int m = (seconds % 3600) / 60;
    int s = seconds % 60;

    ostringstream oss;
    if (h > 0) {
        oss << h << ":" << setw(2) << setfill('0') << m << ":" << setw(2) << setfill('0') << s;
    } else {
        oss << m << ":" << setw(2) << setfill('0') << s;
    }
    return oss.str();
}
