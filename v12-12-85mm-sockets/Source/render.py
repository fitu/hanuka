from pathlib import Path
import bpy
from mathutils import Vector

folder = Path(__file__).resolve().parent
if folder.name == "Source":
    folder = folder.parent
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for name, color in [
    ("Red-Right-AMS", (.88,.016,.038,1)),
    ("White-Left-External", (.95,.95,.95,1)),
]:
    bpy.ops.wm.stl_import(filepath=str(folder/"print"/f"{name}.stl"))
    obj = bpy.context.object
    obj.name = name
    obj.color = color
    # Smooth across tessellation edges and keep the intended ridge and
    # chamfer transitions. STL export geometry is unaffected by shading.
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj.data.set_sharp_from_angle(angle=.28)
bpy.ops.object.camera_add(location=(0,-340,137))
camera = bpy.context.object
camera.rotation_euler = (Vector((0,0,52))-camera.location).to_track_quat("-Z","Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 244
camera.data.clip_end = 3000
scene = bpy.context.scene
scene.camera = camera
scene.render.engine = "BLENDER_WORKBENCH"
shading = scene.display.shading
shading.light = "STUDIO"
shading.color_type = "OBJECT"
shading.show_cavity = False
scene.display.render_aa = "32"
scene.world.color = (.22,.22,.22)
scene.view_settings.view_transform = "Standard"
scene.render.resolution_x = 1440
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100
scene.render.filepath = str(folder/"preview.png")
bpy.ops.render.render(write_still=True)

focus = Vector((0,0,88))
camera.location = focus + Vector((45,-210,62))
camera.rotation_euler = (focus-camera.location).to_track_quat("-Z","Y").to_euler()
camera.data.ortho_scale = 84
scene.render.resolution_x = 1080
scene.render.resolution_y = 870
scene.render.filepath = str(folder/"tip-detail.png")
bpy.ops.render.render(write_still=True)
