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
STEM_RADIUS = 8.2

def progress(t, ramp=.2):
    """Cosine easing into and out of a constant-slope middle."""
    if t > 1-ramp:
        value, speed = progress(1-t,ramp)
        return 1-value, speed
    if t < ramp:
        angle = np.pi*t/ramp
        return (t-ramp*np.sin(angle)/np.pi)/(2*(1-ramp)), (1-np.cos(angle))/(2*(1-ramp))
    return (t-ramp/2)/(1-ramp), 1/(1-ramp)

def twisted_half(start, neck, turns, half, diameter, depth):
    """Sweep a half-cylinder, ending in a continuous helical half of the cup."""
    cup_height = 16
    bore = diameter/2
    if not (0 < bore <= 6.9 and 0 < depth < 15.7):
        raise ValueError("Choose a bore up to 13.8 mm and depth below 15.7 mm.")
    floor = cup_height-depth
    chamfer_start = cup_height-.3
    start, neck = np.asarray(start), np.asarray(neck)
    height = neck[2]-start[2]
    drift = neck[:2]-start[:2]
    distance = np.linalg.norm(drift)
    horizontal = np.r_[drift/distance,0] if distance else np.zeros(3)
    vertical = np.array([0,0,1])
    n = SEGMENTS//2+1
    angle = (np.arange(n)+half*SEGMENTS//2)*(2*np.pi/SEGMENTS)
    vertices, faces, outer_faces = [], [], []

    def ring(center, phase, radius, u, v):
        ids = np.arange(len(vertices),len(vertices)+n)
        vertices.extend(center+radius*(np.cos(phase)[:,None]*u+np.sin(phase)[:,None]*v))
        return ids

    def point(center):
        vertices.append(center)
        return len(vertices)-1

    def quad(a,b,c,d,output=faces,reverse=False):
        triangles = ((a,b,d),(a,d,c))
        output.extend(face[::-1] if reverse else face for face in triangles)

    def connect(low,high,output=faces,reverse=False):
        for j in range(n-1):
            quad(low[j],low[j+1],high[j],high[j+1],output,reverse)

    def fan(edge,center,reverse=False):
        for j in range(n-1):
            face = (center,edge[j],edge[j+1])
            faces.append(face[::-1] if reverse else face)

    def join_sides(lower,upper):
        outer_low, inner_low = lower
        outer_high, inner_high = upper
        for j in (0,n-1):
            # Both halves triangulate their shared radial walls identically.
            quad(outer_low[j],inner_low[j],outer_high[j],inner_high[j],reverse=j==0)

    layers = []
    for z in np.linspace(0,height,round(2*height)+1):
        t = z/height
        fraction, speed = progress(t)
        slope = distance*speed/height
        cosine = 1/np.sqrt(1+slope*slope)
        frame_delta = (cosine-1)*horizontal - slope*cosine*vertical
        u = np.array([1,0,0]) + horizontal[0]*frame_delta
        v = np.array([0,1,0]) + horizontal[1]*frame_delta
        center = start + np.r_[drift*fraction,z]
        phase = angle + 2*np.pi*turns*t
        layers.append((ring(center,phase,STEM_RADIUS,u,v),np.full(n,point(center))))

    cup_levels = sorted(set(np.linspace(0,cup_height,65)[1:]) | {floor,chamfer_start})
    u, v = np.eye(3)[:2]
    for z in cup_levels:
        center = neck + np.array([0,0,z])
        phase = angle + 2*np.pi*turns*(1+z/height)
        bead = np.sin(np.pi*(z-9.5)/6.5)**2 if 9.5 < z < 16 else 0
        outer = ring(center,phase,STEM_RADIUS+bead,u,v)
        if z < floor:
            layers.append((outer,np.full(n,point(center))))
            continue
        inner = ring(center,phase,bore+max(0,z-chamfer_start),u,v)
        if z == floor:
            # This layer has both the floor disk and the inner cup wall.
            floor_index = len(layers)
            floor_center = point(center)
        layers.append((outer,inner))

    fan(layers[0][0],layers[0][1][0],reverse=True)
    for i,(low,high) in enumerate(zip(layers,layers[1:]),1):
        connect(low[0],high[0],outer_faces)
        if i < floor_index:
            join_sides(low,high)
        elif i == floor_index:
            fan(high[1],floor_center)
            for j in (0,n-1):
                # Split the upper radial edge at the bore to avoid a T junction.
                a,b,c,d = low[0][j],low[1][j],high[0][j],high[1][j]
                triangles = ((a,b,d),(b,floor_center,d),(a,d,c))
                faces.extend(face[::-1] if j==0 else face for face in triangles)
        else:
            connect(low[1],high[1],reverse=True)
            join_sides(low,high)
    connect(*layers[-1])
    mesh = trimesh.Trimesh(vertices=vertices,faces=outer_faces+faces)
    assert mesh.is_volume
    angle = np.degrees(np.arcsin(np.clip(-mesh.face_normals[:len(outer_faces),2],0,1))).max()
    return mesh, angle

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
    obj = ET.SubElement(resources,"object",id="4",type="model",name="Hapoel Hanukkiah with spiral rims")
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
    columns = []
    max_overhang = 0
    for i in range(-4,5):
        end = (21*i,0,94 if i==0 else 71)
        start = (14*i,0 if i==0 else 9.5*(-1)**abs(i),9)
        turns = 1.5 if i==0 else 1
        halves = []
        for h, parts in enumerate((red,white)):
            stem, overhang = twisted_half(start,end,turns,h,diameter,depth)
            max_overhang = max(max_overhang,float(overhang))
            parts.append(stem)
            halves.append(stem)
        columns.append(trimesh.boolean.union(halves,engine="manifold"))
    for a,b in zip(columns,columns[1:]):
        assert trimesh.boolean.intersection([a,b],engine="manifold").is_empty
    assert max_overhang < 39
    print(f"Maximum downward wall angle: {max_overhang:.1f} degrees from vertical.")
    red_solid = trimesh.boolean.union(red,engine="manifold")
    white_solid = trimesh.util.concatenate(white)
    for mesh in (red_solid,white_solid):
        assert mesh.is_volume
    full = trimesh.boolean.union([red_solid,white_solid],engine="manifold")
    assert full.is_volume
    assert sum(piece.is_volume and piece.volume > .01 for piece in full.split(only_watertight=False)) == 1
    assert np.allclose(full.extents,[188,46,110])
    assert abs(full.volume-red_solid.volume-white_solid.volume)<.1
    red_solid.export(output/"Red-Right-AMS.stl")
    white_solid.export(output/"White-Left-External.stl")
    coupon.export(output/"Metal-cup-fit-test.stl")
    write_3mf(output/"Hapoel-H2D-menorah-v5.3mf",[("Red - Right AMS",red_solid),("White - Left External",white_solid)])
    print(f"Connected solid, {full.extents} mm; color overlap below 0.1 mm³.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--diameter",type=float,default=12.6)
    parser.add_argument("--depth",type=float,default=14.0)
    args = parser.parse_args()
    build(args.output,args.diameter,args.depth)
