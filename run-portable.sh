#!/usr/bin/env bash
# Portable launch: every file the port generates (saves, shader/pipeline caches and Mesa's own
# caches) stays under this folder's user/ directory instead of the home directory. It does not
# read or write an installed shadPS4's saves/caches; only BB_GPU_USER_DIR is pinned here so the
# GPU cache cannot fall back to ~/.local/share/shadPS4 when user/ is missing.
#   bash run-portable.sh [extra bb-probe arguments]
# Settings (SOTC_GAME_DIR, SOTC_SYS_MODULES, SOTC_DLC_DIR, ...) still come from the environment
# or sotc.ini, as described in sotc.py. FSR 3 frame generation is opt-in:
#   SOTC_FRAMEGEN=fsr bash run-portable.sh    (F8 toggles it in game)
set -euo pipefail
cd -- "$(dirname -- "$0")"
port=$PWD
user=$port/user
mkdir -p "$user"
# bbport: keep saves and the port's GPU caches inside the project folder.
export SOTC_USER_DIR=$user
export BB_GPU_USER_DIR=$user
# Mesa/RADV keep their own compiler/pipeline caches; send those here too.
export XDG_CACHE_HOME=$user/cache
export MESA_SHADER_CACHE_DIR=$user/cache/mesa
mkdir -p "$XDG_CACHE_HOME" "$MESA_SHADER_CACHE_DIR"
# bbport: MangoHud performance overlay. It is enabled by default when installed; use
# SOTC_MANGOHUD=0 to start without it. MANGOHUD_CONFIG (or SOTC_MANGOHUD_CONFIG) customises
# the HUD, e.g. SOTC_MANGOHUD_CONFIG='fps,gpu_stats,cpu_stats,ram,vram'.
case ${SOTC_MANGOHUD:-${MANGOHUD:-1}} in
    0|off|false|no) ;;
    *)
        if command -v mangohud >/dev/null 2>&1; then
            export MANGOHUD=1
            if [[ -n ${SOTC_MANGOHUD_CONFIG:-} ]]; then export MANGOHUD_CONFIG=$SOTC_MANGOHUD_CONFIG; fi
        else
            echo 'run-portable.sh: MangoHud not found; starting without the overlay.' >&2
        fi
        ;;
esac
# Sound is optional: use your decrypted modules from user/sys_modules or an installed shadPS4.
if [[ -z ${SOTC_SYS_MODULES:-} ]]; then
    for candidate in "$user/sys_modules" "${XDG_DATA_HOME:-$HOME/.local/share}/shadPS4/sys_modules"; do
        if [[ -f $candidate/libSceNgs2.sprx && -f $candidate/libSceUlt.sprx ]]; then
            export SOTC_SYS_MODULES=$candidate
            break
        fi
    done
fi
exec bash run.sh "$@"
