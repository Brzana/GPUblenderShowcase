"""Zatrzymuje wszystkie dema GPU showcase (01-04).

Uruchom, gdy teksty HUD nakladaja sie na siebie — np. po odpaleniu kilku
dem naraz. Uruchomienie tego samego dema ponownie tez je wylacza, ale ten
skrypt czysci wszystko naraz.
"""

import bpy


_KEYS = (
    "gpu_showcase_normal_overlay_v1",
    "gpu_showcase_raymarch_v1",
    "gpu_showcase_compute_particles_v1",
    "gpu_showcase_offscreen_v1",
)


def _stop_one(key):
    state = bpy.app.driver_namespace.pop(key, None)
    if not state:
        return False
    handles = []
    if isinstance(state, dict):
        # Format 01: osobne klucze; format 02/03/04: lista "handles".
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
    for handle in handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
        except (ReferenceError, ValueError, RuntimeError):
            pass
    return True


stopped = [key for key in _KEYS if _stop_one(key)]

# Na koniec wymus odswiezenie wszystkich viewportow, zeby nie zostaly duchy.
try:
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
except (AttributeError, ReferenceError):
    pass

print("Zatrzymano: " + (", ".join(stopped) if stopped else "nic nie bylo aktywne"))
