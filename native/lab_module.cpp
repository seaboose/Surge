#include "lab_manifest.hpp"

extern "C" __declspec(dllexport) const LabManifestDeclaration LabIntegrityManifest = {
    lab_manifest_magic, 1, 0x8664,
#ifdef SURGE_EXTRA_RANGE
    3,
#else
    2,
#endif
    {{"LabCodeProbe", "LabCodeProbeEnd"},
     {"LabCodeSecondary", "LabCodeSecondaryEnd"},
#ifdef SURGE_EXTRA_RANGE
     {"LabCodeTertiary", "LabCodeTertiaryEnd"},
#endif
    }};

// A deliberately simple export for inspecting our own DLL in a disassembler.
extern "C" __declspec(dllexport) int LabTransform(int value) {
    return (value ^ 0x35) + 17;
}
