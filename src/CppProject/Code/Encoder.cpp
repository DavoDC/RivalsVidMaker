// Encoder.cpp

#include "Encoder.h"
#include "Command.h"
#include <fstream>

using namespace std;

Encoder::Encoder(const string& ffmpegPath, const string& outputPath)
    : ffmpegPath(ffmpegPath), outputPath(outputPath)
{
    nvencAvailable = checkNvenc();
    if (nvencAvailable) {
        print("GPU encoder: NVENC (h264_nvenc) detected — using GPU encoding.");
    } else {
        print("GPU encoder: NVENC not available — falling back to CPU (libx264).");
    }
}

string Encoder::encode(const Batch& batch, const string& charName) {

    string listFile = writeConcatList(batch, charName);
    string outFile = outputPath + "\\" + charName + "_batch" + to_string(batch.batchNumber) + ".mp4";

    // Build ffmpeg args
    // -f concat -safe 0 -i list.txt
    // GPU: -c:v h264_nvenc -preset p4 -rc vbr -cq 19 -b:v 0
    // CPU: -c:v libx264 -preset fast -crf 18
    // Audio: -c:a aac -b:a 192k
    // -movflags +faststart (YouTube optimisation)
    StringV args = {
        "-y",                            // Overwrite output without asking
        "-f", "concat",
        "-safe", "0",
        "-i", quoteD(listFile),
    };

    if (nvencAvailable) {
        args.insert(args.end(), {
            "-c:v", "h264_nvenc",
            "-preset", "p4",             // Balanced quality/speed preset
            "-rc", "vbr",
            "-cq", "19",                 // Quality level (lower = better, ~19 is high quality)
            "-b:v", "0",
        });
    } else {
        args.insert(args.end(), {
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
        });
    }

    args.insert(args.end(), {
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        quoteD(outFile)
    });

    print("\nEncoding " + charName + " batch " + to_string(batch.batchNumber) + "...");
    Command cmd(ffmpegPath, args);
    cmd.run(false);   // Output goes to log only — console stays clean
    cmd.printTimeTaken();

    printSuccess("Encoded: " + outFile);
    return outFile;
}

string Encoder::writeConcatList(const Batch& batch, const string& charName) {
    string listPath = outputPath + "\\" + charName + "_batch" + to_string(batch.batchNumber) + "_concat.txt";
    ofstream file(listPath);

    for (const Clip& clip : batch.clips) {
        // ffmpeg concat format: file 'path'
        // Use forward slashes and escape single quotes
        string fp = clip.getFilePath();
        replace(fp.begin(), fp.end(), '\\', '/');
        file << "file '" << fp << "'\n";
    }

    file.close();
    return listPath;
}

bool Encoder::checkNvenc() {
    // ffmpeg -encoders 2>/dev/null | grep nvenc
    Command cmd(ffmpegPath, StringV{ "-encoders" });
    cmd.run();
    return contains(cmd.getOutput(), "h264_nvenc");
}
