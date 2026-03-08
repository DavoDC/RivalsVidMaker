// Command.cpp

// Header
#include "Command.h"
#include <chrono>

// Namespace mod
using namespace std;

// ### Constructors

Command::Command() :
    Command("ls")
{
    // Call constructor below with 'ls'
}

Command::Command(const string& progName) : 
    Command(progName, string()) 
{
    // Call constructor below with empty string.
}

Command::Command(const string& progName, const string& argument) : 
    Command(progName, StringV{argument})
{
    // Call constructor below with one argument
}

Command::Command(const string& progName, const StringV& argList) :
    progName(progName), argList(argList), duration(0)
{
    // Save arguments
}

// ### Public methods

void Command::run(bool showOutput) {

    // Log full command before running
    logRaw("[CMD] " + toString());

    // Get starting time
    auto startTime = chrono::high_resolution_clock::now();

    // Set security attributes
    SECURITY_ATTRIBUTES saAttr{};
    saAttr.nLength = sizeof(SECURITY_ATTRIBUTES);
    saAttr.bInheritHandle = TRUE;
    saAttr.lpSecurityDescriptor = nullptr;

    // Get output handle
    HANDLE stdOutRead, stdOutWrite;
    CreatePipe(&stdOutRead, &stdOutWrite, &saAttr, 0);
    SetHandleInformation(stdOutRead, HANDLE_FLAG_INHERIT, 0);

    // Set startup info
    STARTUPINFOA si{};
    si.cb = sizeof(STARTUPINFOA);
    si.hStdOutput = stdOutWrite;
    si.hStdError = stdOutWrite;
    si.dwFlags |= STARTF_USESTDHANDLES;

    // Process information reference
    PROCESS_INFORMATION pi{};

    // If process creation and execution successful
    if (CreateProcessA(
        nullptr, // nullptr to use the command string directly
        const_cast<char*>(toString().c_str()), // Command to be executed
        nullptr,  // Default process security attributes
        nullptr,  // Default process security attributes
        TRUE,     // Child process inherits handles
        0,        // Default creation flags
        nullptr,  // Use parent's environment block
        nullptr,  // Use parent's current directory
        &si,      // Startup information
        &pi       // Process information
    )) {
        CloseHandle(stdOutWrite); // Close the std output write handle
        consoleOutput = getStringFromStream(stdOutRead); // Extract std output
        CloseHandle(stdOutRead); // Close the std output read handle
        WaitForSingleObject(pi.hProcess, INFINITE); // Wait for the child process to exit
        CloseHandle(pi.hProcess); // Close the process handle
        CloseHandle(pi.hThread);  // Close the process's thread handle
    }
    else {
        // Else if execution fails, notify
        logRaw("[CMD ERROR] CreateProcessA failed for: " + toString());
        printErr("Command execution failed");
    }

    // Clean output
    replaceAll(consoleOutput, "\r", "");
    replaceAll(consoleOutput, "\n", "");

    // Always log command output
    logRaw("[CMD OUTPUT] " + (consoleOutput.empty() ? "(empty)" : consoleOutput));

    // Print output to console if wanted
    if (showOutput) {
        printOutput();
    }

    // Get stop time
    auto stopTime = chrono::high_resolution_clock::now();

    // Calculate duration and save
    auto rawDur = duration_cast<chrono::milliseconds>(stopTime - startTime);
    duration = double(rawDur.count()) / 1000.0;

    logRaw("[CMD TIME] " + formatTimeTaken(duration));
}

string Command::toString() const {
    
    // Initialize to program name
    string tempOutput = progName;

    // Append arguments
    for (const string& curArg : argList) {
        tempOutput.append(' ' + curArg);
    }

    // Return result
    return tempOutput;
}

void Command::printAsString() const {
    print(quoteS(" " + toString()));
}

string Command::getOutput() const {
    return consoleOutput;
}

void Command::printOutput() const {
    print("\n" + getOutput() + "\n");
}

double Command::getTimeTaken() const {
    return duration;
}

string Command::formatTimeTaken(const double duration) {
    return format("Time Taken: {} seconds", to_string(duration).erase(5));
}

void Command::printTimeTaken() const {
    print(formatTimeTaken(duration));
}

// ## Protected methods

void Command::updateArg(int argPosition, const string& newArgVal) {

    // If argument position is valid
    if (argPosition >= 0 && argPosition < argList.size()) {

        // Update argument at that position
        argList[argPosition] = newArgVal;
    } else {

        // Else if position invalid, notify and exit
        printErr("Invalid argument position", true);
    }
}

// ## Private methods

string Command::getStringFromStream(HANDLE streamHandle) const {
    constexpr DWORD bufferSize = 4096;
    string tempOutput;
    DWORD bytesRead = 0;
    char buffer[bufferSize];
    while (ReadFile(streamHandle, buffer, bufferSize, &bytesRead, nullptr) && bytesRead > 0) {
        tempOutput.append(buffer, bytesRead);
    }
    return (tempOutput.length() < 3) ? "Empty!" : tempOutput;
}