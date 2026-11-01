"""Headless tests. Run with:

    blender --background --factory-startup --python tests/run_tests.py
"""

import math
import os
import sys
import traceback

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import assemble_by_face  # noqa: E402
from assemble_by_face import operators  # noqa: E402


# ---------------------------------------------------------------- helpers

def reset():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    for mesh in list(bpy.data.meshes):
        bpy.data.meshes.remove(mesh)
    s = bpy.context.scene.assemble_by_face
    s.face_a.clear()
    s.face_b.clear()
    for prop in ("merge_pct", "gap_pct", "seam_pct", "fit_target", "fit_moving", "fit_axis"):
        s.property_unset(prop)
    s.enabled = True


def box(name, size, matrix=Matrix.Identity(4)):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world = matrix
    return obj


def face_facing(obj, direction):
    """Index of the face whose world normal points most along ``direction``."""
    return max(range(len(obj.data.polygons)),
               key=lambda i: operators.face_normal_world(obj, i).dot(Vector(direction)))


def click(ref, obj, face, corner_hint):
    """Pick ``face`` as if clicked near ``corner_hint`` (world space)."""
    centre = sum(operators.face_world(obj, face), Vector()) / len(obj.data.polygons[face].vertices)
    hit = centre.lerp(Vector(corner_hint), 0.9)
    operators.pick_face(ref, obj, hit, face)


# ---------------------------------------------------------------- tests

def test_registers():
    assert hasattr(bpy.types.Scene, "assemble_by_face")
    for op in ("select_faces", "assemble", "clear_faces"):
        assert hasattr(bpy.ops.assemble_by_face, op), op


def test_tools_are_off_until_enabled():
    reset()
    bpy.context.scene.assemble_by_face.enabled = False
    assert not bpy.ops.assemble_by_face.assemble.poll()
    bpy.context.scene.assemble_by_face.enabled = True


def test_pick_takes_the_corner_nearest_the_click():
    reset()
    a = box("A", (2, 2, 2))
    top = face_facing(a, (0, 0, 1))
    s = bpy.context.scene.assemble_by_face
    click(s.face_a, a, top, (1, -1, 1))
    corner = a.matrix_world @ a.data.vertices[s.face_a.vertex].co
    assert (corner - Vector((1, -1, 1))).length < 1e-6, corner


def test_assemble_needs_two_faces():
    reset()
    a = box("A", (2, 2, 2))
    s = bpy.context.scene.assemble_by_face
    assert not bpy.ops.assemble_by_face.assemble.poll()
    click(s.face_a, a, face_facing(a, (0, 0, 1)), (1, 1, 1))
    assert not bpy.ops.assemble_by_face.assemble.poll()        # only one face so far
    b = box("B", (1, 1, 1), Matrix.Translation((5, 0, 0)))
    click(s.face_b, b, face_facing(b, (1, 0, 0)), (5.5, 0.5, 0.5))
    assert bpy.ops.assemble_by_face.assemble.poll()


def test_assemble_faces_meet_corner_to_corner():
    """B starts far away and rotated; after Assemble its picked face points
    straight at A's, the picked corners coincide, both origins sit on that
    corner, and the picks are cleared."""
    reset()
    a = box("A", (2, 3, 1.5), Matrix.Translation((1, 2, 0.5)))
    b = box("B", (1, 1, 1), Matrix.Translation((6, -4, 3))
            @ Euler((0.4, -0.9, 1.3)).to_matrix().to_4x4())
    s = bpy.context.scene.assemble_by_face
    fa = face_facing(a, (0, 0, 1))
    fb = face_facing(b, (1, 0, 0))
    a_corner_hint = max(operators.face_world(a, fa), key=lambda p: p.x + p.y)
    b_corner_hint = operators.face_world(b, fb)[2]
    click(s.face_a, a, fa, a_corner_hint)
    click(s.face_b, b, fb, b_corner_hint)
    va, vb = s.face_a.vertex, s.face_b.vertex
    a_before = a.matrix_world.copy()
    a_points_before = [a.matrix_world @ v.co for v in a.data.vertices]

    assert bpy.ops.assemble_by_face.assemble() == {"FINISHED"}

    pa = a.matrix_world @ a.data.vertices[va].co
    pb = b.matrix_world @ b.data.vertices[vb].co
    na = operators.face_normal_world(a, fa)
    nb = operators.face_normal_world(b, fb)
    print(f"  corners {pa[:]} / {pb[:]}, normals dot {na.dot(nb):.6f}")
    assert (pa - pb).length < 1e-5                            # corners coincide
    assert na.dot(nb) < -0.99999                              # faces point at each other
    assert (a.matrix_world.translation - pa).length < 1e-5    # origins on the corner
    assert (b.matrix_world.translation - pa).length < 1e-5
    assert all((p - (a.matrix_world @ v.co)).length < 1e-5    # A itself didn't move
               for p, v in zip(a_points_before, a.data.vertices))
    assert a.matrix_world.to_3x3() == a_before.to_3x3()
    assert not s.face_a.is_set() and not s.face_b.is_set()    # highlight cleared


