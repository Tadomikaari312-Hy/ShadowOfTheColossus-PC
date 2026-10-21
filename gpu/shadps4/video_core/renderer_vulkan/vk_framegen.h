// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: the frame generation mode. Only AMD FSR 3 frame generation (vk_fsrfg.cpp) is built on
// this port: one generated frame between two game frames (a game locked at 30 FPS is shown at
// 60). SOTC_FRAMEGEN=off|auto|fsr chooses the mode at start. F8 in game switches off <-> FSR 3.

#pragma once

namespace Vulkan::FrameGen {

enum class Mode : int { Off = 0, Fsr = 1 };

/// After the device is created: whether this GPU can run FSR 3. Resolves auto.
void SetAvailable(bool fsr);

/// The current mode (any thread).
Mode Current();

/// A mode was asked at start (the presenter keeps more frames in flight).
bool AskedAtStart();

bool Available(Mode mode);

/// F8 (window thread): the next available mode, which it returns.
Mode Cycle();

/// For the overlay: "off" or "FSR 3".
const char* Name(Mode mode);

/// Present thread, at each game frame: SOTC_FRAMEGEN_TEST_CYCLE=<seconds> switches the mode
/// like F8 that often (scripted tests of the switches).
void TestTick();

} // namespace Vulkan::FrameGen
