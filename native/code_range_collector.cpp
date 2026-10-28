#include "code_range_collector.hpp"
#include "code_range_pe.hpp"
#include <bcrypt.h>
#include <chrono>
#include <iomanip>
#include <sstream>
struct Crypto {
  Crypto() = default;
  Crypto(const Crypto &) = delete;
  Crypto &operator=(const Crypto &) = delete;
  BCRYPT_ALG_HANDLE algorithm = nullptr;
  BCRYPT_HASH_HANDLE hash = nullptr;
  ~Crypto() {
    if (hash)
      BCryptDestroyHash(hash);
    if (algorithm)
      BCryptCloseAlgorithmProvider(algorithm, 0);
  }
};
void require(bool value, const char *message) {
  if (!value)
    throw std::runtime_error(message);
}
std::string hex(const std::vector<unsigned char> &bytes) {
  std::ostringstream out;
  for (auto c : bytes)
    out << std::hex << std::setfill('0') << std::setw(2) << unsigned(c);
  return out.str();
}
std::string sha256(const std::vector<unsigned char> &bytes) {
  Crypto c;
  require(BCryptOpenAlgorithmProvider(&c.algorithm, BCRYPT_SHA256_ALGORITHM,
                                      nullptr, 0) >= 0,
          "CNG provider failed");
  require(BCryptCreateHash(c.algorithm, &c.hash, nullptr, 0, nullptr, 0, 0) >=
              0,
          "CNG hash creation failed");
  require(BCryptHashData(c.hash, const_cast<PUCHAR>(bytes.data()),
                         static_cast<ULONG>(bytes.size()), 0) >= 0,
          "CNG hash update failed");
  std::vector<unsigned char> result(32);
  require(BCryptFinishHash(c.hash, result.data(), 32, 0) >= 0,
          "CNG hash finish failed");
  return hex(result);
}
std::string quote(const std::string &value) {
  std::ostringstream out;
  out << '"';
  for (unsigned char c : value) {
    if (c == '"' || c == '\\')
      out << '\\' << c;
    else if (c < 32)
      out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
          << unsigned(c);
    else
      out << c;
  }
  out << '"';
  return out.str();
}
std::string utf8(const std::wstring &value) {
  int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
                                 static_cast<int>(value.size()), nullptr, 0,
                                 nullptr, nullptr);
  require(size > 0, "UTF-8 path conversion failed");
  std::string out(size, '\0');
  require(WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(),
                              static_cast<int>(value.size()), out.data(), size,
                              nullptr, nullptr) == size,
          "UTF-8 path conversion failed");
  return out;
}
std::string utc() {
  SYSTEMTIME t{};
  GetSystemTime(&t);
  std::ostringstream out;
  out << std::setfill('0') << std::setw(4) << t.wYear << '-' << std::setw(2)
      << t.wMonth << '-' << std::setw(2) << t.wDay << 'T' << std::setw(2)
      << t.wHour << ':' << std::setw(2) << t.wMinute << ':' << std::setw(2)
      << t.wSecond << '.' << std::setw(3) << t.wMilliseconds << 'Z';
  return out.str();
}

