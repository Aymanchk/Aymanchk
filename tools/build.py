#!/usr/bin/env python3
"""Generates the profile SVGs (light + dark) into assets/.

Kanji and the name are converted to outlines so they render the same
everywhere; body text stays live text with system font stacks.
Run: python3 tools/build.py
"""
import math
import random
from html import escape
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTCollection, TTFont

ROOT = Path(__file__).resolve().parent.parent
W = 880

SERIF = "'Iowan Old Style','Palatino Linotype',Palatino,Georgia,'Times New Roman',serif"
MONO = "ui-monospace,'SF Mono',SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
SEAL_INK = "#f7f0e1"

THEMES = {
    "light": dict(
        paper="#f3ecdc", edge="#e2d6bd", ink="#1d1a16", soft="#544d43", faint="#8d8475",
        red="#bf3a2b", gold="#a8834a", wood="#2b2420", wood2="#5a4a3e", border="#d8ccb2",
        ridge=(0.26, 0.5, 0.88), grain="0",
    ),
    "dark": dict(
        paper="#16130f", edge="#0c0a08", ink="#ece4d3", soft="#b9b09e", faint="#7f7768",
        red="#d9483b", gold="#c9a468", wood="#3b3029", wood2="#77634f", border="#2e2923",
        ridge=(0.13, 0.24, 0.42), grain="1",
    ),
}


# ---------- fonts -> outlines ----------

def _face(path, name):
    for f in TTCollection(path).fonts:
        if f["name"].getDebugName(4) == name:
            return f
    raise SystemExit(f"font face not found: {name}")


DIDOT = _face("/System/Library/Fonts/Supplemental/Didot.ttc", "Didot")
DIDOT_B = _face("/System/Library/Fonts/Supplemental/Didot.ttc", "Didot Bold")
MENLO = _face("/System/Library/Fonts/Menlo.ttc", "Menlo Bold")


def _glyph(font, ch, size, x, y):
    gs = font.getGlyphSet()
    name = font.getBestCmap()[ord(ch)]
    s = size / font["head"].unitsPerEm
    pen = SVGPathPen(gs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
    gs[name].draw(TransformPen(pen, (s, 0, 0, -s, x, y)))
    return pen.getCommands(), gs[name].width * s


def htext(font, text, size, x, y, tracking=0.0):
    """Outline of a horizontal run. Returns (path d, end x)."""
    out = []
    for ch in text:
        d, adv = _glyph(font, ch, size, x, y)
        out.append(d)
        x += adv + tracking
    return "".join(out), x


def glyph(text, size, cx, cy, font=None, tracking=0.0):
    """Outline of a short run, optically centred on (cx, cy) by its ink bounds."""
    font = font or MENLO
    gs = font.getGlyphSet()
    s = size / font["head"].unitsPerEm
    bp = BoundsPen(gs)
    x = 0
    for ch in text:
        g = gs[font.getBestCmap()[ord(ch)]]
        g.draw(TransformPen(bp, (s, 0, 0, -s, x, 0)))
        x += g.width * s + tracking
    x0, y0, x1, y1 = bp.bounds
    return htext(font, text, size, cx - (x0 + x1) / 2, cy - (y0 + y1) / 2, tracking)[0]


# ---------- shared pieces ----------

def svg(w, h, body, defs="", css="", label=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{escape(label)}">'
        f"<style>{css}</style><defs>{defs}</defs>{body}</svg>\n"
    )


def grain_filter(t, fid="grain"):
    v = t["grain"]
    return (
        f'<filter id="{fid}" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="4"/>'
        f'<feColorMatrix values="0 0 0 0 {v}  0 0 0 0 {v}  0 0 0 0 {v}  0 0 0 0.55 0"/></filter>'
    )


ROUGH = (
    '<filter id="rough" x="-5%" y="-10%" width="110%" height="120%">'
    '<feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="3" seed="7" result="n"/>'
    '<feDisplacementMap in="SourceGraphic" in2="n" scale="5"/></filter>'
)
WORN = (
    '<filter id="worn" x="-10%" y="-10%" width="120%" height="120%">'
    '<feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="2" seed="11" result="n"/>'
    '<feDisplacementMap in="SourceGraphic" in2="n" scale="1.8"/></filter>'
)

STAMP_CSS = (
    ".stamp{transform-box:fill-box;transform-origin:center;opacity:0;"
    "animation:stamp .45s cubic-bezier(.2,1.4,.4,1) forwards}"
    "@keyframes stamp{from{opacity:0;transform:scale(1.7)}to{opacity:1;transform:scale(1)}}"
    ".in{opacity:0;animation:in .7s ease forwards}"
    "@keyframes in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}"
    ".draw{stroke-dasharray:var(--l);stroke-dashoffset:var(--l);"
    "animation:draw var(--d,1s) cubic-bezier(.6,0,.2,1) forwards}"
    "@keyframes draw{to{stroke-dashoffset:0}}"
)


def seal(t, x, y, w, h, glyph_paths, delay, rot=-3, rx=6):
    cx, cy = x + w / 2, y + h / 2
    glyphs = "".join(f'<path d="{d}" fill="{SEAL_INK}"/>' for d in glyph_paths)
    return (
        f'<g transform="rotate({rot} {cx} {cy})"><g class="stamp" style="animation-delay:{delay}s" filter="url(#worn)">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{t["red"]}"/>{glyphs}</g></g>'
    )


def card_bg(t, w, h, rx=14, cid="card"):
    defs = (
        f'<clipPath id="{cid}"><rect width="{w}" height="{h}" rx="{rx}"/></clipPath>'
        f'<radialGradient id="vig" cx="50%" cy="45%" r="75%"><stop offset="55%" stop-color="{t["edge"]}" stop-opacity="0"/>'
        f'<stop offset="100%" stop-color="{t["edge"]}" stop-opacity=".9"/></radialGradient>' + grain_filter(t)
    )
    back = f'<rect width="{w}" height="{h}" fill="{t["paper"]}"/><rect width="{w}" height="{h}" fill="url(#vig)"/>'
    front = (
        f'<rect width="{w}" height="{h}" filter="url(#grain)" opacity=".13"/>'
        f'</g><rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="none" stroke="{t["border"]}"/>'
    )
    return defs, f'<g clip-path="url(#{cid})">' + back, front


def dry(fid, x, y, w, h, seed=9):
    """Dry-brush streaks: keeps the source only where stretched noise is dense."""
    return (
        f'<filter id="{fid}" filterUnits="userSpaceOnUse" x="{x}" y="{y}" width="{w}" height="{h}" '
        'color-interpolation-filters="sRGB">'
        f'<feTurbulence type="fractalNoise" baseFrequency="0.012 0.9" numOctaves="2" seed="{seed}"/>'
        '<feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  7 0 0 0 -2.2" result="s"/>'
        '<feComposite in="SourceGraphic" in2="s" operator="in"/></filter>'
    )


def rgb01(hexcol):
    return [int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5)]


