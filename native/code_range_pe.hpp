#pragma once
#include "lab_manifest.hpp"
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <set>
#include <vector>
#include <windows.h>

// Strict x64 lab-image parser. Unsupported layouts become unknown, never clean.
class LabImage {
  const std::vector<unsigned char> &bytes_;
  IMAGE_OPTIONAL_HEADER64 optional_{};
  std::vector<IMAGE_SECTION_HEADER> sections_;

public:
  template <class T> T read(std::size_t offset) const {
    if (offset > bytes_.size() || sizeof(T) > bytes_.size() - offset)
      throw std::runtime_error("PE structure exceeds captured file");
    T value{};
    std::memcpy(&value, bytes_.data() + offset, sizeof(T));
    return value;
  }
  explicit LabImage(const std::vector<unsigned char> &bytes) : bytes_(bytes) {
    const auto dos = read<IMAGE_DOS_HEADER>(0);
    if (dos.e_magic != IMAGE_DOS_SIGNATURE || dos.e_lfanew < 0)
      throw std::runtime_error("Invalid DOS header");
    const auto nt = static_cast<std::size_t>(dos.e_lfanew);
    if (read<DWORD>(nt) != IMAGE_NT_SIGNATURE)
      throw std::runtime_error("Invalid PE signature");
    const auto file = read<IMAGE_FILE_HEADER>(nt + sizeof(DWORD));
    if (file.Machine != IMAGE_FILE_MACHINE_AMD64 ||
        !(file.Characteristics & IMAGE_FILE_DLL) || !file.NumberOfSections ||
        file.NumberOfSections > 96 ||
        file.SizeOfOptionalHeader != sizeof(optional_))
      throw std::runtime_error("Unsupported lab image architecture or headers");
    optional_ =
        read<IMAGE_OPTIONAL_HEADER64>(nt + sizeof(DWORD) + sizeof(file));
    if (optional_.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
        optional_.NumberOfRvaAndSizes != IMAGE_NUMBEROF_DIRECTORY_ENTRIES ||
        !optional_.SizeOfImage || optional_.SizeOfImage > 512 * 1024 * 1024 ||
        optional_.SizeOfHeaders > bytes.size())
      throw std::runtime_error("Unsupported optional header");
    auto at = nt + sizeof(DWORD) + sizeof(file) + file.SizeOfOptionalHeader;
    for (unsigned i = 0; i < file.NumberOfSections;
         ++i, at += sizeof(IMAGE_SECTION_HEADER)) {
      auto section = read<IMAGE_SECTION_HEADER>(at);
      if (section.PointerToRawData > bytes.size() ||
          section.SizeOfRawData > bytes.size() - section.PointerToRawData ||
          section.VirtualAddress > optional_.SizeOfImage ||
          std::max(section.Misc.VirtualSize, section.SizeOfRawData) >
              optional_.SizeOfImage - section.VirtualAddress)
        throw std::runtime_error("PE section exceeds file or image");
      if ((section.SizeOfRawData && section.PointerToRawData < optional_.SizeOfHeaders) ||
          (std::max(section.Misc.VirtualSize, section.SizeOfRawData) &&
           section.VirtualAddress < optional_.SizeOfHeaders))
        throw std::runtime_error("PE section overlaps image headers");
      for (const auto &previous : sections_) {
        if (overlaps(section.VirtualAddress,
                     std::max(section.Misc.VirtualSize, section.SizeOfRawData),
                     previous.VirtualAddress,
                     std::max(previous.Misc.VirtualSize, previous.SizeOfRawData)) ||
            overlaps(section.PointerToRawData, section.SizeOfRawData,
                     previous.PointerToRawData, previous.SizeOfRawData))
          throw std::runtime_error("Overlapping PE sections are unsupported");
      }
      sections_.push_back(section);
    }
  }
  DWORD image_size() const { return optional_.SizeOfImage; }
  std::uint64_t preferred_base() const { return optional_.ImageBase; }
  struct Span { DWORD rva; DWORD size; };
  std::vector<Span> executable_ranges() const {
    std::vector<Span> result;
    for (const auto &section : sections_) {
      if (!(section.Characteristics & IMAGE_SCN_MEM_EXECUTE))
        continue;
      if (section.Characteristics & IMAGE_SCN_MEM_WRITE)
        throw std::runtime_error("Writable executable sections are unsupported");
      if (section.SizeOfRawData)
        result.push_back({section.VirtualAddress, section.SizeOfRawData});
    }
    if (result.empty() || result.size() > 32)
      throw std::runtime_error("Unsupported executable section count");
    std::sort(result.begin(), result.end(),
              [](const Span &a, const Span &b) { return a.rva < b.rva; });
    return result;
  }
  std::vector<LabRangeDeclaration> declarations() const {
    const auto rva = exported("LabIntegrityManifest");
    const auto at = offset(rva, sizeof(LabManifestDeclaration));
    bool readonly = false;
    for (const auto &section : sections_) {
      if (rva >= section.VirtualAddress &&
          rva - section.VirtualAddress < section.SizeOfRawData)
        readonly = !(section.Characteristics & (IMAGE_SCN_MEM_WRITE | IMAGE_SCN_MEM_EXECUTE));
    }
    if (!readonly)
      throw std::runtime_error("Manifest declaration must be read-only data");
    const auto descriptor = read<LabManifestDeclaration>(at);
    if (descriptor.magic != lab_manifest_magic || descriptor.version != 1 ||
        descriptor.machine != IMAGE_FILE_MACHINE_AMD64 ||
        descriptor.range_count < 2 || descriptor.range_count > 16)
      throw std::runtime_error("Unsupported integrity manifest declaration");
    auto symbol = [](const char *text) {
      std::size_t length = 0;
      for (; length < 64 && text[length]; ++length) {
        const char c = text[length];
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
              (length && ((c >= '0' && c <= '9') || c == '_'))))
          throw std::runtime_error("Invalid manifest export identifier");
      }
      if (!length || length == 64)
        throw std::runtime_error("Unbounded manifest export identifier");
      for (std::size_t i = length; i < 64; ++i)
        if (text[i])
          throw std::runtime_error("Noncanonical manifest export identifier");
      return std::string(text, length);
    };
    std::set<std::string> names;
    std::vector<LabRangeDeclaration> result;
    for (unsigned i = 0; i < descriptor.range_count; ++i) {
      const auto &entry = descriptor.ranges[i];
      if (!names.insert(symbol(entry.begin)).second ||
          !names.insert(symbol(entry.end)).second)
        throw std::runtime_error("Duplicate manifest export identifier");
      result.push_back(entry);
    }
    for (unsigned i = descriptor.range_count; i < 16; ++i) {
      const auto &entry = descriptor.ranges[i];
      for (unsigned j = 0; j < 64; ++j)
        if (entry.begin[j] || entry.end[j])
          throw std::runtime_error("Unused manifest declarations must be empty");
    }
    return result;
  }
  struct ResolvedRange {
    std::string name;
    DWORD rva;
    std::vector<unsigned char> expected;
  };
  std::vector<ResolvedRange> declared_ranges() const {
    std::vector<ResolvedRange> result;
    for (const auto &declaration : declarations()) {
      DWORD rva = 0;
      auto expected = probe(rva, declaration.begin, declaration.end);
      for (const auto &previous : result)
        if (overlaps(rva, expected.size(), previous.rva, previous.expected.size()))
          throw std::runtime_error("Declared code ranges overlap");
      result.push_back({declaration.begin, rva, std::move(expected)});
    }
    return result;
  }
  std::size_t offset(DWORD rva, std::size_t size) const {
    if (rva > optional_.SizeOfImage || size > optional_.SizeOfImage - rva)
      throw std::runtime_error("RVA outside image");
    std::size_t found = 0, result = 0;
    for (const auto &section : sections_) {
      if (rva < section.VirtualAddress)
        continue;
      const auto delta = rva - section.VirtualAddress;
      if (delta <= section.SizeOfRawData &&
          size <= section.SizeOfRawData - delta) {
        ++found;
        result = static_cast<std::size_t>(section.PointerToRawData) + delta;
      }
    }
    if (found != 1)
      throw std::runtime_error("RVA has no unique file-backed section");
    return result;
  }
  std::string name(DWORD rva) const {
    std::string result;
    for (unsigned i = 0; i < 256; ++i) {
      if (rva > MAXDWORD - i)
        break;
      char c = static_cast<char>(bytes_[offset(rva + i, 1)]);
      if (!c)
        return result;
      result += c;
    }
    throw std::runtime_error("Oversized export name");
  }
  DWORD exported(const std::string &wanted) const {
    const auto directory =
        optional_.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
    if (directory.Size < sizeof(IMAGE_EXPORT_DIRECTORY))
      throw std::runtime_error("Missing exports");
    const auto data = read<IMAGE_EXPORT_DIRECTORY>(
        offset(directory.VirtualAddress, sizeof(IMAGE_EXPORT_DIRECTORY)));
    if (!data.NumberOfFunctions || data.NumberOfFunctions > 4096 ||
        data.NumberOfNames > 4096)
      throw std::runtime_error("Unsupported export count");
    const auto names =
        offset(data.AddressOfNames, data.NumberOfNames * sizeof(DWORD));
    const auto ordinals =
        offset(data.AddressOfNameOrdinals, data.NumberOfNames * sizeof(WORD));
    const auto functions =
        offset(data.AddressOfFunctions, data.NumberOfFunctions * sizeof(DWORD));
    for (unsigned i = 0; i < data.NumberOfNames; ++i) {
      if (name(read<DWORD>(names + i * sizeof(DWORD))) != wanted)
        continue;
      const auto ordinal = read<WORD>(ordinals + i * sizeof(WORD));
      if (ordinal >= data.NumberOfFunctions)
        throw std::runtime_error("Invalid export ordinal");
      const auto rva = read<DWORD>(functions + ordinal * sizeof(DWORD));
      if (rva >= directory.VirtualAddress &&
          static_cast<std::uint64_t>(rva) <
              static_cast<std::uint64_t>(directory.VirtualAddress) +
                  directory.Size)
        throw std::runtime_error("Forwarded probe exports unsupported");
      return rva;
    }
    throw std::runtime_error("Required lab probe export is absent");
  }
  static bool overlaps(std::uint64_t first, std::uint64_t size,
                       std::uint64_t start, std::uint64_t length) {
    return size && length && first < start + length && start < first + size;
  }
  std::vector<unsigned char>
  probe(DWORD &rva, const std::string &begin = "LabCodeProbe",
        const std::string &finish = "LabCodeProbeEnd") const {
    rva = exported(begin);
    const DWORD end = exported(finish);
    if (end <= rva || end - rva > 64)
      throw std::runtime_error("Unsupported probe length");
    const DWORD length = end - rva;
    const auto at = offset(rva, length);
    bool executable = false;
    for (const auto &section : sections_) {
      if (rva >= section.VirtualAddress &&
          rva - section.VirtualAddress < section.SizeOfRawData)
        executable = (section.Characteristics & IMAGE_SCN_MEM_EXECUTE) &&
                     !(section.Characteristics & IMAGE_SCN_MEM_WRITE);
    }
    if (!executable)
      throw std::runtime_error(
          "Probe is not in a read-only executable section");
    const auto iat = optional_.DataDirectory[IMAGE_DIRECTORY_ENTRY_IAT];
    if (overlaps(rva, length, iat.VirtualAddress, iat.Size))
      throw std::runtime_error("Probe intersects loader import fixups");
    const auto reloc = optional_.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC];
    if (reloc.Size > 1024 * 1024)
      throw std::runtime_error("Relocation directory exceeds lab limit");
    if (reloc.Size) {
      const auto base = offset(reloc.VirtualAddress, reloc.Size);
      std::size_t cursor = 0;
      while (cursor < reloc.Size) {
        if (reloc.Size - cursor < sizeof(IMAGE_BASE_RELOCATION))
          throw std::runtime_error("Truncated relocation block");
        auto block = read<IMAGE_BASE_RELOCATION>(base + cursor);
        if (block.SizeOfBlock < sizeof(block) ||
            block.SizeOfBlock > reloc.Size - cursor ||
            (block.SizeOfBlock - sizeof(block)) % sizeof(WORD))
          throw std::runtime_error("Invalid relocation block");
        for (std::size_t i = sizeof(block); i < block.SizeOfBlock;
             i += sizeof(WORD)) {
          const auto item = read<WORD>(base + cursor + i);
          const auto type = item >> 12;
          if (type == IMAGE_REL_BASED_ABSOLUTE)
            continue;
          if (type != IMAGE_REL_BASED_DIR64)
            throw std::runtime_error("Unsupported relocation type");
          const auto target =
              static_cast<std::uint64_t>(block.VirtualAddress) + (item & 0xfff);
          if (target + 8 > optional_.SizeOfImage)
            throw std::runtime_error("Relocation target outside image");
          if (overlaps(rva, length, target, 8))
            throw std::runtime_error(
                "Probe intersects relocation fixup; comparison refused");
        }
        cursor += block.SizeOfBlock;
      }
    }
    return {bytes_.begin() + at, bytes_.begin() + at + length};
  }
};
