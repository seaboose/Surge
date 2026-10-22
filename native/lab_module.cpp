// A deliberately simple export for inspecting our own DLL in a disassembler.
extern "C" __declspec(dllexport) int LabTransform(int value) {
    return (value ^ 0x35) + 17;
}
