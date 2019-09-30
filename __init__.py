import math
import re

import bpy
import rigify
from mathutils import Vector, Matrix

from rigify.utils.widgets import create_widget

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


class ADH_CreateCustomShape(bpy.types.Operator):
    """Creates mesh for custom shape for selected bones, at active bone's position, using its name as suffix."""
    bl_idname = 'armature.adh_create_shape'
    bl_label = 'Create Custom Shape'
    bl_options = {'REGISTER', 'UNDO'}

    widget_shape: bpy.props.EnumProperty(
        name='Shape',
        items=[('sphere', 'Sphere', '8x4 edges'),
               ('ring', 'Ring', '24 vertices'),
               ('square', 'Square', ''),
               ('triangle', 'Triangle', ''),
               ('bidirection', 'Bidirection', ''),
               ('box', 'Box', ''),
               ('fourways', 'Four-Ways', 'Circle with arrows to four directions - 40 vertices'),
               ('fourgaps', 'Four-Gaps', 'Broken circle that complements Four-Ways - 20 vertices'),
               ('selected', 'Selected', 'Shape of selected object')])

    widget_size: bpy.props.FloatProperty(
        name='Size',
        default=1.0,
        min=0,
        max=2,
        step=10,
        description="Widget's scale as relative to bone.")

    widget_pos: bpy.props.FloatProperty(
        name='Position',
        default=0.5,
        min=-.5,
        max=1.5,
        step=5,
        precision=1,
        description="Widget's position along bone's length. 0.0 = base, 1.0 = tip.")

    widget_rot: bpy.props.FloatProperty(
        name='Rotation',
        default=0,
        min=-90,
        max=90,
        step=10,
        precision=1,
        description="Widget's rotation along bone's X axis.")

    widget_prefix: bpy.props.StringProperty(
        name='Prefix',
        description="Prefix for the new widget's name",
        default='WGT-')

    @classmethod
    def poll(cls, context):
        return context.mode == 'POSE' \
               and context.active_pose_bone is not None

    def draw(self, context):
        layout = self.layout

        col = layout.column()
        col.prop(self, 'widget_shape', expand=False, text='')

        col = layout.column(align=1)
        col.prop(self, 'widget_size', slider=True)
        col.prop(self, 'widget_pos', slider=True)
        col.prop(self, 'widget_rot', slider=True)

        col = layout.column(align=1)
        col.label(text='Prefix:')
        col.prop(self, 'widget_prefix', text='')

    def create_widget_from_object(self, rig, bone, widget_src):
        obj_name = self.widget_prefix + bone.name
        scene = bpy.context.scene

        widget_data = bpy.data.meshes.new_from_object(widget_src)
        matrix_src = widget_src.matrix_world
        matrix_bone = rig.matrix_world * bone.matrix
        matrix_wgt = matrix_bone.inverted() * matrix_src
        widget_data.transform(matrix_wgt)

        if obj_name in scene.objects:
            obj = scene.objects[obj_name]
            obj.data = widget_data
        else:
            obj = bpy.data.objects.new(obj_name, widget_data)
            obj.draw_type = 'WIRE'
            scene.objects.link(obj)

        bone.custom_shape = obj
        rigify.utils.obj_to_bone(obj, rig, bone.name)

        return obj

    # --------------- Long, boring widget creation functions ---------------

    @staticmethod
    def create_sphere_widget(rig, bone_name, size=1.0, pos=1.0, rot=0.0, bone_transform_name=None):
        obj = create_widget(rig, bone_name, bone_transform_name)
        if obj != None:
            verts = [(-0.3535533845424652 * size, -0.3535533845424652 * size, 2.9802322387695312e-08 * size),
                     (-0.5 * size, 2.1855694143368964e-08 * size, -1.7763568394002505e-15 * size),
                     (-0.3535533845424652 * size, 0.3535533845424652 * size, -2.9802322387695312e-08 * size),
                     (4.371138828673793e-08 * size, 0.5 * size, -2.9802322387695312e-08 * size),
                     (-0.24999994039535522 * size, -0.3535533845424652 * size, 0.2500000596046448 * size),
                     (-0.3535533845424652 * size, 5.960464477539063e-08 * size, 0.35355344414711 * size),
                     (-0.24999994039535522 * size, 0.3535534143447876 * size, 0.2500000298023224 * size),
                     (7.968597515173315e-08 * size, -0.3535534143447876 * size, 0.35355344414711 * size),
                     (8.585823962903305e-08 * size, 5.960464477539063e-08 * size, 0.5000001192092896 * size),
                     (7.968597515173315e-08 * size, 0.3535534143447876 * size, 0.3535533845424652 * size),
                     (0.25000008940696716 * size, -0.3535533547401428 * size, 0.25 * size),
                     (0.35355350375175476 * size, 5.960464477539063e-08 * size, 0.3535533845424652 * size),
                     (0.25000008940696716 * size, 0.3535534143447876 * size, 0.2499999701976776 * size),
                     (0.3535534739494324 * size, -0.3535534143447876 * size, -2.9802322387695312e-08 * size),
                     (0.5000001192092896 * size, 2.9802315282267955e-08 * size, -8.429370268459024e-08 * size),
                     (0.3535534739494324 * size, 0.3535533845424652 * size, -8.940696716308594e-08 * size),
                     (0.2500000298023224 * size, -0.35355344414711 * size, -0.2500000596046448 * size),
                     (0.3535533845424652 * size, 0.0 * size, -0.35355350375175476 * size),
                     (0.2500000298023224 * size, 0.35355332493782043 * size, -0.25000011920928955 * size),
                     (-4.494675920341251e-08 * size, -0.35355344414711 * size, -0.3535534143447876 * size),
                     (-8.27291728455748e-08 * size, 0.0 * size, -0.5 * size),
                     (-4.494675920341251e-08 * size, 0.3535533845424652 * size, -0.3535534739494324 * size),
                     (1.2802747306750462e-08 * size, -0.5 * size, 0.0 * size),
                     (-0.25000008940696716 * size, -0.35355344414711 * size, -0.24999994039535522 * size),
                     (-0.35355350375175476 * size, 0.0 * size, -0.35355332493782043 * size),
                     (-0.25000008940696716 * size, 0.35355332493782043 * size, -0.25 * size), ]
            edges = [(0, 1), (1, 2), (2, 3), (4, 5), (5, 6), (2, 6), (0, 4), (5, 1), (7, 8), (8, 9), (6, 9), (5, 8),
                     (7, 4), (10, 11), (11, 12), (9, 12), (10, 7), (11, 8), (13, 14), (14, 15), (12, 15), (13, 10),
                     (14, 11), (16, 17), (17, 18), (15, 18), (16, 13), (17, 14), (19, 20), (20, 21), (18, 21), (16, 19),
                     (20, 17), (22, 23), (23, 24), (24, 25), (21, 25), (20, 24), (23, 19), (22, 0), (22, 4), (6, 3),
                     (22, 7), (9, 3), (22, 10), (12, 3), (22, 13), (15, 3), (22, 16), (18, 3), (22, 19), (21, 3),
                     (25, 3), (25, 2), (0, 23), (1, 24), ]
            faces = []
            rot_mat = Matrix.Rotation(math.radians(rot), 4, 'X')
            trans_mat = Matrix.Translation(Vector((0.0, pos, 0.0)))
            mat = trans_mat @ rot_mat

            mesh = obj.data
            mesh.from_pydata(verts, edges, faces)
            mesh.transform(mat)
            mesh.update()
            mesh.update()
            return obj
        else:
            return None

    @staticmethod
    def create_ring_widget(rig, bone_name, size=1.0, pos=1.0, rot=0.0, bone_transform_name=None):
        obj = create_widget(rig, bone_name, bone_transform_name)
        if obj != None:

            verts = [(0.0 * size, 2.9802322387695312e-08 * size, 0.5 * size),
                     (-0.129409521818161 * size, 2.9802322387695312e-08 * size, 0.4829629063606262 * size),
                     (-0.25 * size, 2.9802322387695312e-08 * size, 0.4330126941204071 * size),
                     (-0.3535533845424652 * size, 2.9802322387695312e-08 * size, 0.3535533845424652 * size),
                     (-0.4330127239227295 * size, 1.4901161193847656e-08 * size, 0.2499999850988388 * size),
                     (-0.4829629063606262 * size, 1.4901161193847656e-08 * size, 0.1294095367193222 * size),
                     (-0.5 * size, 3.552713678800501e-15 * size, 3.774895063202166e-08 * size),
                     (-0.4829629361629486 * size, -1.4901161193847656e-08 * size, -0.12940946221351624 * size),
                     (-0.4330127537250519 * size, -1.4901161193847656e-08 * size, -0.24999992549419403 * size),
                     (-0.3535534739494324 * size, -2.9802322387695312e-08 * size, -0.35355329513549805 * size),
                     (-0.25000011920928955 * size, -2.9802322387695312e-08 * size, -0.43301263451576233 * size),
                     (-0.12940968573093414 * size, -2.9802322387695312e-08 * size, -0.48296287655830383 * size),
                     (-1.9470718370939721e-07 * size, -2.9802322387695312e-08 * size, -0.5 * size),
                     (0.1294093132019043 * size, -2.9802322387695312e-08 * size, -0.482962965965271 * size),
                     (0.2499997913837433 * size, -2.9802322387695312e-08 * size, -0.43301281332969666 * size),
                     (0.3535532057285309 * size, -2.9802322387695312e-08 * size, -0.3535535931587219 * size),
                     (0.43301260471343994 * size, -2.9802322387695312e-08 * size, -0.25000014901161194 * size),
                     (0.48296284675598145 * size, -1.4901161193847656e-08 * size, -0.12940971553325653 * size),
                     (0.5 * size, -1.4210854715202004e-14 * size, -2.324561449995599e-07 * size),
                     (0.482962965965271 * size, 1.4901161193847656e-08 * size, 0.12940926849842072 * size),
                     (0.43301284313201904 * size, 1.4901161193847656e-08 * size, 0.2499997466802597 * size),
                     (0.3535536229610443 * size, 2.9802322387695312e-08 * size, 0.3535531759262085 * size),
                     (0.2500002980232239 * size, 2.9802322387695312e-08 * size, 0.43301254510879517 * size),
                     (0.12940987944602966 * size, 2.9802322387695312e-08 * size, 0.48296281695365906 * size), ]
            edges = [(1, 0), (2, 1), (3, 2), (4, 3), (5, 4), (6, 5), (7, 6), (8, 7), (9, 8), (10, 9), (11, 10),
                     (12, 11), (13, 12), (14, 13), (15, 14), (16, 15), (17, 16), (18, 17), (19, 18), (20, 19), (21, 20),
                     (22, 21), (23, 22), (0, 23), ]
            faces = []
            rot_mat = Matrix.Rotation(math.radians(rot), 4, 'X')
            trans_mat = Matrix.Translation(Vector((0.0, pos, 0.0)))
            mat = trans_mat @ rot_mat

            mesh = obj.data
            mesh.from_pydata(verts, edges, faces)
            mesh.transform(mat)
            mesh.update()
            mesh.update()
            return obj
        else:
            return None

    @staticmethod
    def create_square_widget(rig, bone_name, size=1.0, pos=1.0, rot=0.0, bone_transform_name=None):
        obj = create_widget(rig, bone_name, bone_transform_name)
        if obj != None:
            verts = [(0.5 * size, -0.5 * size, 0.0 * size), (-0.5 * size, -0.5 * size, 0.0 * size),
                     (0.5 * size, 0.5 * size, 0.0 * size), (-0.5 * size, 0.5 * size, 0.0 * size), ]
            edges = [(0, 1), (2, 3), (0, 2), (3, 1), ]
            faces = []
            rot_mat = Matrix.Rotation(math.radians(rot), 4, 'X')
            trans_mat = Matrix.Translation(Vector((0.0, pos, 0.0)))
            mat = trans_mat @ rot_mat

            mesh = obj.data
            mesh.from_pydata(verts, edges, faces)
            mesh.transform(mat)
            mesh.update()
            mesh.update()
            return obj
        else:
            return None

    @staticmethod
    def create_triangle_widget(rig, bone_name, size=1.0, pos=1.0, rot=0.0, bone_transform_name=None):
        obj = create_widget(rig, bone_name, bone_transform_name)
        if obj is not None:
            verts = [(0.0 * size, 0.0 * size, 0.0), (0.6 * size, 1.0 * size, 0.0), (-0.6 * size, 1.0 * size, 0.0), ]
            edges = [(1, 2), (0, 1), (2, 0), ]
            faces = []
            rot_mat = Matrix.Rotation(math.radians(rot), 4, 'X')
            trans_mat = Matrix.Translation(Vector((0.0, pos, 0.0)))
            mat = trans_mat @ rot_mat

            mesh = obj.data
            mesh.from_pydata(verts, edges, faces)
            mesh.transform(mat)
            mesh.update()
            mesh.update()
            return obj
        else:
            return None

    @staticmethod
    def create_bidirection_widget(rig, bone_name, size=1.0, pos=1.0, rot=0.0, bone_transform_name=None):
        obj = create_widget(rig, bone_name, bone_transform_name)
        if obj != None:
            verts = [(0.0 * size, -0.5 * size, 0.0 * size), (0.0 * size, 0.5 * size, 0.0 * size),
                     (0.15000000596046448 * size, -0.3499999940395355 * size, 0.0 * size),
                     (-0.15000000596046448 * size, 0.3499999940395355 * size, 0.0 * size),
                     (0.15000000596046448 * size, 0.3499999940395355 * size, 0.0 * size),
                     (-0.15000000596046448 * size, -0.3499999940395355 * size, 0.0 * size), ]
            edges = [(2, 0), (4, 1), (5, 0), (3, 1), (0, 1), ]
            faces = []
            rot_mat = Matrix.Rotation(math.radians(rot), 4, 'X')
            trans_mat = Matrix.Translation(Vector((0.0, pos, 0.0)))
            mat = trans_mat @ rot_mat

            mesh = obj.data
            mesh.from_pydata(verts, edges, faces)
            mesh.transform(mat)
            mesh.update()
            mesh.update()
            return obj
        else:
            return None

    @staticmethod
    def create_box_widget(rig, bone_name, size=1.0, pos=1.0, rot=0.0, bone_transform_name=None):
        obj = create_widget(rig, bone_name, bone_transform_name)
        if obj != None:
            verts = [(-0.5 * size, -0.5, -0.5 * size), (-0.5 * size, 0.5, -0.5 * size), (0.5 * size, 0.5, -0.5 * size),
                     (0.5 * size, -0.5, -0.5 * size), (-0.5 * size, -0.5, 0.5 * size), (-0.5 * size, 0.5, 0.5 * size),
                     (0.5 * size, 0.5, 0.5 * size), (0.5 * size, -0.5, 0.5 * size), ]
            edges = [(4, 5), (5, 1), (1, 0), (0, 4), (5, 6), (6, 2), (2, 1), (6, 7), (7, 3), (3, 2), (7, 4), (0, 3), ]
            faces = []
            rot_mat = Matrix.Rotation(math.radians(rot), 4, 'X')
            trans_mat = Matrix.Translation(Vector((0.0, pos, 0.0)))
            mat = trans_mat @ rot_mat

            mesh = obj.data
            mesh.from_pydata(verts, edges, faces)
            mesh.transform(mat)
            mesh.update()
            mesh.update()
            return obj
        else:
            return None

    @staticmethod
    def create_fourways_widget(rig, bone_name, size=1.0, pos=1.0, rot=0.0, bone_transform_name=None):
        obj = create_widget(rig, bone_name, bone_transform_name)
        if obj != None:
            verts = [(0.5829628705978394 * size, -1.4901161193847656e-08, 0.12940971553325653 * size),
                     (-0.129409521818161 * size, 2.9802322387695312e-08, -0.4829629063606262 * size),
                     (-0.25 * size, 2.9802322387695312e-08, -0.4330126941204071 * size),
                     (-0.3535533845424652 * size, 2.9802322387695312e-08, -0.3535533845424652 * size),
                     (-0.4330127239227295 * size, 1.4901161193847656e-08, -0.2499999850988388 * size),
                     (-0.4829629063606262 * size, 1.4901161193847656e-08, -0.1294095367193222 * size),
                     (0.5829629898071289 * size, 1.4901161193847656e-08, -0.12940926849842072 * size),
                     (-0.4829629361629486 * size, -1.4901161193847656e-08, 0.12940946221351624 * size),
                     (-0.4330127537250519 * size, -1.4901161193847656e-08, 0.24999992549419403 * size),
                     (-0.3535534739494324 * size, -2.9802322387695312e-08, 0.35355329513549805 * size),
                     (-0.25000011920928955 * size, -2.9802322387695312e-08, 0.43301263451576233 * size),
                     (-0.12940968573093414 * size, -2.9802322387695312e-08, 0.48296287655830383 * size),
                     (-0.12940968573093414 * size, -2.9802322387695312e-08, 0.5829628705978394 * size),
                     (0.1294093132019043 * size, -2.9802322387695312e-08, 0.482962965965271 * size),
                     (0.2499997913837433 * size, -2.9802322387695312e-08, 0.43301281332969666 * size),
                     (0.3535532057285309 * size, -2.9802322387695312e-08, 0.3535535931587219 * size),
                     (0.43301260471343994 * size, -2.9802322387695312e-08, 0.25000014901161194 * size),
                     (0.48296284675598145 * size, -1.4901161193847656e-08, 0.12940971553325653 * size),
                     (0.1294093132019043 * size, -2.9802322387695312e-08, 0.5829629898071289 * size),
                     (0.482962965965271 * size, 1.4901161193847656e-08, -0.12940926849842072 * size),
                     (0.43301284313201904 * size, 1.4901161193847656e-08, -0.2499997466802597 * size),
                     (0.3535536229610443 * size, 2.9802322387695312e-08, -0.3535531759262085 * size),
                     (0.2500002980232239 * size, 2.9802322387695312e-08, -0.43301254510879517 * size),
                     (0.12940987944602966 * size, 2.9802322387695312e-08, -0.48296281695365906 * size),
                     (-0.1941145956516266 * size, -2.9802322387695312e-08, 0.5829629898071289 * size),
                     (-2.102837726170037e-07 * size, -3.218650945768786e-08, 0.7560000419616699 * size),
                     (0.19411394000053406 * size, -2.9802322387695312e-08, 0.5829629898071289 * size),
                     (0.5829628705978394 * size, -1.4901161193847656e-08, 0.1941145360469818 * size),
                     (0.7560000419616699 * size, -1.5347723702281886e-14, 2.5105265422098455e-07 * size),
                     (0.5829629898071289 * size, 1.4901161193847656e-08, -0.19411394000053406 * size),
                     (-0.5829628705978394 * size, 1.4901161193847656e-08, -0.19411435723304749 * size),
                     (-0.7560000419616699 * size, 3.8369309255704715e-15, -4.076887094583981e-08 * size),
                     (-0.5829629302024841 * size, -1.4901161193847656e-08, 0.19411414861679077 * size),
                     (0.0 * size, 3.218650945768786e-08, -0.7560000419616699 * size),
                     (-0.1941143274307251 * size, 2.9802322387695312e-08, -0.5829628109931946 * size),
                     (0.1941147744655609 * size, 2.9802322387695312e-08, -0.5829628109931946 * size),
                     (-0.5829629302024841 * size, -1.4901161193847656e-08, 0.12940946221351624 * size),
                     (-0.5829628705978394 * size, 1.4901161193847656e-08, -0.1294095367193222 * size),
                     (0.12940987944602966 * size, 2.9802322387695312e-08, -0.5829628109931946 * size),
                     (-0.129409521818161 * size, 2.9802322387695312e-08, -0.5829628705978394 * size), ]
            edges = [(2, 1), (3, 2), (4, 3), (5, 4), (8, 7), (9, 8), (10, 9), (11, 10), (39, 34), (14, 13), (15, 14),
                     (16, 15), (17, 16), (38, 23), (37, 5), (20, 19), (21, 20), (22, 21), (23, 22), (36, 32), (25, 24),
                     (26, 25), (0, 17), (18, 13), (12, 24), (28, 27), (29, 28), (6, 29), (6, 19), (0, 27), (31, 30),
                     (32, 31), (12, 11), (36, 7), (37, 30), (34, 33), (33, 35), (38, 35), (18, 26), (39, 1), ]
            faces = []
            rot_mat = Matrix.Rotation(math.radians(rot), 4, 'X')
            trans_mat = Matrix.Translation(Vector((0.0, pos, 0.0)))
            mat = trans_mat @ rot_mat

            mesh = obj.data
            mesh.from_pydata(verts, edges, faces)
            mesh.transform(mat)
            mesh.update()
            mesh.update()
            return obj
        else:
            return None

    @staticmethod
    def create_fourgaps_widget(rig, bone_name, size=1.0, pos=1.0, rot=0.0, bone_transform_name=None):
        obj = create_widget(rig, bone_name, bone_transform_name)
        if obj != None:
            verts = [(-0.1941143274307251 * size, 2.9802322387695312e-08, -0.5829628109931946 * size),
                     (-0.30721572041511536 * size, 3.6622967769517345e-08, -0.532113254070282 * size),
                     (-0.4344686269760132 * size, 3.6622967769517345e-08, -0.4344686269760132 * size),
                     (-0.532113254070282 * size, 1.8311483884758673e-08, -0.30721569061279297 * size),
                     (-0.5829628705978394 * size, 1.4901161193847656e-08, -0.19411435723304749 * size),
                     (-0.5829629302024841 * size, -1.4901161193847656e-08, 0.19411414861679077 * size),
                     (-0.5321133136749268 * size, -1.8311483884758673e-08, 0.3072156310081482 * size),
                     (-0.43446874618530273 * size, -3.6622967769517345e-08, 0.43446850776672363 * size),
                     (-0.3072158396244049 * size, -3.6622967769517345e-08, 0.5321131348609924 * size),
                     (-0.1941145956516266 * size, -2.9802322387695312e-08, 0.5829629898071289 * size),
                     (0.19411394000053406 * size, -2.9802322387695312e-08, 0.5829629898071289 * size),
                     (0.30721548199653625 * size, -3.6622967769517345e-08, 0.5321133732795715 * size),
                     (0.4344683885574341 * size, -3.6622967769517345e-08, 0.4344688653945923 * size),
                     (0.5321131348609924 * size, -3.6622967769517345e-08, 0.3072158992290497 * size),
                     (0.5829628705978394 * size, -1.4901161193847656e-08, 0.1941145360469818 * size),
                     (0.5829629898071289 * size, 1.4901161193847656e-08, -0.19411394000053406 * size),
                     (0.5321133732795715 * size, 1.8311483884758673e-08, -0.3072154223918915 * size),
                     (0.43446895480155945 * size, 3.6622967769517345e-08, -0.4344683885574341 * size),
                     (0.307216078042984 * size, 3.6622967769517345e-08, -0.5321130156517029 * size),
                     (0.1941147744655609 * size, 2.9802322387695312e-08, -0.5829628109931946 * size), ]
            edges = [(1, 0), (2, 1), (3, 2), (4, 3), (6, 5), (7, 6), (8, 7), (9, 8), (11, 10), (12, 11), (13, 12),
                     (14, 13), (16, 15), (17, 16), (18, 17), (19, 18), ]
            faces = []
            rot_mat = Matrix.Rotation(math.radians(rot), 4, 'X')
            trans_mat = Matrix.Translation(Vector((0.0, pos, 0.0)))
            mat = trans_mat @ rot_mat

            mesh = obj.data
            mesh.from_pydata(verts, edges, faces)
            mesh.transform(mat)
            mesh.update()
            mesh.update()
            return obj
        else:
            return None

    # ------------ End of long, boring widget creation functions -----------

    def execute(self, context):
        rig = context.active_object
        bone = context.active_pose_bone

        widget_sources = [obj for obj in context.selected_objects
                          if obj.type == 'MESH']

        func = getattr(self, "create_%s_widget" % self.widget_shape, None)
        if func is None and len(widget_sources) == 1:
            widget = self.create_widget_from_object(rig, bone, widget_sources[0])
        else:
            widget = func(rig, bone.name, self.widget_size, self.widget_pos, self.widget_rot)

        for bone in context.selected_pose_bones:
            bone.custom_shape = widget

        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)


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


