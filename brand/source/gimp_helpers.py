import math
from gi.repository import Gimp, Gegl, Gio

R_ = Gimp.ChannelOps
Gimp.context_set_antialias(True)
px = Gimp.Unit.pixel()
F = {f.get_name(): f for f in Gimp.fonts_get_list('')}
B = '/home/zodchi/Desktop/Claude/RINNE/brand/'

DARK = dict(c1='#8b5cf6', c2='#ec4899', text='#ece8f6', kanji='#c9b8ff', bg='#0e1016')
LIGHT = dict(c1='#7c3aed', c2='#db2777', text='#1b1e27', kanji='#6d28d9', bg='#f4f5f9')
A6 = (-90, -30, 30, 90, 150, 210)


def Pc(cx, cy, r, a):
    a = math.radians(a)
    return [cx + r * math.cos(a), cy + r * math.sin(a)]


def doc(w, h, bg=None, bgname='Background (hide for transparent)'):
    im = Gimp.Image.new(w, h, Gimp.ImageBaseType.RGB)
    if bg:
        b = Gimp.Layer.new(im, bgname, w, h, Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
        im.insert_layer(b, None, 0)
        Gimp.context_set_foreground(Gegl.Color.new(bg))
        b.edit_fill(Gimp.FillType.FOREGROUND)
    return im


def lay(im, name):
    l = Gimp.Layer.new(im, name, im.get_width(), im.get_height(), Gimp.ImageType.RGBA_IMAGE, 100, Gimp.LayerMode.NORMAL)
    im.insert_layer(l, None, 0)
    return l


def fill2(layer, c1, c2, x1, y1, x2, y2):
    Gimp.context_set_foreground(Gegl.Color.new(c1))
    Gimp.context_set_background(Gegl.Color.new(c2))
    Gimp.context_set_gradient_fg_bg_rgb()
    layer.edit_gradient_fill(Gimp.GradientType.LINEAR, 0, False, 1, 0, True, x1, y1, x2, y2)


def arrow_arc(im, op, cx, cy, R, W, HW, a_tail, a_base, a_tip, n=96):
    pts = [Pc(cx, cy, R + W, a_tail + (a_base - a_tail) * i / n) for i in range(n + 1)] + \
          [Pc(cx, cy, R - W, a_tail + (a_base - a_tail) * i / n) for i in range(n, -1, -1)]
    im.select_polygon(op, [c for p in pts for c in p])
    tx, ty = Pc(cx, cy, R, a_tail)
    im.select_ellipse(R_.ADD, tx - W, ty - W, 2 * W, 2 * W)
    m = 32
    outer = [Pc(cx, cy, R + HW * (1 - i / m), a_base + (a_tip - a_base) * i / m) for i in range(m + 1)]
    inner = [Pc(cx, cy, R - HW * (1 - i / m), a_base + (a_tip - a_base) * i / m) for i in range(m, -1, -1)]
    im.select_polygon(R_.ADD, [c for p in outer + inner for c in p])


def temple(im, layer, cx, cy, s, c1, c2, simple=False):
    """The Rinne wheel. Full version: arrow rim, 12 beads, banded inner ring, 6 spokes, hub.
    Simple version (for <=48 px): heavier strokes, no beads or bands."""
    P = lambda r, a: Pc(cx, cy, r * s, a)

    def C(op, r, x=None, y=None):
        x = cx if x is None else x
        y = cy if y is None else y
        im.select_ellipse(op, x - r * s, y - r * s, 2 * r * s, 2 * r * s)

    def spoke(a, r0, r1, w0, w1):
        n0 = math.radians(a + 90)
        c, sn = math.cos(n0), math.sin(n0)
        x0, y0 = P(r0, a)
        x1, y1 = P(r1, a)
        w0 *= s
        w1 *= s
        im.select_polygon(R_.ADD, [x0 + c * w0 / 2, y0 + sn * w0 / 2, x1 + c * w1 / 2, y1 + sn * w1 / 2,
                                   x1 - c * w1 / 2, y1 - sn * w1 / 2, x0 - c * w0 / 2, y0 - sn * w0 / 2])

    def plate(a, ri, ro, hd, n=24):
        pts = [P(ro, a - hd + 2 * hd * i / n) for i in range(n + 1)] + [P(ri, a + hd - 2 * hd * i / n) for i in range(n + 1)]
        im.select_polygon(R_.ADD, [c for p in pts for c in p])

    if not simple:
        arrow_arc(im, R_.REPLACE, cx, cy, 515 * s, 26 * s, 62 * s, -52, 280, 296)
        for k in range(12):
            C(R_.ADD, 12, *P(432, -90 + 30 * k + 15))
        C(R_.ADD, 400); C(R_.SUBTRACT, 380)
        for a in A6:
            spoke(a, 110, 385, 16, 40)
        for a in A6:
            plate(a, 373, 407, 11)
        C(R_.ADD, 118); C(R_.SUBTRACT, 80); C(R_.ADD, 36)
    else:
        arrow_arc(im, R_.REPLACE, cx, cy, 500 * s, 48 * s, 110 * s, -48, 270, 298)
        C(R_.ADD, 380); C(R_.SUBTRACT, 330)
        for a in A6:
            spoke(a, 120, 350, 44, 64)
        C(R_.ADD, 150); C(R_.SUBTRACT, 82)
    fill2(layer, c1, c2, cx - 515 * s, cy - 515 * s, cx + 515 * s, cy + 515 * s)
    Gimp.Selection.none(im)


def txt(im, s, font, size, spacing, color, y, name, cx=None, x=None, line_spacing=None):
    t = Gimp.TextLayer.new(im, s, F[font], size, px)
    im.insert_layer(t, None, 0)
    t.set_letter_spacing(spacing)
    t.set_color(Gegl.Color.new(color))
    t.set_antialias(True)
    t.set_name(name)
    if line_spacing is not None:
        t.set_line_spacing(line_spacing)
    if x is None:
        x = (cx if cx is not None else im.get_width() / 2) - t.get_width() / 2
    t.set_offsets(int(x), int(y))
    return t


def hline(im, layer, x, y, length, th, color, fade_left):
    """A thin line that fades to transparent toward its outer end."""
    Gimp.context_set_gradient_fg_transparent()
    im.select_rectangle(R_.REPLACE, x, y - th / 2, length, th)
    Gimp.context_set_foreground(Gegl.Color.new(color))
    if fade_left:
        layer.edit_gradient_fill(Gimp.GradientType.LINEAR, 0, False, 1, 0, True, x + length, 0, x, 0)
    else:
        layer.edit_gradient_fill(Gimp.GradientType.LINEAR, 0, False, 1, 0, True, x, 0, x + length, 0)
    Gimp.Selection.none(im)


def save(im, path):
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, im, Gio.File.new_for_path(B + path), None)


def png(im, path, bg=True, w=None):
    d = im.duplicate()
    if not bg:
        for l in d.get_layers():
            if l.get_name().startswith('Background'):
                d.remove_layer(l)
    d.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
    if w:
        d.scale(w, int(round(w * im.get_height() / im.get_width())))
    Gimp.file_save(Gimp.RunMode.NONINTERACTIVE, d, Gio.File.new_for_path(B + path), None)
    d.delete()


def mark_doc(c1, c2, simple=False, size=1200, bg='#0e1016'):
    im = doc(size, size, bg)
    l = lay(im, 'Mark')
    s = (size / 2 - 50) / (610 if simple else 580)
    temple(im, l, size / 2, size / 2, s, c1, c2, simple)
    return im
