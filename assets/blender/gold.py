# IBI Gold Mines hero renders. Args after "--": <coins|ornaments|single> [--preview] [--out=DIR]
import bpy, bmesh, math, os, sys, random
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MODE = (argv[0] if argv else "coins").lower()
PREVIEW = "--preview" in argv
OUT = os.path.dirname(os.path.abspath(__file__))
for a in argv:
    if a.startswith("--out="):
        OUT = a.split("=", 1)[1]
random.seed(7)

scene = bpy.context.scene
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# ---------- engine ----------
ENGINE = "CYCLES"
try:
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = (d.type == "OPTIX")
    scene.cycles.device = "GPU"
    scene.cycles.samples = 24 if PREVIEW else 160
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.max_bounces = 10
    scene.cycles.glossy_bounces = 6
    scene.cycles.transmission_bounces = 8
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    scene.cycles.blur_glossy = 0.5
except Exception as e:
    print("CYCLES unavailable:", e)
    ENGINE = "BLENDER_EEVEE"
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = 64
print("ENGINE", ENGINE)

SIZES = {"coins": (1600, 1000), "ornaments": (1600, 1000), "single": (800, 800)}
W, H = SIZES[MODE]
scene.render.resolution_x = W // 2 if PREVIEW else W
scene.render.resolution_y = H // 2 if PREVIEW else H
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "8"
scene.render.image_settings.compression = 20
VIEW = "Standard"
for a in argv:
    if a.startswith("--view="):
        VIEW = a.split("=", 1)[1]
    if a.startswith("--samples="):
        scene.cycles.samples = int(a.split("=", 1)[1])
try:
    scene.view_settings.view_transform = VIEW
    scene.view_settings.look = "AgX - Punchy" if VIEW == "AgX" else "None"
except Exception as e:
    print("look:", e)
scene.view_settings.exposure = 0.0

# ---------- helpers ----------
def link(ob):
    scene.collection.objects.link(ob)
    return ob

def new_mesh_object(name, bm, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    return link(ob)

def mark_sharp(me, angle_deg=30):
    thr = math.cos(math.radians(angle_deg))
    bm = bmesh.new(); bm.from_mesh(me)
    for e in bm.edges:
        fs = e.link_faces
        if len(fs) == 2 and fs[0].normal.dot(fs[1].normal) < thr:
            e.smooth = False
    bm.to_mesh(me); bm.free()

def bevel(ob, width, segments=3, angle=30):
    m = ob.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle)
    m.harden_normals = True
    return m

def torus_into(bm, R, r, segs=96, rings=24, matrix=None, mat_index=0):
    verts = []
    for i in range(segs):
        a = 2 * math.pi * i / segs
        ca, sa = math.cos(a), math.sin(a)
        row = []
        for j in range(rings):
            b = 2 * math.pi * j / rings
            p = Vector(((R + r * math.cos(b)) * ca, (R + r * math.cos(b)) * sa, r * math.sin(b)))
            if matrix is not None:
                p = matrix @ p
            row.append(bm.verts.new(p))
        verts.append(row)
    for i in range(segs):
        for j in range(rings):
            f = bm.faces.new((verts[i][j], verts[(i + 1) % segs][j], verts[(i + 1) % segs][(j + 1) % rings], verts[i][(j + 1) % rings]))
            f.material_index = mat_index
    return bm

def sphere_into(bm, r, center, mat_index=0):
    res = bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=r, matrix=Matrix.Translation(Vector(center)))
    for v in res["verts"]:
        for f in v.link_faces:
            f.material_index = mat_index
    return bm

