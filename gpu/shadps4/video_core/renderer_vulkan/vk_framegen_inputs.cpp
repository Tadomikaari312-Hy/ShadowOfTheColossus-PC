// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: the inputs of AMD FSR 3 frame generation, see vk_framegen_inputs.h. Ported to Linux
// from the upstream fork's vk_dlssg.cpp (DLSS-G), with Streamline and Windows removed.

#include "video_core/renderer_vulkan/vk_framegen_inputs.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <utility>
#include <vk_mem_alloc.h>

#include "core/memory.h"
#include "video_core/amdgpu/regs.h"
#include "video_core/renderer_vulkan/vk_framegen.h"
#include "video_core/renderer_vulkan/vk_fsrfg.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_runtime.h"
#include "video_core/texture_cache/texture_cache.h"

namespace Vulkan::FgInputs {

namespace {

/// The camera of a frame, from the guest's view constants (column vectors: clip = M * p).
struct Camera {
    double vp[4][4];      ///< world -> clip, no jitter
    double prev_vp[4][4]; ///< the previous frame's
    double jitter[2];     ///< NDC offset added to clip.xy / clip.w
    double pos[3];        ///< world position
};

/// What the first G-buffer draw of the frame being processed gave (command processor thread).
struct Pending {
    bool captured{};
    VideoCore::ImageId depth_id, mvec_id;
    u64 depth_uid{}, mvec_uid{};
    Camera cam{};
    float yscale{-1.0f}, zscale{1.0f}, zoffset{0.0f};
};

/// The FSR 3 constants of one frame, derived from the camera like Streamline's.
struct FrameConstants {
    float jitter[2];     ///< pixels, y down
    float z_near, z_far; ///< view distances
    float fov_y;         ///< radians
    float pos[3], up[3], right[3], fwd[3];
    bool depth_inverted; ///< 1 at the near plane
    bool reset;          ///< a camera cut
};

/// The inputs of one presentation frame (vk_presenter.h Frame, by id).
struct FrameSlot {
    VmaAllocation depth_alloc{}, mvec_alloc{};
    vk::Image depth, mvec;
    vk::ImageView depth_view, mvec_view;
    vk::Format depth_format{}, mvec_format{};
    u32 width{}, height{};
    u32 index{}; ///< frame counter, 0: no game frame
    bool valid{}; ///< depth, motion vectors and constants are set for this frame
    FrameConstants constants{};
};

constexpr u32 kMaxFrames = 16;
constexpr u64 kMask48 = 0xFFFFFFFFFFFFull;

const Instance* g_instance{};
Pending pending;                     // command processor thread
std::array<FrameSlot, kMaxFrames> frames;
u32 next_index = 0;                  // command processor thread
bool have_prev = false;              // command processor thread
double prev_pos[3]{}, prev_fwd[3];   // command processor thread
u32 bad_cameras = 0;

double Dot3(const double* a, const double* b) {
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

bool Finite(const double* v, int n) {
    for (int i = 0; i < n; ++i) {
        if (!std::isfinite(v[i])) {
            return false;
        }
    }
    return true;
}

/// Reads the view constants the G-buffer vertex shaders use (SotC: srt walker of
/// vs_0x79a4f6d5): view constant buffer = *(*(VS user data 0..1) + 8); its world -> clip matrix
/// rows at +0x80, the previous frame's at +0x100 (rows x, y and w only), the TAA jitter (NDC) at
/// +0x140, the camera position at +0x230.
bool ReadCamera(const AmdGpu::Regs& regs, Camera& cam) {
    auto* memory = Core::Memory::Instance();
    const u64 ud = (u64(regs.vs_program.user_data[0]) | (u64(regs.vs_program.user_data[1]) << 32)) &
                   kMask48;
    if (ud == 0) {
        return false;
    }
    u64 cb = 0;
    if (!memory->TryReadBacking(ud + 8, &cb, sizeof(cb))) {
        return false;
    }
    cb &= kMask48;
    if (cb == 0) {
        return false;
    }
    float raw[0x48 / 4]; // 0x100 .. 0x148
    float cur[16], pos[3];
    if (!memory->TryReadBacking(cb + 0x80, cur, sizeof(cur)) ||
        !memory->TryReadBacking(cb + 0x100, raw, sizeof(raw)) ||
        !memory->TryReadBacking(cb + 0x230, pos, sizeof(pos))) {
        return false;
    }
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            cam.vp[r][c] = cur[r * 4 + c];
        }
    }
    for (int c = 0; c < 4; ++c) {
        cam.prev_vp[0][c] = raw[0 + c];
        cam.prev_vp[1][c] = raw[4 + c];
        cam.prev_vp[2][c] = cur[8 + c];
        cam.prev_vp[3][c] = raw[12 + c];
    }
    cam.jitter[0] = raw[16];
    cam.jitter[1] = raw[17];
    for (int i = 0; i < 3; ++i) {
        cam.pos[i] = pos[i];
    }
    if (!Finite(&cam.vp[0][0], 16) || !Finite(&cam.prev_vp[0][0], 16) || !Finite(cam.jitter, 2) ||
        !Finite(cam.pos, 3)) {
        return false;
    }
    const double s = std::sqrt(Dot3(cam.vp[3], cam.vp[3]));
    if (s < 1e-3 || s > 1e3) {
        return false;
    }
    const double w_at_eye = Dot3(cam.vp[3], cam.pos) + cam.vp[3][3];
    const double scale = 1.0 + std::abs(cam.vp[3][3]);
    return std::abs(w_at_eye) < 1e-2 * scale;
}

/// Fills the FSR 3 constants from the camera. False when the matrix is not a perspective
/// projection we understand.
bool MakeConstants(const Pending& p, u32 width, u32 height, FrameConstants& out) {
    double m[4][4]{}, mp[4][4]{};
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            m[r][c] = p.cam.vp[r][c];
            mp[r][c] = p.cam.prev_vp[r][c];
        }
    }
    double jitter_y = p.cam.jitter[1];
    // The clip space has +y up (D3D-like). A positive viewport y scale maps NDC +y down: flip y
    // so that it does.
    if (p.yscale > 0.0f) {
        for (int c = 0; c < 4; ++c) {
            m[1][c] = -m[1][c];
            mp[1][c] = -mp[1][c];
        }
        jitter_y = -jitter_y;
    }
    // Depth as stored: zscale * z / w + zoffset.
    for (int c = 0; c < 4; ++c) {
        m[2][c] = p.zscale * m[2][c] + p.zoffset * m[3][c];
        mp[2][c] = p.zscale * mp[2][c] + p.zoffset * mp[3][c];
    }

    // Camera basis: forward from the w row, right and up from the x and y rows with their
    // forward part removed (off-centre terms).
    const double s = std::sqrt(Dot3(m[3], m[3]));
    double fwd[3] = {m[3][0] / s, m[3][1] / s, m[3][2] / s};
    double right[3], up[3];
    const double cx = Dot3(m[0], fwd), cy = Dot3(m[1], fwd);
    for (int i = 0; i < 3; ++i) {
        right[i] = m[0][i] - cx * fwd[i];
        up[i] = m[1][i] - cy * fwd[i];
    }
    const double sx = std::sqrt(Dot3(right, right)), sy = std::sqrt(Dot3(up, up));
    if (sx < 1e-6 || sy < 1e-6) {
        return false;
    }
    for (int i = 0; i < 3; ++i) {
        right[i] /= sx;
        up[i] /= sy;
    }
    // Depth: z row = k * w row + (0, 0, 0, b); depth(d) = k + b / (s * d) at view distance d.
    const double k = Dot3(m[2], m[3]) / (s * s);
    const double b = (m[2][3] - k * m[3][3]) / s;
    const bool inverted = b > 0.0;
    double z_near, z_far;
    if (inverted) { // depth 1 at the near plane, 0 at the far one (k = 0: infinite)
        z_near = b / (1.0 - k);
        z_far = k < -1e-9 ? -b / k : 1e6;
    } else {
        z_near = std::abs(k) > 1e-9 ? -b / k : 0.1;
        z_far = b / (1.0 - k);
    }
    if (!(z_near > 0.0) || !(z_far > z_near)) {
        return false;
    }

    // Pixel space jitter: NDC x right, y up -> pixels x right, y down.
    out.jitter[0] = static_cast<float>(p.cam.jitter[0] * width * 0.5);
    out.jitter[1] = static_cast<float>(-jitter_y * height * 0.5);
    out.z_near = static_cast<float>(z_near);
    out.z_far = static_cast<float>(z_far);
    out.fov_y = static_cast<float>(2.0 * std::atan(s / sy));
    for (int i = 0; i < 3; ++i) {
        out.pos[i] = static_cast<float>(p.cam.pos[i]);
        out.up[i] = static_cast<float>(up[i]);
        out.right[i] = static_cast<float>(right[i]);
        out.fwd[i] = static_cast<float>(fwd[i]);
    }
    out.depth_inverted = inverted;

    // A cut: the camera jumped or turned a lot since the last frame.
    bool reset = !have_prev;
    if (have_prev) {
        const double d[3] = {p.cam.pos[0] - prev_pos[0], p.cam.pos[1] - prev_pos[1],
                             p.cam.pos[2] - prev_pos[2]};
        reset = Dot3(d, d) > 50.0 * 50.0 || Dot3(fwd, prev_fwd) < 0.8;
    }
    out.reset = reset;
    have_prev = true;
    std::memcpy(prev_pos, p.cam.pos, sizeof(prev_pos));
    std::memcpy(prev_fwd, fwd, sizeof(prev_fwd));
    return true;
}