def test_assemble_keeps_orientation_when_already_facing():
    """If the faces already point at each other, B is only moved, not turned."""
    reset()
    a = box("A", (2, 2, 2))
    b = box("B", (1, 1, 1), Matrix.Translation((0.3, 0.2, 5)))
    s = bpy.context.scene.assemble_by_face
    click(s.face_a, a, face_facing(a, (0, 0, 1)), (1, 1, 1))
    click(s.face_b, b, face_facing(b, (0, 0, -1)), (0.8, 0.7, 4.5))
    rot_before = b.matrix_world.to_3x3()
    assert bpy.ops.assemble_by_face.assemble() == {"FINISHED"}
    diff = max(abs(x - y) for r1, r2 in zip(rot_before, b.matrix_world.to_3x3())
               for x, y in zip(r1, r2))
    assert diff < 1e-6, diff


def test_shared_mesh_is_refused():
    reset()
    a = box("A", (2, 2, 2))
    b = box("B", (1, 1, 1), Matrix.Translation((4, 0, 0)))
    twin = bpy.data.objects.new("Twin", b.data)               # B's mesh now has 2 users
    bpy.context.scene.collection.objects.link(twin)
    s = bpy.context.scene.assemble_by_face
    click(s.face_a, a, face_facing(a, (1, 0, 0)), (1, 1, 1))
    click(s.face_b, b, face_facing(b, (-1, 0, 0)), (3.5, 0.5, 0.5))
    try:
        result = bpy.ops.assemble_by_face.assemble()
    except RuntimeError as err:                               # ERROR reports raise here
        assert "shares its mesh" in str(err), err
        result = {"CANCELLED"}
    assert result == {"CANCELLED"}


def volume(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.transform(obj.matrix_world)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return vol


def assembled_pair(gap=0.0):
    """A 4x4x2 base with a 2x2x2 block assembled onto its top, corner to corner
    (so the block sits on the base's corner quarter), then optionally lifted
    ``gap`` along the joined faces' normal."""
    a = box("Base", (4, 4, 2))
    b = box("Block", (2, 2, 2), Matrix.Translation((6, -3, 4)))
    s = bpy.context.scene.assemble_by_face
    click(s.face_a, a, face_facing(a, (0, 0, 1)), (2, 2, 1))
    fb = face_facing(b, (0, 0, -1))
    # its bottom corner furthest along +x+y, so the block lands over the base
    click(s.face_b, b, fb, max(operators.face_world(b, fb), key=lambda p: p.x + p.y))
    assert bpy.ops.assemble_by_face.assemble() == {"FINISHED"}
    if gap:
        b.matrix_world = Matrix.Translation((0, 0, gap)) @ b.matrix_world
    return a, b


def merge_selected(a, b):
    for o in bpy.context.scene.objects:
        o.select_set(o in (a, b))
    bpy.context.view_layer.objects.active = a
    assert bpy.ops.assemble_by_face.merge() == {"FINISHED"}
    result = bpy.context.view_layer.objects.active
    from assemble_by_face import merge
    rep = merge.manifold_report(result.data)
    vol = volume(result)
    print(f"  merged: {merge.describe(rep)}, {rep['shells']} shell(s), "
          f"{len(result.data.polygons)} faces, volume {vol:.3f}")
    return result, rep, vol


def test_merge_needs_two_meshes():
    reset()
    a = box("A", (2, 2, 2))
    a.select_set(True)
    bpy.context.view_layer.objects.active = a
    assert not bpy.ops.assemble_by_face.merge.poll()


def test_merge_after_assemble():
    """Faces in exact contact after Assemble merge into one closed shell."""
    reset()
    a, b = assembled_pair()
    result, rep, vol = merge_selected(a, b)
    assert rep["is_manifold"] and rep["shells"] == 1, rep
    assert abs(vol - 40) < 0.2, vol
    assert a.hide_get() and b.hide_get()                 # originals hidden, kept


def test_merge_closes_a_small_gap_across_the_joined_faces():
    """Lifted 0.03 after assembling (1% of these 4-unit parts is 0.04): Merge
    closes the gap along the remembered direction of the joined faces."""
    reset()
    a, b = assembled_pair(gap=0.03)
    result, rep, vol = merge_selected(a, b)
    assert rep["is_manifold"] and rep["shells"] == 1, rep
    assert 40 < vol < 40 + 4 * 0.03 + 0.2, vol            # the gap got filled in


def test_merge_leaves_a_wide_gap_alone():
    reset()
    a, b = assembled_pair(gap=0.5)
    _result, rep, _vol = merge_selected(a, b)
    assert rep["shells"] == 2, rep


def test_merge_without_assemble_does_not_close_gaps():
    reset()
    a = box("Base", (4, 4, 2))
    b = box("Block", (2, 2, 2), Matrix.Translation((1, 1, 2.03)))
    _result, rep, _vol = merge_selected(a, b)
    assert rep["shells"] == 2, rep


# ---------------------------------------------------------------- runner

def main():
    assemble_by_face.register()
    tests = [(k, v) for k, v in globals().items() if k.startswith("test_")]
    only = os.environ.get("ONLY")
    failed = 0
    for name, fn in tests:
        if only and only not in name:
            continue
        print(name)
        try:
            fn()
            print("  ok")
        except Exception:
            failed += 1
            traceback.print_exc()
            print("  FAILED")
    assemble_by_face.unregister()
    print(f"\n{'FAILED' if failed else 'all passed'} ({failed} failures)")
    sys.exit(1 if failed else 0)


main()
