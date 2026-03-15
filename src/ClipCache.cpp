// ClipCache.cpp

#include "ClipCache.h"
#include <fstream>
#include <sstream>

using namespace std;

const string ClipCache::CACHE_DIR = "data\\cache";

string ClipCache::getCachePath(const string& clipFilePath) {
    string stem = fs::path(clipFilePath).stem().string();
    return CACHE_DIR + "\\" + stem + ".cache";
}

bool ClipCache::exists(const string& clipFilePath) {
    return isFileNonEmpty(getCachePath(clipFilePath));
}

ClipScanResult ClipCache::load(const string& clipFilePath) {
    ClipScanResult result;
    ifstream file(getCachePath(clipFilePath));
    if (!file.is_open()) return result;

    string line;
    while (getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        if (!line.empty() && line.back() == '\r') line.pop_back();
        auto eq = line.find('=');
        if (eq == string::npos) continue;
        string key = line.substr(0, eq);
        string val = line.substr(eq + 1);

        if (key == "KillCount") {
            result.killCount = stoi(val);
        } else if (key == "KillTimestamps" && !val.empty()) {
            stringstream ss(val);
            string tok;
            while (getline(ss, tok, ',')) {
                result.killTimestamps.push_back(stod(tok));
            }
        }
    }
    return result;
}

void ClipCache::save(const string& clipFilePath, const ClipScanResult& result) {
    if (!isPathValid(CACHE_DIR)) {
        fs::create_directories(CACHE_DIR);
    }

    ofstream file(getCachePath(clipFilePath));
    if (!file.is_open()) {
        printErr("Could not write cache: " + getCachePath(clipFilePath));
        return;
    }

    file << "KillCount=" << result.killCount << "\n";
    file << "KillTimestamps=";
    for (int i = 0; i < (int)result.killTimestamps.size(); i++) {
        if (i > 0) file << ",";
        file << result.killTimestamps[i];
    }
    file << "\n";
}
