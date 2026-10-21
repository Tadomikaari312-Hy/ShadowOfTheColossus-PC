// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: the inputs of AMD FSR 3 frame generation (vk_fsrfg.cpp): the game's G-buffer depth,
// motion vectors and camera, captured from the draws with an R16G16 float target in MRT 4 (the
// motion vectors, curUV - prevUV per pixel) and the view constants the G-buffer vertex shaders
// use. This is the DLSS-G input capture of the upstream fork (vk_dlssg.cpp), stripped of
// Streamline and Windows. It is captured only while FSR 3 is the frame generation mode.

#pragma once

#include "common/types.h"
#include "video_core/renderer_vulkan/vk_common.h"
#include "video_core/texture_cache/types.h"

namespace AmdGpu {
union Regs;
}
namespace VideoCore {
class TextureCache;
}

namespace Vulkan {
class Instance;
class Runtime;
}

namespace Vulkan::FgInputs {

/// After the device is created.
void Init(const Instance& instance);

/// The current frame generation mode needs the game's inputs: the rasterizer then calls NoteDraw.
bool CapturingInputs();

/// Command processor thread, at each draw: the first G-buffer draw of the frame gives the camera
/// (guest view constants) and the depth and motion vector images.
void NoteDraw(const AmdGpu::Regs& regs, u32 mrt_mask, VideoCore::ImageId depth_id,
              VideoCore::ImageId mvec_id, VideoCore::TextureCache& texture_cache);

/// Command processor thread, in PrepareFrame (no rendering active on cmdbuf): copies this
/// frame's depth and motion vectors into images of presentation frame `frame_id` and sets the
/// frame's constants. Frames without a G-buffer pass get no inputs.
void PrepareInputs(u32 frame_id, vk::CommandBuffer cmdbuf, VideoCore::TextureCache& texture_cache,
                   Runtime& runtime, u32 game_width, u32 game_height);

/// Command processor thread, after the frame's commands are flushed.
void FrameSubmitted(u32 frame_id);

/// A presentation frame without game inputs (blank frame, re-presented frame).
void NoInputs(u32 frame_id);

/// Before the swapchain is recreated or the device destroyed.
void Suspend();

/// A frame's inputs for FSR 3 frame generation.
struct FrameInputs {
    vk::Image mvec;      ///< R16G16 float, curUV - prevUV, layout ShaderReadOnlyOptimal
    vk::ImageUsageFlags mvec_usage;
    u32 width, height;   ///< of the depth and motion vectors (the game's render size)
    float jitter[2];     ///< pixels, y down
    float z_near, z_far; ///< view distances
    float fov_y;         ///< radians
    float pos[3], up[3], right[3], fwd[3];
    bool depth_inverted; ///< 1 at the near plane
    bool reset;          ///< a camera cut
};

/// Present thread: the inputs of presentation frame `frame_id`, false when it has none.
bool GetFrameInputs(u32 frame_id, FrameInputs& out);

} // namespace Vulkan::FgInputs
