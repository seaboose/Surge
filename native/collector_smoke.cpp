#include "code_range_collector.hpp"
#include <iostream>
#include <stdexcept>
int main() {
  try {
    OwnedCollector collector(L"v1");
    require(collector.ranges().size() >= 2 && collector.ranges().size() <= 16,
            "Expected bounded declared ranges");
    require(collector.integrity_manifest().find("surge-integrity-manifest-v1") !=
                std::string::npos,
            "Missing versioned integrity manifest");
    HMODULE module = LoadLibraryExW(collector.path().c_str(), nullptr,
                                    LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
                                        LOAD_LIBRARY_SEARCH_SYSTEM32);
    require(module != nullptr, "Cannot load owned module");
    try {
      const auto rows = collector.snapshot(module);
      require(rows.size() == collector.ranges().size(), "Missing measured range");
      for (const auto &row : rows) {
        require(row.find("\"memory_status\":\"complete\"") != std::string::npos,
                "Range was not readable");
        require(row.find("scenario") == std::string::npos &&
                    row.find("phase") == std::string::npos,
                "Measurement depends on a test scenario");
      }
    } catch (...) {
      FreeLibrary(module);
      throw;
    }
    FreeLibrary(module);
    for (const auto &row : collector.snapshot(nullptr))
      require(row.find("\"memory_status\":\"not_loaded\"") != std::string::npos,
              "Unavailable module must be reported");
    bool rejected = false;
    try {
      collector.snapshot(GetModuleHandleW(nullptr));
    } catch (const std::exception &) {
      rejected = true;
    }
    require(rejected, "Unexpected module accepted");
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what();
    return 1;
  }
}
