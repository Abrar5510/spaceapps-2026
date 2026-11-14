"""Import the baked site textures and build the terrain layer material + parameter collection."""
import os
import sys

import unreal

from common import GAME, SITE, assets, import_file, load, mel, save_all

TEX = f"{GAME}/Textures"


def texture(file, name, srgb=True, normal=False, group=unreal.TextureGroup.TEXTUREGROUP_WORLD, max_size=0):
    if assets.does_asset_exist(f"{TEX}/{name}") and "--reimport" not in sys.argv:
        return load(f"{TEX}/{name}")
    t = import_file(os.path.join(SITE, file), TEX, name)
    t.set_editor_property("srgb", srgb)
    t.set_editor_property("lod_group", group)
    if normal:
        t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        t.set_editor_property("flip_green_channel", True)  # image rows go down (+Y in UE), so flip G
    if max_size:
        t.set_editor_property("max_texture_size", max_size)
    t.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP if not normal else unreal.TextureAddress.TA_WRAP)
    t.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP if not normal else unreal.TextureAddress.TA_WRAP)
    assets.save_loaded_asset(t)
    return t


def mpc():
    path = f"{GAME}/MPC_Marswalk"
    if assets.does_asset_exist(path):
        c = load(path)
    else:
        c = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            "MPC_Marswalk", GAME, unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    p = unreal.CollectionScalarParameter()
    p.set_editor_property("parameter_name", "Layer")
    p.set_editor_property("default_value", 0.0)
    c.set_editor_property("scalar_parameters", [p])
    assets.save_loaded_asset(c)
    return c


