import re

import bpy
import rigify
from mathutils import Vector

bl_info = {
    "name": "ADH Rigging Tools",
    "author": "Adhi Hargo",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Tools > ADH Rigging Tools",
    "description": "Several simple tools to aid rigging.",
    "warning": "",
    "wiki_url": "https://github.com/adhihargo/rigging_tools",
    "tracker_url": "https://github.com/adhihargo/rigging_tools/issues",
    "category": "Rigging"}

PRF_ROOT = "root-"
PRF_TIP = "tip-"
PRF_HOOK = "hook-"
BBONE_BASE_SIZE = 0.01


class ADH_RenameRegex(bpy.types.Operator):
    """Renames selected objects or bones using regular expressions. Depends on re, standard library module."""
    bl_idname = 'object.adh_rename_regex'
    bl_label = 'Rename Regex'
    bl_options = {'REGISTER', 'UNDO'}

    regex_search_pattern: bpy.props.StringProperty(
        name="Search String",
        default="",
    )
    regex_replacement_string: bpy.props.StringProperty(
        name="Replacement String",
        default="",
    )

    @classmethod
    def poll(cls, context):
        return context.selected_objects != []

    def execute(self, context):
        search_str = self.regex_search_pattern
        replacement_str = self.regex_replacement_string
        substring_re = re.compile(search_str)
        if context.mode == 'OBJECT':
            item_list = context.selected_objects
        elif context.mode == 'POSE':
            item_list = context.selected_pose_bones
        elif context.mode == 'EDIT_ARMATURE':
            item_list = context.selected_bones
        else:
            return {'CANCELLED'}

        for item in item_list:
            item.name = substring_re.sub(replacement_str, item.name)

        # In pose mode, operator's result won't show immediately. This
        # solves it somehow: only the View3D area will refresh
        # promptly.
        if context.mode == 'POSE':
            context.area.tag_redraw()

        return {'FINISHED'}


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


class ADH_BindToLattice(bpy.types.Operator):
    """Bind selected objects to active lattice."""
    bl_idname = 'lattice.adh_bind_to_objects'
    bl_label = 'Bind Lattice to Objects'
    bl_options = {'REGISTER', 'UNDO'}

    create_vertex_group: bpy.props.BoolProperty(
        name="Create Vertex Group",
        description="Create limiting vertex group using the lattice object's name.",
        default=False
    )

    @classmethod
    def poll(self, context):
        obj = context.active_object
        return obj and obj.type == 'LATTICE' and context.selected_objects

    def execute(self, context):
        lattice = context.active_object
        objects = [o for o in context.selected_objects if o.type == 'MESH']

        for obj in objects:
            lm_possibles = [m for m in obj.modifiers if
                            m.type == 'LATTICE' and m.object == lattice]
            if lm_possibles:
                lm = lm_possibles[0]
                lm.name = lattice.name
            else:
                lm = obj.modifiers.new(lattice.name, 'LATTICE')
                lm.object = lattice

            lm.show_expanded = False
            if self.create_vertex_group:
                vg = obj.vertex_groups.get(lattice.name, None)
                if not vg:
                    vg = obj.vertex_groups.new(name=lattice.name)
                lm.vertex_group = vg.name

        return {'FINISHED'}


class ADH_ApplyLattices(bpy.types.Operator):
    """Applies all lattice modifiers, deletes all shapekeys. Used for lattice-initialized shapekey creation."""
    bl_idname = 'mesh.adh_apply_lattices'
    bl_label = 'Apply Lattices'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' \
               and context.selected_objects != [] \
               and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        if obj.data.shape_keys:
            for i in range(len(obj.data.shape_keys.key_blocks), 0, -1):
                obj.active_shape_key_index = i - 1
                bpy.ops.object.shape_key_remove()
        for m in obj.modifiers:
            if m.type == 'LATTICE':
                bpy.ops.object.modifier_apply(modifier=m.name)

        return {'FINISHED'}


