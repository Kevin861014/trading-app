# -*- coding: utf-8 -*-
"""Generate PWA / home-screen icons (own design, Pillow only). usage: python make_icons.py <outdir>"""
import sys, os
from PIL import Image, ImageDraw

BG = (15, 17, 23); PANEL = (24, 28, 40); GREEN = (38, 166, 154); RED = (239, 83, 80); GRID = (255, 255, 255, 22)

def draw(size, maskable=False, rounded=False):
    S = size * 4
    img = Image.new('RGBA', (S, S), BG + (255,))
    d = ImageDraw.Draw(img, 'RGBA')
    pad = S * (0.20 if maskable else 0.10)           # maskable: keep content inside the central safe zone
    box = [pad, pad, S - pad, S - pad]
    d.rounded_rectangle(box, radius=S * 0.12, fill=PANEL + (255,))
    w = box[2] - box[0]; h = box[3] - box[1]
    for i in range(1, 4):                              # faint grid
        y = box[1] + h * i / 4; d.line([(box[0] + w * .06, y), (box[2] - w * .06, y)], fill=GRID, width=max(2, S // 256))
    pts = [(.08, .78), (.28, .55), (.42, .66), (.62, .34), (.76, .46), (.92, .16)]   # upward trend with pullbacks
    P = [(box[0] + w * x, box[1] + h * y) for x, y in pts]
    lw = max(6, int(S * 0.035))
    d.line(P, fill=GREEN + (255,), width=lw, joint='curve')
    for x, y in P:
        r = lw * 0.62; d.ellipse([x - r, y - r, x + r, y + r], fill=GREEN + (255,))
    x, y = P[-1]; r = lw * 1.1; d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255))
    ex, ey = P[2]; r = lw * .62; d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=RED + (255,))   # one small red dip = risk
    if rounded:                                        # only for the browser favicon
        m = Image.new('L', (S, S), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, S, S], radius=S * .22, fill=255); img.putalpha(m)
    return img.resize((size, size), Image.LANCZOS)

out = sys.argv[1]; os.makedirs(out, exist_ok=True)
draw(180).convert('RGB').save(os.path.join(out, 'apple-touch-icon.png'))          # iOS: opaque, iOS rounds the corners
draw(192).convert('RGB').save(os.path.join(out, 'icon-192.png'))
draw(512).convert('RGB').save(os.path.join(out, 'icon-512.png'))
draw(512, maskable=True).convert('RGB').save(os.path.join(out, 'icon-maskable-512.png'))
draw(64, rounded=True).save(os.path.join(out, 'favicon.png'))
print(sorted(os.listdir(out)))
