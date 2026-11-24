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
STRIPE_COUNT = 4
STRIPE_WIDTH = 3.0
SPIRAL_PITCH = 46.5
STOP_AZIMUTH = np.radians(290)
TURN = 2*np.pi
STEM_RADIUS = 8.2
BAND_PERIOD = TURN*STEM_RADIUS*SPIRAL_PITCH/(
    STRIPE_COUNT*np.hypot(SPIRAL_PITCH,TURN*STEM_RADIUS)
)
RED_WIDTH = BAND_PERIOD-STRIPE_WIDTH
CUP_HEIGHT = 24
COLLAR_START = CUP_HEIGHT-12
STRIPE_STOP = CUP_HEIGHT-10

def progress(t, ramp=.2):
    """Cosine easing into and out of a constant-slope middle."""
    if t > 1-ramp:
        value, speed = progress(1-t,ramp)
        return 1-value, speed
    if t < ramp:
        angle = np.pi*t/ramp
        return (t-ramp*np.sin(angle)/np.pi)/(2*(1-ramp)), (1-np.cos(angle))/(2*(1-ramp))
    return (t-ramp/2)/(1-ramp), 1/(1-ramp)

def tip_profile():
    lower_ring = 1.05
    crest = CUP_HEIGHT-20
    collar_radius = 9.45
    return np.array([
        (0, STEM_RADIUS),
        (crest-lower_ring/np.tan(np.radians(35)), STEM_RADIUS),
        (crest, STEM_RADIUS+lower_ring),
        (crest+lower_ring/np.tan(np.radians(55)), STEM_RADIUS),
        (COLLAR_START, STEM_RADIUS),
        (STRIPE_STOP, collar_radius),
        (CUP_HEIGHT-.8, collar_radius),
        (CUP_HEIGHT, collar_radius-.8),
    ])

def sector_angles(stripe_index, white_stripe, rotation):
    separation = TURN/STRIPE_COUNT
    # Keep each color's fraction of a normal section fixed. At larger
    # collar radii the local pitch changes to preserve the band widths.
    half_angle = separation*STRIPE_WIDTH/(2*BAND_PERIOD)
    center = np.arange(STRIPE_COUNT)*separation
    if white_stripe:
        start, end, subdivisions = (
            center[stripe_index]-half_angle,center[stripe_index]+half_angle,8
        )
    else:
        start = center[stripe_index]+half_angle
        end = center[(stripe_index+1)%STRIPE_COUNT]-half_angle
        subdivisions = 24
    span = (end-start)%TURN
    angles = np.linspace(start,start+span,subdivisions+1)
    angles[-1] = end
    return angles + STOP_AZIMUTH + rotation

def angular_rate(radius):
    # Model the band widths on the locally developed surface. The
    # circumference projects to four periods measured across the helix.
    projected_fraction = STRIPE_COUNT*BAND_PERIOD/(TURN*radius)
    return np.sqrt(1/projected_fraction**2-1)/radius

def cumulative_rotation(distance, rate):
    steps = np.diff(distance)
    mid_rates = (rate[:-1]+rate[1:])/2
    return np.r_[0,np.cumsum(steps*mid_rates)]

