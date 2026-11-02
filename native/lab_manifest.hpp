#pragma once
#include <cstdint>

// Disk format: no pointers, process addresses, JSON parsing, or executable callbacks.
// Names resolve against the owned DLL's export table before it is loaded.
struct LabRangeDeclaration {
  char begin[64];
  char end[64];
};
struct LabManifestDeclaration {
  std::uint32_t magic;
  std::uint32_t version;
  std::uint32_t machine;
  std::uint32_t range_count;
  LabRangeDeclaration ranges[16];
};
static_assert(sizeof(LabManifestDeclaration) == 2064,
              "The versioned manifest must have a fixed disk layout");
constexpr std::uint32_t lab_manifest_magic = 0x47525553; // SURG, little endian