def gold_material(name, base, rough=0.2, aniso=0.25, rim_reed=False, engrave=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Metallic"].default_value = 1.0
    b.inputs["Roughness"].default_value = rough
    try:
        b.inputs["Anisotropic"].default_value = aniso
    except Exception:
        pass
    tc = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 90.0
    noise.inputs["Detail"].default_value = 2.0
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.3
    ramp.inputs["From Max"].default_value = 0.7
    ramp.inputs["To Min"].default_value = max(0.05, rough - 0.02)
    ramp.inputs["To Max"].default_value = rough + 0.02
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Value"])
    nt.links.new(ramp.outputs["Result"], b.inputs["Roughness"])
    if rim_reed or engrave:
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
        ang = nt.nodes.new("ShaderNodeMath"); ang.operation = "ARCTAN2"
        nt.links.new(sep.outputs["Y"], ang.inputs[0])
        nt.links.new(sep.outputs["X"], ang.inputs[1])
        mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = 140.0 if rim_reed else 64.0
        nt.links.new(ang.outputs[0], mul.inputs[0])
        if engrave:
            add = nt.nodes.new("ShaderNodeMath"); add.operation = "ADD"
            zmul = nt.nodes.new("ShaderNodeMath"); zmul.operation = "MULTIPLY"
            zmul.inputs[1].default_value = 9.0
            nt.links.new(sep.outputs["Z"], zmul.inputs[0])
            nt.links.new(mul.outputs[0], add.inputs[0])
            nt.links.new(zmul.outputs[0], add.inputs[1])
            src = add
        else:
            src = mul
        sin = nt.nodes.new("ShaderNodeMath"); sin.operation = "SINE"
        nt.links.new(src.outputs[0], sin.inputs[0])
        if rim_reed:
            sharp = nt.nodes.new("ShaderNodeMath"); sharp.operation = "MULTIPLY"
            sharp.inputs[1].default_value = 3.0
            nt.links.new(sin.outputs[0], sharp.inputs[0])
            clamp = nt.nodes.new("ShaderNodeClamp")
            clamp.inputs["Min"].default_value = -1.0
            clamp.inputs["Max"].default_value = 1.0
            nt.links.new(sharp.outputs[0], clamp.inputs["Value"])
            hsrc = clamp
        else:
            hsrc = sin
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.6 if rim_reed else 0.28
        bump.inputs["Distance"].default_value = 0.02 if rim_reed else 0.006
        nt.links.new(hsrc.outputs[0], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m

GOLD24 = (1.0, 0.766, 0.336)
GOLD22 = (1.0, 0.72, 0.30)

# ---------- coin ----------
COIN_R, COIN_T = 1.0, 0.14
def make_coin(name, face_mat, rim_mat):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=160,
                          radius1=COIN_R, radius2=COIN_R, depth=COIN_T)
    for f in bm.faces:
        f.material_index = 1 if abs(f.normal.z) < 0.5 else 0
    for sgn in (1, -1):
        z = sgn * COIN_T / 2
        torus_into(bm, 0.80, 0.028, segs=160, rings=16, matrix=Matrix.Translation(Vector((0, 0, z))))
        torus_into(bm, 0.93, 0.02, segs=160, rings=16, matrix=Matrix.Translation(Vector((0, 0, z))))
        for i in range(5):
            for j in range(5):
                x = (i - 2) * 0.2
                y = (j - 2) * 0.2
                sphere_into(bm, 0.062, (x, y, z))
    ob = new_mesh_object(name, bm)
    mark_sharp(ob.data)
    ob.data.materials.append(face_mat)
    ob.data.materials.append(rim_mat)
    bevel(ob, 0.012, 3)
    return ob

# ---------- lights ----------
def aim(ob, loc, target):
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

def area(name, loc, target, power, size, color=(1, 1, 1), size_y=None):
    li = bpy.data.lights.new(name, "AREA")
    li.energy = power
    li.size = size
    if size_y:
        li.shape = "RECTANGLE"
        li.size_y = size_y
    li.color = color
    ob = link(bpy.data.objects.new(name, li))
    aim(ob, loc, target)
    return ob

def emissive_plane(name, loc, target, sx, sy, strength, color=(1, 0.97, 0.9), gradient=True):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    ob = new_mesh_object(name, bm, smooth=False)
    ob.scale = (sx / 2, sy / 2, 1)
    aim(ob, loc, target)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    if gradient:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        grad = nt.nodes.new("ShaderNodeTexGradient")
        grad.gradient_type = "SPHERICAL"
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Location"].default_value = (0.5, 0.5, 0)
        mp.inputs["Scale"].default_value = (1.5, 1.5, 1)
        nt.links.new(tc.outputs["UV"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], grad.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = 0.0
        mr.inputs["From Max"].default_value = 1.0
        mr.inputs["To Min"].default_value = strength * 0.15
        mr.inputs["To Max"].default_value = strength
        nt.links.new(grad.outputs["Fac"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], em.inputs["Strength"])
    nt.links.new(em.outputs[0], out.inputs[0])
    ob.data.materials.append(m)
    me = ob.data
    uv = me.uv_layers.new(name="UV")
    for li, l in enumerate(me.loops):
        v = me.vertices[l.vertex_index].co
        uv.data[li].uv = ((v.x + 1) / 2, (v.y + 1) / 2)
    ob.visible_camera = False
    ob.visible_shadow = False
    return ob

def shadow_floor():
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40.0)
    ob = new_mesh_object("Floor", bm, smooth=False)
    m = bpy.data.materials.new("Floor")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.5, 0.5, 0.5, 1)
    b.inputs["Roughness"].default_value = 0.6
    ob.data.materials.append(m)
    if ENGINE == "CYCLES":
        ob.is_shadow_catcher = True
        ob.visible_glossy = False
    return ob

