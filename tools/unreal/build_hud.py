"""WBP_HUD: the helmet visor display (layout only; Content/Python/marswalk_hud.py drives it every frame).

    python3 tools/make_ui.py && python3 tools/ue.py tools/unreal/build_hud.py

Also imports the HUD images and suit sounds, and re-points BP_Marswalk's BeginPlay at the rebuilt widget.
"""
import json
import os

import unreal
from editor_toolset.toolsets.blueprint import BlueprintTools as B

from common import GAME, REPO, assets, import_file, load, save_all

PATH = f"{GAME}/WBP_HUD"
CYAN, AMBER, WHITE, DIM = (0.45, 0.9, 1.0, 1), (1.0, 0.72, 0.35, 1), (1, 1, 1, 0.95), (1, 1, 1, 0.65)
VARS = []


def tool(name, **kw):
    r = unreal.ToolsetRegistry.execute_tool("UMGToolSet.UMGToolSet", name, json.dumps(kw))
    if not r.is_complete:
        raise RuntimeError(f"{name} did not complete synchronously")
    if r.error:
        raise RuntimeError(f"{name}: {r.error}")
    return json.loads(r.value) if r.value else {}


def ref(p):
    return {"refPath": p}


def add(cls, name, parent=None):
    kw = {"widgetBlueprint": ref(PATH + ".WBP_HUD"), "widgetClass": ref(cls.static_class().get_path_name()), "widgetDisplayName": name}
    if parent is not None:
        kw["parentWidget"] = ref(parent.get_path_name())
    rv = tool("AddWidget", **kw)["returnValue"]

    def resolve(v):
        p = v.get("refPath") if isinstance(v, dict) else v
        return unreal.find_object(None, p) if p and p != "None" else None
    VARS.append(name)
    return resolve(rv["widget"]), resolve(rv.get("slot"))


def place(slot, x, y, w, h, anchor=(0, 0), align=(0, 0), auto=False, fill=False):
    ld = slot.get_editor_property("layout_data")
    ld.set_editor_property("anchors", unreal.Anchors(minimum=unreal.Vector2D(0, 0) if fill else unreal.Vector2D(*anchor),
                                                     maximum=unreal.Vector2D(1, 1) if fill else unreal.Vector2D(*anchor)))
    ld.set_editor_property("offsets", unreal.Margin(x, y, w, h))
    ld.set_editor_property("alignment", unreal.Vector2D(*align))
    slot.set_editor_property("layout_data", ld)
    slot.set_editor_property("auto_size", auto)


def text(name, parent, s="", size=16, color=WHITE, bold=False, wrap=False, center=False):
    w, slot = add(unreal.TextBlock, name, parent)
    w.set_editor_property("text", unreal.Text(s))
    f = w.get_editor_property("font")
    f.set_editor_property("size", size)
    f.set_editor_property("typeface_font_name", "Bold" if bold else "Regular")
    w.set_editor_property("font", f)
    w.set_editor_property("color_and_opacity", unreal.SlateColor(unreal.LinearColor(*color)))
    w.set_editor_property("shadow_offset", unreal.Vector2D(1.5, 1.5))          # readable against a bright dusty sky
    w.set_editor_property("shadow_color_and_opacity", unreal.LinearColor(0, 0, 0, 0.75))
    w.set_editor_property("auto_wrap_text", wrap)
    if center:
        w.set_editor_property("justification", unreal.TextJustify.CENTER)
    return w, slot


def image(name, parent, tex, w, h):
    img, slot = add(unreal.Image, name, parent)
    br = img.get_editor_property("brush")
    br.set_editor_property("resource_object", tex)
    sz = unreal.DeprecateSlateVector2D()
    sz.set_editor_property("x", float(w)); sz.set_editor_property("y", float(h))
    br.set_editor_property("image_size", sz)
    img.set_editor_property("brush", br)
    return img, slot


def panel(name, parent, alpha=0.5):
    b, s = add(unreal.Border, name, parent)
    b.set_editor_property("brush_color", unreal.LinearColor(0.01, 0.015, 0.02, alpha))
    b.set_editor_property("padding", unreal.Margin(18, 12, 18, 14))
    return b, s


