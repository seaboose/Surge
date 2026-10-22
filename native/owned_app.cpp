#include "code_range_collector.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <iostream>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <thread>

namespace {
using Clock = std::chrono::steady_clock;
constexpr char schema[] = "surge-native-stream-v1";
constexpr std::size_t queue_limit = 32;

// The reader may stall without holding the sampling thread or retaining an
// unbounded backlog. Dropped samples still consume sequence numbers.
class Writer {
  HANDLE output_;
  std::mutex mutex_;
  std::condition_variable changed_;
  std::deque<std::string> queue_;
  std::string final_;
  bool closed_ = false;
  std::atomic<bool> failed_{false}, abort_{false};
  std::thread thread_;

  void run() {
    for (;;) {
      std::string next;
      bool last = false;
      {
        std::unique_lock<std::mutex> lock(mutex_);
        changed_.wait(lock,
                      [&] { return abort_ || closed_ || !queue_.empty(); });
        if (abort_)
          return;
        if (!queue_.empty()) {
          next = std::move(queue_.front());
          queue_.pop_front();
        } else {
          next = std::move(final_);
          last = true;
        }
      }
      if (!next.empty()) {
        if (abort_)
          return;
        next += '\n';
        DWORD written = 0;
        if (!WriteFile(output_, next.data(), static_cast<DWORD>(next.size()),
                       &written, nullptr) ||
            written != next.size()) {
          failed_ = true;
          return;
        }
      }
      if (last)
        return;
    }
  }

public:
  Writer() : output_(GetStdHandle(STD_OUTPUT_HANDLE)) {
    require(output_ && output_ != INVALID_HANDLE_VALUE, "Missing output pipe");
    thread_ = std::thread([this] { run(); });
  }
  Writer(const Writer &) = delete;
  Writer &operator=(const Writer &) = delete;
  bool failed() const { return failed_; }
  bool offer(std::string frame) {
    require(frame.size() < 32768, "Stream frame exceeds its bound");
    std::lock_guard<std::mutex> lock(mutex_);
    if (failed_ || closed_ || queue_.size() >= queue_limit)
      return false;
    queue_.push_back(std::move(frame));
    changed_.notify_one();
    return true;
  }
  bool finish(std::string frame) {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      final_ = std::move(frame);
      closed_ = true;
    }
    changed_.notify_one();
    if (WaitForSingleObject(thread_.native_handle(), 2000) != WAIT_OBJECT_0) {
      abort_ = true;
      failed_ = true;
      // Cancel a synchronous pipe write before joining. No thread is detached.
      CancelSynchronousIo(thread_.native_handle());
      changed_.notify_one();
      // A write can start just as cancellation is requested. Retry until the
      // thread observes abort_ or its outstanding synchronous I/O is canceled.
      while (WaitForSingleObject(thread_.native_handle(), 20) == WAIT_TIMEOUT)
        CancelSynchronousIo(thread_.native_handle());
    }
    thread_.join();
    return !failed_;
  }
  ~Writer() {
    if (thread_.joinable())
      finish("");
  }
};

struct Module {
  HMODULE value = nullptr;
  ~Module() {
    if (value)
      FreeLibrary(value);
  }
  void load(const OwnedCollector &collector) {
    if (!value)
      value = LoadLibraryExW(collector.path().c_str(), nullptr,
                             LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
                                 LOAD_LIBRARY_SEARCH_SYSTEM32);
    require(value != nullptr, "Owned DLL load failed");
  }
  void unload() {
    if (value) {
      require(FreeLibrary(value) != 0, "Owned DLL unload failed");
      value = nullptr;
    }
  }
};

// Only the explicit evaluation mode exposes these controls. Bytes in the two
// owned probe exports are never executed by this application.
struct Change {
  unsigned char *address = nullptr;
  unsigned char original = 0;
  DWORD protection = 0;
  bool changed = false, inaccessible = false;
  void restore() {
    DWORD ignored = 0;
    if (changed) {
      require(VirtualProtect(address, 1, PAGE_EXECUTE_READWRITE, &ignored) != 0,
              "Cannot restore owned bytes");
      *address = original;
      require(FlushInstructionCache(GetCurrentProcess(), address, 1) != 0,
              "Cannot flush restored bytes");
    }
    if (changed || inaccessible)
      require(VirtualProtect(address, 1, protection, &ignored) != 0,
              "Cannot restore owned page protection");
    changed = inaccessible = false;
  }
  void apply(const OwnedCollector &collector, HMODULE module,
             const std::string &command) {
    restore();
    require(module != nullptr, "Load the owned DLL before changing it");
    address = reinterpret_cast<unsigned char *>(module) +
              collector.ranges()[command == "change-secondary" ? 1 : 0].rva;
    if (command == "change-outside") {
      // Fixed NOP padding between our two exports; no arbitrary address input.
      const auto &first = collector.ranges()[0];
      const auto offset = first.rva + first.expected.size() + 32;
      require(offset < collector.ranges()[1].rva,
              "Owned padding is outside the expected layout");
      address = reinterpret_cast<unsigned char *>(module) + offset;
      require(*address == 0x90,
              "Owned padding differs from the fixture layout");
    }
    if (command == "unreadable") {
      require(VirtualProtect(address, 1, PAGE_NOACCESS, &protection) != 0,
              "Cannot make owned page unreadable");
      inaccessible = true;
    } else {
      require(VirtualProtect(address, 1, PAGE_EXECUTE_READWRITE, &protection) !=
                  0,
              "Cannot prepare owned change");
      original = *address;
      changed = true;
      *address ^= 1;
      require(FlushInstructionCache(GetCurrentProcess(), address, 1) != 0,
              "Cannot flush owned change");
      DWORD ignored = 0;
      require(VirtualProtect(address, 1, protection, &ignored) != 0,
              "Cannot restore changed page protection");
    }
  }
  ~Change() {
    try {
      restore();
    } catch (...) { // Process exit reclaims the owned image.
    }
  }
};

