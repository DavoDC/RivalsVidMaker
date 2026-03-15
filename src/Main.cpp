// Main.cpp

#include "Common.h"
#include "Processor.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <map>
#include <chrono>
#include <ctime>
#include <windows.h>

using namespace std;

// Read a key=value config file, return map of keys to values
map<string, string> readConfig(const string& configPath) {
    map<string, string> cfg;
    ifstream file(configPath);
    if (!file.is_open()) {
        printErr("config.txt not found at: " + configPath, true);
    }
    string line;
    while (getline(file, line)) {
        if (line.empty() || line[0] == '#') continue;
        // Strip carriage return if present
        if (!line.empty() && line.back() == '\r') line.pop_back();
        auto eq = line.find('=');
        if (eq == string::npos) continue;
        cfg[line.substr(0, eq)] = line.substr(eq + 1);
    }
    return cfg;
}

// Build a timestamped log filename: data\logs\run_YYYYMMDD_HHMMSS.log
string makeLogPath() {
    auto now = chrono::system_clock::now();
    time_t t = chrono::system_clock::to_time_t(now);
    char buf[32];
    tm tmInfo{};
    localtime_s(&tmInfo, &t);
    strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", &tmInfo);
    return string("data\\logs\\run_") + buf + ".log";
}

// Set working directory to repo root (exe lives at Project/x64/Release/, go up 3 levels)
void setRepoRootAsWorkingDir() {
    char exeBuf[MAX_PATH];
    GetModuleFileNameA(NULL, exeBuf, MAX_PATH);
    fs::path repoRoot = fs::path(exeBuf)
        .parent_path()   // Release/
        .parent_path()   // x64/
        .parent_path()   // Project/
        .parent_path();  // repo root
    SetCurrentDirectoryA(repoRoot.string().c_str());
}

int main()
{
    // Fix relative paths — set CWD to repo root before anything else
    setRepoRootAsWorkingDir();

    // Init log before anything else
    initLog(makeLogPath());

    print("###### Welcome to CompilationVidMaker! ######");
    print("Automates batching, encoding, and YouTube description generation.");
    print("Log file: " + getLogPath());

    auto cfg = readConfig("config\\config.txt");
    string clipsPath  = cfg["ClipsPath"];
    string outputPath = cfg["OutputPath"];
    string ffmpegPath = cfg["FFMPEGPath"];
    int minBatchSecs  = cfg.count("MinBatchSeconds") ? stoi(cfg["MinBatchSeconds"]) : 10 * 60;

    logRaw("[CONFIG] ClipsPath       = " + clipsPath);
    logRaw("[CONFIG] OutputPath      = " + outputPath);
    logRaw("[CONFIG] FFMPEGPath      = " + ffmpegPath);
    logRaw("[CONFIG] MinBatchSeconds = " + to_string(minBatchSecs));

    Processor proc(clipsPath, ffmpegPath, outputPath, minBatchSecs);
    proc.run();

    print("\nLog saved to: " + getLogPath());
    print("\nPress Enter to exit...");
    cin.get();
}
