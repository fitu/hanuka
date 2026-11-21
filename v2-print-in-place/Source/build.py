"""Build the aligned color meshes and a standard multipart 3MF."""
import argparse
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
import trimesh

SOURCE = Path(__file__).resolve().parent
SEGMENTS = 96
STEM_RADIUS = 7.7

def twisted_half(height, turns, half):
    levels = int(4*height)
    n = SEGMENTS//2+2
    vertices = []
    for i in range(levels+1):
        t = i/levels
        angle = (np.arange(n-1)+half*SEGMENTS//2)*(2*np.pi/SEGMENTS)
        radius = STEM_RADIUS + 1.04*np.sin(np.pi*t)**2*np.cos(2*angle)
        phase = angle + 2*np.pi*turns*t
        vertices.extend(np.column_stack((radius*np.cos(phase),radius*np.sin(phase),np.full(n-1,t*height))))
        vertices.append([0,0,t*height])
    faces = []
    for row in range(levels):
        for j in range(n):
            a, b = row*n+j, row*n+(j+1)%n
            # Both colors use the same diagonal on their shared radial faces.
            if j == n-1:
                faces.extend(((a,b,b+n),(a,b+n,a+n)))
            else:
                faces.extend(((a,b,a+n),(b,b+n,a+n)))
    for j in range(n-2):
        faces.extend(((n-1,j+1,j),(levels*n+n-1,levels*n+j,levels*n+j+1)))
    mesh = trimesh.Trimesh(vertices=vertices,faces=faces)
    mesh.fix_normals()
    assert mesh.is_volume
    return mesh

def collar(diameter, depth):
    bore = diameter/2
    if not (0 < bore <= 7.5 and 0 < depth < 11.8):
        raise ValueError("Choose a bore up to 15 mm and depth below 11.8 mm.")
    profile = [(0,0),(STEM_RADIUS,0),(9.55,1.85),(9.55,11.5),(9.05,12),
               (bore+.3,12),(bore,11.7),(bore,12-depth),(0,12-depth)]
    mesh = trimesh.creation.revolve(profile, sections=SEGMENTS)
    mesh.fix_normals()
    assert mesh.is_volume
    return mesh

def export_scad(directory, part, diameter, depth):
    path = directory/f"{part}.stl"
    subprocess.run(["openscad","-o",str(path),"-D",f'part="{part}"',
                    "-D",f"socket_diameter={diameter}","-D",f"socket_depth={depth}",
                    str(SOURCE/"body.scad")],check=True)
    mesh = trimesh.load_mesh(path)
    assert mesh.is_volume, part
    return mesh

def write_3mf(path, parts):
    model = ET.Element("model",{"xmlns":"http://schemas.microsoft.com/3dmanufacturing/core/2015/02","unit":"millimeter"})
    resources = ET.SubElement(model,"resources")
    materials = ET.SubElement(resources,"basematerials",id="1")
    ET.SubElement(materials,"base",name="Red - Right AMS",displaycolor="#CE142BFF")
    ET.SubElement(materials,"base",name="White - Left External",displaycolor="#FFFFFFFF")
    for idx,(name,solid) in enumerate(parts):
        obj = ET.SubElement(resources,"object",id=str(idx+2),type="model",name=name,pid="1",pindex=str(idx))
        mesh = ET.SubElement(obj,"mesh")
        vv = ET.SubElement(mesh,"vertices")
        tt = ET.SubElement(mesh,"triangles")
        for x,y,z in solid.vertices:
            ET.SubElement(vv,"vertex",x=f"{x:.7f}",y=f"{y:.7f}",z=f"{z:.7f}")
        for a,b,c in solid.faces:
            ET.SubElement(tt,"triangle",v1=str(a),v2=str(b),v3=str(c))
    obj = ET.SubElement(resources,"object",id="4",type="model",name="Hapoel spiral Hanukkiah")
    components = ET.SubElement(obj,"components")
    ET.SubElement(components,"component",objectid="2")
    ET.SubElement(components,"component",objectid="3")
    build = ET.SubElement(model,"build")
    ET.SubElement(build,"item",objectid="4",transform="1 0 0 0 1 0 0 0 1 155 155 0")
    with ZipFile(path,"w",ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels",'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model",ET.tostring(model,encoding="UTF-8",xml_declaration=True))

def build(output, diameter, depth):
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as fragments:
        temp = Path(fragments)
        base = export_scad(temp,"red-base",diameter,depth)
        inlay = export_scad(temp,"white-inlay",diameter,depth)
        coupon = export_scad(temp,"fit-coupon",diameter,depth)
    red = [base]
    white = [inlay]
    for i in range(-4,5):
        height, turns = (48,1.5) if i==0 else (25,.75)
        x = 21*i
        for h,parts in enumerate((red,white)):
            stem = twisted_half(height, turns, h)
            stem.apply_translation((x,0,50))
            parts.append(stem)
        cap = collar(diameter,depth)
        cap.apply_translation((x,0,50+height))
        red.append(cap)
    red_solid = trimesh.boolean.union(red,engine="manifold")
    red_solid.merge_vertices(digits_vertex=7)
    white_solid = trimesh.util.concatenate(white)
    for mesh in (red_solid,white_solid):
        assert mesh.is_volume
    full = trimesh.boolean.union([red_solid,white_solid],engine="manifold")
    assert full.is_volume
    assert sum(piece.is_volume and piece.volume > .01 for piece in full.split(only_watertight=False)) == 1
    assert np.allclose(full.extents,[200,50,110])
    assert abs(full.volume-red_solid.volume-white_solid.volume)<.1
    red_solid.export(output/"Red-Right-AMS.stl")
    white_solid.export(output/"White-Left-External.stl")
    coupon.export(output/"Metal-cup-fit-test.stl")
    write_3mf(output/"Hapoel-H2D-spiral-v2.3mf",[("Red - Right AMS",red_solid),("White - Left External",white_solid)])
    print(f"Connected solid, {full.extents} mm; color overlap below 0.1 mm³.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--diameter",type=float,default=13.6)
    parser.add_argument("--depth",type=float,default=10.4)
    args = parser.parse_args()
    build(args.output,args.diameter,args.depth)
