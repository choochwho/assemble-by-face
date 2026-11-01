"""Pick a face on each of two objects, then assemble them face to face."""

import time

import bmesh
import bpy
from bpy_extras import view3d_utils
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import merge


def tools_enabled(context):
    scene = getattr(context, "scene", None)
    return scene is not None and scene.assemble_by_face.enabled


def _enabled_poll(cls, context):
    if not tools_enabled(context):
        cls.poll_message_set("Turn on Assemble by Face in its sidebar tab")
        return False
    return True


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------

def base_face_at(obj, world_hit, face_index):
    """Index of the base-mesh polygon under ``world_hit``.

    Ray casts see the evaluated mesh, so with modifiers the hit index may not
    match the mesh's own polygons; then the nearest base-mesh face is used.
    """
    mesh = obj.data
    if not obj.modifiers and 0 <= face_index < len(mesh.polygons):
        return face_index
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    _loc, _n, index, _d = bvh.find_nearest(obj.matrix_world.inverted() @ world_hit)
    if index is None:
        raise ValueError(f"Couldn't find a face of '{obj.name}' there")
    return index


def nearest_corner(obj, face_index, world_point):
    """The vertex of the face closest to ``world_point``."""
    mesh = obj.data
    mw = obj.matrix_world
    return min(mesh.polygons[face_index].vertices,
               key=lambda i: (mw @ mesh.vertices[i].co - world_point).length)


def face_world(obj, face_index):
    """World-space corner positions of a face."""
    mesh, mw = obj.data, obj.matrix_world
    return [mw @ mesh.vertices[i].co for i in mesh.polygons[face_index].vertices]


def face_normal_world(obj, face_index):
    """Outward normal of a face in world space (computed from its world-space
    corners, so non-uniform scale and mirroring are handled)."""
    pts = face_world(obj, face_index)
    n = Vector()
    for a, b in zip(pts, pts[1:] + pts[:1]):           # Newell's method
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    if n.length < 1e-12:
        raise ValueError(f"Face {face_index} of '{obj.name}' has no area")
    return n.normalized()


def set_origin(obj, world_point):
    """Move ``obj``'s origin to ``world_point`` without moving its geometry
    (or its children)."""
    local = obj.matrix_world.inverted() @ world_point
    children = [(c, c.matrix_world.copy()) for c in obj.children]
    obj.data.transform(Matrix.Translation(-local))
    obj.matrix_world = obj.matrix_world @ Matrix.Translation(local)
    for child, mw in children:
        child.matrix_world = mw


def pick_face(face_ref, obj, world_hit, face_index):
    """Store the face under ``world_hit`` and its corner nearest the click."""
    face = base_face_at(obj, world_hit, face_index)
    face_ref.obj = obj
    face_ref.face = face
    face_ref.vertex = nearest_corner(obj, face, world_hit)


