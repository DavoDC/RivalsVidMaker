#pragma once

// Common.h

// Global Libraries
#include <string>
#include <vector>
#include <format>
#include <filesystem>
#include <functional>
#include <fstream>

// String Vector Type
using StringV = std::vector<std::string>;

// Seconds Type
using Seconds = int;

// Filesystem Namespace Mod
namespace fs = std::filesystem;

// ### Function Declarations


// # Log Functions

/**
 * @brief Initialise the log file. Call once at startup.
 *        All print/printSuccess/printErr calls mirror output here automatically.
 * @param logPath Full path to the log file.
*/
void initLog(const std::string& logPath);

/**
 * @brief Write a raw line directly to the log file (no console output).
*/
void logRaw(const std::string& s);

/**
 * @return Path of the current log file.
*/
std::string getLogPath();


// # Printing Functions

/**
 * @brief Prints a given string.
 * @param s The string to print.
 * @param useEndl Toggle end line usage (Default: false).
*/
void print(const std::string& s, bool useEndl = false);

/**
 * @brief Prints a success message.
 * @param msg The message.
*/
void printSuccess(const std::string& msg);

/**
 * @brief Prints an error message.
 * @param msg The message.
 * @param exitAfter Toggle exiting after printing (Default: false).
*/
void printErr(const std::string& msg, bool exitAfter = false);


// # String Functions

/**
 * @brief Removes all substrings from a given string.
 * @param source The original string.
 * @param from The substring to replace.
 * @param to The string to be substituted in.
*/
void replaceAll(std::string& source, const std::string& from, const std::string& to);

/**
 * @param source The string to search in.
 * @param query The search query.
 * @return True if the source contains the query.
*/
bool contains(const std::string& source, const std::string& query);

/**
 * @return The given string surrounded by a pair of single quotes.
*/
std::string quoteS(const std::string& s);

/**
 * @return The given string surrounded by a pair of double quotes.
*/
std::string quoteD(const std::string& s);


// # Filesystem Functions

/**
 * @return Cleaned path for use with fs::path functions.
*/
std::string getCleanPath(const std::string& path);

/**
 * @return True if the given path exists.
*/
bool isPathValid(const std::string& path);

/**
 * @return True if the given file path exists and is non-empty.
*/
bool isFileNonEmpty(const std::string& path);