unsigned number(const wchar_t *text, unsigned minimum, unsigned maximum) {
  const std::wstring value(text);
  require(!value.empty() && value.size() <= 6 &&
              value.find_first_not_of(L"0123456789") == std::wstring::npos,
          "Expected a bounded integer");
  const auto parsed = std::stoul(value);
  require(parsed >= minimum && parsed <= maximum,
          "Integer outside allowed range");
  return static_cast<unsigned>(parsed);
}

std::string prefix(const char *type) {
  return std::string("{\"schema\":") + quote(schema) +
         ",\"type\":" + quote(type);
}
} // namespace

int wmain(int argc, wchar_t **argv) {
  try {
    std::wstring build = L"v1";
    unsigned interval = 500, duration = 600000;
    bool controls = false, seen_build = false, seen_interval = false,
         seen_duration = false;
    for (int i = 1; i < argc; ++i) {
      const std::wstring argument(argv[i]);
      if (argument == L"--test-controls") {
        require(!controls, "Duplicate test control option");
        controls = true;
      } else {
        require(i + 1 < argc, "Missing option value");
        if (argument == L"--build") {
          require(!seen_build, "Duplicate build option");
          seen_build = true;
          build = argv[++i];
        } else if (argument == L"--interval-ms") {
          require(!seen_interval, "Duplicate interval option");
          seen_interval = true;
          interval = number(argv[++i], 100, 5000);
        } else if (argument == L"--duration-ms") {
          require(!seen_duration, "Duplicate duration option");
          seen_duration = true;
          duration = number(argv[++i], 100, 600000);
        } else {
          throw std::runtime_error("Unsupported option");
        }
      }
    }
    HANDLE input = GetStdHandle(STD_INPUT_HANDLE);
    require(input && input != INVALID_HANDLE_VALUE &&
                GetFileType(input) == FILE_TYPE_PIPE,
            "Launch the owned app with a control pipe");
    OwnedCollector collector(build);
    Module module;
    module.load(collector);
    Change change;
    Writer writer;
    require(writer.offer(prefix("ready") + ",\"build\":" + quote(utf8(build)) +
                         ",\"interval_ms\":" + std::to_string(interval) +
                         ",\"duration_ms\":" + std::to_string(duration) +
                         ",\"ranges\":" + collector.manifest() + "}"),
            "Cannot start stream");
    const auto started = Clock::now();
    auto next = started;
    unsigned long long sequence = 0, dropped = 0;
    std::string command;
    bool stopped = false;
    const char *reason = "limit";
    while (Clock::now() - started < std::chrono::milliseconds(duration)) {
      require(!writer.failed(), "Evidence output disconnected");
      DWORD available = 0;
      if (!PeekNamedPipe(input, nullptr, 0, nullptr, &available, nullptr)) {
        require(GetLastError() == ERROR_BROKEN_PIPE, "Control pipe failed");
        stopped = true;
      } else if (available) {
        char buffer[64];
        DWORD read = 0;
        require(ReadFile(input, buffer,
                         std::min<DWORD>(available, sizeof(buffer)), &read,
                         nullptr) &&
                    read,
                "Control pipe read failed");
        for (DWORD i = 0; i < read; ++i) {
          const char c = buffer[i];
          if (c == '\r')
            continue;
          if (c != '\n') {
            require((c >= 'a' && c <= 'z') || c == '-',
                    "Invalid control character");
            require(command.size() < 32, "Control command exceeds its bound");
            command += c;
            continue;
          }
          if (command == "stop") {
            stopped = true;
            break;
          }
          require(controls, "Only stop is available outside evaluation mode");
          if (command == "restore")
            change.restore();
          else if (command == "unload") {
            change.restore();
            module.unload();
          } else if (command == "load")
            module.load(collector);
          else if (command == "change-primary" ||
                   command == "change-secondary" ||
                   command == "change-outside" || command == "unreadable")
            change.apply(collector, module.value, command);
          else
            throw std::runtime_error("Unsupported evaluation control");
          std::cerr << "ack " << command << ' ' << sequence + 1 << '\n';
          command.clear();
        }
      }
      if (stopped) {
        reason = "stopped";
        break;
      }
      const auto now = Clock::now();
      if (now >= next) {
        ++sequence;
        const auto elapsed =
            std::chrono::duration_cast<std::chrono::milliseconds>(now - started)
                .count();
        std::ostringstream frame;
        frame << prefix("sample") << ",\"sequence\":" << sequence
              << ",\"elapsed_ms\":" << elapsed
              << ",\"dropped_samples\":" << dropped << ",\"observations\":[";
        const auto rows = collector.snapshot(module.value);
        for (std::size_t i = 0; i < rows.size(); ++i) {
          auto row = rows[i];
          row.pop_back();
          frame << (i ? "," : "") << row
                << ",\"phase\":\"live\",\"build\":" << quote(utf8(build))
                << "}";
        }
        frame << "]}";
        if (!writer.offer(frame.str()))
          ++dropped;
        // Do not produce a catch-up burst after a slow collection.
        next = now + std::chrono::milliseconds(interval);
      }
      Sleep(10);
    }
    change.restore();
    require(writer.finish(prefix("end") +
                          ",\"sequence\":" + std::to_string(sequence) +
                          ",\"dropped_samples\":" + std::to_string(dropped) +
                          ",\"reason\":" + quote(reason) + "}"),
            "Evidence output did not drain before shutdown");
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