def assemble(scene):
    """Move face B's object so the faces point at each other and the chosen
    vertices coincide, put both origins on that vertex, clear the picks.
    Returns (fixed object, moved object, joined world point)."""
    s = scene.assemble_by_face
    a, b = s.face_a, s.face_b
    if not (a.is_set() and b.is_set()):
        raise ValueError("Pick a face on each object first (Select Faces)")
    fixed, moving = a.obj, b.obj
    if fixed == moving:
        raise ValueError("Both faces are on the same object")
    for obj in (fixed, moving):
        if obj.data.users > 1:
            raise ValueError(f"'{obj.name}' shares its mesh with other objects; setting "
                             "its origin would move them too (make it single-user first)")

    n_fixed = face_normal_world(fixed, a.face)
    n_moving = face_normal_world(moving, b.face)
    p_fixed = fixed.matrix_world @ fixed.data.vertices[a.vertex].co
    p_moving = moving.matrix_world @ moving.data.vertices[b.vertex].co

    # Smallest turn that points the moving face straight at the fixed one, so
    # the moving object keeps as much of its current orientation as possible.
    turn = n_moving.rotation_difference(-n_fixed).to_matrix().to_4x4()
    moving.matrix_world = (Matrix.Translation(p_fixed) @ turn @ Matrix.Translation(-p_moving)
                           @ moving.matrix_world)

    set_origin(fixed, p_fixed)
    set_origin(moving, p_fixed)
    # Remember which way the parts joined, so Merge can close gaps across the
    # joined faces: the fixed face's outward normal points at the moved part.
    s.fit_target, s.fit_moving = fixed, moving
    s.fit_axis = fixed.matrix_world.to_3x3().inverted() @ n_fixed
    a.clear()
    b.clear()
    return fixed, moving, p_fixed


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class ABF_OT_select_faces(bpy.types.Operator):
    """Click a face on one object, then a face on another. The corner of each face
    nearest the click is the one that will be joined"""
    bl_idname = "assemble_by_face.select_faces"
    bl_label = "Select Faces"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return (_enabled_poll(cls, context)
                and context.area is not None and context.area.type == "VIEW_3D")

    def invoke(self, context, event):
        if context.mode != "OBJECT":
            self.report({"WARNING"}, "Switch to Object Mode first")
            return {"CANCELLED"}
        s = context.scene.assemble_by_face
        s.face_a.clear()                # start a fresh pick
        s.face_b.clear()
        context.window_manager.modal_handler_add(self)
        context.window.cursor_modal_set("CROSSHAIR")
        self._status(context)
        _redraw_viewports(context)
        return {"RUNNING_MODAL"}

    def _status(self, context):
        s = context.scene.assemble_by_face
        step = ("click a face on the object that stays put" if not s.face_a.is_set()
                else "click a face on the object to move")
        context.workspace.status_text_set(
            f"Select Faces: {step}, near the corner to join  •  Esc / right-click to cancel")

    def _end(self, context, result):
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        _redraw_viewports(context)
        return result

    def modal(self, context, event):
        # Never keep swallowing clicks: anything but a hit on a mesh ends the tool.
        if not tools_enabled(context) or context.area is None:
            return self._end(context, {"CANCELLED"})
        if event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS":
            return self._end(context, {"CANCELLED"})
        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"PASS_THROUGH"}         # keep viewport navigation working

        region = next((r for r in context.area.regions if r.type == "WINDOW"
                       and r.x <= event.mouse_x < r.x + r.width
                       and r.y <= event.mouse_y < r.y + r.height), None)
        if region is None:                  # clicked outside the viewport itself
            return self._end(context, {"CANCELLED", "PASS_THROUGH"})
        rv3d = context.area.spaces.active.region_3d
        coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        hit, location, _n, index, obj, _m = context.scene.ray_cast(
            context.evaluated_depsgraph_get(), origin, direction)
        if not hit or obj.type != "MESH":
            self.report({"WARNING"}, "No mesh under the cursor; cancelled")
            return self._end(context, {"CANCELLED"})

        obj = obj.original
        s = context.scene.assemble_by_face
        try:
            if not s.face_a.is_set():
                pick_face(s.face_a, obj, location, index)
                self._status(context)
                _redraw_viewports(context)
                return {"RUNNING_MODAL"}
            if obj == s.face_a.obj:
                self.report({"WARNING"}, "Pick the face on the other object")
                return {"RUNNING_MODAL"}
            pick_face(s.face_b, obj, location, index)
        except ValueError as err:
            self.report({"ERROR"}, str(err))
            return self._end(context, {"CANCELLED"})
        self.report({"INFO"}, f"Faces picked on '{s.face_a.obj.name}' and '{obj.name}'. "
                              "Assemble when ready")
        return self._end(context, {"FINISHED"})


