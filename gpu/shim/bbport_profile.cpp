// bbport: in-process sampler for a single host thread (SOTC_PROFILE=1).
//
// Linux only. A SIGPROF is delivered with tgkill() to one chosen thread, so
// guest fibers (16 KiB stacks) never receive the signal and cannot overflow.
// The handler records only the interrupted RIP and TID; the sampler thread
// writes "tid offset" lines where offset is relative to libbbgpu.so, ready for
// addr2line.
#ifdef __linux__

#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <pthread.h>
#include <signal.h>
#include <sys/syscall.h>
#include <sys/ucontext.h>
#include <time.h>
#include <unistd.h>
#include <ucontext.h>

namespace {

constexpr std::size_t kMaxSamples = 200000;
constexpr int kStackWords = 16;

struct Sample {
    std::uintptr_t rip;
    std::uintptr_t stack[kStackWords];
    std::uint32_t tid;
};

Sample g_samples[kMaxSamples];
std::atomic<std::uint32_t> g_count{0};
std::atomic<bool> g_run{true};

void Handler(int, siginfo_t*, void* context) {
    auto* uc = static_cast<ucontext_t*>(context);
    const std::uint32_t i = g_count.fetch_add(1, std::memory_order_relaxed);
    if (i < kMaxSamples) {
        g_samples[i].rip = static_cast<std::uintptr_t>(uc->uc_mcontext.gregs[REG_RIP]);
        const auto sp = reinterpret_cast<const std::uintptr_t*>(uc->uc_mcontext.gregs[REG_RSP]);
        for (int k = 0; k < kStackWords; ++k) {
            g_samples[i].stack[k] = sp[k];
        }
        g_samples[i].tid = static_cast<std::uint32_t>(syscall(SYS_gettid));
    }
}

pid_t FindThread(const char* prefix) {
    DIR* dir = opendir("/proc/self/task");
    if (!dir) {
        return 0;
    }
    const std::size_t len = std::strlen(prefix);
    pid_t found = 0;
    while (dirent* entry = readdir(dir)) {
        if (entry->d_name[0] < '0' || entry->d_name[0] > '9') {
            continue;
        }
        char path[64];
        std::snprintf(path, sizeof(path), "/proc/self/task/%s/comm", entry->d_name);
        FILE* f = std::fopen(path, "r");
        if (!f) {
            continue;
        }
        char comm[32] = {};
        if (std::fgets(comm, sizeof(comm), f)) {
            const std::size_t n = std::strcspn(comm, "\n");
            comm[n] = '\0';
            if (std::strncmp(comm, prefix, len) == 0) {
                found = static_cast<pid_t>(std::atoi(entry->d_name));
                std::fclose(f);
                break;
            }
        }
        std::fclose(f);
    }
    closedir(dir);
    return found;
}

int IntEnv(const char* name, int fallback) {
    const char* value = std::getenv(name);
    return value ? std::atoi(value) : fallback;
}

void CopyMaps(const char* path) {
    FILE* in = std::fopen("/proc/self/maps", "r");
    if (!in) {
        return;
    }
    char maps_path[512];
    std::snprintf(maps_path, sizeof(maps_path), "%s.maps", path);
    FILE* out = std::fopen(maps_path, "w");
    if (!out) {
        std::fclose(in);
        return;
    }
    char line[512];
    while (std::fgets(line, sizeof(line), in)) {
        std::fputs(line, out);
    }
    std::fclose(in);
    std::fclose(out);
}

void Dump() {
    const char* path = std::getenv("SOTC_PROFILE_OUT");
    if (!path) {
        path = "/tmp/opencode/draw-profile.txt";
    }
    CopyMaps(path);
    FILE* f = std::fopen(path, "w");
    if (!f) {
        std::fprintf(stderr, "SOTC PROFILE: cannot write %s\n", path);
        return;
    }
    const std::uint32_t total = g_count.load(std::memory_order_relaxed);
    const std::uint32_t limit = total < kMaxSamples ? total : kMaxSamples;
    for (std::uint32_t i = 0; i < limit; ++i) {
        std::fprintf(f, "%u %llx", g_samples[i].tid,
                     static_cast<unsigned long long>(g_samples[i].rip));
        for (int k = 0; k < kStackWords; ++k) {
            std::fprintf(f, " %llx", static_cast<unsigned long long>(g_samples[i].stack[k]));
        }
        std::fputc('\n', f);
    }
    std::fclose(f);
    std::fprintf(stderr, "SOTC PROFILE: %u samples -> %s\n", limit, path);
}

void* Sampler(void*) {
    const char* list = std::getenv("SOTC_PROFILE_THREAD");
    if (!list) {
        list = "shadPS4:GpuRec";
    }
    const int interval_us = IntEnv("SOTC_PROFILE_INTERVAL_US", 1000);
    const int seconds = IntEnv("SOTC_PROFILE_SECONDS", 60);
    const int delay = IntEnv("SOTC_PROFILE_DELAY", 0);

    constexpr int kMaxTargets = 8;
    char prefixes[kMaxTargets][32] = {};
    pid_t tids[kMaxTargets] = {};
    int targets = 0;
    {
        char copy[256];
        std::snprintf(copy, sizeof(copy), "%s", list);
        for (char* token = std::strtok(copy, ","); token && targets < kMaxTargets;
             token = std::strtok(nullptr, ",")) {
            std::snprintf(prefixes[targets], sizeof(prefixes[targets]), "%s", token);
            ++targets;
        }
    }
    if (targets == 0) {
        return nullptr;
    }
    for (int attempts = 0; attempts < 2400 && g_run.load(std::memory_order_relaxed); ++attempts) {
        bool all = true;
        for (int i = 0; i < targets; ++i) {
            if (!tids[i]) {
                tids[i] = FindThread(prefixes[i]);
            }
            all = all && tids[i] != 0;
        }
        if (all) {
            break;
        }
        usleep(100 * 1000);
    }
    for (int i = 0; i < targets; ++i) {
        std::fprintf(stderr, "SOTC PROFILE: '%s' -> tid %d\n", prefixes[i],
                     static_cast<int>(tids[i]));
    }
    std::fprintf(stderr, "SOTC PROFILE: sampling for %ds (delay %ds)\n", seconds, delay);
    if (delay > 0) {
        sleep(static_cast<unsigned>(delay));
    }

    struct timespec start {};
    clock_gettime(CLOCK_MONOTONIC, &start);
    while (g_run.load(std::memory_order_relaxed)) {
        for (int i = 0; i < targets; ++i) {
            if (tids[i]) {
                syscall(SYS_tgkill, getpid(), tids[i], SIGPROF);
            }
        }
        struct timespec req {0, static_cast<long>(interval_us) * 1000L};
        nanosleep(&req, nullptr);
        struct timespec now {};
        clock_gettime(CLOCK_MONOTONIC, &now);
        const double elapsed = (now.tv_sec - start.tv_sec) + (now.tv_nsec - start.tv_nsec) / 1e9;
        if (elapsed >= seconds) {
            break;
        }
    }
    g_run.store(false, std::memory_order_relaxed);
    Dump();
    return nullptr;
}

__attribute__((constructor)) void BbPortProfileInit() {
    if (!std::getenv("SOTC_PROFILE")) {
        return;
    }
    struct sigaction action {};
    action.sa_sigaction = Handler;
    action.sa_flags = SA_SIGINFO | SA_RESTART;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGPROF, &action, nullptr) != 0) {
        std::fprintf(stderr, "SOTC PROFILE: sigaction failed: %s\n", std::strerror(errno));
        return;
    }
    pthread_t thread;
    if (pthread_create(&thread, nullptr, Sampler, nullptr) == 0) {
        pthread_detach(thread);
    }
}

} // namespace

#else

namespace {
void BbPortProfileUnused() {}
} // namespace

#endif
