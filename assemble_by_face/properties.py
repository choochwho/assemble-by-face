import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty


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


classes = (FaceRef, AssembleByFaceSettings)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.assemble_by_face = bpy.props.PointerProperty(type=AssembleByFaceSettings)


def unregister():
    del bpy.types.Scene.assemble_by_face
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
