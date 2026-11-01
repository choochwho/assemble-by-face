import math
import textwrap

import blf
import bpy
import gpu
from bpy.app.handlers import persistent
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils.geometry import tessellate_polygon

from . import operators
from .operators import tools_enabled

HIGHLIGHT = (1.0, 0.55, 0.05)       # both picked faces share this colour
INSTRUCTIONS = ("Click Select Faces, then click a face on the object that stays put and a "
                "face on the object to move, near the corner to join. Then Assemble.")


def _wrapped(layout, context, text, icon="NONE"):
    """Labels wrapped to the sidebar's current width."""
    scale = context.preferences.system.ui_scale
    width = context.region.width if context.region else 300
    chars = max(20, int((width - 40 * scale) / (6.5 * scale)))
    col = layout.column(align=True)
    for i, line in enumerate(textwrap.wrap(text, chars)):
        col.label(text=line, icon=icon if i == 0 else ("BLANK1" if icon != "NONE" else "NONE"))


def _shortcut(idname):
    for km, kmi in operators._keymaps:
        if kmi.idname == idname:
            return kmi.to_string()
    return ""


class VIEW3D_PT_assemble_by_face(bpy.types.Panel):
    bl_label = "Assemble by Face"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Assemble by Face"

    def draw_header(self, context):
        self.layout.prop(context.scene.assemble_by_face, "enabled", text="")

    def draw(self, context):
        s = context.scene.assemble_by_face
        layout = self.layout
        if not s.enabled:
            layout.label(text="Tick the box to use the tools.")
            return
        _wrapped(layout, context, INSTRUCTIONS, icon="INFO")

        key = _shortcut(operators.ABF_OT_select_faces.bl_idname)
        layout.operator("assemble_by_face.select_faces", icon="FACESEL",
                        text=f"Select Faces ({key})" if key else "Select Faces")
        col = layout.column(align=True)
        for label, ref in (("1 stays", s.face_a), ("2 moves", s.face_b)):
            text = (f"{label}: {ref.obj.name}, face {ref.face}" if ref.is_set()
                    else f"{label}: not picked")
            col.label(text=text, icon="CHECKMARK" if ref.is_set() else "DOT")

        row = layout.row(align=True)
        key = _shortcut(operators.ABF_OT_assemble.bl_idname)
        row.operator("assemble_by_face.assemble", icon="SNAP_ON",
                     text=f"Assemble ({key})" if key else "Assemble")
        row.operator("assemble_by_face.clear_faces", text="", icon="X")
        if draw_error:
            box = layout.box()
            box.alert = True
            box.label(text="Couldn't draw the highlight:", icon="ERROR")
            box.label(text=draw_error)


class VIEW3D_PT_assemble_by_face_merge(bpy.types.Panel):
    bl_label = "Merge"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Assemble by Face"

    @classmethod
    def poll(cls, context):
        return tools_enabled(context)

    def draw(self, context):
        s = context.scene.assemble_by_face
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(s, "merge_pct")
        layout.prop(s, "gap_pct")
        layout.prop(s, "seam_pct")
        meshes = [o for o in context.selected_objects if o.type == "MESH"]
        if len(meshes) >= 2:
            unit = context.scene.unit_settings
            fmt = lambda v: bpy.utils.units.to_string(unit.system, "LENGTH",
                                                      v * unit.scale_length, precision=3)
            size = operators.assembled_size(meshes)
            spacing, gap, seam = operators.merge_settings(context, meshes)
            _wrapped(layout, context,
                     f"The selected parts span {fmt(size)} (their combined size, once "
                     f"they're joined), so 1% = {fmt(size / 100)}: merge {fmt(spacing)}, "
                     f"gaps {fmt(gap)}, seam {fmt(seam)}.")
        layout.operator("assemble_by_face.merge", icon="MOD_BOOLEAN")
        layout.operator("assemble_by_face.check_manifold", icon="CHECKMARK")


# --------------------------------------------------------------------------
# Viewport highlight of the picked faces. The hooks only exist while the
# tools are on, and are re-added just after register (see _resync_drawing).
# --------------------------------------------------------------------------

_handles = []
draw_error = None


def _picked(context):
    """[(face corners in world space, chosen corner, label)] for picked faces."""
    global draw_error
    out = []
    s = context.scene.assemble_by_face
    for label, ref in (("1", s.face_a), ("2", s.face_b)):
        try:
            if ref.is_set() and ref.obj.visible_get(view_layer=context.view_layer):
                mw, mesh = ref.obj.matrix_world, ref.obj.data
                corners = operators.face_world(ref.obj, ref.face)
                out.append((corners, mw @ mesh.vertices[ref.vertex].co, label))
        except Exception as err:                    # noqa: BLE001 - never break drawing
            draw_error = f"face {label}: {err}"
    return out