def terrain_material(ortho, slope, thermal, hazard, detail, collection, n):
    path = f"{GAME}/M_Terrain"
    if assets.does_asset_exist(path):
        assets.delete_asset(path)
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset("M_Terrain", GAME, unreal.Material, unreal.MaterialFactoryNew())
    E = unreal.MaterialExpression

    def node(cls, x, y):
        return mel.create_material_expression(m, cls, x, y)

    # Site UV: Landscape vertex i sits at i*100 cm; the textures cover cells -0.5..n-0.5.
    wp = node(unreal.MaterialExpressionWorldPosition, -1600, 0)
    xy = node(unreal.MaterialExpressionComponentMask, -1400, 0)
    xy.set_editor_property("r", True); xy.set_editor_property("g", True)
    mel.connect_material_expressions(wp, "", xy, "")
    k = node(unreal.MaterialExpressionConstant, -1400, 120)
    k.set_editor_property("r", 1.0 / (100.0 * n))
    off = node(unreal.MaterialExpressionConstant, -1400, 200)
    off.set_editor_property("r", 0.5 / n)
    mul = node(unreal.MaterialExpressionMultiply, -1200, 0)
    mel.connect_material_expressions(xy, "", mul, "A"); mel.connect_material_expressions(k, "", mul, "B")
    uv = node(unreal.MaterialExpressionAdd, -1050, 0)
    mel.connect_material_expressions(mul, "", uv, "A"); mel.connect_material_expressions(off, "", uv, "B")

    def sample(tex, y):
        s = node(unreal.MaterialExpressionTextureSample, -800, y)
        s.set_editor_property("texture", tex)
        s.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
        mel.connect_material_expressions(uv, "", s, "UVs")
        return s

    s_ortho, s_slope, s_th, s_hz = sample(ortho, -400), sample(slope, -100), sample(thermal, 200), sample(hazard, 500)

    layer = node(unreal.MaterialExpressionCollectionParameter, -800, 800)
    layer.set_editor_property("collection", collection)
    layer.set_editor_property("parameter_name", "Layer")

    def step(sub, y):  # saturate(Layer - sub)
        c = node(unreal.MaterialExpressionConstant, -600, y)
        c.set_editor_property("r", float(sub))
        d = node(unreal.MaterialExpressionSubtract, -450, y)
        mel.connect_material_expressions(layer, "", d, "A"); mel.connect_material_expressions(c, "", d, "B")
        s = node(unreal.MaterialExpressionSaturate, -300, y)
        mel.connect_material_expressions(d, "", s, "")
        return s

    def lerp(a, b, alpha, y):
        l = node(unreal.MaterialExpressionLinearInterpolate, -100, y)
        mel.connect_material_expressions(a, "RGB", l, "A") if isinstance(a, unreal.MaterialExpressionTextureSample) else mel.connect_material_expressions(a, "", l, "A")
        mel.connect_material_expressions(b, "RGB", l, "B")
        mel.connect_material_expressions(alpha, "", l, "Alpha")
        return l

    pw = node(unreal.MaterialExpressionPower, -550, -400)
    mel.connect_material_expressions(s_ortho, "RGB", pw, "Base")
    pw.set_editor_property("const_exponent", 1.35)
    dim = node(unreal.MaterialExpressionMultiply, -400, -400)
    mel.connect_material_expressions(pw, "", dim, "A")
    dim.set_editor_property("const_b", 0.8)
    c1 = lerp(dim, s_slope, step(0, 800), -200)
    c2 = lerp(c1, s_th, step(1, 950), 0)
    c3 = lerp(c2, s_hz, step(2, 1100), 200)
    mel.connect_material_property(c3, "", unreal.MaterialProperty.MP_BASE_COLOR)

    # Tiling detail normal (1.6 m tile), faded out with distance so far terrain keeps the DTM shading.
    dk = node(unreal.MaterialExpressionConstant, -1200, 1400)
    dk.set_editor_property("r", 1.0 / 160.0)
    duv = node(unreal.MaterialExpressionMultiply, -1050, 1400)
    mel.connect_material_expressions(xy, "", duv, "A"); mel.connect_material_expressions(dk, "", duv, "B")
    dn = node(unreal.MaterialExpressionTextureSample, -800, 1400)
    dn.set_editor_property("texture", detail)
    dn.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    mel.connect_material_expressions(duv, "", dn, "UVs")
    flat = node(unreal.MaterialExpressionConstant3Vector, -800, 1650)
    flat.set_editor_property("constant", unreal.LinearColor(0, 0, 1, 0))
    dist = node(unreal.MaterialExpressionPixelDepth, -800, 1750)
    fade_k = node(unreal.MaterialExpressionConstant, -800, 1850)
    fade_k.set_editor_property("r", 1.0 / 2500.0)
    fd = node(unreal.MaterialExpressionMultiply, -600, 1750)
    mel.connect_material_expressions(dist, "", fd, "A"); mel.connect_material_expressions(fade_k, "", fd, "B")
    fadd = node(unreal.MaterialExpressionAdd, -520, 1750)
    mel.connect_material_expressions(fd, "", fadd, "A")
    fadd.set_editor_property("const_b", 0.45)  # keep the grit subtle even underfoot
    fs = node(unreal.MaterialExpressionSaturate, -450, 1750)
    mel.connect_material_expressions(fadd, "", fs, "")
    nl = node(unreal.MaterialExpressionLinearInterpolate, -200, 1500)
    mel.connect_material_expressions(dn, "RGB", nl, "A"); mel.connect_material_expressions(flat, "", nl, "B")
    mel.connect_material_expressions(fs, "", nl, "Alpha")
    mel.connect_material_property(nl, "", unreal.MaterialProperty.MP_NORMAL)

    rough = node(unreal.MaterialExpressionConstant, -200, 1900)
    rough.set_editor_property("r", 0.93)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    spec = node(unreal.MaterialExpressionConstant, -200, 2000)
    spec.set_editor_property("r", 0.3)
    mel.connect_material_property(spec, "", unreal.MaterialProperty.MP_SPECULAR)

    mel.recompile_material(m)
    assets.save_loaded_asset(m)
    return m


def emissive_material(name, color, strength):
    path = f"{GAME}/{name}"
    if assets.does_asset_exist(path):
        assets.delete_asset(path)
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, GAME, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    c = mel.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -400, 0)
    c.set_editor_property("constant", unreal.LinearColor(color[0] * strength, color[1] * strength, color[2] * strength, 1))
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    assets.save_loaded_asset(m)
    return m


def main():
    from common import site
    n = site()["samples"]
    ortho = texture("ortho.png", "T_Ortho", max_size=8192)
    slope = texture("layer_slope.png", "T_LayerSlope")
    thermal = texture("layer_thermal.png", "T_LayerThermal")
    hazard = texture("layer_hazard.png", "T_LayerHazard")
    detail = texture("detail_normal.png", "T_DetailNormal", srgb=False, normal=True)
    for i in range(5):
        texture(f"photos/stop{i}.jpg", f"T_Stop{i}", group=unreal.TextureGroup.TEXTUREGROUP_UI)
    texture("route_map.png", "T_RouteMap", group=unreal.TextureGroup.TEXTUREGROUP_UI)
    c = mpc()
    terrain_material(ortho, slope, thermal, hazard, detail, c, n)
    emissive_material("M_Route", (0.25, 0.85, 1.0), 900.0)  # nits: must compete with ~55k lux sunlight
    emissive_material("M_Stop", (1.0, 0.75, 0.2), 4000.0)
    save_all()
    print("assets ok:", sorted(assets.list_assets(GAME, recursive=True)))


main()