void DestroyImages(FrameSlot& f) {
    const vk::Device device = g_instance->GetDevice();
    if (f.depth_view) {
        device.destroyImageView(f.depth_view);
    }
    if (f.mvec_view) {
        device.destroyImageView(f.mvec_view);
    }
    if (f.depth) {
        vmaDestroyImage(g_instance->GetAllocator(), f.depth, f.depth_alloc);
    }
    if (f.mvec) {
        vmaDestroyImage(g_instance->GetAllocator(), f.mvec, f.mvec_alloc);
    }
    f = FrameSlot{};
}

bool CreateImage(vk::Format format, u32 width, u32 height, bool depth, vk::Image& image,
                 VmaAllocation& alloc, vk::ImageView& view) {
    vk::ImageUsageFlags usage = vk::ImageUsageFlagBits::eTransferDst |
                                vk::ImageUsageFlagBits::eTransferSrc |
                                vk::ImageUsageFlagBits::eSampled;
    if (!depth) {
        usage |= vk::ImageUsageFlagBits::eStorage;
    }
    const VkImageCreateInfo info = static_cast<VkImageCreateInfo>(vk::ImageCreateInfo{
        .imageType = vk::ImageType::e2D,
        .format = format,
        .extent = {width, height, 1},
        .mipLevels = 1,
        .arrayLayers = 1,
        .samples = vk::SampleCountFlagBits::e1,
        .tiling = vk::ImageTiling::eOptimal,
        .usage = usage,
        .initialLayout = vk::ImageLayout::eUndefined,
    });
    const VmaAllocationCreateInfo alloc_info = {
        .usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE,
    };
    VkImage raw{};
    if (vmaCreateImage(g_instance->GetAllocator(), &info, &alloc_info, &raw, &alloc, nullptr) !=
        VK_SUCCESS) {
        return false;
    }
    image = vk::Image{raw};
    const vk::ImageViewCreateInfo view_info = {
        .image = image,
        .viewType = vk::ImageViewType::e2D,
        .format = format,
        .subresourceRange{
            .aspectMask = depth ? vk::ImageAspectFlagBits::eDepth : vk::ImageAspectFlagBits::eColor,
            .baseMipLevel = 0,
            .levelCount = 1,
            .baseArrayLayer = 0,
            .layerCount = 1,
        },
    };
    auto [result, v] = g_instance->GetDevice().createImageView(view_info);
    if (result != vk::Result::eSuccess) {
        vmaDestroyImage(g_instance->GetAllocator(), image, alloc);
        image = nullptr;
        return false;
    }
    view = v;
    return true;
}

