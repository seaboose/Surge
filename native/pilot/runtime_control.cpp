#include <cstddef>
#ifdef EXCEPTION_CONTROL
#include <stdexcept>
#endif
#if !__has_feature(address_sanitizer)
#error Runtime control requires ASan
#endif
extern "C" int LLVMFuzzerTestOneInput(const unsigned char* data, std::size_t size) {
  #ifdef EXCEPTION_CONTROL
  try { throw std::runtime_error("controlled refusal"); }
  catch (const std::runtime_error&) {}
  #endif
  if (size) { volatile unsigned char value = data[0]; (void)value; }
  return 0;
}