def button(name, parent, label, size=15):
    """Clickable; marswalk_hud polls is_pressed(). Not focusable, so keys keep going to the walker."""
    b, s = add(unreal.Button, name, parent)
    b.set_editor_property("background_color", unreal.LinearColor(0.1, 0.45, 0.6, 0.95))
    b.set_editor_property("is_focusable", False)
    if s is not None:
        s.set_editor_property("padding", unreal.Margin(0, 8, 10, 0))
    text("Txt" + name[3:] + "Btn", b, label, size, WHITE, bold=True)
    return b


def bar(name, parent, x, y, w, color, anchor, align):
    p, s = add(unreal.ProgressBar, name, parent)
    p.set_editor_property("percent", 1.0)
    p.set_editor_property("fill_color_and_opacity", unreal.LinearColor(*color))
    place(s, x, y, w, 9, anchor=anchor, align=align)
    return p


def ui_texture(file, name):
    path = f"{GAME}/UI/{name}"
    if assets.does_asset_exist(path):
        assets.delete_asset(path)
    t = import_file(os.path.join(REPO, "data", "ui", file), f"{GAME}/UI", name)
    t.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
    t.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
    assets.save_loaded_asset(t)
    return t


def sounds():
    for name in ("breath", "hum", "step", "drill", "beep", "alarm", "tick"):
        s = import_file(os.path.join(REPO, "data", "audio", f"{name}.wav"), f"{GAME}/Audio", f"S_{name}")
        s.set_editor_property("looping", name in ("breath", "hum", "drill", "alarm"))
        assets.save_loaded_asset(s)