# ---------- header ----------

def _noise(seed):
    rnd = random.Random(seed)
    layers = [([rnd.random() for _ in range(f + 2)], f, a) for f, a in ((4, 1), (9, 0.5), (20, 0.24), (44, 0.1))]
    total = sum(a for _, _, a in layers)

    def n(u):
        v = 0
        for vals, f, a in layers:
            p = u * f
            i = int(p)
            k = (1 - math.cos((p - i) * math.pi)) / 2
            v += a * (vals[i] * (1 - k) + vals[i + 1] * k)
        return v / total

    return n


def ridge(seed, base, amp, env, h):
    n = _noise(seed)
    pts = [(x, base - amp * env(x) * (0.35 + 0.65 * n((x + 10) / (W + 20)))) for x in range(-10, W + 11, 5)]
    d = "M" + " L".join(f"{x},{y:.1f}" for x, y in pts) + f" L{W + 10},{h} L-10,{h}Z"
    return d, {x: y for x, y in pts}


def bump(c, s, lo=0.22):
    return lambda x: lo + (1 - lo) * math.exp(-(((x - c) / s) ** 2))


def header(t):
    h, shore = 320, 264
    defs, back, front = card_bg(t, W, h)
    a_far, a_mid, a_near = t["ridge"]
    pr, pg, pb = rgb01(t["paper"])
    rnd = random.Random(5)

    far, _ = ridge(3, 226, 132, bump(606, 170), shore)
    mid, mid_y = ridge(8, 250, 84, bump(430, 250, 0.3), shore)
    near, _ = ridge(21, 268, 46, lambda x: 0.12 + 0.88 * math.exp(-(((x - 850) / 150) ** 2)), shore)

    def grad(gid, top, bottom, a):
        return (
            f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="0" y1="{top}" x2="0" y2="{bottom}">'
            f'<stop offset="0" stop-color="{t["ink"]}" stop-opacity="{a}"/>'
            f'<stop offset=".6" stop-color="{t["ink"]}" stop-opacity="{a * 0.5:.2f}"/>'
            f'<stop offset="1" stop-color="{t["ink"]}" stop-opacity="{a * 0.18:.2f}"/></linearGradient>'
        )

    name_d, _ = htext(DIDOT, "Aiman", 98, 54, 132, tracking=1.5)

    px, py = 706, mid_y[705] + 2
    pagoda = "".join(
        f'<path d="M{px - w},{py - y} q{w * 0.45},-1 {w * 0.62},-7 h{w * 0.76} q{w * 0.17},6 {w * 0.62},7 q-{w},-2.4 -{2 * w},0z"/>'
        f'<rect x="{px - w * 0.42}" y="{py - y}" width="{w * 0.84}" height="6"/>'
        for w, y in ((13, 6), (10.5, 19), (8, 32))
    ) + f'<path d="M{px},{py - 39} v-13" stroke="{t["ink"]}" stroke-width="1.3"/>'
    lights = "".join(
        f'<rect class="lamp" style="animation-delay:-{i * 1.3}s" x="{px - 1.5}" y="{py - y + 1.5}" width="3" height="3" fill="{t["gold"]}"/>'
        for i, y in enumerate((6, 19, 32))
    )

    # petals: three nested motions (fall, sway, flutter); big ones are out of focus
    petals = ""
    for i in range(11):
        x = 180 + i * 70 + rnd.randint(-25, 25)
        s = rnd.choice((0.6, 0.75, 0.9, 1.0, 1.15, 1.7, 2.1))
        dur = rnd.uniform(10, 16) / (0.7 + s * 0.3)
        blur = ' filter="url(#dof)" opacity=".55"' if s > 1.5 else ' opacity=".85"'
        petals += (
            f'<g transform="translate({x} 0)"><g class="fall" style="animation-duration:{dur:.1f}s;animation-delay:-{rnd.uniform(0, 16):.1f}s">'
            f'<g class="sway" style="animation-duration:{rnd.uniform(2.4, 3.8):.1f}s"><g transform="scale({s})"{blur}>'
            f'<path class="flut" style="animation-duration:{rnd.uniform(1.1, 2.1):.1f}s" d="M0,-5 C5,-6 8,-1 5,4 C3,7 -3,7 -5,3 C-7,-1 -4,-5 0,-5Z" '
            f'fill="{t["red"]}"/></g></g></g></g>'
        )

    birds = ""
    for bx, by, bs, bd in ((0, 0, 1, 0.52), (26, 14, 0.8, 0.47), (-20, 20, 0.7, 0.58), (48, -6, 0.6, 0.5), (-44, 6, 0.55, 0.44)):
        birds += (
            f'<g transform="translate({bx} {by}) scale({bs})"><path d="M-8,0 q4,-7 8,0 q4,-7 8,0">'
            f'<animate attributeName="d" dur="{bd}s" repeatCount="indefinite" calcMode="spline" keyTimes="0;.5;1" '
            'keySplines=".4 0 .6 1;.4 0 .6 1" values="M-8,0 q4,-7 8,0 q4,-7 8,0;M-8,-2 q4,3 8,2 q4,1 8,-2;M-8,0 q4,-7 8,0 q4,-7 8,0"/></path></g>'
        )

    glitter = "".join(
        f'<ellipse class="glit" style="animation-delay:-{rnd.uniform(0, 3):.1f}s" cx="{618 + rnd.uniform(-5, 5):.0f}" cy="{270 + i * 5.2:.1f}" '
        f'rx="{max(6, 34 - i * 2.2 + rnd.uniform(-8, 8)):.0f}" ry="1.5" fill="{t["red"]}"/>' for i in range(10)
    )
    ripples = "".join(
        f'<path class="rip" style="animation-duration:{d}s" d="M{x},{y} h{w}" stroke="{t["ink"]}" stroke-opacity=".3" stroke-width="1" stroke-linecap="round"/>'
        for x, y, w, d in ((70, 276, 90, 9), (250, 300, 130, 13), (420, 284, 70, 11), (700, 296, 110, 12), (160, 310, 60, 8), (520, 308, 90, 10))
    )
    boat = (
        f'<g class="boat"><g class="bob" fill="{t["ink"]}"><path d="M-17,0 q17,7 36,-1 l-5,-1.5 h-26z"/>'
        '<path d="M-3,-2 l2,-9 3,0 1.5,9z"/><path d="M-5,-11.5 l5.5,-4 5.5,4z"/>'
        f'<path d="M3,-9 L15,5" stroke="{t["ink"]}" stroke-width="1" fill="none"/></g></g>'
    )

    code = ""
    k = 0
    for cx, word in ((842, "while(true)"), (816, "build();")):
        for i, ch in enumerate(word):
            col = t["red"] if ch in "(){};" else t["ink"]
            code += (
                f'<text class="vc in" style="animation-delay:{2.4 + k * 0.07:.2f}s" x="{cx}" y="{44 + i * 16.5}" '
                f'text-anchor="middle" fill="{col}">{ch}</text>'
            )
            k += 1

    defs += (
        WORN + dry("dryb", 40, 138, 360, 30)
        + grad("gf", 100, shore, a_far) + grad("gm", 180, shore, a_mid) + grad("gn", 228, shore, a_near)
        + f'<radialGradient id="glow"><stop offset=".42" stop-color="{t["red"]}" stop-opacity=".4"/>'
        f'<stop offset="1" stop-color="{t["red"]}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="wat" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="{t["ink"]}" stop-opacity=".16"/>'
        f'<stop offset="1" stop-color="{t["ink"]}" stop-opacity=".03"/></linearGradient>'
        '<linearGradient id="fband" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="fm1" maskUnits="userSpaceOnUse" x="0" y="160" width="{W}" height="90"><rect y="160" width="{W}" height="90" fill="url(#fband)"/></mask>'
        f'<mask id="fm2" maskUnits="userSpaceOnUse" x="0" y="212" width="{W}" height="64"><rect y="212" width="{W}" height="64" fill="url(#fband)"/></mask>'
        '<filter id="fog" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.006 0.028" numOctaves="3" seed="2"/>'
        f'<feColorMatrix values="0 0 0 0 {pr:.3f}  0 0 0 0 {pg:.3f}  0 0 0 0 {pb:.3f}  2.6 0 0 0 -0.85"/></filter>'
        '<filter id="dof"><feGaussianBlur stdDeviation="1.1"/></filter>'
        f'<filter id="water" filterUnits="userSpaceOnUse" x="0" y="{shore - 6}" width="{W}" height="{h - shore + 6}" color-interpolation-filters="sRGB">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.006 0.12" numOctaves="2" seed="5" result="n">'
        '<animate attributeName="baseFrequency" dur="9s" values="0.006 0.12;0.01 0.17;0.006 0.12" repeatCount="indefinite"/></feTurbulence>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="20" xChannelSelector="R" yChannelSelector="G"/></filter>'
        f'<clipPath id="wclip"><rect y="{shore}" width="{W}" height="{h - shore}"/></clipPath>'
        '<filter id="bleed" filterUnits="userSpaceOnUse" x="0" y="0" width="560" height="200">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="3" result="n"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="46"/><feGaussianBlur stdDeviation="5"/></filter>'
        '<mask id="nm" maskUnits="userSpaceOnUse" x="0" y="0" width="560" height="200">'
        '<rect x="-30" y="10" width="0" height="150" fill="#fff" filter="url(#bleed)">'
        '<animate attributeName="width" values="0;520" keyTimes="0;1" calcMode="spline" keySplines=".35 0 .25 1" '
        'begin=".5s" dur="2s" fill="freeze"/></rect></mask>'
        '<filter id="inkedge" x="-20%" y="-20%" width="140%" height="140%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.05" numOctaves="2" seed="8" result="n"/>'
        '<feDisplacementMap in="SourceGraphic" in2="n" scale="5"/></filter>'
        '<mask id="brush"><path class="draw" style="--l:340;--d:.9s;animation-delay:2s" d="M50,153 L384,150" '
        'stroke="#fff" stroke-width="26" fill="none"/></mask>'
    )
    css = STAMP_CSS + (
        ".sun{transform-box:fill-box;transform-origin:center;animation:bloom 2.8s cubic-bezier(.15,.7,.2,1) both}"
        "@keyframes bloom{from{opacity:0;transform:scale(.05)}35%{opacity:.9}to{opacity:1;transform:scale(1)}}"
        ".glow{transform-box:fill-box;transform-origin:center;animation:pulse 5s ease-in-out infinite alternate}"
        "@keyframes pulse{from{opacity:.5;transform:scale(.94)}to{opacity:1;transform:scale(1.06)}}"
        ".fog{animation:drift 38s ease-in-out infinite alternate}.fog.b{animation-duration:52s;animation-direction:alternate-reverse}"
        "@keyframes drift{from{transform:translateX(0)}to{transform:translateX(-420px)}}"
        ".flock{animation:fade 30s linear infinite}@keyframes fade{0%,100%{opacity:0}8%,86%{opacity:1}}"
        ".fall{animation:fall linear infinite}@keyframes fall{from{transform:translate(60px,-30px)}to{transform:translate(-140px,350px)}}"
        ".sway{animation:sway ease-in-out infinite alternate}@keyframes sway{from{transform:translateX(-16px)}to{transform:translateX(16px)}}"
        ".flut{transform-box:fill-box;transform-origin:center;animation:flut ease-in-out infinite alternate}"
        "@keyframes flut{from{transform:rotate(-50deg) scaleY(1)}50%{transform:rotate(30deg) scaleY(.25)}to{transform:rotate(120deg) scaleY(-1)}}"
        ".glit{transform-box:fill-box;transform-origin:center;animation:glit 2.8s ease-in-out infinite alternate}"
        "@keyframes glit{from{opacity:.15;transform:scaleX(.5)}to{opacity:.85;transform:scaleX(1.15)}}"
        ".rip{animation:rip ease-in-out infinite alternate}@keyframes rip{from{transform:translateX(-22px);opacity:.2}to{transform:translateX(22px);opacity:1}}"
        ".boat{animation:sail 70s linear infinite alternate}@keyframes sail{from{transform:translate(210px,288px)}to{transform:translate(430px,286px)}}"
        ".bob{animation:bob 3.4s ease-in-out infinite alternate}@keyframes bob{from{transform:translateY(-1px) rotate(-2.5deg)}to{transform:translateY(1.2px) rotate(2.5deg)}}"
        ".lamp{animation:lamp 3.7s steps(1) infinite}@keyframes lamp{0%{opacity:.95}42%{opacity:.55}50%{opacity:1}78%{opacity:.7}}"
        f".role{{font:500 12.5px {MONO};letter-spacing:2.6px}}.vc{{font:600 14px {MONO}}}"
    )

    body = back
    body += (
        f'<circle class="glow" cx="618" cy="120" r="108" fill="url(#glow)"/>'
        f'<g filter="url(#inkedge)"><circle class="sun" cx="618" cy="120" r="54" fill="{t["red"]}"/></g>'
        f'<g class="flock" fill="none" stroke="{t["ink"]}" stroke-width="1.6" stroke-linecap="round"><g>{birds}'
        '<animateMotion dur="30s" repeatCount="indefinite" path="M410,104 C500,66 640,40 800,58"/></g></g>'
        f'<path d="{far}" fill="{t["paper"]}"/><path d="{far}" fill="url(#gf)"/>'
        f'<g mask="url(#fm1)"><rect class="fog" x="0" y="160" width="1300" height="90" filter="url(#fog)"/></g>'
        f'<path d="{mid}" fill="url(#gm)"/><g fill="{t["ink"]}" opacity="{min(1, a_mid * 1.6)}">{pagoda}</g>{lights}'
        f'<g mask="url(#fm2)"><rect class="fog b" x="0" y="212" width="1300" height="64" filter="url(#fog)"/></g>'
        f'<path d="{near}" fill="url(#gn)"/>'
        # water: mirrored ridges and sun glitter, displaced by animated noise
        f'<rect y="{shore}" width="{W}" height="{h - shore}" fill="{t["paper"]}"/>'
        f'<rect y="{shore}" width="{W}" height="{h - shore}" fill="url(#wat)"/>'
        f'<g clip-path="url(#wclip)"><g filter="url(#water)"><g transform="translate(0 {2 * shore}) scale(1 -1)" opacity=".55">'
        f'<path d="{far}" fill="url(#gf)"/><path d="{mid}" fill="url(#gm)"/><path d="{near}" fill="url(#gn)"/></g>{glitter}</g>'
        f'{ripples}{boat}</g>'
        f'<path d="M0,{shore + .5}H{W}" stroke="{t["ink"]}" stroke-opacity=".28"/>'
    )
    body += petals
    body += f'<g mask="url(#nm)"><path d="{name_d}" fill="{t["ink"]}"/></g>'
    body += (
        f'<g mask="url(#brush)"><path filter="url(#dryb)" d="M56,153 C92,144 240,143 374,147 C381,147.4 381,150.4 374,151 '
        f'C250,155 120,158 61,159.5 C53,159.6 51,155 56,153Z" fill="{t["ink"]}"/></g>'
        f'<text class="role in" style="animation-delay:2.5s" x="57" y="190" fill="{t["soft"]}">'
        "BACKEND DEVELOPER  ·  AI ENGINEER  ·  CO-FOUNDER</text>"
    )
    body += code
    body += seal(t, 809, 238, 40, 40, [glyph("A", 30, 829, 258, DIDOT_B)], 3.9, rot=-4, rx=5)
    body += front
    return svg(W, h, body, defs, css, "Aiman — Backend Developer · AI Engineer · Co-founder")


