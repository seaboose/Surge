#include "code_range_collector.hpp"
#include <iostream>
#include <sstream>
#include <stdexcept>
struct Module {
  Module() = default;
  Module(const Module &) = delete;
  Module &operator=(const Module &) = delete;
  HMODULE value = nullptr;
  ~Module() {
    if (value)
      FreeLibrary(value);
  }
};
struct ScenarioChange {
  ScenarioChange() = default;
  ScenarioChange(const ScenarioChange &) = delete;
  ScenarioChange &operator=(const ScenarioChange &) = delete;
  unsigned char *address = nullptr;
  unsigned char original = 0;
  DWORD protection = 0;
  bool changed = false, inaccessible = false;
  void restore() {
    DWORD ignored = 0;
    if (changed) {
      require(VirtualProtect(address, 1, PAGE_EXECUTE_READWRITE, &ignored) != 0,
              "Cannot restore lab bytes");
      *address = original;
      require(FlushInstructionCache(GetCurrentProcess(), address, 1) != 0,
              "Cannot flush restored lab bytes");
    }
    if (changed || inaccessible)
      require(VirtualProtect(address, 1, protection, &ignored) != 0,
              "Cannot restore lab page protection");
    changed = inaccessible = false;
  }
  ~ScenarioChange() {
    try {
      restore();
    } catch (...) { /* Process exit reclaims this owned image. */
    }
  }
};
int wmain(int argc, wchar_t **argv) {
  try {
    require(argc == 5 && std::wstring(argv[1]) == L"--build" &&
                std::wstring(argv[3]) == L"--scenario",
            "Use --build v1|v2 --scenario "
            "clean|memory-change|boundary-change|secondary-change|unreadable|unloaded");
    const std::wstring build = argv[2], scenario = argv[4];
    require(scenario == L"clean" || scenario == L"memory-change" || scenario == L"boundary-change" ||
                scenario == L"secondary-change" || scenario == L"unreadable" ||
                scenario == L"unloaded",
            "Unsupported scenario");
    OwnedCollector collector(build);
    Module module;
    module.value = LoadLibraryExW(collector.path().c_str(), nullptr,
                                  LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
                                      LOAD_LIBRARY_SEARCH_SYSTEM32);
    require(module.value != nullptr, "Owned DLL load failed");
    auto address =
        reinterpret_cast<unsigned char *>(module.value) +
        collector.ranges()[scenario == L"secondary-change" ? 1 : 0].rva;
    if (scenario == L"boundary-change")
      address += collector.ranges()[0].expected.size() - 1;
    std::vector<std::string> observations;
    auto observe = [&](const char *phase) {
      for (auto row : collector.snapshot(module.value)) {
        row.pop_back();
        row += ",\"phase\":" + quote(phase) +
               ",\"build\":" + quote(utf8(build)) +
               ",\"scenario\":" + quote(utf8(scenario)) + "}";
        observations.push_back(std::move(row));
      }
    };
    observe("initial");
    ScenarioChange change;
    change.address = address;
    if (scenario == L"memory-change" || scenario == L"boundary-change" || scenario == L"secondary-change") {
      require(VirtualProtect(address, 1, PAGE_EXECUTE_READWRITE,
                             &change.protection) != 0,
              "Cannot prepare owned lab mutation");
      change.original = *address;
      change.changed = true;
      *address ^= 1;
      require(FlushInstructionCache(GetCurrentProcess(), address, 1) != 0,
              "Cannot flush owned lab mutation");
      DWORD ignored = 0;
      require(VirtualProtect(address, 1, change.protection, &ignored) != 0,
              "Cannot restore lab mutation protection");
    } else if (scenario == L"unreadable") {
      require(VirtualProtect(address, 1, PAGE_NOACCESS, &change.protection) !=
                  0,
              "Cannot prepare owned unreadable page");
      change.inaccessible = true;
    } else if (scenario == L"unloaded") {
      require(FreeLibrary(module.value) != 0, "Cannot unload owned DLL");
      module.value = nullptr;
    }
    observe("sample");
    change.restore();
    if (!module.value) {
      module.value = LoadLibraryExW(collector.path().c_str(), nullptr,
                                    LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
                                        LOAD_LIBRARY_SEARCH_SYSTEM32);
      require(module.value != nullptr, "Cannot reload owned DLL");
    }
    observe("restored");

    std::ostringstream output;
    output << "{\"schema\":\"native-code-capture-v2\",\"ranges\":"
           << collector.manifest() << ",\"integrity_manifest\":"
           << collector.integrity_manifest() << ",\"observations\":[";
    for (std::size_t i = 0; i < observations.size(); ++i)
      output << (i ? "," : "") << observations[i];
    output << "]}\n";
    HANDLE file =
        CreateFileW(L"exported_code_audit.json", GENERIC_WRITE, 0, nullptr,
                    CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    require(file != INVALID_HANDLE_VALUE, "Cannot create new code report");
    const auto text = output.str();
    DWORD written = 0;
    const bool saved =
        WriteFile(file, text.data(), static_cast<DWORD>(text.size()), &written,
                  nullptr) &&
        written == text.size() && FlushFileBuffers(file);
    CloseHandle(file);
    require(saved, "Code report write incomplete");
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