def main():
    visor, arrow = ui_texture("visor.png", "T_Visor"), ui_texture("arrow.png", "T_Arrow")
    sounds()
    if assets.does_asset_exist(PATH):
        assets.delete_asset(PATH)
    tool("CreateWidgetBlueprint", folderPath=GAME, assetName="WBP_HUD", parentClass=ref("/Script/UMG.UserWidget"))
    root, _ = add(unreal.CanvasPanel, "Root")
    L, T = 120, 84                      # inner edge of the helmet rim at 1920x1080

    _, s = image("ImgVisor", root, visor, 1920, 1080)
    place(s, 0, 0, 0, 0, fill=True)

    # Top centre: where to go. The arrow turns toward the next stop.
    _, s = image("ImgArrow", root, arrow, 64, 64)
    place(s, 0, 64, 64, 64, anchor=(0.5, 0), align=(0.5, 0))
    _, s = text("TxtDist", root, "000 m", 30, CYAN, bold=True, center=True)
    place(s, 0, 132, 600, 0, anchor=(0.5, 0), align=(0.5, 0), auto=True)
    _, s = text("TxtNav", root, "NEXT", 15, AMBER, bold=True, center=True)
    place(s, 0, 176, 900, 0, anchor=(0.5, 0), align=(0.5, 0), auto=True)

    # Top left: mission checklist and clocks.
    box, s = panel("ObjBox", root)
    place(s, L, T, 430, 0, auto=True)
    vb, _ = add(unreal.VerticalBox, "ObjStack", box)
    text("TxtTitle", vb, "EVA-1  BOXWORK RIDGES, MOUNT SHARP", 13, AMBER, bold=True)
    text("TxtObj", vb, "objectives", 15, WHITE)
    text("TxtClock", vb, "clock", 14, DIM)

    # Bottom left: suit.
    box, s = panel("SuitBox", root)
    place(s, L, -T, 360, 196, anchor=(0, 1), align=(0, 1))
    cv, _ = add(unreal.CanvasPanel, "SuitCanvas", box)
    for i, (key, label, color) in enumerate((("O2", "OXYGEN", (0.35, 0.85, 1.0, 1)), ("Dose", "DOSE", (0.55, 1.0, 0.55, 1)),
                                             ("Day", "DAYLIGHT", (1.0, 0.8, 0.35, 1)))):
        _, s = text(f"Txt{key}", cv, label, 13, WHITE, bold=True)
        place(s, 0, i * 44, 320, 0, auto=True)
        bar(f"Bar{key}", cv, 0, i * 44 + 23, 320, color, (0, 0), (0, 0))
    _, s = text("TxtStatus", cv, "status", 12, DIM)
    place(s, 0, 136, 320, 0, auto=True)

    # Bottom centre: what E does here, with progress.
    _, s = text("TxtPrompt", root, "", 18, WHITE, bold=True, center=True)
    place(s, 0, -210, 900, 0, anchor=(0.5, 1), align=(0.5, 1), auto=True)
    bar("BarAction", root, 0, -190, 380, (1.0, 0.75, 0.3, 1), (0.5, 1), (0.5, 1))

    # Warning banner.
    _, s = text("TxtWarn", root, "", 20, (1.0, 0.2, 0.14, 1), bold=True, center=True)
    place(s, 0, 0, 1100, 0, anchor=(0.5, 0.36), align=(0.5, 0.5), auto=True)

    # Right: Curiosity's photo of this stop / the habitat plan card.
    card, s = panel("StopCard", root, 0.62)
    place(s, -L, T, 400, 0, anchor=(1, 0), align=(1, 0), auto=True)
    cv2, _ = add(unreal.VerticalBox, "StopStack", card)
    for k in range(5):
        img, _ = image(f"ImgStop{k}", cv2, load(f"{GAME}/Textures/T_Stop{k}"), 364, 364)
        img.set_visibility(unreal.SlateVisibility.COLLAPSED)
    text("TxtStop", cv2, "Stop", 13, WHITE, wrap=True)
    plan, s = panel("PlanCard", root, 0.7)
    place(s, -L, T, 520, 0, anchor=(1, 0), align=(1, 0), auto=True)
    pv, _ = add(unreal.VerticalBox, "PlanStack", plan)
    text("TxtStats", pv, "Route", 15)
    ph, _ = add(unreal.HorizontalBox, "PlanBtns", pv)
    button("BtnBack", ph, "BACK TO SUIT VIEW  [M]")
    button("BtnLayer", ph, "NEXT DATA LAYER  [L]")

    # Centre: mission brief before the airlock opens, debrief at the end.
    big, s = panel("BigCard", root, 0.82)
    place(s, 0, 0, 900, 0, anchor=(0.5, 0.5), align=(0.5, 0.5), auto=True)
    bv, _ = add(unreal.VerticalBox, "BigStack", big)
    text("TxtBigTitle", bv, "MARSWALK", 30, AMBER, bold=True)
    text("TxtBig", bv, "brief", 17, WHITE, wrap=True)
    bh, _ = add(unreal.HorizontalBox, "BigBtns", bv)
    button("BtnStart", bh, "OPEN THE AIRLOCK  [Enter]", 18)
    button("BtnMap", bh, "MAP  [M]", 18)
    button("BtnEnd", bh, "END MISSION: DEBRIEF  [X]", 18)

    _, s = text("TxtKeys", root, "", 15, WHITE, bold=True, center=True)      # always on screen: which key does what
    place(s, 0, -T - 52, 1300, 0, anchor=(0.59, 1), align=(0.5, 1), auto=True)   # right of centre: clear of the suit box
    kh, s = add(unreal.HorizontalBox, "KeyBtns", root)
    place(s, 0, -T, 900, 0, anchor=(0.59, 1), align=(0.5, 1), auto=True)
    for n, label in (("Photo", "PHOTO [F]"), ("HudMap", "MAP [M]"), ("HudLayer", "DATA LAYERS [L]"), ("Restart", "RESTART [R]")):
        button("Btn" + n, kh, label, 13)

    _, s = image("ImgCursor", root, arrow, 26, 26)     # our own pointer, drawn last: the OS one does not show in the game window
    place(s, 0, 0, 26, 26)

    wbp = load(PATH)
    for n in VARS:
        w = unreal.find_object(None, f"{PATH}.WBP_HUD:WidgetTree.{n}")
        tool("ToggleWidgetAsVariable", widgetBlueprint=ref(PATH + ".WBP_HUD"), widget=ref(w.get_path_name()), bIsVariable=True)
    print("compile:", tool("CompileWidgetBlueprint", widgetBlueprint=ref(PATH + ".WBP_HUD")))
    assets.save_loaded_asset(wbp)

    bp = load(f"{GAME}/BP_Marswalk")       # the old widget class is gone: write BeginPlay again
    B.write_graph_dsl(B.get_graph(bp, "EventGraph"), '''(event EventBeginPlay
  (bind pc (Game|GetPlayerController :PlayerIndex 0))
  (bind hud (UserInterface|CreateWidget :Class "/Game/Marswalk/WBP_HUD.WBP_HUD_C" :OwningPlayer pc))
  (UserInterface|Viewport|AddtoViewport :self hud :ZOrder 0))''')
    B.compile_blueprint(bp)
    assets.save_loaded_asset(bp)
    save_all()
    print("hud ok:", len(VARS), "widgets")


main()
