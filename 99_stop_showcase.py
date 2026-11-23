"""Stops all GPU showcase demos (01-06).

Run when HUD texts overlap — e.g. after starting several demos at once.
Re-running a single demo also toggles it off, but this script cleans all.
00 has no viewport handler, so there is nothing to clean for it.
"""

import bpy


_KEYS = (
    "gpu_showcase_hello_v1",
    "gpu_showcase_normal_overlay_v1",
    "gpu_showcase_shader_toy_v1",
    "gpu_showcase_raymarch_v1",
    "gpu_showcase_offscreen_v1",
    "gpu_showcase_compute_particles_v1",
)


def _stop_one(key):
    state = bpy.app.driver_namespace.pop(key, None)
    if not state:
        return False
    handles = []
    if isinstance(state, dict):
        # 02 used view_handle/hud_handle in older revisions;
        # 01/03/04/05/06 use a "handles" list. Support both.
        for single in ("view_handle", "hud_handle"):
            handle = state.get(single)
            if handle is not None:
                handles.append(handle)
        listed = state.get("handles")
        if isinstance(listed, (list, tuple)):
            handles.extend(listed)
        timer = state.get("timer")
        if timer is not None:
            try:
                if bpy.app.timers.is_registered(timer):
                    bpy.app.timers.unregister(timer)
            except (ReferenceError, ValueError, RuntimeError):
                pass
        offscreen = state.get("offscreen")
        if offscreen is not None:
            try:
                offscreen.free()
            except (ReferenceError, RuntimeError):
                pass
        # 06 stores ping-pong GPUTextures; dropping refs releases GPU memory.
        for tex in state.get("textures", ()):
            try:
                del tex
            except (ReferenceError, RuntimeError):
                pass
    for handle in handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        except (ReferenceError, ValueError, RuntimeError):
            pass
    return True


def main():
    stopped = [key for key in _KEYS if _stop_one(key)]

    # Force-refresh viewports so no ghost overlays remain.
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except (AttributeError, ReferenceError, RuntimeError):
        pass

    print("Stopped: " + (", ".join(stopped) if stopped else "nothing was running"))


if __name__ == "__main__":
    main()