def twisted_sector(start, neck, stripe_index, white_stripe, diameter, depth):
    """Sweep one complementary color sector through the stem and cup."""
    bore = diameter/2
    if not (0 < bore <= 6.9 and 0 < depth < 15.7):
        raise ValueError("Choose a bore up to 13.8 mm and depth below 15.7 mm.")
    floor = CUP_HEIGHT-depth
    chamfer_start = CUP_HEIGHT-.3
    start, neck = np.asarray(start), np.asarray(neck)
    height = neck[2]-start[2]
    drift = neck[:2]-start[:2]
    distance = np.linalg.norm(drift)
    horizontal = np.r_[drift/distance,0] if distance else np.zeros(3)
    vertical = np.array([0,0,1])
    n = len(sector_angles(stripe_index,white_stripe,0))
    vertices = []

    def ring(center, phase, radius, u, v):
        ids = np.arange(len(vertices),len(vertices)+n)
        vertices.extend(center+radius*(np.cos(phase)[:,None]*u+np.sin(phase)[:,None]*v))
        return ids

    def point(center):
        vertices.append(center)
        return len(vertices)-1

    def quad(a,b,c,d,output,reverse=False):
        triangles = ((a,b,d),(a,d,c))
        output.extend(face[::-1] if reverse else face for face in triangles)

    def connect(low,high,output,reverse=False):
        for j in range(n-1):
            quad(low[j],low[j+1],high[j],high[j+1],output,reverse)

    def fan(edge,center,output,reverse=False):
        for j in range(n-1):
            face = (center,edge[j],edge[j+1])
            output.append(face[::-1] if reverse else face)

    def join_sides(lower,upper,output):
        outer_low, inner_low = lower
        outer_high, inner_high = upper
        for j in (0,n-1):
            # Both sectors triangulate their shared radial walls identically.
            quad(outer_low[j],inner_low[j],outer_high[j],inner_high[j],output,reverse=j==0)

    stem_levels = np.linspace(0,height,int(np.ceil(height/.35))+1)
    easing = np.array([progress(z/height) for z in stem_levels])
    slope = distance*easing[:,1]/height
    stem_rotation = cumulative_rotation(stem_levels,angular_rate(STEM_RADIUS)*np.hypot(1,slope))

    heights, radii = tip_profile().T
    # Subdivide each profile interval without creating tiny sliver layers
    # beside the exact levels of the rim, ridge, and socket floor.
    tip_breaks = sorted(set(heights) | {floor,chamfer_start})
    tip_levels = np.concatenate([
        np.linspace(a,b,int(np.ceil((b-a)/.16))+1)[:-1]
        for a,b in zip(tip_breaks,tip_breaks[1:])
    ] + [np.array([CUP_HEIGHT])])
    tip_radii = np.interp(tip_levels,heights,radii)
    meridian = np.r_[0,np.cumsum(np.hypot(np.diff(tip_levels),np.diff(tip_radii)))]
    tip_rotation = cumulative_rotation(meridian,angular_rate(tip_radii))
    stop_rotation = stem_rotation[-1]+tip_rotation[np.searchsorted(tip_levels,STRIPE_STOP)]

    layers, centers = [], []
    for z,(fraction,_),slope_at_z,rotation in zip(stem_levels,easing,slope,stem_rotation-stop_rotation):
        cosine = 1/np.sqrt(1+slope_at_z*slope_at_z)
        frame_delta = (cosine-1)*horizontal - slope_at_z*cosine*vertical
        u = np.array([1,0,0]) + horizontal[0]*frame_delta
        v = np.array([0,1,0]) + horizontal[1]*frame_delta
        center = start + np.r_[drift*fraction,z]
        phase = sector_angles(stripe_index,white_stripe,rotation)
        layers.append((ring(center,phase,STEM_RADIUS,u,v),ring(center,phase,bore,u,v)))
        centers.append(np.full(n,point(center)))

    u, v = np.eye(3)[:2]
    for z,radius,rotation in zip(tip_levels[1:],tip_radii[1:],stem_rotation[-1]+tip_rotation[1:]-stop_rotation):
        if z == STRIPE_STOP:
            cutoff = len(layers)
        if z == floor:
            floor_index = len(layers)
        center = neck + np.array([0,0,z])
        phase = sector_angles(stripe_index,white_stripe,rotation)
        outer = ring(center,phase,radius,u,v)
        inner = ring(center,phase,bore+max(0,z-chamfer_start),u,v)
        layers.append((outer,inner))
        centers.append(np.full(n,point(center)))

    def make_shell(first_layer, last_layer):
        faces, outside = [], []
        connect(*layers[first_layer],faces,reverse=True)
        for low, high in zip(layers[first_layer:last_layer],layers[first_layer+1:last_layer+1]):
            connect(low[0],high[0],outside)
            connect(low[1],high[1],faces,reverse=True)
            join_sides(low,high,faces)
        connect(*layers[last_layer],faces)
        mesh = trimesh.Trimesh(vertices=vertices,faces=outside+faces)
        mesh.remove_unreferenced_vertices()
        assert mesh.is_volume
        angle = np.degrees(np.arcsin(np.clip(-mesh.face_normals[:len(outside),2],0,1))).max()
        return mesh, angle

    # The red core ends at the socket floor. Keeping the stripe volumes
    # outside this core prevents them from touching along the stem axis.
    core_layers = [(layers[i][1],centers[i]) for i in range(floor_index+1)]
    core_faces = []
    fan(core_layers[0][0],centers[0][0],core_faces,reverse=True)
    for low, high in zip(core_layers,core_layers[1:]):
        connect(low[0],high[0],core_faces)
        join_sides(low,high,core_faces)
    fan(core_layers[-1][0],centers[floor_index][0],core_faces)
    core = trimesh.Trimesh(vertices=vertices,faces=core_faces)
    core.remove_unreferenced_vertices()
    assert core.is_volume

    top = len(layers)-1
    if white_stripe:
        stripe, lower_angle = make_shell(0,cutoff)
        red_cap, upper_angle = make_shell(cutoff,top)
        return [core,red_cap], [stripe], max(lower_angle,upper_angle)
    red_body, wall_angle = make_shell(0,top)
    return [core,red_body], [], wall_angle

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
    obj = ET.SubElement(resources,"object",id="4",type="model",name="Hapoel Hanukkiah with refined curved surfaces")
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
    columns = {}
    max_overhang = 0
    reflection = np.diag([-1,1,1,1])
    for i in range(5):
        end = (21*i,0,(110 if i==0 else 87)-CUP_HEIGHT)
        start = (14*i,0 if i==0 else 9.5*(-1)**abs(i),9)
        stem_red, stem_white = [], []
        for stripe_index in range(STRIPE_COUNT):
            for stripe in (True,False):
                red_parts, white_parts, overhang = twisted_sector(
                    start,end,stripe_index,stripe,diameter,depth
                )
                stem_red.extend(red_parts)
                stem_white.extend(white_parts)
                max_overhang = max(max_overhang,float(overhang))
        red.extend(stem_red)
        white.extend(stem_white)
        columns[i] = trimesh.boolean.union(stem_red+stem_white,engine="manifold")
        if i:
            # Mirrored winding gives the two sides the same band profile from the front.
            red.extend(part.copy().apply_transform(reflection) for part in stem_red)
            white.extend(part.copy().apply_transform(reflection) for part in stem_white)
            columns[-i] = columns[i].copy().apply_transform(reflection)
    for i in range(-4,4):
        assert trimesh.boolean.intersection([columns[i],columns[i+1]],engine="manifold").is_empty
    assert max_overhang < 41
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
    write_3mf(output/"Hapoel-H2D-menorah-v11.3mf",[("Red - Right AMS",red_solid),("White - Left External",white_solid)])
    print(f"Connected solid, {full.extents} mm; color overlap below 0.1 mm³.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--diameter",type=float,default=12.6)
    parser.add_argument("--depth",type=float,default=14.0)
    args = parser.parse_args()
    build(args.output,args.diameter,args.depth)
