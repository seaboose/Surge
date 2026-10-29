#define NOMINMAX
#include "seed.hpp"
#include <fstream>
#include <iostream>
#include <sstream>
#include <iomanip>
#include <filesystem>
#if !__has_feature(address_sanitizer)
#error Pilot requires AddressSanitizer instrumentation
#endif

std::string classify(const std::vector<unsigned char>& bytes) {
  try {
    LabImage image(bytes);
    const auto spans = image.executable_ranges();
    const auto ranges = image.declared_ranges();
    std::ostringstream out;
    out << "OK|" << image.image_size();
    for (const auto &span : spans) out << "|S:" << span.rva << ':' << span.size;
    for (const auto &range : ranges) {
      out << "|R:" << range.name << ':' << range.rva << ':';
      for (auto byte : range.expected)
        out << std::hex << std::setw(2) << std::setfill('0') << unsigned(byte);
      out << std::dec;
    }
    return out.str();
  } catch (const std::runtime_error &error) {
    return std::string("REFUSED|") + error.what();
  }
}

#ifdef SURGE_FUZZ
extern "C" int LLVMFuzzerTestOneInput(const unsigned char* data, size_t size) {
  if (size > 65536) return 0;
  const std::vector<unsigned char> bytes(data, data + size);
  // Keep reporting outside the coverage-guided loop. Replay records refusals.
  try {
    LabImage image(bytes);
    image.executable_ranges();
    image.declared_ranges();
  } catch (const std::runtime_error&) {
    // The parser's documented refusal is an expected outcome.
  }
  return 0;
}
#else
int main(int argc, char** argv) {
  if (argc != 3) return 2;
  const std::filesystem::path folder(argv[2]);
  if (std::string(argv[1]) == "seed") {
    auto valid = fixture();
    auto bad = valid;
    bad[declaration_at] ^= 1;
    const std::vector<std::pair<std::string,std::vector<unsigned char>>> seeds = {
      {"valid.bin",valid}, {"short.bin",{1,2,3}}, {"descriptor.bin",bad}
    };
    for (const auto &entry : seeds) {
      std::ofstream out(folder / entry.first, std::ios::binary);
      out.write(reinterpret_cast<const char*>(entry.second.data()), entry.second.size());
      if (!out) return 3;
    }
  } else if (std::string(argv[1]) == "replay") {
    std::vector<std::filesystem::path> paths;
    for (const auto &entry : std::filesystem::directory_iterator(folder))
      if (entry.is_regular_file()) paths.push_back(entry.path());
    std::sort(paths.begin(), paths.end());
    for (const auto &path : paths) {
      if (std::filesystem::file_size(path) > 65536) return 4;
      std::ifstream in(path,std::ios::binary);
      const std::vector<unsigned char> bytes((std::istreambuf_iterator<char>(in)),{});
      if (in.bad()) return 5;
      std::cout << path.filename().string() << '\t' << classify(bytes) << '\n';
    }
  } else return 2;
  return 0;
}
#endif
