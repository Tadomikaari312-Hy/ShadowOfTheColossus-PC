// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: the frame generation mode, see vk_framegen.h.

#include "video_core/renderer_vulkan/vk_framegen.h"

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace Vulkan::FrameGen {

namespace {

enum class Asked { Off, Auto, Fsr };

Asked AskedMode() {
    static const Asked asked = [] {
        if (const char* v = std::getenv("SOTC_FRAMEGEN"); v && v[0]) {
            if (std::strcmp(v, "auto") == 0) {
                return Asked::Auto;
            }
            if (std::strcmp(v, "fsr") == 0 || std::strcmp(v, "fsr3") == 0) {
                return Asked::Fsr;
            }
            if (std::strcmp(v, "off") != 0 && v[0] != '0') {
                std::fprintf(stderr, "SOTC FRAMEGEN: unknown SOTC_FRAMEGEN=%s, off (this port "
                                     "builds FSR 3 only)\n", v);
            }
            return Asked::Off;
        }
        return Asked::Off;
    }();
    return asked;
}

std::atomic<int> current{static_cast<int>(Mode::Off)};
std::atomic<bool> have_fsr{false};

} // namespace

void SetAvailable(bool fsr) {
    have_fsr = fsr;
    Mode mode = Mode::Off;
    switch (AskedMode()) {
    case Asked::Off:
        break;
    case Asked::Auto:
        mode = fsr ? Mode::Fsr : Mode::Off;
        break;
    case Asked::Fsr:
        mode = fsr ? Mode::Fsr : Mode::Off;
        break;
    }
    current = static_cast<int>(mode);
    std::fprintf(stderr, "SOTC FRAMEGEN: %s (FSR 3 %s; F8 switches)\n", Name(mode),
                 fsr ? "available" : "unavailable");
}

Mode Current() {
    return static_cast<Mode>(current.load(std::memory_order_relaxed));
}

bool AskedAtStart() {
    return AskedMode() != Asked::Off;
}

bool Available(Mode mode) {
    switch (mode) {
    case Mode::Off:
        return true;
    case Mode::Fsr:
        return have_fsr;
    }
    return false;
}

Mode Cycle() {
    Mode mode = Current();
    for (int i = 0; i < 2; ++i) {
        mode = static_cast<Mode>((static_cast<int>(mode) + 1) % 2);
        if (Available(mode)) {
            break;
        }
    }
    current = static_cast<int>(mode);
    std::fprintf(stderr, "SOTC FRAMEGEN: switched to %s\n", Name(mode));
    return mode;
}

void TestTick() {
    static const double every = [] {
        const char* v = std::getenv("SOTC_FRAMEGEN_TEST_CYCLE");
        return v ? std::atof(v) : 0.0;
    }();
    if (every <= 0.0) {
        return;
    }
    static auto last = std::chrono::steady_clock::now();
    const auto now = std::chrono::steady_clock::now();
    if (std::chrono::duration<double>(now - last).count() >= every) {
        last = now;
        Cycle();
    }
}

const char* Name(Mode mode) {
    switch (mode) {
    case Mode::Off:
        return "off";
    case Mode::Fsr:
        return "FSR 3";
    }
    return "?";
}

} // namespace Vulkan::FrameGen