def camera(loc, target, lens=60, fstop=None, focus=None, ortho=None):
    cam = link(bpy.data.objects.new("Cam", bpy.data.cameras.new("cam")))
    aim(cam, loc, target)
    cam.data.lens = lens
    cam.data.sensor_width = 36
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    if fstop:
        cam.data.dof.use_dof = True
        cam.data.dof.aperture_fstop = fstop
        if focus is not None:
            cam.data.dof.focus_object = focus
    scene.camera = cam
    return cam

def world(gray=0.12):
    scene.world = bpy.data.worlds.new("W")
    scene.world.use_nodes = True
    nt = scene.world.node_tree
    bg = nt.nodes["Background"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -0.2
    mr.inputs["From Max"].default_value = 1.0
    mr.inputs["To Min"].default_value = gray * 0.25
    mr.inputs["To Max"].default_value = gray * 2.2
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], bg.inputs["Strength"])
    bg.inputs["Color"].default_value = (1.0, 0.96, 0.9, 1)

def studio(target, scale=1.0, cam_loc=None):
    t = Vector(target)
    s = scale
    area("Key", t + Vector((-5, -6, 8)) * s, t, 1800 * s * s, 5 * s, color=(1, 0.98, 0.95))
    area("Fill", t + Vector((7, -6, 3.5)) * s, t, 400 * s * s, 7 * s, color=(0.95, 0.97, 1.0))
    area("Rim", t + Vector((1.5, 7, 5)) * s, t, 1400 * s * s, 4 * s, color=(1, 0.82, 0.6))
    if cam_loc is not None:
        c = Vector(cam_loc)
        back = t + (c - t) * 1.6 + Vector((0, 0, 1.5 * s))
        emissive_plane("Reflector", back, t, 34 * s, 22 * s, 2.6, color=(1, 0.98, 0.93))
    emissive_plane("Top", t + Vector((0, 1, 12)) * s, t, 18 * s, 18 * s, 1.4, color=(1, 0.98, 0.93))
    emissive_plane("Strip", t + Vector((-2, -1, 9)) * s, t, 16 * s, 1.6 * s, 14.0, color=(1, 1, 1), gradient=False)
    emissive_plane("Strip2", t + Vector((8, 2, 6)) * s, t, 10 * s, 1.0 * s, 6.0, color=(1, 0.95, 0.85), gradient=False)

# ---------- scenes ----------
if MODE in ("coins", "single"):
    face = gold_material("Gold24", GOLD24, rough=0.2, aniso=0.2)
    rim = gold_material("Gold24Rim", GOLD24, rough=0.24, rim_reed=True)