# ---------- section headers ----------

def section(t, mark, title, sub):
    h = 68
    css = STAMP_CSS + f".t{{font:700 25px {SERIF}}}.s{{font:500 10.5px {MONO};letter-spacing:2.4px}}"
    body = seal(t, 3, 10, 46, 46, [glyph(mark, 21 if len(mark) > 1 else 28, 26, 33, tracking=-1)], 0.2)
    body += (
        f'<text class="t in" style="animation-delay:.35s" x="66" y="34" fill="{t["ink"]}">{escape(title)}</text>'
        f'<text class="s in" style="animation-delay:.5s" x="67" y="53" fill="{t["faint"]}">{escape(sub)}</text>'
        f'<g filter="url(#dl)"><path class="draw" style="--l:560;--d:1.3s;animation-delay:.6s" d="M300,33 C420,29 640,36 852,32" fill="none" '
        f'stroke="{t["ink"]}" stroke-opacity=".7" stroke-width="3.4" stroke-linecap="round"/></g>'
        f'<circle class="stamp" style="animation-delay:1.8s" cx="866" cy="32" r="4.5" fill="{t["red"]}"/>'
    )
    return svg(W, h, body, WORN + dry("dl", 290, 20, 580, 26, seed=4), css, title)


# ---------- terminal scroll ----------

