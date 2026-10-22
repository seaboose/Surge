#pragma once
#define NOMINMAX
#include <string>
#include <vector>
#include <windows.h>

struct CodeRange {
  std::string name;
  DWORD rva;
  std::vector<unsigned char> expected;
};
std::string quote(const std::string &value);
std::string utf8(const std::wstring &value);
void require(bool value, const char *message);

// Fixed owned DLLs only. This API accepts no PID, address or external path.
class OwnedCollector {
  HANDLE file_ = INVALID_HANDLE_VALUE;
  std::wstring path_;
  std::string file_hash_, session_, started_;
  std::size_t file_size_ = 0;
  std::vector<CodeRange> ranges_;

public:
  explicit OwnedCollector(const std::wstring &build);
  ~OwnedCollector();
  OwnedCollector(const OwnedCollector &) = delete;
  OwnedCollector &operator=(const OwnedCollector &) = delete;
  const std::wstring &path() const { return path_; }
  const std::vector<CodeRange> &ranges() const { return ranges_; }
  std::string manifest() const;
  std::vector<std::string> snapshot(HMODULE module) const;
};