if MODE == "coins":
    world(0.12)
    shadow_floor()
    T = COIN_T
    for i in range(4):
        c = make_coin("Stack%d" % i, face, rim)
        c.location = (random.uniform(-0.04, 0.04), random.uniform(-0.04, 0.04), T / 2 + i * T)
        c.rotation_euler = (0, 0, random.uniform(0, 6.28))
    lean = make_coin("Lean", face, rim)
    tilt = math.radians(66)
    lean.rotation_euler = (tilt, 0, math.radians(-14))
    lean.location = (-0.62, -1.26, COIN_R * math.sin(tilt) + T / 2 * math.cos(tilt) - 0.02)
    a = make_coin("LooseA", face, rim)
    a.location = (2.05, -1.55, T / 2)
    a.rotation_euler = (0, 0, math.radians(35))
    b = make_coin("LooseB", face, rim)
    b.location = (2.95, -0.75, T * 0.95)
    b.rotation_euler = (math.radians(-2.5), math.radians(3.0), math.radians(80))
    target = (1.0, -0.7, 0.35)
    cam_loc = (1.0 + 2.6, -0.7 - 11.2, 0.35 + 5.6)
    cam = camera(cam_loc, target, lens=62, fstop=6.0, focus=lean)
    studio(target, 1.0, cam_loc)
    outname = "hero-coins.png"

elif MODE == "single":
    world(0.12)
    c = make_coin("Coin", face, rim)
    c.location = (0, 0, 0)
    target = (0, 0, 0)
    cam_loc = (0, -0.001, 14)
    cam = camera(cam_loc, target, ortho=2.3)
    area("Key", (-5, 5, 8), target, 1600, 5, color=(1, 0.98, 0.95))
    area("Fill", (6, -4, 6), target, 500, 7, color=(0.95, 0.97, 1.0))
    emissive_plane("Reflector", (-5, 4, 9), target, 26, 20, 3.4, color=(1, 0.98, 0.93))
    emissive_plane("Strip", (2.5, -3.5, 7), target, 14, 1.3, 12.0, color=(1, 1, 1), gradient=False)
    emissive_plane("Dark", (6, -5, 6), target, 12, 12, 0.02, color=(0.2, 0.2, 0.25), gradient=False)
    outname = "coin-single.png"

