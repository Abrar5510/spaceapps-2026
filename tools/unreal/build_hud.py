"""WBP_HUD layout (UMG toolset). Logic is written separately by build_hud_logic.py."""
import json

import unreal

from common import GAME, assets, load, save_all

PATH = f"{GAME}/WBP_HUD"


def tool(name, **kw):
    r = unreal.ToolsetRegistry.execute_tool("UMGToolSet.UMGToolSet", name, json.dumps(kw))
    if not r.is_complete:
        raise RuntimeError(f"{name} did not complete synchronously")
    if r.error:
        raise RuntimeError(f"{name}: {r.error}")
    return json.loads(r.value) if r.value else {}


def ref(p):
    return {"refPath": p}


def obj(p):
    return unreal.find_object(None, p)


def add(cls, name, parent=None):
    kw = {"widgetBlueprint": ref(PATH + ".WBP_HUD"), "widgetClass": ref(cls.static_class().get_path_name()), "widgetDisplayName": name}
    if parent is not None:
        kw["parentWidget"] = ref(parent.get_path_name())
    res = tool("AddWidget", **kw)
    rv = res["returnValue"]
    def resolve(v):
        p = v.get("refPath") if isinstance(v, dict) else v
        return obj(p) if p and p != "None" else None
    return resolve(rv["widget"]), resolve(rv.get("slot"))


def text(w, s, size=18, color=(1, 1, 1, 1), bold=False, wrap=False):
    w.set_editor_property("text", unreal.Text(s))
    f = w.get_editor_property("font")
    f.set_editor_property("size", size)
    f.set_editor_property("typeface_font_name", "Bold" if bold else "Regular")
    w.set_editor_property("font", f)
    w.set_editor_property("color_and_opacity", unreal.SlateColor(unreal.LinearColor(*color)))
    w.set_editor_property("auto_wrap_text", wrap)


def place(slot, x, y, w, h, anchor=(0, 0), align=(0, 0), auto=False):
    ld = slot.get_editor_property("layout_data")
    ld.set_editor_property("anchors", unreal.Anchors(minimum=unreal.Vector2D(*anchor), maximum=unreal.Vector2D(*anchor)))
    ld.set_editor_property("offsets", unreal.Margin(x, y, w, h))
    ld.set_editor_property("alignment", unreal.Vector2D(*align))
    slot.set_editor_property("layout_data", ld)
    slot.set_editor_property("auto_size", auto)


def panel(name, parent, alpha=0.55):
    b, s = add(unreal.Border, name, parent)
    b.set_editor_property("brush_color", unreal.LinearColor(0.02, 0.02, 0.03, alpha))
    b.set_editor_property("padding", unreal.Margin(16, 12, 16, 12))
    return b, s


def main():
    if assets.does_asset_exist(PATH):
        assets.delete_asset(PATH)
    tool("CreateWidgetBlueprint", folderPath=GAME, assetName="WBP_HUD", parentClass=ref("/Script/UMG.UserWidget"))
    root, _ = add(unreal.CanvasPanel, "Root")

    # Helmet HUD, top-left: navigation + suit status.
    nav, s = panel("NavBox", root)
    place(s, 24, 24, 470, 0, auto=True)
    vb, _ = add(unreal.VerticalBox, "NavStack", nav)
    t, _ = add(unreal.TextBlock, "TxtTitle", vb)
    text(t, "MARSWALK  |  Boxwork ridges, Mount Sharp", 15, (1.0, 0.75, 0.45, 1), bold=True)
    t, _ = add(unreal.TextBlock, "TxtNav", vb)
    text(t, "Next: Ridge stop  000 deg  000 m", 22, (0.55, 0.92, 1.0, 1), bold=True)
    t, _ = add(unreal.TextBlock, "TxtStatus", vb)
    text(t, "Slope 0 deg | EVA 00:00 | Dose 0.000 mGy", 16)

    # Warning banner, top centre.
    warn, s = add(unreal.TextBlock, "TxtWarn", root)
    text(warn, "", 26, (1.0, 0.25, 0.2, 1), bold=True)
    warn.set_editor_property("justification", unreal.TextJustify.CENTER)
    place(s, 0, 30, 900, 0, anchor=(0.5, 0), align=(0.5, 0), auto=True)

    # Rover photo card, right side (shown near a stop).
    card, s = panel("StopCard", root, 0.7)
    place(s, -24, 24, 460, 0, anchor=(1, 0), align=(1, 0), auto=True)
    cv, _ = add(unreal.VerticalBox, "StopStack", card)
    for k in range(5):  # one image per stop (Curiosity Navcam frame), only the nearby one is shown
        img, _ = add(unreal.Image, f"ImgStop{k}", cv)
        br = img.get_editor_property("brush")
        br.set_editor_property("resource_object", load(f"{GAME}/Textures/T_Stop{k}"))
        sz = unreal.DeprecateSlateVector2D()
        sz.set_editor_property("x", 428.0); sz.set_editor_property("y", 428.0)
        br.set_editor_property("image_size", sz)
        img.set_editor_property("brush", br)
        img.set_visibility(unreal.SlateVisibility.COLLAPSED)
    t, _ = add(unreal.TextBlock, "TxtStop", cv)
    text(t, "Stop", 15, wrap=True)

    # Habitat plan-view card, right side (plan view only).
    plan, s = panel("PlanCard", root, 0.7)
    place(s, -24, 24, 520, 0, anchor=(1, 0), align=(1, 0), auto=True)
    t, _ = add(unreal.TextBlock, "TxtStats", plan)
    text(t, "Route", 16)

    # Key help, bottom-left.
    keys, s = add(unreal.TextBlock, "TxtKeys", root)
    text(keys, "WASD walk | M plan view | L layer | K solar storm | [ ] time of day | T time x10", 14, (1, 1, 1, 0.8))
    place(s, 24, -24, 1100, 0, anchor=(0, 1), align=(0, 1), auto=True)

    wbp = load(PATH)
    for n in ("TxtNav", "TxtStatus", "TxtWarn", "StopCard", "TxtStop", "PlanCard", "TxtStats", "NavBox", "TxtKeys",
              "ImgStop0", "ImgStop1", "ImgStop2", "ImgStop3", "ImgStop4"):
        w = next(x for x in [obj(f"{PATH}.WBP_HUD:WidgetTree.{n}")] if x)
        tool("ToggleWidgetAsVariable", widgetBlueprint=ref(PATH + ".WBP_HUD"), widget=ref(w.get_path_name()), bIsVariable=True)
    print("compile:", tool("CompileWidgetBlueprint", widgetBlueprint=ref(PATH + ".WBP_HUD")))
    assets.save_loaded_asset(wbp)
    save_all()


main()
