import bpy
from bpy.props import (BoolProperty, FloatProperty, FloatVectorProperty, IntProperty,
                       PointerProperty)


def _redraw(self, context):
    from . import ui
    ui.sync_drawing()


class FaceRef(bpy.types.PropertyGroup):
    """A picked face: the object, the polygon's index in its mesh, and the
    index of the face's vertex that will be joined."""
    obj: PointerProperty(type=bpy.types.Object)
    face: IntProperty(default=-1)
    vertex: IntProperty(default=-1)

    def is_set(self):
        """True if this still points at a face and vertex of the object's mesh."""
        if self.obj is None or self.obj.type != "MESH":
            return False
        mesh = self.obj.data
        return (0 <= self.face < len(mesh.polygons)
                and self.vertex in mesh.polygons[self.face].vertices)

    def clear(self):
        self.obj = None
        self.face = self.vertex = -1


class AssembleByFaceSettings(bpy.types.PropertyGroup):
    enabled: BoolProperty(
        name="Assemble by Face",
        description="Turn the tools on. While off, the add-on draws nothing and its "
                    "tools are disabled",
        default=False, update=_redraw,
    )
    face_a: PointerProperty(type=FaceRef, description="First face picked: this object stays put")
    face_b: PointerProperty(type=FaceRef, description="Second face picked: this object moves")

    # Merge settings are percentages of the assembled parts' size (the largest
    # dimension of their combined bounding box), so they suit any scale.
    merge_pct: FloatProperty(
        name="Merge Distance",
        description="Percent of the assembled size. In the seam area, vertices end up "
                    "about this far apart and never closer; no part is subdivided finer "
                    "than this. Vertices away from the seam are never merged",
        default=1.0, min=0.0, soft_max=5.0, max=100.0, subtype="PERCENTAGE", precision=2,
    )
    gap_pct: FloatProperty(
        name="Fill Gaps Up To",
        description="Percent of the assembled size. Gaps between the assembled parts up "
                    "to this wide are closed when merging, measured across the joined "
                    "faces (slightly wider gaps are partly closed). 0 = don't close gaps",
        default=1.0, min=0.0, soft_max=5.0, max=100.0, subtype="PERCENTAGE", precision=2,
    )
    seam_pct: FloatProperty(
        name="Smooth Seam",
        description="Percent of the assembled size. The two parts' walls are blended "
                    "together across a band this wide on each side of the seam. Nothing "
                    "outside the band is changed. 0 = don't smooth",
        default=1.0, min=0.0, soft_max=5.0, max=100.0, subtype="PERCENTAGE", precision=2,
    )

    # Remembered from the last Assemble, so Merge can close gaps across the
    # joined faces: the fixed face's outward normal, in the fixed object's space.
    fit_target: PointerProperty(type=bpy.types.Object)
    fit_moving: PointerProperty(type=bpy.types.Object)
    fit_axis: FloatVectorProperty(size=3, description="In the target's local space")


classes = (FaceRef, AssembleByFaceSettings)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.assemble_by_face = bpy.props.PointerProperty(type=AssembleByFaceSettings)


def unregister():
    del bpy.types.Scene.assemble_by_face
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