elif MODE == "ornaments":
    world(0.12)
    shadow_floor()
    polished = gold_material("Gold22", GOLD22, rough=0.17, aniso=0.2)
    engraved = gold_material("Gold22Engraved", GOLD22, rough=0.22, engrave=True)
    ringmat = gold_material("Gold22Ring", GOLD22, rough=0.15, aniso=0.2)
    BR, Br = 1.7, 0.14
    bm = bmesh.new(); torus_into(bm, BR, Br, segs=160, rings=32)
    bA = new_mesh_object("BangleA", bm); bA.data.materials.append(polished)
    bA.location = (-1.1, 0.5, Br)
    bm = bmesh.new(); torus_into(bm, BR, Br * 1.15, segs=160, rings=32)
    bB = new_mesh_object("BangleB", bm); bB.data.materials.append(engraved)
    tiltB = math.radians(54)
    bB.rotation_euler = (tiltB, 0, math.radians(-25))
    bB.location = (0.9, 1.55, (BR + Br * 1.15) * math.sin(tiltB) * 0.985)
    RR, Rr = 0.5, 0.075
    bm = bmesh.new(); torus_into(bm, RR, Rr, segs=128, rings=32)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=48, radius1=0.25, radius2=0.25, depth=0.18,
                          matrix=Matrix.Translation(Vector((0, RR + 0.02, 0))) @ Matrix.Rotation(math.radians(90), 4, "X"))
    ring = new_mesh_object("Ring", bm); ring.data.materials.append(ringmat)
    mark_sharp(ring.data); bevel(ring, 0.012, 3)
    ring.rotation_euler = (math.radians(90), 0, math.radians(35))
    ring.location = (1.15, -1.55, RR + Rr)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.235)
    gem = new_mesh_object("Gem", bm, smooth=False)
    gem.parent = ring
    gem.location = (0, RR + 0.13, 0)
    gm = bpy.data.materials.new("Ruby"); gm.use_nodes = True
    gb = gm.node_tree.nodes["Principled BSDF"]
    gb.inputs["Base Color"].default_value = (0.85, 0.03, 0.06, 1)
    gb.inputs["Roughness"].default_value = 0.03
    gb.inputs["IOR"].default_value = 1.77
    gb.inputs["Transmission Weight"].default_value = 1.0
    try:
        gb.inputs["Coat Weight"].default_value = 0.5
    except Exception:
        pass
    gem.data.materials.append(gm)
    # chain: interlocking tori placed by hand along a Catmull-Rom spline (the
    # Array+Curve modifier stack blew the bounding box up to 1e6 units)
    LR, Lr = 0.085, 0.024
    pts = [Vector((x, y, 0.085 + z)) for x, y, z in [(-4.4, 0.3, 0.0), (-4.0, -1.2, 0.02), (-2.9, -2.1, 0.0), (-1.6, -2.3, 0.03), (-0.6, -1.9, 0.0), (0.2, -2.6, 0.02), (1.4, -3.1, 0.0), (2.9, -2.9, 0.03), (3.9, -2.0, 0.0), (4.2, -0.6, 0.02), (3.5, 0.5, 0.0)]]
    def catmull(p0, p1, p2, p3, t):
        return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)
    samples = []
    ext = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(ext) - 2):
        for k in range(60):
            samples.append(catmull(ext[i - 1], ext[i], ext[i + 1], ext[i + 2], k / 60.0))
    samples.append(pts[-1])
    pitch = 0.105
    bm = bmesh.new()
    dist_acc = 0.0
    next_at = 0.0
    n = 0
    for i in range(1, len(samples)):
        seg = samples[i] - samples[i - 1]
        L = seg.length
        while next_at <= dist_acc + L and L > 0:
            f = (next_at - dist_acc) / L
            pos = samples[i - 1] + seg * f
            T = seg.normalized()
            N = T.cross(Vector((0, 0, 1))).normalized()
            B = N.cross(T).normalized()
            basis = Matrix((T, B, N)).transposed().to_4x4()
            twist = Matrix.Rotation(math.radians(90 * n + 35), 4, "X")
            flat = Matrix.Diagonal((1.0, 1.0, 0.72, 1.0))
            torus_into(bm, LR, Lr, segs=28, rings=10, matrix=Matrix.Translation(pos) @ basis @ twist @ flat)
            n += 1
            next_at += pitch
        dist_acc += L
    chain = new_mesh_object("Chain", bm); chain.data.materials.append(polished)
    print("CHAIN links", n)
    target = (0.1, -0.2, 0.75)
    cam_loc = (0.1 + 2.2, -0.2 - 13.8, 0.75 + 6.6)
    cam = camera(cam_loc, target, lens=50, fstop=7.0, focus=ring)
    studio(target, 1.15, cam_loc)
    outname = "hero-ornaments.png"

if "--probe" in argv:
    deps = bpy.context.evaluated_depsgraph_get()
    for ob in scene.objects:
        if ob.type == "MESH":
            bb = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
            xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
            print("BB %-12s x[%.1f,%.1f] y[%.1f,%.1f] z[%.1f,%.1f] cam_vis=%s" % (ob.name, min(xs), max(xs), min(ys), max(ys), min(zs), max(zs), ob.visible_camera))
    cam = scene.camera
    for dx in (-0.3, 0, 0.3):
        for dz in (-0.2, 0, 0.2):
            d = (Vector(target) + Vector((dx * 5, 0, dz * 5)) - cam.location).normalized()
            hit, loc, nrm, idx, ob, mat = scene.ray_cast(deps, cam.location, d)
            print("RAY", dx, dz, "hit", ob.name if hit else None, "at", tuple(round(v, 2) for v in loc) if hit else None)
    sys.exit(0)
if PREVIEW:
    outname = outname.replace(".png", "-preview.png")
scene.render.filepath = os.path.join(OUT, outname)
bpy.ops.render.render(write_still=True)
print("DONE", MODE, scene.render.filepath, ENGINE)