CH = 8.4  # advance of one monospace cell at 14px; enforced with textLength


def terminal(t):
    h = 404
    x0, top, bot = 78, 40, 344
    px = x0 + 11 * CH
    u0, ud = 0.3, 1.7  # the scroll unrolls from the centre first
    spl = 'calcMode="spline" keyTimes="0;1" keySplines=".5 0 .15 1"'
    rnd = random.Random(12)
    defs = (
        WORN + grain_filter(t) + dry("dre", 620, 100, 200, 200, seed=6)
        + f'<linearGradient id="rod" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="{t["wood"]}"/>'
        f'<stop offset=".35" stop-color="{t["wood2"]}"/><stop offset="1" stop-color="{t["wood"]}"/></linearGradient>'
        f'<linearGradient id="shade" x1="0" x2="1" y1="0" y2="0"><stop offset="0" stop-color="#000" stop-opacity=".3"/>'
        '<stop offset=".05" stop-color="#000" stop-opacity="0"/><stop offset=".95" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity=".3"/></linearGradient>'
        f'<clipPath id="unroll"><rect x="440" y="0" width="0" height="{h}">'
        f'<animate attributeName="x" values="440;46" {spl} begin="{u0}s" dur="{ud}s" fill="freeze"/>'
        f'<animate attributeName="width" values="0;788" {spl} begin="{u0}s" dur="{ud}s" fill="freeze"/></rect></clipPath>'
        '<mask id="em"><circle class="enso" cx="716" cy="196" r="72" pathLength="100" fill="none" stroke="#fff" stroke-width="40" '
        'transform="rotate(-70 716 196)"/></mask>'
    )
    css = STAMP_CSS + (
        f"text{{font:14px {MONO}}}.o{{opacity:0;animation:show .25s ease forwards}}"
        "@keyframes show{to{opacity:1}}"
        ".blink{opacity:0;animation:blink 1.1s steps(1) infinite}"
        "@keyframes blink{0%{opacity:1}50%{opacity:0}}"
        f".tassel{{transform-origin:846px 366px;animation:damp 3.6s ease-in-out {u0}s both,swing 4.6s ease-in-out {u0 + 3.6}s infinite alternate}}"
        "@keyframes damp{0%{transform:rotate(0)}12%{transform:rotate(-24deg)}28%{transform:rotate(19deg)}44%{transform:rotate(-13deg)}"
        "60%{transform:rotate(9deg)}76%{transform:rotate(-6deg)}90%{transform:rotate(4deg)}100%{transform:rotate(-3deg)}}"
        "@keyframes swing{from{transform:rotate(-3deg)}to{transform:rotate(3deg)}}"
        f".enso{{stroke-dasharray:100;stroke-dashoffset:100;animation:enso 2.2s cubic-bezier(.5,0,.2,1) {u0 + ud}s forwards}}"
        "@keyframes enso{to{stroke-dashoffset:6}}"
        ".wm{animation:breathe 7s ease-in-out infinite alternate}@keyframes breathe{from{opacity:.09}to{opacity:.17}}"
    )

    def rod(x, start, extra=""):
        return (
            f'<g transform="translate({start - x} 0)"><animateTransform attributeName="transform" type="translate" values="{start - x} 0;0 0" {spl} '
            f'begin="{u0}s" dur="{ud}s" fill="freeze"/>'
            f'<rect x="{x}" y="28" width="24" height="328" rx="5" fill="url(#rod)"/>'
            f'<rect x="{x + 4}" y="17" width="16" height="12" rx="2" fill="{t["gold"]}"/>'
            f'<rect x="{x + 4}" y="355" width="16" height="12" rx="2" fill="{t["gold"]}"/>{extra}</g>'
        )

    tassel = (
        f'<g class="tassel"><path d="M846,366 v16" stroke="{t["red"]}" stroke-width="1.6"/>'
        f'<path d="M846,380 l6,6 -6,6 -6,-6z" fill="{t["red"]}"/>'
        f'<path d="M842,393 v22 M844.7,393 v25 M847.3,393 v25 M850,393 v22" stroke="{t["red"]}" stroke-width="1.5"/></g>'
    )

    paper = (
        f'<rect x="46" y="{top}" width="788" height="{bot - top}" fill="{t["paper"]}"/>'
        f'<rect x="46" y="{top}" width="788" height="9" fill="{t["red"]}" opacity=".9"/>'
        f'<rect x="46" y="{bot - 9}" width="788" height="9" fill="{t["red"]}" opacity=".9"/>'
        f'<path d="M46,{top + 12.5}H834M46,{bot - 12.5}H834" stroke="{t["gold"]}" stroke-width="1"/>'
        f'<rect x="46" y="{top}" width="788" height="{bot - top}" filter="url(#grain)" opacity=".13"/>'
        f'<rect x="46" y="{top}" width="788" height="{bot - top}" fill="url(#shade)"/>'
        # ensō: a ring of uneven weight, revealed along its stroke
        f'<g class="wm"><g mask="url(#em)"><path filter="url(#dre)" fill-rule="evenodd" fill="{t["ink"]}" '
        'd="M716,112 a84,84 0 1 0 .1,0z M719,128 a69,67 0 1 1 -.1,0z"/></g></g>'
        f'<circle cx="{x0 + 4}" cy="71" r="5" fill="{t["red"]}"/><circle cx="{x0 + 22}" cy="71" r="5" fill="{t["gold"]}"/>'
        f'<circle cx="{x0 + 40}" cy="71" r="5" fill="{t["faint"]}"/>'
        f'<text x="440" y="75" text-anchor="middle" fill="{t["faint"]}" style="font-size:12px">aiman — zsh</text>'
        f'<path d="M{x0 - 6},86.5H808" stroke="{t["ink"]}" stroke-opacity=".14"/>'
    )

    def prompt(y, at):
        return (
            f'<text class="o" style="animation-delay:{at}s;animation-duration:.01s" x="{x0}" y="{y}" '
            f'textLength="{10 * CH:.1f}" lengthAdjust="spacing"><tspan fill="{t["red"]}">aiman</tspan>'
            f'<tspan fill="{t["faint"]}"> ~ </tspan><tspan fill="{t["gold"]}">❯</tspan><tspan> </tspan></text>'
        )

    def typed(i, y, cmd, at, start):
        # uneven keystrokes: discrete steps on jittered key times
        n = len(cmd)
        gaps = [rnd.uniform(0.05, 0.16) + (0.18 if cmd[k - 1] in " ." else 0) for k in range(1, n + 1)]
        dur = sum(gaps) + 0.05
        acc, kt = 0.0, ["0"]
        for g in gaps:
            acc += g
            kt.append(f"{acc / dur:.3f}")
        kt = ";".join(kt)
        widths = ";".join(f"{k * CH:.1f}" for k in range(n + 1))
        xs = ";".join(f"{px + k * CH:.1f}" for k in range(n + 1))
        return dur, prompt(y, at) + (
            f'<clipPath id="c{i}"><rect x="{px}" y="{y - 14}" width="0" height="20">'
            f'<animate attributeName="width" values="{widths}" keyTimes="{kt}" calcMode="discrete" begin="{start}s" dur="{dur:.2f}s" fill="freeze"/>'
            f"</rect></clipPath>"
            f'<text x="{px}" y="{y}" clip-path="url(#c{i})" fill="{t["ink"]}" textLength="{n * CH:.1f}" '
            f'lengthAdjust="spacing">{escape(cmd)}</text>'
            f'<rect x="{px}" y="{y - 12.5}" width="8" height="16" fill="{t["ink"]}" opacity="0">'
            f'<set attributeName="opacity" to=".85" begin="{at}s" dur="{start - at + dur + 0.35:.2f}s"/>'
            f'<animate attributeName="x" values="{xs}" keyTimes="{kt}" calcMode="discrete" begin="{start}s" dur="{dur:.2f}s" fill="freeze"/></rect>'
        )

    def line(y, at, parts):
        spans = "".join(f'<tspan fill="{t[c]}">{escape(s)}</tspan>' for c, s in parts)
        return f'<text class="o" style="animation-delay:{at:.2f}s" x="{x0}" y="{y}" xml:space="preserve">{spans}</text>'

    script = [
        ("whoami", [[("ink", "Aiman"), ("faint", "  ·  "), ("soft", "backend developer, AI engineer, co-founder")]]),
        ("cat focus.txt", [
            [("red", "→ "), ("ink", "Esep"), ("soft", "  fair bill splitting: Flutter + Django/DRF")],
            [("red", "→ "), ("ink", "Backend"), ("soft", " @ SU Solutions  ·  "), ("ink", "Co-founder"), ("soft", " @ Corstack Solutions")],
            [("red", "→ "), ("ink", "ML"), ("soft", "  predictive models, clustering, RL")],
        ]),
        ("echo $MOTTO", [[("ink", "A journey of a thousand miles begins with a single step.")]]),
    ]
    lines, y, at = "", 112, u0 + ud + 0.3
    for i, (cmd, outs) in enumerate(script):
        start = at + 0.5
        dur, markup = typed(i, y, cmd, at, start)
        lines += markup
        at = start + dur + 0.45
        for parts in outs:
            y += 24
            lines += line(y, at, parts)
            at += 0.16
        y += 32
        at += 0.5
    lines += prompt(y, at) + f'<rect class="blink" style="animation-delay:{at:.2f}s" x="{px}" y="{y - 12.5}" width="8" height="16" fill="{t["ink"]}"/>'

    body = f'<g clip-path="url(#unroll)">{paper}{lines}</g>' + rod(22, 416) + rod(834, 440, tassel)
    return svg(W, h, body, defs, css, "Terminal: whoami, cat focus.txt, echo $MOTTO")


