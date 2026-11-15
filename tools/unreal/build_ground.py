"""M_Terrain v2: HiRISE colour at site scale, scanned sand / regolith / bedrock detail at walking scale.

    python3 tools/ue.py tools/unreal/build_ground.py

The HiRISE orthoimage sets the colour and brightness everywhere (so the map stays real data). Within ~40 m of
the walker, three Poly Haven surface scans add what a 25 cm/px image cannot: grains, pebbles and fractures.
Which scan goes where is decided by the data: bedrock on steep or blocky ground (DTM slope and roughness),
sand where HiRISE is dark (basaltic sand), pebbly regolith elsewhere.
"""
import json
import os

import unreal

from common import GAME, REPO, SITE, assets, import_file, load, mel, save_all, site
from graph import Graph, ST

PH = os.path.join(REPO, "data", "assets", "polyhaven", "textures")
TEX = f"{GAME}/Ground"
SETS = {"sand": "gravelly_sand", "reg": "moon_dusted_02", "rock": "dry_riverbed_rock"}
NEAR_CM, FAR_CM, MICRO_CM = 260.0, 1900.0, 70.0   # tile sizes of the three detail scales


def ground_texture(name, kind):
    path = f"{TEX}/T_{name}"
    if assets.does_asset_exist(path):
        return load(path)
    t = import_file(os.path.join(PH, f"{name}.jpg"), TEX, f"T_{name}")
    t.set_editor_property("srgb", kind == "color")
    if kind == "normal":
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
    if kind == "mask":
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
    assets.save_loaded_asset(t)
    return t


