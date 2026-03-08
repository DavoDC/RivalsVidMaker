// Processor.cpp

#include "Processor.h"
#include "Command.h"
#include <chrono>
#include <iostream>
#include <windows.h>

using namespace std;
using namespace chrono;

Processor::Processor(const string& clipsPath,
                     const string& exePath,
                     const string& outputPath,
                     int minBatchSeconds)
    : clipsPath(clipsPath), exePath(exePath), outputPath(outputPath),
      minBatchSeconds(minBatchSeconds)
{
}

void Processor::run() {

    auto startTime = high_resolution_clock::now();

    string ffmpegPath  = exePath + "ffmpeg.exe";
    string ffprobePath = exePath + "ffprobe.exe";

    // Validate root clips path
    if (!isPathValid(clipsPath)) {
        printErr("Clips path not found: " + clipsPath, true);
    }

    // Create output folder if it doesn't exist
    if (!isPathValid(outputPath)) {
        fs::create_directories(outputPath);
        print("Created output folder: " + outputPath);
    }

    // Discover character subfolders (one level deep)
    vector<fs::path> charFolders;
    for (const auto& entry : fs::directory_iterator(clipsPath)) {
        if (entry.is_directory()) {
            charFolders.push_back(entry.path());
        }
    }
    sort(charFolders.begin(), charFolders.end());

    if (charFolders.empty()) {
        // No subfolders — treat clipsPath itself as a single character folder
        charFolders.push_back(fs::path(clipsPath));
    }

    // --- Character selection menu ---
    print("\nAvailable characters:");
    for (int i = 0; i < (int)charFolders.size(); i++) {
        print("  [" + to_string(i + 1) + "] " + charFolders[i].filename().string());
    }
    print("  [0] All characters");

    int choice = -1;
    while (choice < 0 || choice > (int)charFolders.size()) {
        print("\nEnter choice: ");
        cout.flush();
        cin >> choice;
        if (cin.fail() || choice < 0 || choice > (int)charFolders.size()) {
            cin.clear();
            cin.ignore(1000, '\n');
            print("Invalid choice, try again.");
            choice = -1;
        }
    }

    // Build list of folders to process
    vector<fs::path> toProcess;
    if (choice == 0) {
        toProcess = charFolders;
    } else {
        toProcess.push_back(charFolders[choice - 1]);
    }

    logRaw("[SELECTION] Processing " + to_string(toProcess.size()) + " character(s).");

    Encoder encoder(ffmpegPath, outputPath);
    DescriptionWriter descWriter(outputPath);

    int totalBatches = 0;

    for (const fs::path& charPath : toProcess) {
        string charName = charPath.filename().string();
        print("\n============================");
        print("Character: " + charName);
        print("============================");

        ClipList clipList(charPath.string(), ffprobePath);
        if (clipList.getCount() == 0) {
            print("No clips found, skipping.");
            continue;
        }

        Batcher batcher(clipList);

        int batchNum = 1;
        for (const Batch& batch : batcher.getBatches()) {
            int mins = batch.totalDurationSeconds / 60;
            int secs = batch.totalDurationSeconds % 60;
            string durStr = to_string(mins) + "m " + to_string(secs) + "s";

            print("\n--- " + charName + " Batch " + to_string(batchNum)
                + " of " + to_string(batcher.getCount()) + " (" + durStr + ") ---");

            // Skip batches shorter than minimum — YouTube algorithm targets ~15min
            if (batch.totalDurationSeconds < minBatchSeconds) {
                print("SKIPPED — too short (" + durStr + ", minimum is "
                    + to_string(minBatchSeconds / 60) + "m). Not worth uploading.");
                logRaw("[SKIP] " + charName + " batch " + to_string(batchNum)
                    + " skipped: " + durStr + " < " + to_string(minBatchSeconds / 60) + "m minimum.");
                batchNum++;
                continue;
            }

            vector<KillEvent> kills = KillDetector::detect(batch);
            if (!kills.empty()) {
                print("Kill events: " + to_string(kills.size()));
                for (const KillEvent& ev : kills) {
                    print("  " + ev.tier + " at " + to_string(ev.timestampSeconds)
                        + "s — " + ev.clipName);
                }
            }

            string outFile = encoder.encode(batch, charName);
            descWriter.write(batch, kills, charName);

            // Clean up intermediate concat list file
            string concatFile = outputPath + "\\" + charName + "_batch"
                + to_string(batch.batchNumber) + "_concat.txt";
            if (isPathValid(concatFile)) {
                fs::remove(concatFile);
                logRaw("[CLEANUP] Removed concat list: " + concatFile);
            }

            batchNum++;
            totalBatches++;
        }
    }

    // Summary
    auto stopTime = high_resolution_clock::now();
    double totalSecs = duration_cast<milliseconds>(stopTime - startTime).count() / 1000.0;

    print("\n=== Done ===");
    print("Characters processed: " + to_string(toProcess.size()));
    print("Total batches encoded: " + to_string(totalBatches));
    print("Output folder: " + outputPath);
    print(Command::formatTimeTaken(totalSecs));

    // Bell alert — encoding complete, check the video
    logRaw("[DONE] Encoding complete. Alerting user.");
    Beep(1000, 400);
    Beep(1200, 400);
    print("\n>>> Encoding complete! Please check the output video. <<<");
}