bool EnsureImages(FrameSlot& f, vk::Format depth_format, vk::Format mvec_format, u32 width,
                  u32 height) {
    if (f.depth && f.depth_format == depth_format && f.mvec_format == mvec_format &&
        f.width == width && f.height == height) {
        return true;
    }
    const u32 index = f.index;
    DestroyImages(f);
    f.index = index;
    if (!CreateImage(depth_format, width, height, true, f.depth, f.depth_alloc, f.depth_view) ||
        !CreateImage(mvec_format, width, height, false, f.mvec, f.mvec_alloc, f.mvec_view)) {
        std::fprintf(stderr, "SOTC FRAMEGEN: cannot create the input images %ux%u\n", width, height);
        DestroyImages(f);
        f.index = index;
        return false;
    }
    f.depth_format = depth_format;
    f.mvec_format = mvec_format;
    f.width = width;
    f.height = height;
    return true;
}

} // namespace

void Init(const Instance& instance) {
    g_instance = &instance;
}

bool CapturingInputs() {
    return FrameGen::Current() == FrameGen::Mode::Fsr && g_instance != nullptr;
}

void NoteDraw(const AmdGpu::Regs& regs, u32 mrt_mask, VideoCore::ImageId depth_id,
              VideoCore::ImageId mvec_id, VideoCore::TextureCache& texture_cache) {
    if (pending.captured || !(mrt_mask & (1u << 4)) || !depth_id || !mvec_id ||
        !CapturingInputs()) {
        return;
    }
    const auto& cb4 = regs.color_buffers[4];
    if (!cb4 || cb4.GetDataFmt() != AmdGpu::DataFormat::Format16_16 ||
        cb4.GetNumberFmt() != AmdGpu::NumberFormat::Float || !regs.depth_buffer.DepthValid()) {
        return;
    }
    auto& depth = texture_cache.GetImage(depth_id);
    auto& mvec = texture_cache.GetImage(mvec_id);
    if (depth.info.size.width < 640 || mvec.info.size.width < 640 || depth.info.num_samples != 1 ||
        mvec.info.num_samples != 1 || !(depth.aspect_mask & vk::ImageAspectFlagBits::eDepth)) {
        return;
    }
    Pending p{};
    if (!ReadCamera(regs, p.cam)) {
        if (bad_cameras++ < 5) {
            std::fprintf(stderr, "SOTC FRAMEGEN: G-buffer draw without a readable camera\n");
        }
        return;
    }
    p.captured = true;
    p.depth_id = depth_id;
    p.depth_uid = depth.image_uid;
    p.mvec_id = mvec_id;
    p.mvec_uid = mvec.image_uid;
    const auto& vp = regs.viewports[0];
    p.yscale = regs.viewport_control.yscale_enable ? vp.yscale : 1.0f;
    p.zscale = regs.viewport_control.zscale_enable ? vp.zscale : 1.0f;
    p.zoffset = regs.viewport_control.zoffset_enable ? vp.zoffset : 0.0f;
    pending = p;
}

