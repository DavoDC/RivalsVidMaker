// Clip.cpp

#include "Clip.h"

using namespace std;

Clip::Clip(const string& filePath, int durationSeconds)
    : filePath(filePath),
      fileName(fs::path(filePath).filename().string()),
      durationSeconds(durationSeconds)
{
}

const string& Clip::getFilePath() const {
    return filePath;
}

const string& Clip::getFileName() const {
    return fileName;
}

int Clip::getDuration() const {
    return durationSeconds;
}