OwnedCollector::OwnedCollector(const std::wstring &build) {
  require(build == L"v1" || build == L"v2", "Unsupported owned build");
  std::vector<wchar_t> buffer(32768);
  const DWORD length = GetModuleFileNameW(nullptr, buffer.data(),
                                          static_cast<DWORD>(buffer.size()));
  require(length && length < buffer.size(), "Collector path unavailable");
  path_.assign(buffer.data(), length);
  path_ = path_.substr(0, path_.find_last_of(L"\\/") + 1) +
          (build == L"v1" ? L"lab_module.dll" : L"lab_module_v2.dll");
  file_ = CreateFileW(path_.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
                      OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, nullptr);
  require(file_ != INVALID_HANDLE_VALUE, "Cannot open fixed owned DLL");
  try {
    LARGE_INTEGER size{};
    require(GetFileSizeEx(file_, &size) && size.QuadPart > 0 &&
                size.QuadPart <= 64 * 1024 * 1024,
            "Owned DLL size unsupported");
    std::vector<unsigned char> disk(static_cast<std::size_t>(size.QuadPart));
    DWORD read = 0;
    require(ReadFile(file_, disk.data(), static_cast<DWORD>(disk.size()), &read,
                     nullptr) &&
                read == disk.size(),
            "Owned DLL read incomplete");
    file_hash_ = sha256(disk);
    file_size_ = disk.size();
    LabImage image(disk);
    image_size_ = image.image_size();
    preferred_base_ = image.preferred_base();
    for (const auto &span : image.executable_ranges())
      executable_ranges_.push_back({span.rva, span.size});
    for (auto &range : image.declared_ranges())
      ranges_.push_back({range.name, range.rva, std::move(range.expected)});
    auto ordered = ranges_;
    std::sort(ordered.begin(), ordered.end(),
              [](const CodeRange &a, const CodeRange &b) { return a.rva < b.rva; });
    for (const auto &span : executable_ranges_) {
      DWORD cursor = span.rva;
      const DWORD end = span.rva + span.size; // PE parser proved image bound.
      for (const auto &range : ordered) {
        if (range.rva < span.rva || range.rva >= end)
          continue;
        require(range.expected.size() <= end - range.rva,
                "Declared range crosses executable span");
        if (range.rva > cursor)
          exclusions_.push_back({cursor, range.rva - cursor});
        cursor = range.rva + static_cast<DWORD>(range.expected.size());
      }
      if (cursor < end)
        exclusions_.push_back({cursor, end - cursor});
    }
    require(exclusions_.size() <= 128, "Too many excluded code intervals");
    FILETIME creation{}, exit{}, kernel{}, user{};
    require(GetProcessTimes(GetCurrentProcess(), &creation, &exit, &kernel,
                            &user) != 0,
            "Process lifetime unavailable");
    const auto lifetime =
        (static_cast<unsigned long long>(creation.dwHighDateTime) << 32) |
        creation.dwLowDateTime;
    started_ = std::to_string(lifetime);
    session_ = std::to_string(GetCurrentProcessId()) + "-" + started_;
  } catch (...) {
    CloseHandle(file_);
    file_ = INVALID_HANDLE_VALUE;
    throw;
  }
}
OwnedCollector::~OwnedCollector() {
  if (file_ != INVALID_HANDLE_VALUE)
    CloseHandle(file_);
}
std::string OwnedCollector::manifest() const {
  std::ostringstream out;
  out << '[';
  bool first = true;
  for (const auto &range : ranges_) {
    if (!first)
      out << ',';
    first = false;
    out << "{\"range_name\":" << quote(range.name)
        << ",\"range_rva\":" << range.rva
        << ",\"range_size\":" << range.expected.size()
        << ",\"reference_hex\":" << quote(hex(range.expected))
        << ",\"reference_sha256\":" << quote(sha256(range.expected)) << '}';
  }
  out << ']';
  return out.str();
}
std::string OwnedCollector::integrity_manifest() const {
  std::size_t executable = 0, checked = 0, excluded = 0;
  for (const auto &span : executable_ranges_) executable += span.size;
  for (const auto &range : ranges_) checked += range.expected.size();
  for (const auto &span : exclusions_) excluded += span.size;
  require(checked + excluded == executable, "Incomplete executable coverage partition");
  std::ostringstream out;
  out << "{\"schema\":\"surge-integrity-manifest-v1\",\"descriptor_version\":1"
      << ",\"architecture\":\"x64\",\"module_sha256\":" << quote(file_hash_)
      << ",\"module_size\":" << file_size_ << ",\"image_size\":" << image_size_
      << ",\"relocation_policy\":\"reject\",\"executable_bytes\":" << executable
      << ",\"checked_bytes\":" << checked << ",\"excluded_bytes\":" << excluded
      << ",\"ranges\":" << manifest() << ",\"executable_ranges\":[";
  for (std::size_t i = 0; i < executable_ranges_.size(); ++i) {
    const auto &span = executable_ranges_[i];
    out << (i ? "," : "") << "{\"range_rva\":" << span.rva
        << ",\"range_size\":" << span.size << '}';
  }
  out << "],\"exclusions\":[";
  for (std::size_t i = 0; i < exclusions_.size(); ++i) {
    const auto &span = exclusions_[i];
    out << (i ? "," : "") << "{\"range_rva\":" << span.rva
        << ",\"range_size\":" << span.size << ",\"reason\":\"not_declared\"}";
  }
  out << "]}";
  return out.str();
}
std::vector<std::string> OwnedCollector::snapshot(HMODULE module) const {
  if (module) {
    std::vector<wchar_t> buffer(32768);
    DWORD length = GetModuleFileNameW(module, buffer.data(),
                                      static_cast<DWORD>(buffer.size()));
    require(length && length < buffer.size() &&
                std::wstring(buffer.data(), length) == path_,
            "Only the owned loaded DLL may be measured");
  }
  std::vector<std::string> result;
  for (const auto &range : ranges_) {
    const auto start = std::chrono::steady_clock::now();
    auto address = module
                       ? reinterpret_cast<unsigned char *>(module) + range.rva
                       : nullptr;
    std::vector<unsigned char> observed(range.expected.size());
    SIZE_T obtained = 0;
    DWORD error = 0;
    std::string status = "complete";
    MEMORY_BASIC_INFORMATION region{};
    if (!module)
      status = "not_loaded";
    else if (reinterpret_cast<void *>(
                 GetProcAddress(module, range.name.c_str())) != address) {
      error = ERROR_INVALID_ADDRESS;
      status = "failed";
    } else if (!VirtualQuery(address, &region, sizeof(region))) {
      error = GetLastError();
      status = "failed";
    } else if (region.AllocationBase != module || region.Type != MEM_IMAGE ||
               region.State != MEM_COMMIT ||
               reinterpret_cast<std::uintptr_t>(address) + observed.size() >
                   reinterpret_cast<std::uintptr_t>(region.BaseAddress) +
                       region.RegionSize) {
      error = ERROR_INVALID_ADDRESS;
      status = "failed";
    } else if (!ReadProcessMemory(GetCurrentProcess(), address, observed.data(),
                                  observed.size(), &obtained)) {
      error = GetLastError();
      status = "failed";
    } else if (obtained != observed.size()) {
      error = ERROR_PARTIAL_COPY;
      status = "failed";
    }
    std::ostringstream out;
    out << "{\"schema\":\"native-code-range-v1\",\"captured_at\":"
        << quote(utc()) << ",\"session_id\":" << quote(session_)
        << ",\"pid\":" << GetCurrentProcessId()
        << ",\"process_started\":" << quote(started_)
        << ",\"module_path\":" << quote(utf8(path_))
        << ",\"module_sha256\":" << quote(file_hash_)
        << ",\"module_size\":" << file_size_
        << ",\"range_name\":" << quote(range.name)
        << ",\"range_rva\":" << range.rva
        << ",\"range_size\":" << range.expected.size() << ",\"module_base\":"
        << (module ? reinterpret_cast<std::uintptr_t>(module) : 0)
        << ",\"reference_hex\":" << quote(hex(range.expected))
        << ",\"reference_sha256\":" << quote(sha256(range.expected))
        << ",\"observed_hex\":"
        << (status == "complete" ? quote(hex(observed)) : "null")
        << ",\"memory_status\":" << quote(status) << ",\"error_code\":" << error
        << ",\"page_protection\":" << region.Protect << ",\"collection_ms\":"
        << std::chrono::duration<double, std::milli>(
               std::chrono::steady_clock::now() - start)
               .count()
        << '}';
    result.push_back(out.str());
  }
  return result;
}
