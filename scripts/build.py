#!/usr/bin/env python3
"""Generate every SVG in /assets from scripts/profile.json plus live GitHub & pub.dev data.

Standard library only. Run locally with `python scripts/build.py`; the
`refresh` GitHub Action runs it weekly. If an API call fails, the last good
values in scripts/cache.json are used, so a build never produces broken cards.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import textwrap
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CFG = json.loads((ROOT / "scripts" / "profile.json").read_text("utf-8"))
CACHE_FILE = ROOT / "scripts" / "cache.json"

SANS = "'Inter','Segoe UI Variable Display','Segoe UI',-apple-system,BlinkMacSystemFont,'SF Pro Display','Helvetica Neue',Arial,sans-serif"
MONO = "'JetBrains Mono','SF Mono','Cascadia Code',ui-monospace,Menlo,Consolas,'Liberation Mono',monospace"

THEMES = {
    "dark": dict(
        bg="#0A0E15", bg2="#0D121C", card="#0D131D", border="#1E2836", text="#E6EDF3",
        strong="#C9D1D9", muted="#8B949E", faint="#2A3545", grid="#FFFFFF", grid_op=0.045,
        glow=0.30, card_glow=0.20, phone="#070A10", screen="#0C1320", surface="#162031",
        chip="#0F1622", accent="#22D3EE", accent2="#A78BFA", accent3="#F472B6", ok="#34D399",
        track="#1A2230",
    ),
    "light": dict(
        bg="#FFFFFF", bg2="#F4F7FB", card="#FFFFFF", border="#E2E8F0", text="#0F172A",
        strong="#334155", muted="#64748B", faint="#CBD5E1", grid="#0F172A", grid_op=0.05,
        glow=0.16, card_glow=0.10, phone="#FFFFFF", screen="#F6F8FC", surface="#EAF0F7",
        chip="#FFFFFF", accent="#0891B2", accent2="#7C3AED", accent3="#DB2777", ok="#059669",
        track="#EEF2F7",
    ),
}

ACCENTS = {
    "cyan": ("#22D3EE", "#3B82F6"),
    "violet": ("#A78BFA", "#EC4899"),
    "emerald": ("#34D399", "#06B6D4"),
    "amber": ("#FBBF24", "#F97316"),
    "rose": ("#FB7185", "#8B5CF6"),
    "blue": ("#60A5FA", "#6366F1"),
    "lime": ("#A3E635", "#10B981"),
}

LANG_COLORS = {
    "Dart": "#00B4AB", "Python": "#3572A5", "TypeScript": "#3178C6", "JavaScript": "#F1E05A",
    "HTML": "#E34C26", "Kotlin": "#A97BFF", "Swift": "#F05138", "Typst": "#239DAD",
}

# 24×24 stroke icons (white on the gradient tile).
ICONS = {
    "sparkles": '<path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z"/><path d="M18.5 15.5l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8z"/>',
    "radar": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><path d="M12 12l6.4-6.4"/><circle cx="16" cy="9" r="1" fill="#fff"/>',
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3.2"/>',
    "cpu": '<rect x="6" y="6" width="12" height="12" rx="2.5"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20.5 20.5l-4.6-4.6"/>',
    "plate": '<rect x="2.5" y="7" width="19" height="10" rx="2"/><path d="M6.5 7v10M9.5 12h8"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="3.8" ry="9"/><path d="M3 12h18"/>',
    "chat": '<path d="M4.5 5.5h15a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H10l-4.5 3.5v-3.5h-1a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z"/><path d="M8.5 11h.01M12 11h.01M15.5 11h.01" stroke-width="2.6"/>',
    "terminal": '<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="M7 9.5l3 2.5-3 2.5M12.5 15h4.5"/>',
    "film": '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M6.5 15h6M14.5 15h3M6.5 11.5h3M11.5 11.5h6"/>',
    "store": '<path d="M4 9.5V19a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V9.5"/><path d="M3 9.5l1.6-5h14.8l1.6 5a2.6 2.6 0 0 1-5.1.6 2.6 2.6 0 0 1-5.8 0 2.6 2.6 0 0 1-5.8 0A2.6 2.6 0 0 1 3 9.5z"/><path d="M9.5 20v-5h5v5"/>',
    "pulse": '<path d="M3 12h4l2.5-6 5 12 2.5-6h4"/>',
    "bot": '<rect x="4.5" y="8" width="15" height="11" rx="3"/><path d="M12 4.5V8"/><circle cx="12" cy="3.8" r="1.1"/><path d="M9.3 13.2h.01M14.7 13.2h.01" stroke-width="2.8"/><path d="M2.5 12.5v2.5M21.5 12.5v2.5"/>',
}


# --------------------------------------------------------------------------- data

def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "profile-readme-builder", "Accept": "application/json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def collect() -> dict:
    cache = json.loads(CACHE_FILE.read_text("utf-8")) if CACHE_FILE.exists() else {}
    user = CFG["user"]
    data = {"user": cache.get("user", {}), "repos": cache.get("repos", {}), "pub": cache.get("pub", {})}

    try:
        u = _get(f"https://api.github.com/users/{user}")
        data["user"] = {"followers": u["followers"], "public_repos": u["public_repos"], "created_at": u["created_at"]}
        repos = _get(f"https://api.github.com/users/{user}/repos?per_page=100&type=owner")
        data["repos"] = {
            r["name"]: {"stars": r["stargazers_count"], "forks": r["forks_count"], "language": r["language"], "fork": r["fork"]}
            for r in repos
        }
    except Exception as e:  # noqa: BLE001
        print(f"! GitHub API failed, using cache: {e}", file=sys.stderr)

    pkgs = [p["id"] for p in CFG["packages"]] + [p["id"] for p in CFG["more_packages"]]
    for p in pkgs:
        try:
            info = _get(f"https://pub.dev/api/packages/{p}")
            score = _get(f"https://pub.dev/api/packages/{p}/score")
            data["pub"][p] = {
                "version": info["latest"]["version"],
                "likes": score.get("likeCount") or 0,
                "points": score.get("grantedPoints") or 0,
                "max_points": score.get("maxPoints") or 160,
                "dl30": score.get("downloadCount30Days") or 0,
            }
        except Exception as e:  # noqa: BLE001
            print(f"! pub.dev failed for {p}, using cache: {e}", file=sys.stderr)

    CACHE_FILE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", "utf-8")
    return data


# --------------------------------------------------------------------------- helpers

def x(s) -> str:
    return escape(str(s), quote=True)


def svg_open(w: int, h: int, label: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{x(label)}"><title>{x(label)}</title>')


def text_w(s: str, size: float, mono: bool = False) -> float:
    """Rough text width; generous on purpose so layouts never collide."""
    return len(s) * size * (0.62 if mono else 0.56)


def pill(x0: float, y0: float, label: str, *, size: float, fill: str, stroke: str, color: str,
         mono: bool = True, fill_op: float = 1.0, weight: int = 500) -> tuple[float, str]:
    h = size + 14
    w = text_w(label, size, mono) + 24
    fam = MONO if mono else SANS
    return w, (f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h}" rx="{h / 2}" fill="{fill}" '
               f'fill-opacity="{fill_op}" stroke="{stroke}"/>'
               f'<text x="{x0 + w / 2:.1f}" y="{y0 + h / 2 + size * 0.36:.1f}" text-anchor="middle" '
               f'font-family="{fam}" font-size="{size}" font-weight="{weight}" fill="{color}">{x(label)}</text>')


REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}.rm-hide{display:none}.rm-show{display:inline!important}}"


# --------------------------------------------------------------------------- hero

def hero(theme: str, stats: dict) -> str:
    c = THEMES[theme]
    dark = theme == "dark"
    W, H = 1200, 440
    first, last = CFG["name"]
    A, A2, A3 = c["accent"], c["accent2"], c["accent3"]

    # Rotating phrases, overlap-proof: only phrase 0 is visible by default (others carry
    # opacity="0" as an attribute), and CSS fades them in one at a time. A renderer without
    # animation support therefore shows one clean phrase, never several stacked on top of each other.
    phrases = CFG["typing"]
    n = len(phrases)
    period = 4.0
    T = n * period
    fs = 18
    tx0 = 102
    rotator = []
    for i, p in enumerate(phrases):
        w = len(p) * fs * 0.6
        rotator.append(
            f'<g class="ph ph{i}" opacity="{1 if i == 0 else 0}" style="animation-delay:{i * period:.0f}s">'
            f'<text x="{tx0}" y="334" textLength="{w:.1f}" lengthAdjust="spacing" '
            f'font-family="{MONO}" font-size="{fs}" fill="{c["strong"]}">{x(p)}</text>'
            f'<rect class="blink" x="{tx0 + w + 5:.1f}" y="318" width="9" height="21" rx="1.5" fill="{A}"/></g>')
    share = 100 / n
    rot_css = (f".ph{{opacity:0;animation:ph {T:.0f}s ease-in-out infinite backwards}}"
               f"@keyframes ph{{0%{{opacity:0;transform:translateY(10px)}}"
               f"{share * 0.12:.1f}%,{share * 0.85:.1f}%{{opacity:1;transform:translateY(0)}}"
               f"{share:.1f}%,100%{{opacity:0;transform:translateY(-10px)}}}}"
               f"@media (prefers-reduced-motion: reduce){{.ph0{{opacity:1}}}}")

    # Stats row
    items = [(CFG["years"], "years shipping"), (str(stats["packages"]), "pub.dev packages"),
             (str(stats["repos"]), "open-source repos"), (str(stats["stars"]), "stars earned")]
    stat_svg = ""
    for i, (num, label) in enumerate(items):
        sx = 72 + i * 158
        stat_svg += (f'<text x="{sx}" y="388" font-family="{SANS}" font-size="28" font-weight="750" fill="{c["text"]}" letter-spacing="-0.5">{x(num)}</text>'
                     f'<text x="{sx}" y="412" font-family="{MONO}" font-size="13" fill="{c["muted"]}">{x(label)}</text>')
        if i:
            stat_svg += f'<rect x="{sx - 20}" y="368" width="1" height="46" fill="{c["faint"]}"/>'

    # Phone position; chips are laid out around it with a clear gap on both sides.
    px, py, pw, ph = 846, 28, 214, 384
    gap = 18

    def chip_w(label: str) -> float:
        return len(label) * 8.1 + 40

    right = px + pw + gap
    left = [("Flutter", "#54C5F8", 84, 0, 0), ("Python", "#FFD43B" if dark else "#3572A5", 212, 1.4, 20),
            ("Ollama", c["text"], 340, 2.6, 4)]
    chips = [(lbl, col, px - gap - chip_w(lbl) - inset, cy_, d) for lbl, col, cy_, d, inset in left]
    chips += [("Kotlin", "#A97BFF", right, 98, 0.8), ("Swift", "#F05138", right + 10, 246, 2.0),
              ("Gemini", "#8E75FF", right, 392, 3.2)]
    chip_svg = ""
    for i, (label, col, cx_, cy_, delay) in enumerate(chips):
        w = chip_w(label)
        chip_svg += (f'<g class="float" style="animation-delay:-{delay}s">'
                     f'<rect x="{cx_:.1f}" y="{cy_}" width="{w:.1f}" height="34" rx="17" fill="{c["chip"]}" stroke="{c["border"]}"/>'
                     f'<circle cx="{cx_ + 17:.1f}" cy="{cy_ + 17}" r="4.5" fill="{col}"/>'
                     f'<text x="{cx_ + 29:.1f}" y="{cy_ + 22}" font-family="{MONO}" font-size="13" font-weight="600" fill="{c["strong"]}">{x(label)}</text></g>')

    # Phone mock-up with an on-device assistant
    sx, sy, sw, sh = px + 9, py + 9, pw - 18, ph - 18
    ocx, ocy = sx + sw / 2, 152
    phone = f'''
<g filter="url(#shadow)"><rect x="{px}" y="{py}" width="{pw}" height="{ph}" rx="40" fill="{c["phone"]}" stroke="{c["border"]}" stroke-width="1.5"/></g>
<rect x="{sx}" y="{sy}" width="{sw}" height="{sh}" rx="31" fill="url(#screen)"/>
<rect x="{ocx - 30}" y="{sy + 10}" width="60" height="17" rx="8.5" fill="{c["phone"]}"/>
<text x="{sx + 16}" y="{sy + 56}" font-family="{SANS}" font-size="14" font-weight="700" fill="{c["text"]}">Assistant</text>
<rect x="{sx + sw - 82}" y="{sy + 43}" width="68" height="19" rx="9.5" fill="{c["ok"]}" fill-opacity="0.14"/>
<circle cx="{sx + sw - 71}" cy="{sy + 52.5}" r="3" fill="{c["ok"]}"/>
<text x="{sx + sw - 63}" y="{sy + 56.5}" font-family="{MONO}" font-size="10" font-weight="600" fill="{c["ok"]}">on-device</text>
<circle class="ring" cx="{ocx}" cy="{ocy}" r="30" fill="none" stroke="{A}" stroke-width="1.5"/>
<circle class="ring r2" cx="{ocx}" cy="{ocy}" r="30" fill="none" stroke="{A2}" stroke-width="1.5"/>
<circle class="orb" cx="{ocx}" cy="{ocy}" r="30" fill="url(#orb)"/>
<g class="u1"><rect x="{sx + sw - 152}" y="206" width="140" height="32" rx="13" fill="url(#name)"/>
<text x="{sx + sw - 140}" y="226" textLength="116" lengthAdjust="spacingAndGlyphs" font-family="{SANS}" font-size="11.5" font-weight="600" fill="#fff">Summarize my notes</text></g>
<g class="dots" opacity="0"><rect x="{sx + 12}" y="250" width="56" height="28" rx="13" fill="{c["surface"]}"/>
<circle class="d d1" cx="{sx + 28}" cy="264" r="3.2" fill="{c["muted"]}"/><circle class="d d2" cx="{sx + 40}" cy="264" r="3.2" fill="{c["muted"]}"/><circle class="d d3" cx="{sx + 52}" cy="264" r="3.2" fill="{c["muted"]}"/></g>
<g class="a1"><rect x="{sx + 12}" y="250" width="168" height="50" rx="13" fill="{c["surface"]}"/>
<text x="{sx + 24}" y="270" textLength="140" lengthAdjust="spacingAndGlyphs" font-family="{SANS}" font-size="11.5" fill="{c["text"]}">Done: 3 key points found.</text>
<text x="{sx + 24}" y="289" textLength="130" lengthAdjust="spacingAndGlyphs" font-family="{SANS}" font-size="11.5" fill="{c["text"]}">Ran 100% on your phone.</text></g>
<g class="m1"><text x="{sx + 14}" y="322" textLength="150" lengthAdjust="spacingAndGlyphs" font-family="{MONO}" font-size="10" fill="{c["muted"]}">⚡ 42 tok/s · 0 bytes sent</text></g>
<rect x="{sx + 10}" y="{sy + sh - 48}" width="{sw - 20}" height="34" rx="17" fill="{c["surface"]}"/>
<text x="{sx + 26}" y="{sy + sh - 26.5}" font-family="{SANS}" font-size="11.5" fill="{c["muted"]}">Ask anything…</text>
<circle cx="{sx + sw - 27}" cy="{sy + sh - 31}" r="12" fill="url(#name)"/>
<path d="M{sx + sw - 27} {sy + sh - 25.5}v-11m-4.5 4.5l4.5-4.5 4.5 4.5" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
'''

    blob_op = c["glow"]
    first_w = text_w(first + " ", 76) * 0.93
    return f'''{svg_open(W, H, f"{first} {last}, mobile and AI engineer")}
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{c["bg"]}"/><stop offset="1" stop-color="{c["bg2"]}"/></linearGradient>
<radialGradient id="b1"><stop offset="0" stop-color="{A}" stop-opacity="{blob_op}"/><stop offset="1" stop-color="{A}" stop-opacity="0"/></radialGradient>
<radialGradient id="b2"><stop offset="0" stop-color="{A2}" stop-opacity="{blob_op}"/><stop offset="1" stop-color="{A2}" stop-opacity="0"/></radialGradient>
<radialGradient id="b3"><stop offset="0" stop-color="{A3}" stop-opacity="{blob_op * 0.8:.2f}"/><stop offset="1" stop-color="{A3}" stop-opacity="0"/></radialGradient>
<linearGradient id="name" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="420" y2="0" spreadMethod="reflect">
<stop offset="0" stop-color="{A}"/><stop offset="0.5" stop-color="{A2}"/><stop offset="1" stop-color="{A3}"/>
<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="840 0" dur="9s" repeatCount="indefinite"/></linearGradient>
<radialGradient id="orb" cx="0.38" cy="0.32" r="0.75"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0.95"/><stop offset="0.35" stop-color="{A}"/><stop offset="1" stop-color="{A2}"/></radialGradient>
<linearGradient id="screen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c["screen"]}"/><stop offset="1" stop-color="{c["bg2"]}"/></linearGradient>
<pattern id="grid" width="44" height="44" patternUnits="userSpaceOnUse"><path d="M44 0H0V44" fill="none" stroke="{c["grid"]}" stroke-opacity="{c["grid_op"]}"/></pattern>
<radialGradient id="fade" cx="0.62" cy="0.45" r="0.62"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>
<mask id="gm"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>
<clipPath id="frame"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="28"/></clipPath>
<filter id="shadow" x="-30%" y="-20%" width="160%" height="150%"><feDropShadow dx="0" dy="18" stdDeviation="20" flood-color="#000" flood-opacity="{0.55 if dark else 0.14}"/></filter>
</defs>
<style>
.blob{{animation:drift 18s ease-in-out infinite alternate}}
.blob.k2{{animation-duration:22s;animation-direction:alternate-reverse}}
.blob.k3{{animation-duration:26s}}
@keyframes drift{{0%{{transform:translate(0,0)}}50%{{transform:translate(60px,-30px)}}100%{{transform:translate(-40px,30px)}}}}
.pulse{{transform-origin:94px 75px;animation:pulse 2.4s ease-out infinite}}
@keyframes pulse{{0%{{transform:scale(1);opacity:.7}}100%{{transform:scale(2.8);opacity:0}}}}
.blink{{animation:blink 1s steps(1) infinite}}
@keyframes blink{{50%{{opacity:0}}}}
.float{{animation:float 6s ease-in-out infinite}}
@keyframes float{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-9px)}}}}
.ring{{transform-origin:{ocx}px {ocy}px;animation:ring 3s ease-out infinite}}
.r2{{animation-delay:1.5s}}
@keyframes ring{{0%{{transform:scale(1);opacity:.8}}100%{{transform:scale(1.9);opacity:0}}}}
.orb{{transform-origin:{ocx}px {ocy}px;animation:breathe 4s ease-in-out infinite}}
@keyframes breathe{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.07)}}}}
.u1{{animation:u1 10s infinite}}.dots{{animation:dots 10s infinite}}.a1{{animation:a1 10s infinite}}.m1{{animation:m1 10s infinite}}
@keyframes u1{{0%,5%{{opacity:0;transform:translateY(10px)}}11%,92%{{opacity:1;transform:translateY(0)}}100%{{opacity:0}}}}
@keyframes dots{{0%,14%{{opacity:0}}18%,32%{{opacity:1}}35%,100%{{opacity:0}}}}
@keyframes a1{{0%,33%{{opacity:0;transform:translateY(10px)}}39%,92%{{opacity:1;transform:translateY(0)}}100%{{opacity:0}}}}
@keyframes m1{{0%,45%{{opacity:0}}51%,92%{{opacity:1}}100%{{opacity:0}}}}
.d{{animation:bounce 1s ease-in-out infinite}}.d2{{animation-delay:.15s}}.d3{{animation-delay:.3s}}
@keyframes bounce{{0%,60%,100%{{transform:translateY(0)}}30%{{transform:translateY(-4px)}}}}
{rot_css}
{REDUCED}
</style>
<g clip-path="url(#frame)">
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<g class="blob"><circle cx="230" cy="70" r="300" fill="url(#b1)"/></g>
<g class="blob k2"><circle cx="760" cy="420" r="330" fill="url(#b2)"/></g>
<g class="blob k3"><circle cx="1110" cy="60" r="260" fill="url(#b3)"/></g>
<rect width="{W}" height="{H}" fill="url(#grid)" mask="url(#gm)"/>
</g>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="28" fill="none" stroke="{c["border"]}"/>

<rect x="72" y="56" width="262" height="38" rx="19" fill="{c["ok"]}" fill-opacity="0.10" stroke="{c["ok"]}" stroke-opacity="0.35"/>
<circle class="pulse" cx="94" cy="75" r="5" fill="{c["ok"]}"/>
<circle cx="94" cy="75" r="5" fill="{c["ok"]}"/>
<text x="110" y="80.5" font-family="{SANS}" font-size="15" font-weight="600" fill="{c["strong"]}">{x(CFG["status"])}</text>

<text x="74" y="136" font-family="{MONO}" font-size="15" font-weight="600" letter-spacing="3.5" fill="{A}">{x(CFG["role"])}</text>
<text x="70" y="210" font-family="{SANS}" font-size="76" font-weight="800" letter-spacing="-2.5" fill="{c["text"]}">{x(first)} <tspan fill="url(#name)">{x(last)}</tspan></text>
<text font-family="{SANS}" font-size="21" fill="{c["muted"]}"><tspan x="73" y="254">{x(CFG["tagline"][0])}</tspan><tspan x="73" y="284">{x(CFG["tagline"][1])}</tspan></text>

<text x="74" y="334" font-family="{MONO}" font-size="{fs}" font-weight="700" fill="{A}">❯</text>
{"".join(rotator)}

{stat_svg}
{phone}
{chip_svg}
</svg>
'''


# --------------------------------------------------------------------------- cards

def card(theme: str, *, title: str, subtitle: str, blurb: str, tags: list[str], icon: str,
         accent: str, stats: str, badge: str | None = None) -> str:
    c = THEMES[theme]
    a1, a2 = ACCENTS[accent]
    W, H = 580, 236
    lines = textwrap.wrap(blurb, 54)
    if len(lines) > 2:
        print(f"! blurb for {title!r} wraps to {len(lines)} lines; keep it to 2 (about 100 chars)", file=sys.stderr)
    lines = lines[:2]

    tags_svg, tx = "", 28.0
    stats_w = text_w(stats, 13, True)
    for t in tags:
        w, s = pill(tx, H - 58, t, size=12, fill=a1, fill_op=0.10 if theme == "dark" else 0.08,
                    stroke=c["border"], color=c["strong"])
        if tx + w > W - 40 - stats_w:
            break
        tags_svg += s
        tx += w + 8

    badge_svg = ""
    if badge:
        _, badge_svg = pill(0, 0, badge, size=11, fill=a1, fill_op=0.16, stroke=a1, color=a1 if theme == "dark" else c["text"], weight=700)
        bw = text_w(badge, 11, True) + 24
        badge_svg = f'<g transform="translate({W - 28 - bw:.1f} 30)">{badge_svg}</g>'

    blurb_svg = "".join(f'<tspan x="28" y="{124 + i * 26}">{x(l)}</tspan>' for i, l in enumerate(lines))
    return f'''{svg_open(W, H, f"{title}: {blurb}")}
<defs>
<linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a1}"/><stop offset="1" stop-color="{a2}"/></linearGradient>
<radialGradient id="glow" cx="1" cy="0" r="1"><stop offset="0" stop-color="{a1}" stop-opacity="{c["card_glow"]}"/><stop offset="0.6" stop-color="{a2}" stop-opacity="0"/></radialGradient>
<linearGradient id="edge" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{a1}" stop-opacity="0"/><stop offset="0.5" stop-color="{a1}" stop-opacity="0.9"/><stop offset="1" stop-color="{a2}" stop-opacity="0"/></linearGradient>
<clipPath id="c"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="20"/></clipPath>
</defs>
<g clip-path="url(#c)">
<rect width="{W}" height="{H}" fill="{c["card"]}"/>
<rect width="{W}" height="{H}" fill="url(#glow)"/>
<rect x="60" y="1" width="{W - 120}" height="1.5" fill="url(#edge)"/>
</g>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="20" fill="none" stroke="{c["border"]}"/>
<rect x="28" y="28" width="52" height="52" rx="14" fill="url(#g)"/>
<g transform="translate(40 40) scale(1.17)" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICONS[icon]}</g>
<text x="98" y="52" font-family="{MONO}" font-size="21" font-weight="700" fill="{c["text"]}">{x(title)}</text>
<text x="98" y="76" font-family="{MONO}" font-size="13" fill="{c["muted"]}">{x(subtitle)}</text>
{badge_svg}
<text font-family="{SANS}" font-size="17" fill="{c["strong"]}">{blurb_svg}</text>
{tags_svg}
<text x="{W - 28}" y="{H - 39}" text-anchor="end" font-family="{MONO}" font-size="13" fill="{c["muted"]}">{x(stats)}</text>
</svg>
'''


# --------------------------------------------------------------------------- section header / stats / footer

def section(theme: str, idx: str, title: str, kicker: str) -> str:
    c = THEMES[theme]
    W, H = 1000, 72
    return f'''{svg_open(W, H, title)}
<defs>
<linearGradient id="l" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{c["accent"]}"/><stop offset="0.35" stop-color="{c["accent2"]}" stop-opacity="0.6"/><stop offset="1" stop-color="{c["accent2"]}" stop-opacity="0"/></linearGradient>
<linearGradient id="s" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.5" stop-color="#fff" stop-opacity="{0.9 if theme == "dark" else 0.0}"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
</defs>
<style>.sweep{{animation:sweep 7s ease-in-out infinite}}@keyframes sweep{{0%{{transform:translateX(-160px)}}60%,100%{{transform:translateX(1000px)}}}}{REDUCED}</style>
<text x="0" y="42" font-family="{MONO}" font-size="15" font-weight="700" fill="{c["accent"]}">{x(idx)}</text>
<text x="38" y="44" font-family="{SANS}" font-size="30" font-weight="800" letter-spacing="-0.6" fill="{c["text"]}">{x(title)}</text>
<text x="{W}" y="43" text-anchor="end" font-family="{MONO}" font-size="14" fill="{c["muted"]}">{x(kicker)}</text>
<rect x="0" y="62" width="{W}" height="2" rx="1" fill="url(#l)"/>
<rect class="sweep" x="0" y="62" width="160" height="2" fill="url(#s)"/>
</svg>
'''


def stats_card(theme: str, s: dict) -> str:
    c = THEMES[theme]
    W, H = 1000, 312
    tiles = [
        ("STARS EARNED", f"{s['stars']}", "on original repositories"),
        ("PUBLIC REPOS", f"{s['repos']}", f"{s['followers']} followers"),
        ("PUB.DEV PACKAGES", f"{s['packages']}", f"avg {s['avg_points']} / 160 pub points"),
        ("PUB DOWNLOADS", f"{s['dl30']:,}", "across packages, last 30 days"),
    ]
    tw, gap = 235, 20
    tiles_svg = ""
    accents = [c["accent"], c["accent2"], c["accent3"], c["ok"]]
    for i, (label, num, sub) in enumerate(tiles):
        tx = i * (tw + gap)
        tiles_svg += (f'<rect x="{tx + 0.5}" y="0.5" width="{tw - 1}" height="136" rx="18" fill="{c["card"]}" stroke="{c["border"]}"/>'
                      f'<rect x="{tx + 22}" y="24" width="18" height="3" rx="1.5" fill="{accents[i]}"/>'
                      f'<text x="{tx + 22}" y="50" font-family="{MONO}" font-size="12" font-weight="600" letter-spacing="1.2" fill="{c["muted"]}">{x(label)}</text>'
                      f'<text x="{tx + 21}" y="96" font-family="{SANS}" font-size="40" font-weight="800" letter-spacing="-1" fill="{c["text"]}">{x(num)}</text>'
                      f'<text x="{tx + 22}" y="120" font-family="{SANS}" font-size="14" fill="{c["muted"]}">{x(sub)}</text>')

    # Language bar
    langs = s["languages"]
    total = sum(v for _, v in langs) or 1
    bx, by, bw = 24, 210, W - 48
    seg, acc = "", 0.0
    legend = ""
    for i, (name, v) in enumerate(langs):
        w = bw * v / total
        col = LANG_COLORS.get(name, "#8B949E")
        seg += f'<rect x="{bx + acc:.1f}" y="{by}" width="{max(w - 2, 1):.1f}" height="12" fill="{col}"/>'
        acc += w
        lx = 24 + (i % 4) * 238
        ly = 254 + (i // 4) * 28
        legend += (f'<circle cx="{lx + 5}" cy="{ly - 4.5}" r="5" fill="{col}"/>'
                   f'<text x="{lx + 18}" y="{ly}" font-family="{SANS}" font-size="14" font-weight="600" fill="{c["strong"]}">{x(name)} '
                   f'<tspan font-family="{MONO}" font-weight="400" fill="{c["muted"]}">{100 * v / total:.0f}%</tspan></text>')
    return f'''{svg_open(W, H, "GitHub and pub.dev statistics")}
<defs><clipPath id="bar"><rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6"/></clipPath></defs>
{tiles_svg}
<rect x="0.5" y="156.5" width="{W - 1}" height="{H - 157}" rx="18" fill="{c["card"]}" stroke="{c["border"]}"/>
<text x="24" y="190" font-family="{MONO}" font-size="12" font-weight="600" letter-spacing="1.2" fill="{c["muted"]}">LANGUAGES · BY REPOSITORY</text>
<text x="{W - 24}" y="190" text-anchor="end" font-family="{MONO}" font-size="12" fill="{c["muted"]}">auto-updated {s['date']}</text>
<rect x="{bx}" y="{by}" width="{bw}" height="12" rx="6" fill="{c["track"]}"/>
<g clip-path="url(#bar)">{seg}</g>
{legend}
</svg>
'''


def footer(theme: str) -> str:
    c = THEMES[theme]
    W, H = 1000, 170
    return f'''{svg_open(W, H, "Let's build something remarkable")}
<defs>
<linearGradient id="t" gradientUnits="userSpaceOnUse" x1="250" y1="0" x2="750" y2="0" spreadMethod="reflect">
<stop offset="0" stop-color="{c["accent"]}"/><stop offset="0.5" stop-color="{c["accent2"]}"/><stop offset="1" stop-color="{c["accent3"]}"/>
<animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="1000 0" dur="10s" repeatCount="indefinite"/></linearGradient>
<radialGradient id="h" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{c["accent2"]}" stop-opacity="{c["glow"] * 0.6:.2f}"/><stop offset="1" stop-color="{c["accent2"]}" stop-opacity="0"/></radialGradient>
</defs>
<ellipse cx="500" cy="80" rx="420" ry="90" fill="url(#h)"/>
<text x="500" y="76" text-anchor="middle" font-family="{SANS}" font-size="40" font-weight="800" letter-spacing="-1.2" fill="{c["text"]}">Let’s build something <tspan fill="url(#t)">remarkable.</tspan></text>
<text x="500" y="114" text-anchor="middle" font-family="{MONO}" font-size="15" fill="{c["muted"]}">mobile apps  ·  on-device AI  ·  autonomous agents  ·  open source</text>
<rect x="400" y="140" width="200" height="2" rx="1" fill="url(#t)"/>
</svg>
'''


# --------------------------------------------------------------------------- main

def main() -> None:
    d = collect()
    repos = d["repos"]
    own = {k: v for k, v in repos.items() if not v["fork"]}
    pkg_ids = [p["id"] for p in CFG["packages"]] + [p["id"] for p in CFG["more_packages"]]
    pub = {k: v for k, v in d["pub"].items() if k in pkg_ids}

    langs: dict[str, int] = {}
    for v in own.values():
        if v["language"]:
            langs[v["language"]] = langs.get(v["language"], 0) + 1
    top = sorted(langs.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(top) > 7:
        top = top[:7] + [("Other", sum(v for _, v in top[7:]))]

    stats = {
        "stars": sum(v["stars"] for v in own.values()),
        "repos": len(own),
        "followers": d["user"].get("followers", 0),
        "packages": len(pkg_ids),
        "dl30": sum(p["dl30"] for p in pub.values()),
        "avg_points": round(sum(p["points"] for p in pub.values()) / max(len(pub), 1)),
        "languages": top,
        "date": dt.date.today().isoformat(),
    }

    ASSETS.mkdir(exist_ok=True)
    out: dict[str, str] = {}
    for t in THEMES:
        out[f"hero-{t}.svg"] = hero(t, stats)
        out[f"stats-{t}.svg"] = stats_card(t, stats)
        out[f"footer-{t}.svg"] = footer(t)
        for idx, key, title, kicker in [
            ("01", "now", "Now", "what I'm shipping"),
            ("02", "packages", "Open-source packages", f"{stats['packages']} on pub.dev"),
            ("03", "projects", "Selected projects", "apps · agents · local AI"),
            ("04", "stack", "Toolkit", "what I build with"),
            ("05", "activity", "Activity", "live from GitHub & pub.dev"),
        ]:
            out[f"section-{key}-{t}.svg"] = section(t, idx, title, kicker)

        for p in CFG["packages"]:
            m = pub.get(p["id"], {})
            likes = m.get("likes", 0)
            st = (f"♥ {likes}  ·  " if likes else "") + f"{m.get('points', 0)} pts"
            out[f"pkg-{p['id']}-{t}.svg"] = card(
                t, title=p["id"], subtitle=f"pub.dev  ·  v{m.get('version', '–')}", blurb=p["blurb"], tags=p["tags"],
                icon=p["icon"], accent=p["accent"], stats=st, badge=p.get("badge"))

        for p in CFG["projects"]:
            r = repos.get(p["repo"], {})
            st = f"★ {r.get('stars', 0)}"
            out[f"proj-{p['repo']}-{t}.svg"] = card(
                t, title=p["title"], subtitle=f"{r.get('language') or 'Code'}  ·  github.com/{CFG['user']}",
                blurb=p["blurb"], tags=p["tags"], icon=p["icon"], accent=p["accent"], stats=st)

    for name, svg in out.items():
        (ASSETS / name).write_text(svg, "utf-8", newline="\n")
    print(f"wrote {len(out)} SVGs | {stats['stars']} stars | {stats['repos']} repos | {stats['dl30']} pub downloads/30d")


if __name__ == "__main__":
    main()