# ---------- stack ----------

STACK = [
    ("{}", "BACKEND", ["Python", "Django", "DRF", "PostgreSQL", "Node.js"]),
    ("</>", "MOBILE · WEB", ["Flutter", "Dart", "Next.js", "React", "TypeScript"]),
    ("Σ", "ML", ["scikit-learn", "NumPy", "Pandas", "Jupyter", "Gymnasium"]),
    ("$_", "TOOLS", ["Docker", "Git", "Linux"]),
]


def stack(t):
    row, cw = 54, 8.1
    h = row * len(STACK) + 6
    css = STAMP_CSS + (
        f".c{{font:500 10.5px {MONO};letter-spacing:2.2px}}.g{{font:13.5px {MONO}}}"
        ".dot{transform-box:fill-box;transform-origin:center;animation:dot 3.2s ease-in-out infinite}"
        "@keyframes dot{0%,70%,100%{transform:scale(1);opacity:.75}82%{transform:scale(1.9);opacity:1}}"
    )
    body, k = "", 0
    for r, (mark, cap, items) in enumerate(STACK):
        cy = 30 + r * row
        size = {1: 21, 2: 15, 3: 11.5}[len(mark)]
        body += (
            f'<g class="stamp" style="animation-delay:{0.15 + r * 0.18:.2f}s" filter="url(#worn)">'
            f'<circle cx="24" cy="{cy}" r="18" fill="{t["red"]}"/><path d="{glyph(mark, size, 24, cy, tracking=-0.6)}" fill="{SEAL_INK}"/></g>'
            f'<text class="c in" style="animation-delay:{0.3 + r * 0.18:.2f}s" x="56" y="{cy + 4}" fill="{t["faint"]}">{cap}</text>'
        )
        if r:
            body += f'<path d="M56,{cy - row / 2}H{W - 4}" stroke="{t["ink"]}" stroke-opacity=".1"/>'
        x = 200
        for name in items:
            w = len(name) * cw + 30
            body += (
                f'<g class="in" style="animation-delay:{0.5 + k * 0.07:.2f}s">'
                f'<rect x="{x}" y="{cy - 16}" width="{w:.1f}" height="32" rx="5" fill="{t["ink"]}" fill-opacity=".05" '
                f'stroke="{t["ink"]}" stroke-opacity=".4"/>'
                f'<circle class="dot" style="animation-delay:{k * 0.16:.2f}s" cx="{x + 11}" cy="{cy}" r="2" fill="{t["red"]}"/>'
                f'<text class="g" x="{x + 20}" y="{cy + 4.7}" fill="{t["ink"]}" textLength="{len(name) * cw:.1f}" '
                f'lengthAdjust="spacing">{escape(name)}</text></g>'
            )
            x += w + 10
            k += 1
    return svg(W, h, body, WORN, css, "Stack: " + ", ".join(i for _, _, it in STACK for i in it))


