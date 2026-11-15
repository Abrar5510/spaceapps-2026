"""Tiny wrapper over MaterialEditingLibrary for building material graphs from Python."""
import unreal

from common import mel

SM = unreal.SamplerSourceMode
ST = unreal.MaterialSamplerType


class Graph:
    """Tiny wrapper over MaterialEditingLibrary: values are nodes or (node, output) pairs or floats."""

    def __init__(self, material):
        self.m, self.k = material, 0

    def node(self, cls, **props):
        e = mel.create_material_expression(self.m, cls, -2400 + (self.k % 12) * 180, (self.k // 12) * 160)
        self.k += 1
        for k, v in props.items():
            e.set_editor_property(k, v)
        return e

    def link(self, v, node, pin):
        e, o = v if isinstance(v, tuple) else (v, "")
        mel.connect_material_expressions(e, o, node, pin)

    def op(self, cls, a, b):
        n = self.node(cls)
        for v, pin, prop in ((a, "A", "const_a"), (b, "B", "const_b")):
            if isinstance(v, (int, float)):
                n.set_editor_property(prop, float(v))
            else:
                self.link(v, n, pin)
        return n

    def mul(self, a, b): return self.op(unreal.MaterialExpressionMultiply, a, b)
    def add(self, a, b): return self.op(unreal.MaterialExpressionAdd, a, b)
    def sub(self, a, b): return self.op(unreal.MaterialExpressionSubtract, a, b)
    def div(self, a, b): return self.op(unreal.MaterialExpressionDivide, a, b)
    def vmax(self, a, b): return self.op(unreal.MaterialExpressionMax, a, b)

    def lerp(self, a, b, t):
        n = self.node(unreal.MaterialExpressionLinearInterpolate)
        for v, pin, prop in ((a, "A", "const_a"), (b, "B", "const_b"), (t, "Alpha", "const_alpha")):
            if isinstance(v, (int, float)):
                n.set_editor_property(prop, float(v))
            else:
                self.link(v, n, pin)
        return n

    def sat(self, a):
        n = self.node(unreal.MaterialExpressionSaturate)
        self.link(a, n, "")
        return n

    def ramp(self, a, lo, hi):
        """saturate((a - lo) / (hi - lo))"""
        return self.sat(self.mul(self.sub(a, lo), 1.0 / (hi - lo)))

    def one_minus(self, a):
        n = self.node(unreal.MaterialExpressionOneMinus)
        self.link(a, n, "")
        return n

    def mask(self, a, ch="rg"):
        n = self.node(unreal.MaterialExpressionComponentMask, **{c: c in ch for c in "rgba"})
        self.link(a, n, "")
        return n

    def c3(self, r, g, b):
        return self.node(unreal.MaterialExpressionConstant3Vector, constant=unreal.LinearColor(r, g, b, 0))

    def append(self, a, b):
        n = self.node(unreal.MaterialExpressionAppendVector)
        self.link(a, n, "A"); self.link(b, n, "B")
        return n

    def tex(self, texture, uv, kind=ST.SAMPLERTYPE_COLOR, wrap=True):
        n = self.node(unreal.MaterialExpressionTextureSample, texture=texture, sampler_type=kind,
                      sampler_source=SM.SSM_WRAP_WORLD_GROUP_SETTINGS if wrap else SM.SSM_CLAMP_WORLD_GROUP_SETTINGS)
        self.link(uv, n, "UVs")
        return n
