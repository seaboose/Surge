#define NOMINMAX
#include "code_range_pe.hpp"
#include <iostream>

namespace {
template <class T> void put(std::vector<unsigned char> &bytes, std::size_t at, const T &value) {
  if (at > bytes.size() || sizeof(T) > bytes.size() - at)
    throw std::runtime_error("Invalid test image write");
  std::memcpy(bytes.data() + at, &value, sizeof(T));
}
constexpr std::size_t optional_at = 152;
constexpr std::size_t section_at = optional_at + sizeof(IMAGE_OPTIONAL_HEADER64);
constexpr std::size_t declaration_at = 1024 + 0x300;

std::vector<unsigned char> fixture() {
  std::vector<unsigned char> bytes(5120);
  IMAGE_DOS_HEADER dos{};
  dos.e_magic = IMAGE_DOS_SIGNATURE;
  dos.e_lfanew = 128;
  put(bytes, 0, dos);
  put(bytes, 128, DWORD(IMAGE_NT_SIGNATURE));
  IMAGE_FILE_HEADER file{};
  file.Machine = IMAGE_FILE_MACHINE_AMD64;
  file.Characteristics = IMAGE_FILE_DLL;
  file.NumberOfSections = 2;
  file.SizeOfOptionalHeader = sizeof(IMAGE_OPTIONAL_HEADER64);
  put(bytes, 132, file);
  IMAGE_OPTIONAL_HEADER64 optional{};
  optional.Magic = IMAGE_NT_OPTIONAL_HDR64_MAGIC;
  optional.NumberOfRvaAndSizes = IMAGE_NUMBEROF_DIRECTORY_ENTRIES;
  optional.SizeOfImage = 0x4000;
  optional.SizeOfHeaders = 512;
  optional.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT] = {0x2000, 0x300};
  put(bytes, optional_at, optional);
  IMAGE_SECTION_HEADER code{};
  code.VirtualAddress = 0x1000;
  code.Misc.VirtualSize = code.SizeOfRawData = 512;
  code.PointerToRawData = 512;
  code.Characteristics = IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_READ;
  put(bytes, section_at, code);
  IMAGE_SECTION_HEADER data{};
  data.VirtualAddress = 0x2000;
  data.Misc.VirtualSize = data.SizeOfRawData = 4096;
  data.PointerToRawData = 1024;
  data.Characteristics = IMAGE_SCN_MEM_READ;
  put(bytes, section_at + sizeof(code), data);
  IMAGE_EXPORT_DIRECTORY exports{};
  exports.NumberOfFunctions = exports.NumberOfNames = 5;
  exports.AddressOfFunctions = 0x2040;
  exports.AddressOfNames = 0x2060;
  exports.AddressOfNameOrdinals = 0x2080;
  put(bytes, 1024, exports);
  const DWORD addresses[] = {0x1000, 0x1009, 0x1020, 0x1026, 0x2300};
  const char *names[] = {"LabCodeProbe", "LabCodeProbeEnd", "LabCodeSecondary",
                         "LabCodeSecondaryEnd", "LabIntegrityManifest"};
  for (unsigned i = 0; i < 5; ++i) {
    put(bytes, 1024 + 0x40 + i * sizeof(DWORD), addresses[i]);
    put(bytes, 1024 + 0x60 + i * sizeof(DWORD), DWORD(0x2100 + i * 64));
    put(bytes, 1024 + 0x80 + i * sizeof(WORD), WORD(i));
    std::memcpy(bytes.data() + 1024 + 0x100 + i * 64, names[i], std::strlen(names[i]) + 1);
  }
  LabManifestDeclaration manifest{lab_manifest_magic, 1, IMAGE_FILE_MACHINE_AMD64, 2,
                                {{"LabCodeProbe", "LabCodeProbeEnd"},
                                 {"LabCodeSecondary", "LabCodeSecondaryEnd"}}};
  put(bytes, declaration_at, manifest);
  std::fill(bytes.begin() + 512, bytes.begin() + 1024, static_cast<unsigned char>(0x90));
  return bytes;
}
} // namespace