class ADH_AbstractMaskOperator:
    MASK_NAME = 'Z_ADH_MASK'

    @classmethod
    def poll(cls, context):
        return context.active_object is not None \
               and context.active_object.type == 'MESH'

    orig_vg = None

    def save_vg(self, context):
        self.orig_vg = context.object.vertex_groups.active

    def restore_vg(self, context):
        if self.orig_vg:
            context.object.vertex_groups.active_index = self.orig_vg.index

    def setup_mask_modifier(self, context):
        mesh = context.active_object
        mm = mesh.modifiers.get(self.MASK_NAME)
        if not mm or mm.type != 'MASK':
            mm = mesh.modifiers.new(self.MASK_NAME, 'MASK')
        mm.show_render = False
        mm.show_expanded = False
        mm.vertex_group = self.MASK_NAME


class ADH_DeleteMask(bpy.types.Operator, ADH_AbstractMaskOperator):
    """Delete mask and its vertex group."""
    bl_idname = 'mesh.adh_delete_mask'
    bl_label = 'Delete Mask'
    bl_options = {'REGISTER'}

    def execute(self, context):
        mesh = context.active_object

        mm = mesh.modifiers.get(self.MASK_NAME)
        if mm and mm.type == 'MASK':
            mesh.modifiers.remove(mm)

        vg = mesh.vertex_groups.get(self.MASK_NAME)
        if vg:
            mesh.vertex_groups.remove(vg)

        return {'FINISHED'}


