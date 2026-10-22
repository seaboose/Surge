#define NOMINMAX
#include "code_range_pe.hpp"
#include <iostream>

template<class T> void put(std::vector<unsigned char>& bytes, std::size_t at, const T& value) {
    if (at + sizeof(T) > bytes.size()) throw std::runtime_error("Invalid test fixture");
    std::memcpy(bytes.data() + at, &value, sizeof(T));
}
std::vector<unsigned char> fixture() {
    std::vector<unsigned char> bytes(2048);
    IMAGE_DOS_HEADER dos{}; dos.e_magic = IMAGE_DOS_SIGNATURE; dos.e_lfanew = 128; put(bytes, 0, dos);
    put(bytes, 128, DWORD(IMAGE_NT_SIGNATURE));
    IMAGE_FILE_HEADER file{}; file.Machine = IMAGE_FILE_MACHINE_AMD64; file.Characteristics = IMAGE_FILE_DLL;
    file.NumberOfSections = 1; file.SizeOfOptionalHeader = sizeof(IMAGE_OPTIONAL_HEADER64); put(bytes, 132, file);
    IMAGE_OPTIONAL_HEADER64 optional{}; optional.Magic = IMAGE_NT_OPTIONAL_HDR64_MAGIC;
    optional.NumberOfRvaAndSizes = IMAGE_NUMBEROF_DIRECTORY_ENTRIES; optional.SizeOfImage = 0x3000; optional.SizeOfHeaders = 512;
    optional.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT] = {0x1000, 128}; put(bytes, 152, optional);
    IMAGE_SECTION_HEADER section{}; section.VirtualAddress = 0x1000; section.Misc.VirtualSize = 1536;
    section.SizeOfRawData = 1536; section.PointerToRawData = 512; section.Characteristics = IMAGE_SCN_MEM_EXECUTE | IMAGE_SCN_MEM_READ;
    put(bytes, 152 + sizeof(optional), section);
    IMAGE_EXPORT_DIRECTORY exports{}; exports.NumberOfFunctions = exports.NumberOfNames = 2;
    exports.AddressOfFunctions = 0x1040; exports.AddressOfNames = 0x1048; exports.AddressOfNameOrdinals = 0x1050; put(bytes, 512, exports);
    put(bytes, 576, DWORD(0x1200)); put(bytes, 580, DWORD(0x1209));
    put(bytes, 584, DWORD(0x1060)); put(bytes, 588, DWORD(0x1070)); put(bytes, 592, WORD(0)); put(bytes, 594, WORD(1));
    std::memcpy(bytes.data() + 608, "LabCodeProbe", 13); std::memcpy(bytes.data() + 624, "LabCodeProbeEnd", 16);
    for (std::size_t i = 1024; i < 1033; ++i) bytes[i] = 0x90;
    return bytes;
}
int main() {
    try {
        auto valid = fixture(); DWORD rva = 0;
        if (LabImage(valid).probe(rva).size() != 9 || rva != 0x1200) return 1;
        int refusals = 0;
        auto reject = [&](std::vector<unsigned char> bytes) {
            try { LabImage(bytes).probe(rva); } catch (const std::exception&) { ++refusals; return; }
            throw std::runtime_error("Malformed/unsupported image was accepted");
        };
        reject({1, 2, 3});
        auto bad = valid; put(bad, 60, LONG(MAXLONG)); reject(bad);
        bad = valid; put(bad, 132, WORD(IMAGE_FILE_MACHINE_I386)); reject(bad);
        bad = valid; put(bad, 152 + sizeof(IMAGE_OPTIONAL_HEADER64) + 20, DWORD(MAXDWORD)); reject(bad);
        bad = valid; put(bad, 576, DWORD(0x1001)); reject(bad); // forwarded export
        bad = valid; put(bad, 580, DWORD(0x1300)); reject(bad); // oversized range
        bad = valid; put(bad, 592, WORD(4096)); reject(bad); // invalid ordinal
        bad = valid;
        auto optional = LabImage(bad).read<IMAGE_OPTIONAL_HEADER64>(152);
        optional.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC] = {0x1300, 12}; put(bad, 152, optional);
        IMAGE_BASE_RELOCATION block{0x1000, 12}; put(bad, 1280, block);
        put(bad, 1288, WORD((IMAGE_REL_BASED_DIR64 << 12) | 0x200)); reject(bad); // overlaps probe
        bad = valid; optional = LabImage(bad).read<IMAGE_OPTIONAL_HEADER64>(152);
        optional.DataDirectory[IMAGE_DIRECTORY_ENTRY_IAT] = {0x1200, 8}; put(bad, 152, optional); reject(bad);
        bad = valid; optional = LabImage(bad).read<IMAGE_OPTIONAL_HEADER64>(152);
        optional.DataDirectory[IMAGE_DIRECTORY_ENTRY_BASERELOC] = {0x1300, 12}; put(bad, 152, optional);
        block.SizeOfBlock = 1; put(bad, 1280, block); reject(bad);
        std::cout << "PE parser: valid range and " << refusals << " malformed/unsupported layouts checked\n";
        return 0;
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