class ADH_MapShapeKeysToBones(bpy.types.Operator):
    """Create driver for shape keys, driven by selected bone of the same name."""
    bl_idname = 'object.adh_map_shape_keys_to_bones'
    bl_label = 'Map Shape Keys to Bones'
    bl_options = {'REGISTER', 'UNDO'}

    slider_axis: bpy.props.EnumProperty(
        name="Slider Axis",
        items=[("LOC_X", "X", "X axis"), ("LOC_Y", "Y", "Y axis"),
               ("LOC_Z", "Z", "X axis")],
        default="LOC_X",
    )

    slider_distance: bpy.props.FloatProperty(
        name="Slider Distance",
        min=-2.0, max=2.0, default=0.2, step=0.05,
        subtype="DISTANCE", unit="LENGTH",
    )

    @classmethod
    def poll(self, context):
        return context.active_object != None \
               and context.active_object.type in ['MESH', 'LATTICE'] \
               and len(context.selected_objects) == 2

    def execute(self, context):
        obj1, obj2 = context.selected_objects
        mesh = obj1.data
        armature = obj2
        if obj2.type in ["MESH", "LATTICE"]:
            mesh = obj2.data
            armature = obj1

        if armature.type != "ARMATURE":
            return {"CANCELLED"}

        mesh_keys = mesh.shape_keys
        if not mesh_keys.animation_data:
            mesh_keys.animation_data_create()

        slider_formula = "a * %0.1f" % (1.0 / self.slider_distance) \
            if self.slider_distance != 0.0 else "a"
        for shape in mesh_keys.key_blocks:
            # Create driver only if the shape key isn't Basis, the
            # corresponding bone exists and is selected.
            bone = armature.data.bones.get(shape.name, None)
            if shape == mesh_keys.reference_key or not (bone and bone.select):
                continue

            data_path = 'key_blocks["%s"].value' % shape.name
            fc = mesh_keys.driver_add(data_path)

            dv = fc.driver.variables[0] if len(fc.driver.variables) > 0 \
                else fc.driver.variables.new()
            dv.name = "a"
            dv.type = "TRANSFORMS"

            target = dv.targets[0]
            target.id = armature
            target.bone_target = shape.name
            target.data_path = dv.targets[0].data_path
            target.transform_space = "LOCAL_SPACE"
            target.transform_type = self.slider_axis

            fc.driver.type = "SCRIPTED"
            fc.driver.expression = slider_formula

        return {"FINISHED"}


module_classes = (
    ADH_RenameRegex,
    ADH_UseSameCustomShape,
    ADH_SelectCustomShape,
    ADH_CreateCustomShape,
    ADH_BindToLattice,
    ADH_ApplyLattices,
    ADH_MaskSelectedVertices,
    ADH_DeleteMask,
    ADH_CreateHooks,
    ADH_CreateSpokes,
    ADH_RemoveVertexGroupsUnselectedBones,
    ADH_BindToBone,
    ADH_SyncCustomShapePositionToBone,
    ADH_MapShapeKeysToBones,
)


def register():
    from bpy.utils import register_class
    for cls in module_classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class
    for cls in module_classes:
        unregister_class(cls)


if __name__ == "__main__":
    register()