def build(collection):
    n_site = site()["samples"]
    means = json.load(open(os.path.join(PH, "means.json")))
    T = {k: {m: ground_texture(f"{name}_{m}", kind) for m, kind in (("Diffuse", "color"), ("nor_dx", "normal"), ("arm", "mask"))}
         for k, name in SETS.items()}
    site_tex = {k: load(f"{GAME}/Textures/{v}") for k, v in
                {"ortho": "T_Ortho", "slope": "T_LayerSlope", "thermal": "T_LayerThermal", "hazard": "T_LayerHazard"}.items()}
    rough_path = f"{GAME}/Textures/T_Rough"
    if not assets.does_asset_exist(rough_path):
        t = import_file(os.path.join(SITE, "rough.png"), f"{GAME}/Textures", "T_Rough")
        t.set_editor_property("srgb", False)
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
        assets.save_loaded_asset(t)
    rough_tex = load(rough_path)

    path = f"{GAME}/M_Terrain"
    m = load(path)
    mel.delete_all_material_expressions(m)   # rebuild in place: the terrain tiles keep their material reference
    m.set_editor_property("tangent_space_normal", False)
    g = Graph(m)

    wp = g.node(unreal.MaterialExpressionWorldPosition)
    xy = g.mask(wp, "rg")
    uv_site = g.add(g.mul(xy, 1.0 / (100.0 * n_site)), 0.5 / n_site)
    uv_near, uv_far = g.mul(xy, 1.0 / NEAR_CM), g.mul(xy, 1.0 / FAR_CM)
    uv_micro = g.mul(xy, 1.0 / MICRO_CM)

    ortho = g.tex(site_tex["ortho"], uv_site, wrap=False)
    pw =g.node(unreal.MaterialExpressionPower, const_exponent=1.35)
    g.link((ortho, "RGB"), pw, "Base")
    macro = g.mul(pw, 0.8)

    # Which scan where.
    vn = g.node(unreal.MaterialExpressionVertexNormalWS)
    nz = g.mask(vn, "b")
    steep = g.ramp(g.one_minus(nz), 0.05, 0.13)                       # ~18 deg -> ~30 deg
    blocky = g.ramp((g.tex(rough_tex, uv_site, ST.SAMPLERTYPE_LINEAR_GRAYSCALE, wrap=False), "R"), 0.08, 0.2)  # 0.2-0.5 m relief
    w_rock = g.vmax(steep, blocky)
    lum = g.node(unreal.MaterialExpressionDesaturation)
    g.link((ortho, "RGB"), lum, "")
    w_sand = g.mul(g.one_minus(g.ramp(g.mask(lum, "r"), 0.07, 0.11)), g.one_minus(w_rock))   # HiRISE-dark = basaltic sand

    def blend3(v):  # v: dict of sand / reg / rock values
        return g.lerp(g.lerp(v["reg"], v["sand"], w_sand), v["rock"], w_rock)

    depth = g.node(unreal.MaterialExpressionPixelDepth)
    w_near = g.one_minus(g.ramp(depth, 1200.0, 4500.0))
    w_far = g.one_minus(g.ramp(depth, 12000.0, 45000.0))
    w_micro = g.one_minus(g.ramp(depth, 250.0, 900.0))       # grains and pebbles at the walker's boots

    def detail(uv, with_arm):
        col, nor, arm = {}, {}, {}
        for k, name in SETS.items():
            d = g.tex(T[k]["Diffuse"], uv)
            mean = means[name]
            col[k] = g.mul((d, "RGB"), g.c3(1 / mean[0], 1 / mean[1], 1 / mean[2]))   # scan / its mean: detail only
            nor[k] = (g.tex(T[k]["nor_dx"], uv, ST.SAMPLERTYPE_NORMAL), "RGB")
            if with_arm:
                arm[k] = (g.tex(T[k]["arm"], uv, ST.SAMPLERTYPE_MASKS), "RGB")
        return blend3(col), blend3(nor), blend3(arm) if with_arm else None

    c_near, n_near, arm_near = detail(uv_near, True)
    c_far, n_far, _ = detail(uv_far, False)
    c_micro, n_micro, _ = detail(uv_micro, False)

    one = g.c3(1, 1, 1)
    # Keep the scans' own hue a little muted so HiRISE stays in charge of colour.
    def soften(c, amount):
        d = g.node(unreal.MaterialExpressionDesaturation)
        g.link(c, d, "")
        return g.lerp(d, c, amount)
    shade = g.mul(g.lerp(one, soften(c_near, 0.5), w_near), g.lerp(one, soften(c_far, 0.35), g.mul(w_far, 0.75)))
    shade = g.mul(shade, g.lerp(one, soften(c_micro, 0.4), g.mul(w_micro, 0.7)))
    surface = g.mul(macro, shade)

    # Data layers on top (L key): slope, thermal inertia, hazards.
    layer = g.node(unreal.MaterialExpressionCollectionParameter, collection=collection, parameter_name="Layer")
    out = surface
    for i, k in enumerate(("slope", "thermal", "hazard")):
        out = g.lerp(out, (g.tex(site_tex[k], uv_site, wrap=False), "RGB"), g.sat(g.sub(layer, float(i))))
    mel.connect_material_property(out, "", unreal.MaterialProperty.MP_BASE_COLOR)

    # World-space normal: DTM normal bent by the scans (texture U = east, V = south, DirectX green).
    bend = g.add(g.mul(g.mask(n_near, "rg"), g.mul(w_near, 1.5)), g.mul(g.mask(n_far, "rg"), g.mul(w_far, 0.9)))
    bend = g.add(bend, g.mul(g.mask(n_micro, "rg"), g.mul(w_micro, 1.2)))
    nrm = g.node(unreal.MaterialExpressionNormalize)
    g.link(g.add(vn, g.append(bend, g.node(unreal.MaterialExpressionConstant, r=0.0))), nrm, "")
    mel.connect_material_property(nrm, "", unreal.MaterialProperty.MP_NORMAL)

    mel.connect_material_property(g.lerp(0.92, g.mask(arm_near, "g"), w_near), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(g.lerp(1.0, g.mask(arm_near, "r"), w_near), "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    mel.connect_material_property(g.node(unreal.MaterialExpressionConstant, r=0.25), "", unreal.MaterialProperty.MP_SPECULAR)

    mel.recompile_material(m)
    assets.save_loaded_asset(m)
    print("M_Terrain rebuilt:", g.k, "nodes")


build(load(f"{GAME}/MPC_Marswalk"))
save_all()
