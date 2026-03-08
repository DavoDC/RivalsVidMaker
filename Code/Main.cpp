// Main.cpp

#include "Common.h"
#include "Processor.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include <map>
#include <chrono>
#include <ctime>

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

// Build a timestamped log filename: logs\run_YYYYMMDD_HHMMSS.log
string makeLogPath() {
    auto now = chrono::system_clock::now();
    time_t t = chrono::system_clock::to_time_t(now);
    char buf[32];
    strftime(buf, sizeof(buf), "%Y%m%d_%H%M%S", localtime(&t));
    return string("logs\\run_") + buf + ".log";
}

int main()
{
    // Init log before anything else
    initLog(makeLogPath());

    print("###### Welcome to CompilationVidMaker! ######");
    print("Automates batching, encoding, and YouTube description generation.");
    print("Log file: " + getLogPath());

    auto cfg = readConfig("config.txt");
    string clipsPath  = cfg["ClipsPath"];
    string outputPath = cfg["OutputPath"];
    string ffmpegPath = cfg["FFMPEGPath"];

    logRaw("[CONFIG] ClipsPath  = " + clipsPath);
    logRaw("[CONFIG] OutputPath = " + outputPath);
    logRaw("[CONFIG] FFMPEGPath = " + ffmpegPath);

    Processor proc(clipsPath, ffmpegPath, outputPath);
    proc.run();

    print("\nLog saved to: " + getLogPath());
    print("\nPress Enter to exit...");
    cin.get();
}
