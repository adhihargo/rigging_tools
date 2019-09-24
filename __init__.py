import bpy
import rigify

bl_info = {
    "name": "ADH Rigging Tools",
    "author": "Adhi Hargo",
    "version": (1, 0, 0),
    "blender": (2, 8, 0),
    "location": "View3D > Tools > ADH Rigging Tools",
    "description": "Several simple tools to aid rigging.",
    "warning": "",
    "wiki_url": "https://github.com/adhihargo/rigging_tools",
    "tracker_url": "https://github.com/adhihargo/rigging_tools/issues",
    "category": "Rigging"}

class ADH_UseSameCustomShape(bpy.types.Operator):
    """Copies active pose bone's custom shape to each selected pose bone."""
    bl_idname = 'armature.adh_use_same_shape'
    bl_label = 'Use Same Custom Shape'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_pose_bone is not None

    def execute(self, context):
        if context.active_pose_bone is None:
            return {'CANCELLED'}

        custom_shape = context.active_pose_bone.custom_shape
        for obj in context.selected_objects:
            if obj.type == 'MESH':
                custom_shape = obj
                break

        for bone in context.selected_pose_bones:
            bone.custom_shape = custom_shape

        return {'FINISHED'}


class ADH_SelectCustomShape(bpy.types.Operator):
    """Selects custom shape object of active bone."""
    bl_idname = 'armature.adh_select_shape'
    bl_label = 'Select Custom Shape'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_pose_bone is not None and \
               context.active_pose_bone.custom_shape is not None

    def execute(self, context):
        bone = context.active_pose_bone
        bone_shape = bone.custom_shape
        # shape_layers = [l for l in bone_shape.layers]  # can't index on bpy_prop_array
        if bone_shape:
            bpy.ops.object.mode_set(mode="OBJECT", toggle=False)
            context.active_object.select_set(False)

            # tampilkan semua koleksi yang mengandung objek custom
            # shape. harusnya cuma yang di viewport tapi sudahlah biar cepat.
            for coll in bone_shape.users_collection:
                coll.hide_viewport = False
            par = bone_shape.parent
            while par is not None:
                par.hide_viewport = False
                par.hide_set(False)
                par = par.parent

            bone_shape.hide_set(False)
            bone_shape.select_set(True)
            context.view_layer.objects.active = bone_shape
        else:
            return {'CANCELLED'}

        return {'FINISHED'}


class ADH_RemoveVertexGroupsUnselectedBones(bpy.types.Operator):
    """Removes all vertex groups other than selected bones.

    Used right after automatic weight assignment, to remove unwanted bone influence."""
    bl_idname = 'armature.adh_remove_vertex_groups_unselected_bones'
    bl_label = 'Remove Vertex Groups of Unselected Bones'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(self, context):
        return context.active_object is not None \
               and context.selected_pose_bones is not None

    def execute(self, context):
        bone_names = [b.name for b in context.selected_pose_bones]
        affected_objects = [o for o in context.selected_objects
                            if o.type == 'MESH']

        for obj in affected_objects:
            for vg in obj.vertex_groups:
                if not (vg.name in bone_names or vg.lock_weight):
                    obj.vertex_groups.remove(vg)

        return {'FINISHED'}


class ADH_BindToBone(bpy.types.Operator):
    """Binds all selected objects to selected bone, adding armature and vertex group if none exist yet."""
    bl_idname = 'armature.adh_bind_to_bone'
    bl_label = 'Bind Object to Bone'
    bl_options = {'REGISTER', 'UNDO'}

    only_selected = bpy.props.BoolProperty(
        name="Only Selected",
        description="Bind only selected vertices.",
        default=False,
        options={'SKIP_SAVE'})

    set_as_parent = bpy.props.BoolProperty(
        name="Set as Parent",
        description="Also parent object to armature.",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2 and \
               context.active_pose_bone is not None

    def execute(self, context):
        meshes = [obj for obj in context.selected_objects if obj.type == 'MESH']
        armature = context.active_object
        bone = context.active_pose_bone
        for mesh in meshes:
            armature_mods = [m for m in mesh.modifiers
                             if m.type == 'ARMATURE' and m.object == armature]
            if not armature_mods:
                am = mesh.modifiers.new('Armature', 'ARMATURE')
                am.object = armature

            if self.set_as_parent:
                mesh.parent = armature

            vertex_indices = [v.index for v in mesh.data.vertices if v.select] \
                if self.only_selected else range(len(mesh.data.vertices))
            vg = mesh.vertex_groups.get(bone.name, None)
            for other_vg in mesh.vertex_groups:
                if other_vg == vg:
                    continue
                other_vg.remove(vertex_indices)
            if not vg:
                vg = mesh.vertex_groups.new(name=bone.name)
            vg.add(vertex_indices, 1.0, 'REPLACE')

        return {'FINISHED'}

    def invoke(self, context, event):
        self.only_selected = event.shift
        return self.execute(context)


class ADH_SyncCustomShapePositionToBone(bpy.types.Operator):
    """Sync a mesh object's position to each selected bone using it as a custom shape. Depends on Rigify."""
    bl_idname = 'object.adh_sync_shape_position_to_bone'
    bl_label = 'Sync Custom Shape Position to Bone'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None \
               and context.active_object.type == 'ARMATURE' \
               and context.mode == 'POSE'

    def execute(self, context):
        for bone in context.selected_pose_bones:
            obj = bone.custom_shape
            if obj:
                rigify.utils.obj_to_bone(obj, context.active_object,
                                         bone.name)

        return {'FINISHED'}


def register():
    bpy.utils.register_class(ADH_UseSameCustomShape)
    bpy.utils.register_class(ADH_SelectCustomShape)
    bpy.utils.register_class(ADH_RemoveVertexGroupsUnselectedBones)
    bpy.utils.register_class(ADH_BindToBone)
    bpy.utils.register_class(ADH_SyncCustomShapePositionToBone)


def unregister():
    bpy.utils.unregister_class(ADH_UseSameCustomShape)
    bpy.utils.unregister_class(ADH_SelectCustomShape)
    bpy.utils.unregister_class(ADH_RemoveVertexGroupsUnselectedBones)
    bpy.utils.unregister_class(ADH_BindToBone)
    bpy.utils.unregister_class(ADH_SyncCustomShapePositionToBone)


if __name__ == "__main__":
    register()