# ---------- contacts ----------

CONTACTS = [("telegram", ">_", "Telegram"), ("linkedin", "in", "LinkedIn")]


def contact(t, mark, label):
    w, h = 190, 52
    css = STAMP_CSS + f".l{{font:600 14px {MONO};letter-spacing:.6px}}"
    size = {1: 21, 2: 15, 3: 11}[len(mark)]
    body = (
        f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="8" fill="{t["ink"]}" fill-opacity=".05" '
        f'stroke="{t["ink"]}" stroke-opacity=".45"/>'
        + seal(t, 10, 9, 34, 34, [glyph(mark, size, 27, 26, tracking=-0.6)], 0.2, rx=5)
        + f'<text class="l" x="58" y="31" fill="{t["ink"]}">{label}</text>'
        f'<text class="l" x="{w - 24}" y="31" fill="{t["red"]}">↗</text>'
    )
    return svg(w, h, body, WORN, css, label)


# ---------- footer: koi pond ----------

def footer(t):
    h = 176
    defs, back, front = card_bg(t, W, h)
    belly = "#fbf6ea" if t["grain"] == "0" else "#efe7d6"
    defs += (
        '<clipPath id="kb"><path d="M25,0 C21,-9.5 2,-11 -14,-4.5 L-23,0 L-14,4.5 C2,11 21,9.5 25,0Z"/></clipPath>'
        '<filter id="ksh" x="-30%" y="-80%" width="160%" height="260%"><feGaussianBlur stdDeviation="3"/></filter>'
    )
    css = STAMP_CSS + (
        f".q{{font:italic 18px {SERIF}}}"
        ".ring{transform-box:fill-box;transform-origin:center;animation:ring 5.5s cubic-bezier(.2,.6,.3,1) infinite}"
        "@keyframes ring{0%{transform:scale(.08);opacity:0}12%{opacity:.6}100%{transform:scale(1);opacity:0}}"
    )

    def koi(path, dur, begin, spots, scale=1.0, wag=0.62):
        marks = "".join(f'<circle cx="{x}" cy="{y}" r="{r}"/>' for x, y, r in spots)
        wig = f'dur="{wag}s" repeatCount="indefinite" calcMode="spline" keyTimes="0;.5;1" keySplines=".4 0 .6 1;.4 0 .6 1"'
        return (
            f'<g><animateMotion dur="{dur}s" begin="{begin}s" repeatCount="indefinite" rotate="auto" path="{path}"/>'
            f'<g transform="scale({scale})">'
            f'<ellipse cx="-2" cy="9" rx="24" ry="7" fill="#000" opacity=".22" filter="url(#ksh)"/>'
            f'<g><animateTransform attributeName="transform" type="rotate" values="-5;5;-5" {wig}/>'
            f'<g transform="translate(-21 0)"><g><animateTransform attributeName="transform" type="rotate" values="24;-24;24" {wig}/>'
            f'<path d="M2,0 C-7,-3 -15,-10 -21,-9 C-17,-3 -17,3 -21,9 C-15,10 -7,3 2,0Z" fill="{belly}" fill-opacity=".85" '
            f'stroke="{t["ink"]}" stroke-opacity=".45" stroke-width=".7"/></g></g>'
            f'<path d="M9,-7 q-3,-9 -11,-9 q2,6 4,8z M9,7 q-3,9 -11,9 q2,-6 4,-8z" fill="{belly}" fill-opacity=".7" stroke="{t["ink"]}" stroke-opacity=".4" stroke-width=".6"/>'
            f'<path d="M25,0 C21,-9.5 2,-11 -14,-4.5 L-23,0 L-14,4.5 C2,11 21,9.5 25,0Z" fill="{belly}" stroke="{t["ink"]}" stroke-opacity=".55" stroke-width=".8"/>'
            f'<g clip-path="url(#kb)" fill="{t["red"]}">{marks}</g>'
            f'<circle cx="18.5" cy="-4" r="1" fill="{t["ink"]}"/><circle cx="18.5" cy="4" r="1" fill="{t["ink"]}"/></g></g></g>'
        )

    rings = ""
    for x, y, d in ((170, 118, 0), (640, 136, 1.9), (420, 104, 3.4), (790, 96, 4.4)):
        for j in range(3):
            rings += (
                f'<ellipse class="ring" style="animation-delay:{d + j * 0.7:.1f}s" cx="{x}" cy="{y}" rx="{46 - j * 4}" ry="{15 - j}" '
                f'fill="none" stroke="{t["ink"]}" stroke-opacity=".5" stroke-width="1"/>'
            )
    body = back + rings
    body += koi("M-70,128 C120,84 300,168 470,122 S780,92 950,134", 24, 0, [(13, -3, 8), (-5, 4, 7), (-17, -2, 4)], 1.15)
    body += koi("M950,104 C780,150 590,84 400,124 S110,156 -70,108", 31, -9, [(20, 0, 7), (0, -5, 6)], 0.9, 0.55)
    body += koi("M-70,154 C200,170 380,110 560,150 S820,160 950,120", 38, -21, [(6, 3, 9), (-12, -3, 5)], 0.75, 0.5)
    body += (
        f'<text class="q in" style="animation-delay:.3s" x="{W / 2}" y="54" text-anchor="middle" fill="{t["ink"]}">'
        "Building products that people actually use.</text>"
    )
    body += front
    return svg(W, h, body, defs, css, "Building products that people actually use.")


def main():
    for theme, t in THEMES.items():
        out = ROOT / "assets" / theme
        out.mkdir(parents=True, exist_ok=True)
        files = {
            "header": header(t),
            "terminal": terminal(t),
            "stack": stack(t),
            "footer": footer(t),
            "s-about": section(t, ">_", "About me", "WHOAMI  ·  THE PATH"),
            "s-stack": section(t, "#", "Stack", "TOOLS  ·  THE CRAFT"),
            "s-contact": section(t, "@", "Contact", "PING  ·  REACH OUT"),
        }
        files.update({f"c-{slug}": contact(t, mark, label) for slug, mark, label in CONTACTS})
        for name, data in files.items():
            (out / f"{name}.svg").write_text(data, encoding="utf-8")
        print(theme, len(files), "files", sum(len(d) for d in files.values()) // 1024, "KB")


if __name__ == "__main__":
    main()
