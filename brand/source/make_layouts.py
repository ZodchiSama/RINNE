"""Compose Rinne brand layouts from the GIMP-made mark PNGs.

    python -I make_brand.py /path/to/RINNE/brand
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BRAND = Path(sys.argv[1])
CINZEL = '/home/zodchi/.local/share/fonts/Cinzel.ttf'
YUJI = '/home/zodchi/.fonts/Yuji_Boku/YujiBoku-Regular.ttf'
CORM_I = '/home/zodchi/.local/share/fonts/Cormorant-Italic.ttf'

MODES = {
    'dark-mode': dict(text='#ece8f6', kanji='#c9b8ff', c1='#8b5cf6', c2='#ec4899', bg='#0e1016', bg2='#1b1830', sub='#a9a3c2'),
    'light-mode': dict(text='#1b1e27', kanji='#6d28d9', c1='#7c3aed', c2='#db2777', bg='#f4f5f9', bg2='#ece6fb', sub='#5f6577'),
}


def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def font(path, size, var=None):
    f = ImageFont.truetype(path, size)
    if var:
        f.set_variation_by_name(var)
    return f


def text(s, f, color, tracking=0.0, vertical=False):
    """Render text with letter spacing (in em), cropped tightly to its ink."""
    size = f.size
    W = int(size * (len(s) + 1) * (1 + tracking) + size) if not vertical else size * 3
    H = size * 3 if not vertical else int(size * (len(s) + 1) * (1 + tracking) + size)
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y = size, size
    for ch in s:
        d.text((x, y), ch, font=f, fill=color)
        if vertical:
            y += size * (1 + tracking)
        else:
            x += f.getlength(ch) + size * tracking
    return im.crop(im.getbbox())


def fade_line(length, th, color, fade_to_left):
    r, g, b = hex2rgb(color)
    im = Image.new('RGBA', (length, th))
    for x in range(length):
        t = x / (length - 1)
        a = int(255 * (t if fade_to_left else 1 - t))
        for y in range(th):
            im.putpixel((x, y), (r, g, b, a))
    return im


def mark(mode, simple=False):
    name = ('rinne-mark-simple-' if simple else 'rinne-mark-') + mode + '.png'
    im = Image.open(BRAND / 'mark' / name).convert('RGBA')
    return im.crop((50, 50, 1150, 1150))  # centred on the wheel hub; rim radius ~ 0.466 of width


def canvas(w, h, bg=None):
    return Image.new('RGBA', (w, h), hex2rgb(bg) + (255,) if bg else (0, 0, 0, 0))


def paste(dst, src, x, y):
    dst.alpha_composite(src, (int(round(x)), int(round(y))))


def scaled(im, h=None, w=None):
    if h:
        w = round(im.width * h / im.height)
    else:
        h = round(im.height * w / im.width)
    return im.resize((w, h), Image.LANCZOS)


def pad(im, frac=0.08, bg=None):
    p = int(max(im.width, im.height) * frac)
    out = canvas(im.width + 2 * p, im.height + 2 * p, bg)
    paste(out, im, p, p)
    return out


def kanji_row(c, kanji_img, line_len, gap):
    """輪廻 flanked by two fading lines, as one image."""
    th = max(4, kanji_img.height // 22)
    w = kanji_img.width + 2 * (gap + line_len)
    out = canvas(w, kanji_img.height)
    cy = kanji_img.height / 2
    paste(out, fade_line(line_len, th, c['c1'], True), 0, cy - th / 2)
    paste(out, kanji_img, line_len + gap, 0)
    paste(out, fade_line(line_len, th, c['c2'], False), line_len + gap + kanji_img.width, cy - th / 2)
    return out


def stack(items, gap_list, align='center'):
    """Stack images vertically with given gaps."""
    w = max(i.width for i in items)
    h = sum(i.height for i in items) + sum(gap_list)
    out = canvas(w, h)
    y = 0
    for i, im in enumerate(items):
        x = (w - im.width) / 2 if align == 'center' else 0
        paste(out, im, x, y)
        y += im.height + (gap_list[i] if i < len(gap_list) else 0)
    return out


def save(im, rel):
    p = BRAND / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    im.save(p, optimize=True)
    print('wrote', rel, im.size)


# ---------- shared pieces ----------
def pieces(mode, scale=1.0):
    c = MODES[mode]
    word = text('RINNE', font(CINZEL, int(300 * scale), b'Bold'), c['text'], tracking=0.233)
    kanji = text('輪廻', font(YUJI, int(130 * scale)), c['kanji'], tracking=0.42)
    return c, word, kanji


def tagline(c, size, s='The cycle of rebirth · a weekly anime planner'):
    return text(s, font(CORM_I, size, b'Italic'), c['sub'], tracking=0.02)


for mode in MODES:
    c, word, kanji = pieces(mode)

    # Title only: RINNE, and RINNE + 輪廻
    save(pad(word, 0.06), f'title/rinne-title-{mode}.png')
    krow = kanji_row(c, kanji, int(word.width * 0.30), int(kanji.height * 0.55))
    save(pad(stack([word, krow], [int(word.height * 0.42)]), 0.06), f'title/rinne-title-kanji-{mode}.png')

    # Horizontal logo: mark left, RINNE over 輪廻 right
    text_block_h = word.height + int(word.height * 0.42) + kanji.height
    m = scaled(mark(mode), h=int(text_block_h * 1.75))
    gap = int(m.width * 0.12)
    kline = canvas(word.width, kanji.height)
    paste(kline, kanji, 0, 0)
    th = max(4, kanji.height // 22)
    lx = kanji.width + int(kanji.height * 0.5)
    paste(kline, fade_line(word.width - lx, th, c['c2'], False), lx, kanji.height / 2 - th / 2)
    block = stack([word, kline], [int(word.height * 0.42)], align='left')
    H = max(m.height, block.height)
    out = canvas(m.width + gap + block.width, H)
    paste(out, m, 0, (H - m.height) / 2)
    paste(out, block, m.width + gap, (H - block.height) / 2)
    save(pad(out, 0.05), f'logo/rinne-logo-horizontal-{mode}.png')
    horizontal = out

    # Japanese: 輪廻 leads, RINNE supports
    big_k = text('輪廻', font(YUJI, 420), c['kanji'] if mode == 'light-mode' else c['text'], tracking=0.12)
    small_w = text('RINNE', font(CINZEL, 110, b'Bold'), c['kanji'], tracking=0.5)
    wrow = kanji_row(c, small_w, int(big_k.width * 0.22), int(small_w.height * 0.9))
    jp_title = stack([big_k, wrow], [int(big_k.height * 0.22)])
    save(pad(jp_title, 0.06), f'japanese/rinne-jp-title-{mode}.png')

    m2 = scaled(mark(mode), w=int(big_k.width * 0.95))
    save(pad(stack([m2, big_k, wrow], [int(big_k.height * 0.28), int(big_k.height * 0.22)]), 0.06),
         f'japanese/rinne-jp-stacked-{mode}.png')

    jh = big_k.height + int(big_k.height * 0.22) + wrow.height
    m3 = scaled(mark(mode), h=int(jh * 1.4))
    jblock = stack([big_k, wrow], [int(big_k.height * 0.22)])
    H = max(m3.height, jblock.height)
    out = canvas(m3.width + int(m3.width * 0.12) + jblock.width, H)
    paste(out, m3, 0, (H - m3.height) / 2)
    paste(out, jblock, m3.width + int(m3.width * 0.12), (H - jblock.height) / 2)
    save(pad(out, 0.05), f'japanese/rinne-jp-horizontal-{mode}.png')

    # Vertical (tategaki): mark on top, 輪 over 廻, a fading rule, small RINNE rotated alongside
    vk = text('輪廻', font(YUJI, 420), c['kanji'] if mode == 'light-mode' else c['text'], tracking=0.08, vertical=True)
    vw = text('RINNE', font(CINZEL, 90, b'Bold'), c['kanji'], tracking=0.5).rotate(-90, expand=True)
    m4 = scaled(mark(mode), w=int(vk.width * 1.5))
    vgap = int(vw.width * 1.4)
    W = max(m4.width, vk.width + 2 * (vgap + vw.width))  # keep 輪廻 centred under the wheel
    out = canvas(W, m4.height + int(vk.width * 0.3) + max(vk.height, vw.height))
    paste(out, m4, (W - m4.width) / 2, 0)
    ky = m4.height + int(vk.width * 0.3)
    paste(out, vk, (W - vk.width) / 2, ky)
    paste(out, vw, (W + vk.width) / 2 + vgap, ky + (vk.height - vw.height) / 2)
    save(pad(out, 0.06), f'japanese/rinne-jp-vertical-{mode}.png')


# ---------- banners ----------
def bg_gradient(w, h, c):
    top, bot = hex2rgb(c['bg2']), hex2rgb(c['bg'])
    g = Image.new('RGBA', (1, h))
    for y in range(h):
        t = y / (h - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,))
    return g.resize((w, h))


def watermark(mode, size, opacity):
    m = scaled(mark(mode), w=size)
    a = m.getchannel('A').point(lambda v: int(v * opacity))
    m.putalpha(a)
    return m


def banner(mode, w, h, rel, jp=False):
    c = MODES[mode]
    out = bg_gradient(w, h, c)
    wm = watermark(mode, int(h * 1.5), 0.10 if mode == 'dark-mode' else 0.12)
    paste(out, wm, w - wm.width * 0.62, (h - wm.height) / 2)
    src = Image.open(BRAND / (('japanese/rinne-jp-horizontal-' if jp else 'logo/rinne-logo-horizontal-') + mode + '.png'))
    wide = w / h > 2.5
    lock = scaled(src, h=int(h * (0.58 if wide else 0.50)))
    tag = tagline(c, int(h * (0.072 if wide else 0.062)))
    x = int(w * 0.075)
    total = lock.height + int(h * 0.04) + tag.height
    y = (h - total) / 2
    paste(out, lock, x, y)
    paste(out, tag, x + lock.width * 0.05 / 1.1, y + lock.height + h * 0.04)  # align with the mark's left edge (lockup has 5% padding)
    save(out.convert('RGB'), rel)


banner('dark-mode', 1280, 640, 'banner/rinne-social-preview-1280x640.png')
banner('dark-mode', 1280, 640, 'banner/rinne-social-preview-jp-1280x640.png', jp=True)
banner('dark-mode', 1600, 500, 'banner/rinne-readme-banner-dark-mode.png')
banner('light-mode', 1600, 500, 'banner/rinne-readme-banner-light-mode.png')
