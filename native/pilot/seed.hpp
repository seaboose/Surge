#pragma once
#include "../code_range_pe.hpp"
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