class ADH_MaskSelectedVertices(bpy.types.Operator, ADH_AbstractMaskOperator):
    """Add selected vertices to mask"""
    bl_idname = 'mesh.adh_mask_selected_vertices'
    bl_label = 'Mask Selected Vertices'
    bl_options = {'REGISTER'}

    action: bpy.props.EnumProperty(
        name='Action',
        items=[('add', 'Add', 'Add selected vertices to mask.'),
               ('remove', 'Remove', 'Remove selected vertices from mask.'),
               ('invert', 'Invert', 'Invert mask')],
        default='add',
        options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        mesh = context.active_object
        self.save_vg(context)

        if event.shift:
            self.action = 'remove'
        elif event.ctrl:
            self.action = 'invert'

        vg = mesh.vertex_groups.get(self.MASK_NAME)
        if not vg:
            vg = mesh.vertex_groups.new(name=self.MASK_NAME)
        mesh.vertex_groups.active_index = vg.index

        if self.action == 'invert':
            bpy.ops.object.vertex_group_invert()

        self.setup_mask_modifier(context)

        mesh.data.update()
        selected_verts = [vert.index for vert in mesh.data.vertices if vert.select is True]

        if self.action == 'add':
            if context.object.mode == 'EDIT':
                bpy.ops.object.vertex_group_assign()
            else:
                vg.add(selected_verts, 1.0, 'REPLACE')
        elif self.action == 'remove':
            if context.object.mode == 'EDIT':
                bpy.ops.object.vertex_group_remove_from()
            else:
                vg.remove(selected_verts)

        self.restore_vg(context)

        return {'FINISHED'}


class ADH_CreateHooks(bpy.types.Operator):
    """Creates parentless bone for each selected bones (local copy-transformed) or lattice points."""
    bl_idname = 'armature.adh_create_hooks'
    bl_label = 'Create Hooks'
    bl_options = {'REGISTER', 'UNDO'}

    hook_layers: bpy.props.BoolVectorProperty(
        name="Hook Layers",
        description="Armature layers where new hooks will be placed",
        subtype='LAYER',
        size=32,
        default=[x == 30 for x in range(0, 32)]
    )

    invoked = False

    def setup_copy_constraint(self, armature, bone_name):
        bone = armature.pose.bones[bone_name]
        ct_constraint = bone.constraints.new('COPY_TRANSFORMS')
        ct_constraint.owner_space = 'LOCAL'
        ct_constraint.target_space = 'LOCAL'
        ct_constraint.target = armature
        ct_constraint.subtarget = PRF_HOOK + bone_name

    def hook_on_lattice(self, context, lattice, armature):
        objects = context.view_layer.objects

        prev_lattice_mode = lattice.mode
        bpy.ops.object.mode_set(mode='OBJECT')  # Needed for matrix calculation

        armature_mat_inv = armature.matrix_world.inverted()
        lattice_mat = lattice.matrix_world

        def global_lat_point_co(p):
            local_point_co = (lattice_mat @ p)
            return armature_mat_inv @ local_point_co

        def get_selected_points(lat):
            return [point for point in lat.data.points if point.select]

        lattice_pos = get_selected_points(lattice)
        bone_pos = [global_lat_point_co(point.co) for point in lattice_pos]
        bone_names = [
            "%(prefix)s%(lat)s.%(index)d%(suffix)s" %
            dict(prefix=PRF_HOOK, lat=lattice.name, index=index,
                 suffix=".R" if global_lat_point_co(point).x < 0 \
                     else ".L" if point.x > 0 else "")
            for index, point in enumerate(bone_pos)]

        objects.active = armature
        prev_mode = armature.mode
        bpy.ops.object.mode_set(mode='EDIT')
        for index, point_co in enumerate(bone_pos):
            bone_name = bone_names[index]
            bone = armature.data.edit_bones.new(bone_name)
            bone.head = point_co
            bone.tail = point_co + Vector([0, 0, BBONE_BASE_SIZE * 5])
            bone.bbone_x = BBONE_BASE_SIZE
            bone.bbone_z = BBONE_BASE_SIZE
            bone.layers = self.hook_layers
            bone.use_deform = False
        armature.data.layers = list(
            map(any, zip(armature.data.layers, self.hook_layers)))
        bpy.ops.object.mode_set(mode=prev_mode)

        objects.active = lattice
        bpy.ops.object.mode_set(mode='EDIT')
        selected_points = get_selected_points(lattice)  # previous one lost after toggling
        for point in selected_points:
            point.select = False
        for index, point in enumerate(selected_points):
            bone_name = bone_names[index]
            mod = lattice.modifiers.new(bone_name, 'HOOK')
            mod.object = armature
            mod.subtarget = bone_name
            point.select = True
            bpy.ops.object.hook_assign(modifier=bone_name)
            bpy.ops.object.hook_reset(modifier=bone_name)
            point.select = False
        for point in selected_points:
            point.select = True
        bpy.ops.object.mode_set(mode=prev_lattice_mode)

        return {'FINISHED'}

    def hook_on_bone(self, context, armature):
        prev_mode = armature.mode
        bpy.ops.object.mode_set(mode='EDIT')
        for bone in context.selected_bones:
            hook_name = PRF_HOOK + bone.name
            hook = armature.data.edit_bones.new(hook_name)
            hook.head = bone.head
            hook.tail = bone.tail
            hook.bbone_x = bone.bbone_x * 2
            hook.bbone_z = bone.bbone_z * 2
            hook.layers = self.hook_layers
            hook.use_deform = False
            hook.roll = bone.roll
            hook.parent = bone.parent
        bpy.ops.object.mode_set(mode='POSE')
        for bone in context.selected_pose_bones:
            self.setup_copy_constraint(armature, bone.name)
        bpy.ops.object.mode_set(mode=prev_mode)

        return {'FINISHED'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and \
               context.active_object.type in ['ARMATURE', 'LATTICE']

    def draw(self, context):
        layout = self.layout

        if self.invoked:
            return

        row = layout.row(align=True)
        row.prop(self, "hook_layers")

    def execute(self, context):
        obj1 = context.active_object
        if obj1.type == 'LATTICE':
            selected = [obj for obj in context.selected_objects if obj != obj1]
            if not selected:
                return {'CANCELLED'}
            obj2 = selected[0]
            return self.hook_on_lattice(context, obj1, obj2)
        else:
            return self.hook_on_bone(context, obj1)

    # def invoke(self, context, event):
    #     retval = context.window_manager.invoke_props_dialog(self)
    #     self.invoked = True
    #     return retval


class ADH_CreateSpokes(bpy.types.Operator):
    """Creates parentless bones in selected armature from the 3D cursor, ending at each selected vertices of active mesh object."""
    bl_idname = 'armature.adh_create_spokes'
    bl_label = 'Create Spokes'
    bl_options = {'REGISTER', 'UNDO'}

    parent: bpy.props.BoolProperty(
        name="Parent",
        description="Create parent bone, one for each if armature selected.",
        default=False
    )

    tip: bpy.props.BoolProperty(
        name="Tracked Tip",
        description="Create tip bone and insert Damped Track constraint with the tip as target.",
        default=False
    )

    spoke_layers: bpy.props.BoolVectorProperty(
        name="Spoke Layers",
        description="Armature layers where spoke bones will be placed",
        subtype='LAYER',
        size=32,
        default=[x == 29 for x in range(0, 32)]
    )

    aux_layers: bpy.props.BoolVectorProperty(
        name="Parent and Tip Layers",
        description="Armature layers where spoke tip and parent bones" + \
                    " will be placed",
        subtype='LAYER',
        size=32,
        default=[x == 30 for x in range(0, 32)]
    )

    basename: bpy.props.StringProperty(
        name="Bone Name",
        default="spoke",
    )

    invoked = False

    def setup_bone_parent(self, armature, bone, parent_bone):
        # Create per-bone parent if no parent set
        if not parent_bone and self.parent:
            parent_bone = armature.data.edit_bones.new(PRF_ROOT + bone.name)
            parent_bone.tail = bone.head + Vector([0, 0, -.05])
            parent_bone.head = bone.head
            parent_bone.bbone_x = bone.bbone_x * 2
            parent_bone.bbone_z = bone.bbone_x * 2
            parent_bone.layers = self.aux_layers
            parent_bone.align_orientation(bone)
            parent_bone.use_deform = False

            delta = parent_bone.head - parent_bone.tail
            parent_bone.head += delta
            parent_bone.tail += delta

        if parent_bone:
            bone_parent = bone.parent
            bone.parent = parent_bone
            bone.use_connect = True

            parent_bone.parent = bone_parent

    def setup_bone_tip(self, armature, bone):
        if not self.tip:
            return
        tip_bone = armature.data.edit_bones.new(PRF_TIP + bone.name)
        tip_bone.head = bone.tail
        tip_bone.tail = bone.tail + Vector([.05, 0, 0])
        tip_bone.bbone_x = bone.bbone_x * 2
        tip_bone.bbone_z = bone.bbone_z * 2
        tip_bone.align_orientation(bone)
        tip_bone.layers = self.aux_layers
        tip_bone.use_deform = False

    def setup_bone_constraint(self, armature, bone_name):
        if not self.tip:
            return
        pbone = armature.pose.bones[bone_name]
        tip_name = PRF_TIP + bone_name
        dt_constraint = pbone.constraints.new('DAMPED_TRACK')
        dt_constraint.target = armature
        dt_constraint.subtarget = tip_name

    def setup_bone(self, armature, bone_name, head_co, tail_co, parent):
        bone = armature.data.edit_bones.new(bone_name)
        bone.head = head_co
        bone.tail = tail_co
        bone.bbone_x = BBONE_BASE_SIZE
        bone.bbone_z = BBONE_BASE_SIZE
        bone.use_deform = True
        bone.select = True
        bone.layers = self.spoke_layers
        self.setup_bone_parent(armature, bone, parent)
        self.setup_bone_tip(armature, bone)

    def set_armature_layers(self, armature):
        combined_layers = list(
            map(any,
                zip(armature.data.layers, self.spoke_layers, self.aux_layers)
                if (self.parent or self.tip) else
                zip(armature.data.layers, self.spoke_layers)))
        armature.data.layers = combined_layers

    def get_vertex_coordinates(self, mesh, armature):
        # Get vertex coordinates localized to armature's matrix
        mesh.update_from_editmode()
        armature_mat_inv = armature.matrix_world.inverted()
        mesh_mat = mesh.matrix_world
        return [armature_mat_inv * (mesh_mat * vert.co)
                for vert in mesh.data.vertices if vert.select]

    def create_spokes(self, context, mesh, armature):
        scene = context.scene

        vert_coordinates = self.get_vertex_coordinates(mesh, armature)
        cursor_co = armature.matrix_world.inverted() * scene.cursor_location

        bpy.ops.object.editmode_toggle()
        scene.objects.active = armature
        prev_mode = armature.mode

        bpy.ops.object.mode_set(mode='EDIT')
        for bone in context.selected_editable_bones:
            bone.select = False

        parent = None
        if self.parent:
            parent = armature.data.edit_bones.new(PRF_ROOT + self.basename)
            parent.head = cursor_co + Vector([0, 0, -1])
            parent.tail = cursor_co
        for index, vert_co in enumerate(vert_coordinates):
            bone_name = "%s.%d" % (self.basename, index)
            self.setup_bone(armature, bone_name, cursor_co, vert_co, parent)

        bpy.ops.object.mode_set(mode='POSE')
        for index in range(len(vert_coordinates)):
            bone_name = "%s.%d" % (self.basename, index)
            self.setup_bone_constraint(armature, bone_name)
        bpy.ops.object.mode_set(mode=prev_mode)

        self.set_armature_layers(armature)

        return {'FINISHED'}

    def create_spoke_tips(self, context, armature):
        prev_mode = armature.mode

        bpy.ops.object.mode_set(mode='EDIT')
        for bone in context.selected_bones:
            self.setup_bone_parent(armature, bone, None)
            self.setup_bone_tip(armature, bone)

        bpy.ops.object.mode_set(mode='POSE')
        for bone in context.selected_pose_bones:
            self.setup_bone_constraint(armature, bone.name)
        bpy.ops.object.mode_set(mode=prev_mode)

        self.set_armature_layers(armature)

        return {'FINISHED'}

    @classmethod
    def poll(cls, context):
        active = context.active_object
        return active is not None and active.mode in ['EDIT', 'POSE'] and \
               active.type in ['MESH', 'ARMATURE'] and \
               len(context.selected_objects) <= 2

    def draw(self, context):
        layout = self.layout

        if self.invoked:
            return

        row = layout.row(align=True)
        row.prop(self, "basename")

        row = layout.row(align=True)
        row.prop(self, "parent", toggle=True)
        row.prop(self, "tip", toggle=True)

        column = layout.column()
        column.prop(self, "spoke_layers")

        column = layout.column()
        column.prop(self, "aux_layers")

    def execute(self, context):
        obj1 = context.active_object
        selected = [obj for obj in context.selected_objects if obj != obj1]
        obj2 = selected[0] if selected else None

        if obj1.type == 'MESH' and obj1.mode == 'EDIT' \
                and obj2 and obj2.type == 'ARMATURE':
            return self.create_spokes(context, obj1, obj2)
        elif obj1.type == 'ARMATURE':
            return self.create_spoke_tips(context, obj1)

        return {'CANCELLED'}

    # def invoke(self, context, event):
    #     retval = context.window_manager.invoke_props_dialog(self)
    #     self.invoked = True
    #     return retval


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

    only_selected: bpy.props.BoolProperty(
        name="Only Selected",
        description="Bind only selected vertices.",
        default=False,
        options={'SKIP_SAVE'})

    set_as_parent: bpy.props.BoolProperty(
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
    bpy.utils.register_class(ADH_RenameRegex)
    bpy.utils.register_class(ADH_UseSameCustomShape)
    bpy.utils.register_class(ADH_SelectCustomShape)
    bpy.utils.register_class(ADH_BindToLattice)
    bpy.utils.register_class(ADH_ApplyLattices)
    bpy.utils.register_class(ADH_MaskSelectedVertices)
    bpy.utils.register_class(ADH_DeleteMask)
    bpy.utils.register_class(ADH_CreateHooks)
    bpy.utils.register_class(ADH_CreateSpokes)
    bpy.utils.register_class(ADH_RemoveVertexGroupsUnselectedBones)
    bpy.utils.register_class(ADH_BindToBone)
    bpy.utils.register_class(ADH_SyncCustomShapePositionToBone)


def unregister():
    bpy.utils.unregister_class(ADH_RenameRegex)
    bpy.utils.unregister_class(ADH_UseSameCustomShape)
    bpy.utils.unregister_class(ADH_SelectCustomShape)
    bpy.utils.unregister_class(ADH_BindToLattice)
    bpy.utils.unregister_class(ADH_ApplyLattices)
    bpy.utils.unregister_class(ADH_MaskSelectedVertices)
    bpy.utils.unregister_class(ADH_DeleteMask)
    bpy.utils.unregister_class(ADH_CreateHooks)
    bpy.utils.unregister_class(ADH_CreateSpokes)
    bpy.utils.unregister_class(ADH_RemoveVertexGroupsUnselectedBones)
    bpy.utils.unregister_class(ADH_BindToBone)
    bpy.utils.unregister_class(ADH_SyncCustomShapePositionToBone)


if __name__ == "__main__":
    register()
