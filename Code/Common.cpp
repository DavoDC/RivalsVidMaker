// Common.cpp

// Header file
#include "Common.h"

// ### Libraries
#include <iostream>
#include <iomanip>
#include <ranges>
#include <string_view>
#include <chrono>
#include <ctime>
#include <sstream>

// Namespace mods
using namespace std;


// ### Log State

static ofstream gLogFile;
static string gLogPath;

void initLog(const string& logPath) {
    gLogPath = logPath;

    // Ensure parent directory exists
    fs::create_directories(fs::path(logPath).parent_path());

    gLogFile.open(logPath, ios::out | ios::trunc);
    if (!gLogFile.is_open()) {
        cerr << "WARNING: Could not open log file: " << logPath << "\n";
    }

    // Header
    auto now = chrono::system_clock::now();
    time_t t = chrono::system_clock::to_time_t(now);
    char buf[64];
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", localtime(&t));
    logRaw("=== CompilationVidMaker Log ===");
    logRaw("Started: " + string(buf));
    logRaw("Log file: " + logPath);
    logRaw("================================");
}

void logRaw(const string& s) {
    if (gLogFile.is_open()) {
        gLogFile << s << "\n";
        gLogFile.flush();
    }
}

string getLogPath() {
    return gLogPath;
}


// ### Function Definitions

// # Printing Functions

// Internal: write to both console and log
static void output(const string& s) {
    cout << "\n" << s;
    logRaw(s);
}

void print(const string& s, bool useEndl)
{
    cout << "\n" << s;
    logRaw(s);
    if (useEndl) {
        cout << endl;
    }
}

// Private helper
void printMessage(char startSymbol, const string& type, const string& msg)
{
    print(string(3, startSymbol) + " " + type + " " + quoteD(msg) + "!");
}

void printSuccess(const string& msg)
{
    printMessage('#', "SUCCESS", msg);
}

void printErr(const string& msg, bool exitAfter)
{
    printMessage('!', "ERROR", msg);

    if (exitAfter) {
        print("\n");
        logRaw("=== EXITING DUE TO ERROR ===");
        exit(EXIT_FAILURE);
    }
}


// # String Functions

void replaceAll(string& source, const string& from, const string& to)
{
    string newString;
    newString.reserve(source.length()); // Avoids a few memory allocations
    string::size_type lastPos = 0;
    string::size_type findPos;
    while (string::npos != (findPos = source.find(from, lastPos)))
    {
        newString.append(source, lastPos, findPos - lastPos);
        newString += to;
        lastPos = findPos + from.length();
    }
    newString += source.substr(lastPos);
    source.swap(newString);
}

bool contains(const string& source, const string& query)
{
    return source.find(query) != string::npos;
}

string quoteS(const string& s)
{
    return "'" + s + "'";
}

string quoteD(const string& s)
{
    return "\"" + s + "\"";
}


// # Filesystem Functions

string getCleanPath(const string& path)
{
    // Remove surrounding quotes if they exist
    string cleanedPath = path;
    if (!cleanedPath.empty()
        && cleanedPath.front() == '"'
        && cleanedPath.back() == '"') {
        cleanedPath = cleanedPath.substr(1, cleanedPath.size() - 2);
    }
    return cleanedPath;
}

bool isPathValid(const string& path) {
    return fs::exists(fs::path(getCleanPath(path)));
}

bool isFileNonEmpty(const string& path) {

    // If file exists
    string cleanPath = getCleanPath(path);
    if (isPathValid(cleanPath)) {

        // Return true if non-empty,  false if empty
        return fs::file_size(cleanPath) != 0;
    } else {

        // Else if file doesn't exist, return false
        return false;
    }
}