class ABF_OT_assemble(bpy.types.Operator):
    """Turn the second object so the two faces point at each other, move it so the
    chosen corners meet, and set both origins to that corner"""
    bl_idname = "assemble_by_face.assemble"
    bl_label = "Assemble"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _enabled_poll(cls, context):
            return False
        s = context.scene.assemble_by_face
        if not (s.face_a.is_set() and s.face_b.is_set()):
            cls.poll_message_set("Pick a face on each of two objects first (Select Faces)")
            return False
        return True

    def execute(self, context):
        if context.mode != "OBJECT":
            self.report({"WARNING"}, "Switch to Object Mode first")
            return {"CANCELLED"}
        try:
            fixed, moving, point = assemble(context.scene)
        except ValueError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        _redraw_viewports(context)
        self.report({"INFO"}, f"Moved '{moving.name}' onto '{fixed.name}'; both origins are "
                              "now at the joined corner")
        return {"FINISHED"}


class ABF_OT_clear_faces(bpy.types.Operator):
    """Forget the picked faces"""
    bl_idname = "assemble_by_face.clear_faces"
    bl_label = "Clear Faces"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        s = context.scene.assemble_by_face
        return _enabled_poll(cls, context) and (s.face_a.obj is not None
                                                or s.face_b.obj is not None)

    def execute(self, context):
        s = context.scene.assemble_by_face
        s.face_a.clear()
        s.face_b.clear()
        _redraw_viewports(context)
        return {"FINISHED"}


# --------------------------------------------------------------------------
# Merge (the same as in Assemble by Points)
# --------------------------------------------------------------------------

def selected_meshes(context):
    return [o for o in context.selected_objects if o.type == "MESH"]


def assembled_size(objects):
    """Largest dimension of the objects' combined world bounding box: the
    reference that the merge percentages are taken of."""
    corners = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    if not corners:
        return 0.0
    return max(max(c[i] for c in corners) - min(c[i] for c in corners) for i in range(3))


def merge_settings(context, objects):
    """(merge distance, max gap, seam width) in scene units for these objects."""
    s = context.scene.assemble_by_face
    size = assembled_size(objects)
    return tuple(size * pct / 100 for pct in (s.merge_pct, s.gap_pct, s.seam_pct))


class _ObjectModeScope:
    """Leave edit mode for the duration, then restore it."""

    def __init__(self, context):
        self.was_edit = context.mode == "EDIT_MESH"

    def __enter__(self):
        if self.was_edit:
            bpy.ops.object.mode_set(mode="OBJECT")
        return self

    def __exit__(self, *exc):
        if self.was_edit:
            bpy.ops.object.mode_set(mode="EDIT")
        return False