int main() {
  try {
    auto valid = fixture();
    LabImage image(valid);
    const auto ranges = image.declared_ranges();
    if (ranges.size() != 2 || ranges[0].rva != 0x1000 || ranges[0].expected.size() != 9 ||
        ranges[1].expected.size() != 6 || image.executable_ranges()[0].size != 512)
      throw std::runtime_error("Valid declaration resolved incorrectly");
    int refusals = 0;
    auto reject = [&](const std::vector<unsigned char> &bytes) {
      try {
        LabImage bad(bytes);
        bad.executable_ranges();
        bad.declared_ranges();
      } catch (const std::exception &) { ++refusals; return; }
      throw std::runtime_error("Unsupported manifest accepted");
    };
    auto mutate = [&](auto change) {
      auto bytes = valid;
      auto declaration = image.read<LabManifestDeclaration>(declaration_at);
      change(declaration);
      put(bytes, declaration_at, declaration);
      reject(bytes);
    };
    mutate([](auto &m) { m.magic = 0; });
    mutate([](auto &m) { m.version = 2; });
    mutate([](auto &m) { m.machine = IMAGE_FILE_MACHINE_I386; });
    mutate([](auto &m) { m.range_count = 1; });
    mutate([](auto &m) { m.range_count = 17; });
    mutate([](auto &m) { m.ranges[1] = m.ranges[0]; });
    mutate([](auto &m) { std::memset(m.ranges[0].begin, 'A', 64); });
    mutate([](auto &m) { m.ranges[0].begin[0] = '1'; });
    mutate([](auto &m) { m.ranges[0].begin[63] = 'X'; });
    mutate([](auto &m) { m.ranges[2].begin[0] = 'X'; });
    mutate([](auto &m) { m.ranges[0].end[0] = 'Z'; });
    auto bytes = valid;
    put(bytes, 1024 + 0x40 + 2 * sizeof(DWORD), DWORD(0x1005)); // overlap first
    reject(bytes);
    bytes = valid;
    put(bytes, 1024 + 0x40 + sizeof(DWORD), DWORD(0x1000)); // empty range
    reject(bytes);
    bytes = valid;
    put(bytes, 1024 + 0x40 + 4 * sizeof(DWORD), DWORD(0x2001)); // forwarded descriptor
    reject(bytes);
    bytes = valid;
    put(bytes, 1024 + 0x40 + 4 * sizeof(DWORD), DWORD(0x2fff)); // descriptor crosses section
    reject(bytes);
    const auto data = image.read<IMAGE_SECTION_HEADER>(section_at + sizeof(IMAGE_SECTION_HEADER));
    bytes = valid; auto changed = data;
    changed.Characteristics |= IMAGE_SCN_MEM_WRITE;
    put(bytes, section_at + sizeof(IMAGE_SECTION_HEADER), changed); reject(bytes);
    bytes = valid; changed = data; changed.Characteristics |= IMAGE_SCN_MEM_EXECUTE;
    put(bytes, section_at + sizeof(IMAGE_SECTION_HEADER), changed); reject(bytes);
    bytes = valid; changed = data; changed.PointerToRawData = 512;
    put(bytes, section_at + sizeof(IMAGE_SECTION_HEADER), changed); reject(bytes);
    bytes = valid; changed = data; changed.VirtualAddress = 0x1100;
    put(bytes, section_at + sizeof(IMAGE_SECTION_HEADER), changed); reject(bytes);
    bytes = valid;
    auto code = image.read<IMAGE_SECTION_HEADER>(section_at);
    code.Characteristics |= IMAGE_SCN_MEM_WRITE;
    put(bytes, section_at, code); reject(bytes);
    bytes = valid;
    auto optional = image.read<IMAGE_OPTIONAL_HEADER64>(optional_at);
    optional.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC] = {0x2c00, 12};
    put(bytes, optional_at, optional);
    put(bytes, 1024 + 0xc00, IMAGE_BASE_RELOCATION{0x1000, 12});
    put(bytes, 1024 + 0xc08, WORD(IMAGE_REL_BASED_DIR64 << 12));
    reject(bytes);
    std::cout << "Manifest parser: declarations resolved; " << refusals
              << " malformed or unsupported images refused\n";
    return 0;
  } catch (const std::exception &error) { std::cerr << error.what() << '\n'; return 1; }
}
