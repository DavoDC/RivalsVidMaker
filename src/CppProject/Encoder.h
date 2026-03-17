#pragma once

// Encoder.h

// ### Headers
#include "Common.h"
#include "Batcher.h"

/**
 * @brief Encodes a batch of clips into a single MP4 using FFmpeg.
 *        Uses NVENC (GPU) for fast hardware-accelerated encoding.
 *        Falls back to CPU (libx264) if NVENC is unavailable.
*/
class Encoder {
public:
    // ### Constructor
    Encoder(const std::string& ffmpegPath, const std::string& outputPath);

    // ### Public methods

    /**
     * @brief Encode a batch into one output MP4.
     * @param charName Character name used in output filename.
     * @return Path to the output file.
    */
    std::string encode(const Batch& batch, const std::string& charName);

private:
    std::string ffmpegPath;
    std::string outputPath;
    bool nvencAvailable;

    /**
     * @brief Write a concat list file for ffmpeg concat demuxer.
     * @return Path to the written list file.
    */
    std::string writeConcatList(const Batch& batch, const std::string& charName);

    /**
     * @brief Probe ffmpeg to check if h264_nvenc encoder is available.
    */
    bool checkNvenc();
};