class ABF_OT_merge(bpy.types.Operator):
    """Merge the selected objects into one new, closed mesh: close small gaps across
    the joined faces, union them, and remove internal voids"""
    bl_idname = "assemble_by_face.merge"
    bl_label = "Merge Into New Object"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        if not _enabled_poll(cls, context):
            return False
        if len(selected_meshes(context)) < 2:
            cls.poll_message_set("Select at least two mesh objects")
            return False
        return True

    def execute(self, context):
        s = context.scene.assemble_by_face
        t0 = time.perf_counter()
        with _ObjectModeScope(context):
            objects = selected_meshes(context)
            active = context.active_object
            if active in objects:                    # active first: it names the result
                objects.remove(active)
                objects.insert(0, active)

            gap_pair, axis = self._gap_axis(context, objects)
            spacing, max_gap, seam_width = merge_settings(context, objects)
            try:
                result, report = merge.merge(objects, context, spacing, max_gap,
                                             seam_width=seam_width, gap_pair=gap_pair,
                                             axis=axis)
            except ValueError as err:
                self.report({"ERROR"}, str(err))
                return {"CANCELLED"}

            for o in objects:
                o.select_set(False)
                o.hide_set(True)
            result.select_set(True)
            context.view_layer.objects.active = result

        notes = []
        if report["holes_filled"]:
            notes.append(f"filled {report['holes_filled']} hole(s) in the input meshes")
        if report["gap_vertices_moved"]:
            notes.append(f"closed gaps at {report['gap_vertices_moved']} vertices")
        elif gap_pair is None and s.gap_pct > 0:
            notes.append("gaps not closed (use Assemble on these parts first)")
        if report["edges_split"] or report["seam_split"]:
            notes.append(f"split {report['edges_split'] + report['seam_split']} coarse edges")
        if report["seam_collapsed"]:
            notes.append(f"merged {report['seam_collapsed']} crowded vertices at the seam")
        if report["seam_smoothed"]:
            notes.append(f"smoothed the seam ({report['seam_smoothed']} vertices)")
        if report["voids_removed"]:
            notes.append(f"removed {report['voids_removed']} internal void(s)")
        if report["faces_repaired"]:
            notes.append(f"repaired {report['faces_repaired']} faces")
        ok = report["is_manifold"] and report["shells"] == 1
        state = "one closed, printable shell" if ok else merge.describe(report)
        if report["shells"] > 1:
            state += f"; {report['shells']} separate pieces (the parts don't touch everywhere)"
        msg = (f"Created '{result.name}' in {time.perf_counter() - t0:.1f}s "
               f"({len(result.data.polygons)} faces): {state}")
        if notes:
            msg += ". " + "; ".join(notes).capitalize()
        self.report({"INFO"} if ok else {"WARNING"}, msg)
        return {"FINISHED"}

    @staticmethod
    def _gap_axis(context, objects):
        """((fixed, moved), world axis) to close gaps along, or (None, None):
        the joined faces' direction from the last Assemble on these parts."""
        s = context.scene.assemble_by_face
        t, m = s.fit_target, s.fit_moving
        if t in objects and m in objects and Vector(s.fit_axis).length > 0:
            return (t, m), (t.matrix_world.to_3x3() @ Vector(s.fit_axis)).normalized()
        return None, None


class ABF_OT_check_manifold(bpy.types.Operator):
    """Report whether each selected mesh is a closed manifold"""
    bl_idname = "assemble_by_face.check_manifold"
    bl_label = "Check Manifold"

    @classmethod
    def poll(cls, context):
        return _enabled_poll(cls, context) and bool(selected_meshes(context))

    def execute(self, context):
        with _ObjectModeScope(context):
            lines = [f"{o.name}: {merge.describe(merge.manifold_report(o.data))}"
                     for o in selected_meshes(context)]
        all_ok = all(line.endswith(": manifold") for line in lines)
        self.report({"INFO"} if all_ok else {"WARNING"}, " | ".join(lines))
        return {"FINISHED"}



def _redraw_viewports(context):
    for area in context.screen.areas if context.screen else ():
        if area.type == "VIEW_3D":
            area.tag_redraw()


# --------------------------------------------------------------------------
# Shortcuts: Shift+Alt+F / Shift+Alt+A, in the Object Mode keymap (the only
# mode the tools work in). Neither is used by Blender in Object Mode; Shift+Alt+A
# is only taken in Sculpt and Weight Paint, which have their own keymaps.
# Editable under Preferences > Keymap > 3D View > Object Mode.
# --------------------------------------------------------------------------

KEYMAP = (
    (ABF_OT_select_faces.bl_idname, "F"),
    (ABF_OT_assemble.bl_idname, "A"),
)
_keymaps = []


def register_keymaps():
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:                      # background mode has no key configs
        return
    km = kc.keymaps.new(name="Object Mode", space_type="EMPTY")
    for idname, key in KEYMAP:
        kmi = km.keymap_items.new(idname, key, "PRESS", shift=True, alt=True)
        _keymaps.append((km, kmi))


def unregister_keymaps():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()


classes = (ABF_OT_select_faces, ABF_OT_assemble, ABF_OT_clear_faces, ABF_OT_merge,
           ABF_OT_check_manifold)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_keymaps()


def unregister():
    unregister_keymaps()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