def _draw_3d():
    global draw_error
    context = bpy.context
    if not tools_enabled(context):
        return
    try:
        faces = _picked(context)
        if not faces:
            return
        tris, edges = [], []
        for corners, _corner, _label in faces:
            for tri in tessellate_polygon([corners]):
                tris += [corners[i][:] for i in tri]
            for a, b in zip(corners, corners[1:] + corners[:1]):
                edges += [a[:], b[:]]
        depth, blend = gpu.state.depth_test_get(), gpu.state.blend_get()
        gpu.state.depth_test_set("NONE")            # visible even through the mesh
        gpu.state.blend_set("ALPHA")
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        shader.uniform_float("color", (*HIGHLIGHT, 0.45))
        batch_for_shader(shader, "TRIS", {"pos": tris}).draw(shader)
        line = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        line.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
        line.uniform_float("lineWidth", 3.0)
        line.uniform_float("color", (*HIGHLIGHT, 1.0))
        batch_for_shader(line, "LINES", {"pos": edges}).draw(line)
        gpu.state.depth_test_set(depth)
        gpu.state.blend_set(blend)
    except Exception as err:                        # noqa: BLE001
        draw_error = f"faces: {err}"


def _disc(cx, cy, radius, segments=20):
    pts = [(cx, cy)]
    for k in range(segments + 1):
        ang = 2 * math.pi * k / segments
        pts.append((cx + radius * math.cos(ang), cy + radius * math.sin(ang)))
    return pts


def _draw_2d():
    """The chosen corner of each face as a dot, labelled 1 (stays) / 2 (moves)."""
    global draw_error
    context = bpy.context
    if not tools_enabled(context):
        return
    try:
        region, rv3d = context.region, context.region_data
        spots = []
        for _corners, corner, label in _picked(context):
            xy = view3d_utils.location_3d_to_region_2d(region, rv3d, corner)
            if xy is not None:
                spots.append((xy, label))
        if not spots:
            return
        blend = gpu.state.blend_get()
        gpu.state.blend_set("ALPHA")
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        for xy, _label in spots:
            for radius, rgba in ((9.5, (0, 0, 0, 0.9)), (7.0, (1, 1, 1, 1))):
                shader.uniform_float("color", rgba)
                batch_for_shader(shader, "TRI_FAN", {"pos": _disc(xy.x, xy.y, radius)}).draw(shader)
        gpu.state.blend_set(blend)
        font = 0
        blf.size(font, 16)
        blf.enable(font, blf.SHADOW)
        blf.shadow(font, 3, 0.0, 0.0, 0.0, 1.0)
        for xy, label in spots:
            blf.position(font, xy.x + 11, xy.y + 5, 0)
            blf.color(font, *HIGHLIGHT, 1.0)
            blf.draw(font, label)
        blf.disable(font, blf.SHADOW)
    except Exception as err:                        # noqa: BLE001
        draw_error = f"corners: {err}"


def _redraw_viewports():
    wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", []):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def sync_drawing():
    """Add or remove the draw hooks to match the on/off checkbox."""
    want = not bpy.app.background and tools_enabled(bpy.context)
    if want and not _handles:
        _handles.append(bpy.types.SpaceView3D.draw_handler_add(
            _draw_3d, (), "WINDOW", "POST_VIEW"))
        _handles.append(bpy.types.SpaceView3D.draw_handler_add(
            _draw_2d, (), "WINDOW", "POST_PIXEL"))
    elif not want:
        _remove_handles()
    _redraw_viewports()


def _remove_handles():
    while _handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), "WINDOW")
        except (ValueError, RuntimeError):
            pass                    # Blender already freed it (see _resync_drawing)


def _resync_drawing():
    """Drop and re-add the draw hooks. Blender's Reload Scripts discards every
    Python draw hook *after* add-ons have registered again, so hooks added
    during register silently stop drawing; this runs just after, from a timer.
    """
    try:
        _remove_handles()
        sync_drawing()
    except AttributeError:          # still no usable context
        pass
    return None                     # run once


@persistent
def _on_load(_dummy):
    sync_drawing()


classes = (VIEW3D_PT_assemble_by_face, VIEW3D_PT_assemble_by_face_merge)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.load_post.append(_on_load)
    try:
        sync_drawing()
    except AttributeError:          # restricted context while Blender starts up
        pass
    if not bpy.app.background:
        bpy.app.timers.register(_resync_drawing, first_interval=0.25)


def unregister():
    if bpy.app.timers.is_registered(_resync_drawing):
        bpy.app.timers.unregister(_resync_drawing)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    _remove_handles()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