void PrepareInputs(u32 frame_id, vk::CommandBuffer cmdbuf, VideoCore::TextureCache& texture_cache,
                   Runtime& runtime, u32 game_width, u32 game_height) {
    if (frame_id >= kMaxFrames) {
        return;
    }
    FrameSlot& f = frames[frame_id];
    f.valid = false;
    FsrFg::NoDepth(frame_id);
    if (FrameGen::Current() != FrameGen::Mode::Fsr) {
        pending = Pending{};
        return;
    }
    f.index = ++next_index;

    const Pending p = std::exchange(pending, Pending{});
    if (!p.captured) {
        return;
    }
    VideoCore::Image* depth = texture_cache.TryGetImage(p.depth_id, p.depth_uid);
    VideoCore::Image* mvec = texture_cache.TryGetImage(p.mvec_id, p.mvec_uid);
    if (!depth || !mvec) {
        return;
    }
    const u32 width = std::min({game_width, depth->info.size.width, mvec->info.size.width});
    const u32 height = std::min({game_height, depth->info.size.height, mvec->info.size.height});
    if (width < 64 || height < 64) {
        return;
    }
    FrameConstants constants{};
    if (!MakeConstants(p, width, height, constants)) {
        if (bad_cameras++ < 5) {
            std::fprintf(stderr, "SOTC FRAMEGEN: camera matrix not understood\n");
        }
        return;
    }
    if (!EnsureImages(f, depth->info.pixel_format, mvec->info.pixel_format, width, height)) {
        return;
    }

    // Game images -> transfer source (tracked by the texture cache), ours -> transfer dest.
    runtime.Transit(depth, vk::ImageLayout::eTransferSrcOptimal, vk::PipelineStageFlagBits2::eCopy,
                    vk::AccessFlagBits2::eTransferRead);
    runtime.Transit(mvec, vk::ImageLayout::eTransferSrcOptimal, vk::PipelineStageFlagBits2::eCopy,
                    vk::AccessFlagBits2::eTransferRead);
    runtime.FlushBarriers();
    const auto range = [](vk::ImageAspectFlags aspect) {
        return vk::ImageSubresourceRange{
            .aspectMask = aspect, .baseMipLevel = 0, .levelCount = 1, .baseArrayLayer = 0,
            .layerCount = 1};
    };
    const vk::ImageAspectFlags depth_aspect =
        depth->aspect_mask & (vk::ImageAspectFlagBits::eDepth | vk::ImageAspectFlagBits::eStencil);
    const std::array to_dst{
        vk::ImageMemoryBarrier2{
            .srcStageMask = vk::PipelineStageFlagBits2::eAllCommands,
            .srcAccessMask = vk::AccessFlagBits2::eNone,
            .dstStageMask = vk::PipelineStageFlagBits2::eCopy,
            .dstAccessMask = vk::AccessFlagBits2::eTransferWrite,
            .oldLayout = vk::ImageLayout::eUndefined,
            .newLayout = vk::ImageLayout::eTransferDstOptimal,
            .image = f.depth,
            .subresourceRange = range(depth_aspect),
        },
        vk::ImageMemoryBarrier2{
            .srcStageMask = vk::PipelineStageFlagBits2::eAllCommands,
            .srcAccessMask = vk::AccessFlagBits2::eNone,
            .dstStageMask = vk::PipelineStageFlagBits2::eCopy,
            .dstAccessMask = vk::AccessFlagBits2::eTransferWrite,
            .oldLayout = vk::ImageLayout::eUndefined,
            .newLayout = vk::ImageLayout::eTransferDstOptimal,
            .image = f.mvec,
            .subresourceRange = range(vk::ImageAspectFlagBits::eColor),
        },
    };
    cmdbuf.pipelineBarrier2(vk::DependencyInfo{
        .imageMemoryBarrierCount = static_cast<u32>(to_dst.size()),
        .pImageMemoryBarriers = to_dst.data(),
    });
    const auto copy = [&](vk::Image src, vk::Image dst, vk::ImageAspectFlags aspect) {
        const vk::ImageCopy region{
            .srcSubresource = {aspect, 0, 0, 1},
            .srcOffset = {0, 0, 0},
            .dstSubresource = {aspect, 0, 0, 1},
            .dstOffset = {0, 0, 0},
            .extent = {width, height, 1},
        };
        cmdbuf.copyImage(src, vk::ImageLayout::eTransferSrcOptimal, dst,
                         vk::ImageLayout::eTransferDstOptimal, region);
    };
    copy(depth->GetImage(), f.depth, vk::ImageAspectFlagBits::eDepth);
    copy(mvec->GetImage(), f.mvec, vk::ImageAspectFlagBits::eColor);
    const std::array to_read{
        vk::ImageMemoryBarrier2{
            .srcStageMask = vk::PipelineStageFlagBits2::eCopy,
            .srcAccessMask = vk::AccessFlagBits2::eTransferWrite,
            .dstStageMask = vk::PipelineStageFlagBits2::eAllCommands,
            .dstAccessMask = vk::AccessFlagBits2::eShaderRead,
            .oldLayout = vk::ImageLayout::eTransferDstOptimal,
            .newLayout = vk::ImageLayout::eShaderReadOnlyOptimal,
            .image = f.depth,
            .subresourceRange = range(depth_aspect),
        },
        vk::ImageMemoryBarrier2{
            .srcStageMask = vk::PipelineStageFlagBits2::eCopy,
            .srcAccessMask = vk::AccessFlagBits2::eTransferWrite,
            .dstStageMask = vk::PipelineStageFlagBits2::eAllCommands,
            .dstAccessMask = vk::AccessFlagBits2::eShaderRead,
            .oldLayout = vk::ImageLayout::eTransferDstOptimal,
            .newLayout = vk::ImageLayout::eShaderReadOnlyOptimal,
            .image = f.mvec,
            .subresourceRange = range(vk::ImageAspectFlagBits::eColor),
        },
    };
    cmdbuf.pipelineBarrier2(vk::DependencyInfo{
        .imageMemoryBarrierCount = static_cast<u32>(to_read.size()),
        .pImageMemoryBarriers = to_read.data(),
    });

    f.constants = constants;
    f.valid = true;
    // FSR 3 reads depth as R32F: from the copy, now ShaderReadOnlyOptimal.
    FsrFg::ConvertDepth(frame_id, cmdbuf, f.depth_view, width, height, constants.depth_inverted);
}

