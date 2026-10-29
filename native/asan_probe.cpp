// Test-only instrumentation control. Never linked into Surge or its fixtures.
#include <cstring>
#include <cstdio>
int main(int argc, char **argv) {
  if (argc != 2 || (std::strcmp(argv[1], "safe") && std::strcmp(argv[1], "fault")))
    return 2;
  volatile int index = std::strcmp(argv[1], "safe") == 0 ? 0 : 4;
  volatile int *values = new int[4];
  values[index] = 42; // Fault mode deliberately tests an ASan heap boundary.
  delete[] values;
  std::puts("ASAN_PROBE_COMPLETED");
  return 0;
}