void FrameSubmitted(u32 frame_id) {
    (void)frame_id;
}

void NoInputs(u32 frame_id) {
    if (frame_id < kMaxFrames) {
        frames[frame_id].valid = false;
        frames[frame_id].index = 0;
    }
    FsrFg::NoDepth(frame_id);
}

void Suspend() {
    pending = Pending{};
    for (auto& f : frames) {
        f.valid = false;
    }
}

bool GetFrameInputs(u32 frame_id, FrameInputs& out) {
    if (frame_id >= kMaxFrames || !frames[frame_id].valid) {
        return false;
    }
    const FrameSlot& f = frames[frame_id];
    const FrameConstants& c = f.constants;
    out.mvec = f.mvec;
    out.mvec_usage = vk::ImageUsageFlagBits::eTransferDst | vk::ImageUsageFlagBits::eTransferSrc |
                     vk::ImageUsageFlagBits::eSampled | vk::ImageUsageFlagBits::eStorage;
    out.width = f.width;
    out.height = f.height;
    out.jitter[0] = c.jitter[0];
    out.jitter[1] = c.jitter[1];
    out.z_near = c.z_near;
    out.z_far = c.z_far;
    out.fov_y = c.fov_y;
    std::memcpy(out.pos, c.pos, sizeof(out.pos));
    std::memcpy(out.up, c.up, sizeof(out.up));
    std::memcpy(out.right, c.right, sizeof(out.right));
    std::memcpy(out.fwd, c.fwd, sizeof(out.fwd));
    out.depth_inverted = c.depth_inverted;
    out.reset = c.reset;
    return true;
}

} // namespace Vulkan::FgInputs
