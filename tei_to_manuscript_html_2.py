#!/usr/bin/env python3
"""
tei_to_manuscript_html_2.py

Render a Saktumiva-flavoured TEI transcription as a facsimile-like HTML page
that imitates the physical manuscript: one paper leaf per <pb>, one visual row
per <lb>, double ruled borders, marginal notes in the margins, supralinear /
infralinear additions above / below the writing line, top / bottom notes in
the upper / lower margin, and editorial information in a separate colour layer.

A plain reading text (.txt) is written next to the HTML.

Usage:
    python tei_to_manuscript_html_2.py INPUT.xml [OUTPUT.html]
           [--pdf PATH | --no-pdf] [--pages 0001_2,0010_1-0012_2]

In the page: "Manuscript" shows the text as written, with a caret under the
line where each marginal note belongs; "Reading" applies the corrections and
weaves the marginal notes into the text; "Editorial layer" toggles the
colour-coded editorial marks.
"""

import argparse
import math
import os
import random
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from html import escape

TEI = "{http://www.tei-c.org/ns/1.0}"
XMLID = "{http://www.w3.org/XML/1998/namespace}id"

# Marginal notes which are part of the page furniture (running titles, folio
# numbers).  They are drawn in the margin without an insertion mark.
FURNITURE = {
    "HND": "Running title (left margin)",
    "CSP": "Short title (left margin)",
    "FOLIO": "Folio number (left margin)",
    "FR": "Folio number (right margin)",
}

DEL_RENDS = {
    "lightened": "deleted by lightening the ink",
    "smudge-out": "deleted by smudging",
    "supra-mark": "deleted with marks above",
    "infra-mark": "deleted with marks below",
    "supra-equal": "deleted with an ‘=’ mark above",
}


def lname(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def attr(s):
    return escape(s or "", quote=True)


def norm_place(place):
    place = (place or "").strip().lower()
    if place in ("infraalinear", "infra-linear", "below"):
        return "infralinear"
    if place in ("supra-linear", "above", "interlinear"):
        return "supralinear"
    if place in ("margin-left",):
        return "left"
    if place in ("margin-right",):
        return "right"
    return place


def orphan_base(s):
    """A vowel sign or other combining mark with no consonant before it (a
    split akṣara at a line start, or a sign added above the line) is given an
    invisible no-break-space base so browsers do not draw a dotted circle."""
    if s and unicodedata.category(s[0]) in ("Mn", "Mc"):
        return "\u00a0" + s
    return s


def folio_label(n):
    m = re.match(r"^0*(\d+)_(\d)$", n or "")
    if not m:
        return f"page {n}"
    side = {"1": "r", "2": "v"}.get(m.group(2), "/" + m.group(2))
    return f"f. {m.group(1)}{side}"


# ---------------------------------------------------------------- model --

class Line:
    def __init__(self, n, brk):
        self.n = n
        self.brk = brk
        self.parts = []
        self.left = []
        self.right = []

    def html(self):
        return "".join(self.parts)


class Page:
    def __init__(self, n, seq):
        self.n = n
        self.seq = seq
        self.lines = []
        self.top = []
        self.bottom = []
        self.apparatus = []
        self.prelude = []     # footnote marks met before the first line


# -------------------------------------------------------------- builder --

class Builder:
    """Streams the TEI tree into pages and lines.

    Inline wrappers (<hi>, <quote>, <unclear>, ...) may contain <lb>/<pb>.
    They are kept on a stack, closed at every line end and re-opened at the
    start of the next line, so every rendered line is well-formed HTML.
    Positioned material (marginal notes, additions) is rendered by a nested
    builder in `mini` mode, which yields a single fragment.
    """

    def __init__(self, ctx, mini=False):
        self.ctx = ctx
        self.mini = mini
        self.stack = []
        self.page = None
        self.line = None
        self.pending = []
        self.fresh = True       # at a line start: no akṣara written yet
        self.insitu = False     # inside a <subst> overwritten in situ
        if mini:
            self.line = Line("", "")

    # -- low level output
    def out(self, s):
        if self.mini:
            self.line.parts.append(s)
            return
        if self.line is None:
            if self.page is None:
                self.new_page("", implicit=True)
            self.new_line("", None)
        self.line.parts.append(s)

    def text(self, s):
        if not s:
            return
        s = re.sub(r"\s+", " ", s)
        if not self.mini and self.line is None and not s.strip():
            return
        if self.fresh and s.strip():
            s = orphan_base(s.lstrip())
            self.fresh = False
        self.out(escape(s, quote=False))

    def push(self, open_html, close_html):
        self.stack.append((open_html, close_html))
        if self.line is not None:
            self.line.parts.append(open_html)

    def pop(self):
        _, close_html = self.stack.pop()
        if self.line is not None:
            self.line.parts.append(close_html)

    def close_line(self):
        if self.line is not None:
            for _, c in reversed(self.stack):
                self.line.parts.append(c)
        self.line = None

    def new_line(self, n, brk):
        self.close_line()
        if self.page is None:
            self.new_page("", implicit=True)
        self.line = Line(n, brk)
        self.fresh = True
        self.page.lines.append(self.line)
        for o, _ in self.stack:
            self.line.parts.append(o)
        self.line.parts.extend(self.pending)
        self.pending = []

    def new_page(self, n, implicit=False):
        self.close_line()
        seq = self.ctx.page_seq
        if not implicit:
            self.ctx.page_seq += 1
            seq = self.ctx.page_seq
            if n in self.ctx.seen_pages:
                self.ctx.warnings.append(f"duplicate <pb n=\"{n}\"> (occurrence #{seq})")
            self.ctx.seen_pages.add(n)
        self.page = Page(n, seq)
        self.ctx.pages.append(self.page)

    def current_line(self):
        if self.line is None:
            self.out("")
        return self.line

    # -- tree walking
    def children(self, el):
        self.text(el.text)
        for c in el:
            self.walk(c)
            self.text(c.tail)

    def fragment(self, el, standalone=True):
        """Render an element's content as one self-contained HTML fragment.
        `standalone` fragments (additions, notes) are written apart from the
        line, so a leading vowel sign gets an invisible base."""
        sub = Builder(self.ctx, mini=True)
        sub.fresh = standalone
        sub.children(el)
        return sub.line.html().strip(" ")

    def wrap(self, el, cls, tip=None, extra=""):
        t = f' data-tip="{attr(tip)}"' if tip else ""
        self.push(f'<span class="{cls}"{t}{extra}>', "</span>")
        self.children(el)
        self.pop()

    def walk(self, el):
        tag = lname(el.tag)
        fn = getattr(self, "t_" + tag, None)
        if fn is None:
            self.children(el)
        else:
            fn(el)

    # milestones
    def t_lb(self, el):
        if self.mini:
            if el.get("break") != "no":
                self.out(" ")
            return
        self.new_line(el.get("n", ""), el.get("break"))

    def t_pb(self, el):
        if self.mini:
            return
        self.new_page(el.get("n", "?"))

    # structure
    def t_div(self, el):
        n = el.get("n", "")
        name = el.get("id") or el.get(XMLID) or el.get("type", "")
        if not self.mini:
            label = f"{n}. {name}" if n else name
            flag = (f'<span class="anchor-up ed ed-flag" data-tip="{attr(el.get("type", "division"))} {attr(label)} begins">'
                    f'<span class="up-t">❡ {escape(label)}</span></span>')
            if self.line is None:
                self.pending.append(flag)
            else:
                self.out(flag)
        self.children(el)

    def t_lg(self, el):
        vid = el.get("id") or el.get(XMLID, "")
        self.wrap(el, "lg", tip=f"Mūla verse {vid}", extra=f' data-verse="{attr(vid)}"')

    def t_quote(self, el):
        src = el.get("source", "")
        names = []
        for part in src.split():
            key = part.lstrip("#")
            names.append(self.ctx.biblio.get(key, key))
        depth = sum(1 for o, _ in self.stack if 'class="quote' in o)
        tip = "Quotation" + (": " + "; ".join(names) if names else "")
        self.wrap(el, f"quote q{min(depth, 2)}", tip=tip)

    def t_hi(self, el):
        rend = el.get("rend", "")
        cls = "red" if rend == "redfont" else "hi-" + re.sub(r"[^\w-]", "", rend)
        self.wrap(el, cls)

    def t_unclear(self, el):
        self.wrap(el, "unclear", tip="Unclear reading")

    def t_surplus(self, el):
        reason = el.get("reason", "")
        tip = "Surplus (written, but superfluous)" + (f": {reason}" if reason else "")
        self.wrap(el, "surplus", tip=tip)

    def t_supplied(self, el):
        self.wrap(el, "supplied", tip="Supplied by the editor")

    def t_del(self, el):
        rend = el.get("rend", "")
        cls = "del del-" + re.sub(r"[^\w-]", "", rend or "plain")
        if self.insitu:         # drawn apart, beneath the new writing
            self.fresh = True
        self.wrap(el, cls, tip="Deleted: " + DEL_RENDS.get(rend, rend or "deletion"))

    def t_choice(self, el):
        orig = el.find(TEI + "orig")
        corr = el.find(TEI + "corr")
        o = self.fragment(orig, standalone=False) if orig is not None else ""
        c = self.fragment(corr, standalone=False) if corr is not None else ""
        self.fresh = False
        tip = f"Manuscript: {''.join(orig.itertext()) if orig is not None else ''} → Correction: {''.join(corr.itertext()) if corr is not None else ''}"
        self.out(
            f'<span class="choice" data-tip="{attr(tip)}"><span class="orig">{o}</span>'
            f'<span class="corr">{c}</span></span>'
        )

    def t_gap(self, el):
        q = el.get("quantity", "1")
        try:
            k = max(1, min(int(q), 30))
        except ValueError:
            k = 1
        tip = f"Gap: {el.get('reason', 'lost')}, {q} {el.get('unit', '')}".strip()
        self.out(f'<span class="gap" data-tip="{attr(tip)}">{"◌" * k}</span>')

    def t_space(self, el):
        q = el.get("quantity", "1")
        try:
            k = max(0.5, float(q))
        except ValueError:
            k = 1
        tip = f"Blank space left by the scribe: {q} {el.get('unit', '')}".strip()
        self.out(f'<span class="space" style="width:{k * 0.95:.2f}em" data-tip="{attr(tip)}"></span>')

    def t_subst(self, el):
        dels = el.findall(TEI + "del")
        adds = el.findall(TEI + "add")
        places = {norm_place(a.get("place")) for a in adds}
        cls = ["subst"]
        if dels:
            cls.append("has-del")
        if dels and "insitu" in places:
            cls.append("insitu")
        kind = "Substitution" if dels and adds else ("Deletion" if dels else "Addition")
        outer, self.insitu = self.insitu, "insitu" in cls
        self.push(f'<span class="{" ".join(cls)}" data-kind="{kind}">', "</span>")
        self.children(el)
        self.pop()
        self.insitu = outer

    def t_add(self, el):
        place = norm_place(el.get("place"))
        body = self.fragment(el)
        tip = f"Added by the scribe ({place or 'unspecified place'})"
        if place == "supralinear":
            self.out(f'<span class="anchor-up add" data-tip="{attr(tip)}"><span class="up-t">{body}</span></span>')
        elif place == "infralinear":
            self.out(f'<span class="anchor-down add" data-tip="{attr(tip)}"><span class="down-t">{body}</span></span>')
        elif place in ("left", "right", "top", "bottom"):
            self.margin(place, body, tip, kind="add")
        else:  # insitu and anything else: written in the line itself
            self.fresh = False
            self.out(f'<span class="add add-insitu" data-tip="{attr(tip)}">{body}</span>')

    def t_note(self, el):
        place = norm_place(el.get("place"))
        nid = el.get("id", "")
        resp = el.get("resp", "")
        if resp == "editorial" or (not place and not nid):
            self.editorial_note(el)
            return
        body = self.fragment(el)
        if place == "supralinear":
            self.out(f'<span class="anchor-up mnote-inline" data-tip="Note written above the line"><span class="up-t">{body}</span></span>')
        elif place == "infralinear":
            self.out(f'<span class="anchor-down mnote-inline" data-tip="Note written below the line"><span class="down-t">{body}</span></span>')
        elif place in ("left", "right", "top", "bottom"):
            if nid in FURNITURE:
                self.margin(place, body, FURNITURE[nid], kind="furniture " + nid.lower(), caret=False)
            else:
                self.margin(place, body, f"Note in the {place} margin", kind="note")
        else:
            self.out(f'<span class="mnote-inline" data-tip="Note ({attr(place)})">{body}</span>')

    def margin(self, place, body, tip, kind, caret=True):
        self.ctx.link_seq += 1
        lid = f"m{self.ctx.link_seq}"
        if self.mini:
            self.out(f'<span class="mnote-inline" data-tip="{attr(tip)}">{body}</span>')
            return
        if caret:
            arrow = {"left": "◂", "right": "▸", "top": "▴", "bottom": "▾"}[place]
            self.out(f'<span class="caret" data-link="{lid}" data-tip="{attr(tip)} — insertion point"></span>'
                     f'<span class="ins-note" data-link="{lid}" data-tip="{attr(tip)}, woven into the text">{body}</span>')
            tip = f"{tip} {arrow}"
        note = f'<span class="mnote {kind}" data-link="{lid}" data-tip="{attr(tip)}">{body}</span>'
        if place in ("left", "right"):
            line = self.current_line()
            (line.left if place == "left" else line.right).append(note)
        else:
            (self.page.top if place == "top" else self.page.bottom).append(note)

    def editorial_note(self, el):
        text = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
        if self.mini:
            self.out(f'<span class="ed ed-fn" data-tip="{attr(text)}">*</span>')
            return
        if self.page is None:
            self.new_page("", implicit=True)
        self.ctx.link_seq += 1
        lid = f"e{self.ctx.link_seq}"
        self.page.apparatus.append((text, lid))
        mark = f'<sup class="ed ed-fn" data-link="{lid}" data-tip="{attr(text)}">{len(self.page.apparatus)}</sup>'
        if self.line is None:       # note before the first <lb> of the page
            self.page.prelude.append(mark)
        else:
            self.out(mark)


class Context:
    def __init__(self, biblio):
        self.biblio = biblio
        self.pages = []
        self.page_seq = 0
        self.seen_pages = set()
        self.link_seq = 0
        self.warnings = []


# ------------------------------------------------------- reading text ---

def reading_text(body):
    """Corrected reading text: corr over orig, no deletions or surplus,
    additions, supplied text and marginal notes woven in; page furniture and
    editorial notes omitted.  One output line per manuscript line."""
    lines = []
    cur = []

    def flush():
        lines.append(re.sub(r"[ \t]+", " ", "".join(cur)).strip())
        cur.clear()

    def walk(el, inside_note=False):
        tag = lname(el.tag)
        if tag in ("del", "orig", "surplus"):
            return
        if tag == "note":
            if el.get("resp") == "editorial" or el.get("id") in FURNITURE:
                return
        if tag == "lb":
            if inside_note:
                if el.get("break") != "no":
                    cur.append(" ")
                return
            flush()
            return
        if tag == "pb":
            flush()
            lines.append(f"[{el.get('n', '?')}]")
            return
        if tag == "gap":
            cur.append("…")
            return
        if tag == "space":
            cur.append(" ")
            return
        if el.text:
            cur.append(re.sub(r"\s+", " ", el.text))
        for c in el:
            walk(c, inside_note or tag == "note")
            if c.tail:
                cur.append(re.sub(r"\s+", " ", c.tail))

    walk(body)
    flush()
    out = []
    for ln in lines:
        if ln == "" and (not out or out[-1] == ""):
            continue
        out.append(ln)
    return "\n".join(x for x in out if x != "").strip() + "\n"


# -------------------------------------------------------------- render ---

# Leaf outline -------------------------------------------------------------
# Units are cqw (1 = 1% of the leaf width); the leaf is about LEAF_H tall.
# Damage stays inside the blank margins (top 3.9, bottom 4.4, sides 8.6 cqw).
LEAF_H = 45.6


def leaf_key(n):
    """Physical leaf of a folio side: '0002_1' and '0002_2' share '0002'."""
    m = re.match(r"^(\d+)_\d$", n or "")
    return m.group(1) if m else None


def is_verso(n):
    return bool(re.match(r"^\d+_2$", n or ""))


def leaf_outline(key):
    """Clip-path polygon of one physical leaf, seen from its recto: a ragged
    edge, worn or snipped corners and, now and then, torn bites and clean cut
    notches.  The verso shows the same outline mirrored top-to-bottom, since
    the leaves are turned over their long axis."""
    rnd = random.Random("leaf-" + key)
    W, H = 100.0, LEAF_H
    rag = rnd.uniform(0.08, 0.42)               # ragged amplitude

    # corners: TL, TR, BR, BL -> ("round", r) | ("snip", a, b) | ("torn", a, b)
    corners = []
    for _ in range(4):
        x = rnd.random()
        if x < 0.16:
            corners.append(("snip", rnd.uniform(0.8, 3.5), rnd.uniform(0.6, 2.8)))
        elif x < 0.30:
            corners.append(("torn", rnd.uniform(2.0, 6.5), rnd.uniform(1.4, 3.4)))
        else:
            corners.append(("round", rnd.uniform(0.25, 1.6)))

    def corner_len(c, along_x):
        if c[0] == "round":
            return c[1]
        return c[1] if along_x else c[2]

    # edge features: (edge, kind, centre 0..1, width, depth)
    max_depth = {"top": 3.2, "bottom": 3.7, "right": 2.0, "left": 2.0}
    feats = []
    for _ in range(rnd.choice((0, 1, 1, 2, 2, 3))):
        edge = rnd.choices(("top", "bottom", "left", "right"), (4, 4, 1, 1))[0]
        x = rnd.random()
        if x < 0.55:                              # torn bite
            feats.append((edge, "tear", rnd.uniform(0.06, 0.94), rnd.uniform(1.5, 9.0),
                          rnd.uniform(0.45, 1.0) * max_depth[edge]))
        elif x < 0.75:                            # narrow split into the margin
            feats.append((edge, "slit", rnd.uniform(0.06, 0.94), rnd.uniform(0.35, 0.9),
                          rnd.uniform(0.6, 1.0) * max_depth[edge]))
        else:                                     # clean cut notch
            feats.append((edge, "cut", rnd.uniform(0.1, 0.9), rnd.uniform(1.2, 5.0),
                          rnd.uniform(0.35, 0.85) * max_depth[edge]))
    frayed = []                                   # stretches with a rougher edge
    for _ in range(rnd.choice((0, 1, 1, 2))):
        frayed.append((rnd.choice(("top", "bottom", "left", "right")),
                       rnd.uniform(0, 1), rnd.uniform(0.1, 0.35)))

    def edge_profile(edge, length, s0, s1):
        """Inward depth along an edge, as (s, depth) with s in cqw."""
        step = 1.1
        knots = [rnd.random() for _ in range(int(length / 6) + 3)]

        def smooth(s):                            # value noise, 6 cqw period
            u = s / 6.0
            i = int(u)
            f = u - i
            f = f * f * (3 - 2 * f)
            return knots[i] * (1 - f) + knots[i + 1] * f

        def rough(s):
            t = s / length
            k = 1.0
            for e, c, w in frayed:
                if e == edge and abs(t - c) < w / 2:
                    k = 3.2
            return rag * k * (0.35 + 0.65 * smooth(s)) + rnd.uniform(0, rag * 0.6 * k)

        mine = [f for f in feats if f[0] == edge]
        spans = [(f[2] * length - f[3] / 2, f[2] * length + f[3] / 2, f) for f in mine]
        spans = [(max(a, s0 + 0.5), min(b, s1 - 0.5), f) for a, b, f in spans if b - a > 0.8]
        pts = []
        s = s0
        while s <= s1:
            if not any(a <= s <= b for a, b, _ in spans):
                pts.append((s, rough(s)))
            s += step
        for a, b, f in spans:
            _, kind, _, _, d = f
            if kind == "cut":                     # clean, straight-sided notch
                slope = rnd.uniform(0.1, 0.45) * (b - a)
                pts += [(a, 0.0), (a + slope, d), (b - slope * rnd.uniform(0.3, 1), d), (b, 0.0)]
            elif kind == "slit":                  # thin crack with a ragged lip
                m = (a + b) / 2 + rnd.uniform(-0.15, 0.15)
                pts += [(a, rag), (m - 0.08, d * 0.55), (m, d), (m + 0.06, d * 0.6), (b, rag)]
            else:                                 # jagged torn bite
                k = rnd.randint(7, 12)
                for i in range(k + 1):
                    u = i / k
                    shape = 1 - abs(2 * u - 1) ** rnd.uniform(1.1, 1.8)
                    pts.append((a + u * (b - a), max(0.0, d * shape * rnd.uniform(0.55, 1.0))))
        pts.sort()
        return pts

    poly = []
    # top edge, left -> right
    tl, tr, br, bl = corners
    a0, a1 = corner_len(tl, True), W - corner_len(tr, True)
    poly += corner_pts(tl, 0, W, H)
    poly += [(sv, d) for sv, d in edge_profile("top", W, a0, a1)]
    poly += corner_pts(tr, 1, W, H)
    b0, b1 = corner_len(tr, False), H - corner_len(br, False)
    poly += [(W - d, sv) for sv, d in edge_profile("right", H, b0, b1)]
    poly += corner_pts(br, 2, W, H)
    c0, c1 = corner_len(br, True), W - corner_len(bl, True)
    poly += [(W - sv, H - d) for sv, d in edge_profile("bottom", W, c0, c1)]
    poly += corner_pts(bl, 3, W, H)
    d0, d1 = corner_len(bl, False), H - corner_len(tl, False)
    poly += [(d, H - sv) for sv, d in edge_profile("left", H, d0, d1)]
    return "polygon(" + ",".join(f"{x / W * 100:.1f}% {y / H * 100:.1f}%" for x, y in poly) + ")"


def corner_pts(c, which, W, H):
    """Points of one corner, clockwise; which: 0 TL, 1 TR, 2 BR, 3 BL."""
    if c[0] == "snip":
        a, b = c[1], c[2]
        local = [(0, b), (a, 0)]                 # TL: from left edge to top edge
    elif c[0] == "torn":                         # corner torn away, jagged
        a, b = c[1], c[2]
        rnd = random.Random(f"{a:.4f}{b:.4f}")
        k = rnd.randint(6, 10)
        local = []
        for i in range(k + 1):
            u = i / k                            # from (0,b) to (a,0), bowed inward
            bow = math.sin(math.pi * u) * rnd.uniform(0.05, 0.3)
            j = rnd.uniform(-0.25, 0.25) if 0 < i < k else 0
            local.append((u * a * (1 + bow) + j, (1 - u) * b * (1 + bow) + j * 0.6))
    else:
        r = c[1]
        local = [(r - r * math.cos(t), r - r * math.sin(t))
                 for t in (i * math.pi / 2 / 4 for i in range(5))]
    out = []
    for x, y in local:                           # rotate TL corner into place
        if which == 0:
            out.append((x, y))
        elif which == 1:
            out.append((W - y, x))
        elif which == 2:
            out.append((W - x, H - y))
        else:
            out.append((y, H - x))
    return out


def leaf_stains(key):
    rnd = random.Random("stain-" + key)
    g = []
    for _ in range(3):
        x, y = rnd.randint(5, 95), rnd.randint(5, 95)
        sz = rnd.randint(18, 40)
        a = rnd.uniform(0.05, 0.12)
        g.append(f"radial-gradient(ellipse {sz}% {sz * 0.8:.0f}% at {x}% {y}%, rgba(150,100,40,{a:.2f}), transparent 70%)")
    return ",".join(g)


def leaf_styles(pages):
    """One CSS rule per physical leaf, shared by its recto and verso."""
    rules = []
    for key in sorted({leaf_key(p.n) for p in pages if leaf_key(p.n)}):
        rules.append(f'.leaf[data-leaf="{key}"]{{--shape:{leaf_outline(key)};--stains:{leaf_stains(key)}}}')
    return "\n".join(rules)


def render_page(page, pdf_rel):
    if not page.lines and not page.top and not page.bottom and not page.apparatus:
        return ""
    pid = f"p{page.seq}"
    label = folio_label(page.n) if page.n else "front matter"
    facs = ""
    if pdf_rel and page.n:
        facs = (f'<a class="facs" href="{attr(pdf_rel)}#page={page.seq + 1}" target="_blank" '
                f'rel="noopener">facsimile · PDF p. {page.seq + 1} ↗</a>')
    h = [f'<section class="folio" id="{pid}" data-n="{attr(page.n)}" data-label="{attr(label)}">']
    h.append(f'<header class="folio-head"><span class="flabel">{escape(label)}</span>'
             f'<span class="fn">{escape(page.n)}</span>{facs}</header>')
    key = leaf_key(page.n)
    leaf_attr = f' data-leaf="{key}"' if key else ""
    side = " verso" if is_verso(page.n) else ""
    h.append(f'<div class="leaf-wrap"><div class="leaf{side}"{leaf_attr}>')
    h.append('<div class="paper-sh"><div class="paper">'
             '<div class="rule rule-l"></div><div class="rule rule-r"></div></div></div>')
    h.append('<div class="mtop">' + "".join(page.top) + "</div>")
    h.append('<div class="lines">')
    for k, ln in enumerate(page.lines):
        inner = ln.html().strip(" ")
        if k == 0:
            inner = "".join(page.prelude) + inner
        cont = ' data-break="no"' if ln.brk == "no" else ""
        h.append(
            f'<div class="row" data-ln="{attr(ln.n)}"{cont}>'
            f'<div class="ml"><span class="lnno">{escape(ln.n)}</span><div class="mstack">{"".join(ln.left)}</div></div>'
            f'<div class="tx"><span class="tx-in">{inner}</span></div>'
            f'<div class="mr"><div class="mstack">{"".join(ln.right)}</div></div>'
            f'</div>'
        )
    h.append("</div>")
    h.append('<div class="mbottom">' + "".join(page.bottom) + "</div>")
    h.append("</div></div>")
    if page.apparatus:
        h.append('<aside class="apparatus"><span class="ap-h">Editorial notes</span><ol>')
        for text, lid in page.apparatus:
            h.append(f'<li data-link="{lid}">{escape(text)}</li>')
        h.append("</ol></aside>")
    h.append("</section>")
    return "".join(h)


CSS = r"""
:root{
  --desk:#2b221c; --desk-2:#3a2e25; --desk-ink:#e9dcc2; --desk-dim:#a8957a;
  --paper:#e7d0a0; --paper-hi:#efdcb3; --paper-edge:#c9a564;
  --ink:#1d140d; --ink-soft:#3a2b1e;
  --vermilion:#b23a24; --vermilion-soft:#c8644c;
  --rule-red:#a63a2c; --rule-ochre:#d2a43a;
  /* editorial layer — mineral pigments that sit well on buff paper */
  --indigo:#2d4a7c; --verdigris:#2f7d64; --ochre-wash:rgba(206,150,32,.33);
  --lac:#8a2f5e; --sepia:#7b6650; --saffron-wash:rgba(232,150,40,.18);
  --lm:8.6%; --gut:2.4%; --rm:8.6%;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--desk);color:var(--desk-ink);
  font-family:"Noto Serif Devanagari","Tiro Devanagari Sanskrit","Kohinoor Devanagari","Devanagari Sangam MN",serif;
  background-image:radial-gradient(ellipse at 50% 0,var(--desk-2),var(--desk) 70%);background-attachment:fixed}
.ui{font-family:"Inter","Segoe UI",system-ui,-apple-system,sans-serif}

/* ---------- toolbar ---------- */
.bar{position:sticky;top:0;z-index:50;display:flex;flex-wrap:wrap;gap:.4rem 1.1rem;align-items:center;
  padding:.55rem 1.2rem;background:rgba(32,25,20,.94);backdrop-filter:blur(6px);
  border-bottom:1px solid #5a4636;font-size:13px}
.bar h1{font-size:15px;font-weight:600;margin:0;color:#f3e6cc;letter-spacing:.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:34rem}
.bar label{display:inline-flex;gap:.35rem;align-items:center;cursor:pointer;color:var(--desk-ink);user-select:none}
.bar input[type=checkbox]{accent-color:var(--vermilion)}
.bar select,.bar button{background:#3d3027;color:var(--desk-ink);border:1px solid #6b5544;border-radius:6px;padding:.25rem .5rem;font:inherit}
.bar button{cursor:pointer}.bar button:hover{background:#4d3c30}
.seg{display:inline-flex;border:1px solid #6b5544;border-radius:7px;overflow:hidden}
.seg button{border:0;border-radius:0;background:transparent}
.seg button[aria-pressed=true]{background:var(--vermilion);color:#fff}
.bar .sp{flex:1}
.legend{display:none;padding:.8rem 1.2rem 1rem;background:rgba(32,25,20,.97);border-bottom:1px solid #5a4636;font-size:13px;
  position:sticky;top:44px;z-index:49}
.legend.open{display:block}
.legend ul{display:flex;flex-wrap:wrap;gap:.5rem 1.4rem;margin:0;padding:0;list-style:none}
.legend li{display:flex;gap:.5rem;align-items:center}
.legend .sw{display:inline-block;min-width:2.4em;padding:0 .35em;border-radius:4px;background:var(--paper);color:var(--ink);
  font-family:"Noto Serif Devanagari",serif;font-size:15px;line-height:1.6;text-align:center;position:relative}
.legend .del,.legend .surplus{display:inline!important}
.legend .caret{display:inline-block!important;color:var(--indigo)}
.legend .caret::before{width:12px;height:9px;left:-6px;top:2px}
.legend .ed-fn{top:-.5em}
.intro{max-width:1500px;margin:1.4rem auto .2rem;padding:0 3rem;color:var(--desk-dim);font-size:13px}
.intro .t{font-size:1.5rem;color:#f2e4c6;margin:0 0 .2rem}
.intro p{margin:.15rem 0}

/* ---------- folio ---------- */
main{padding:.5rem 0 4rem}
.folio{max-width:1500px;margin:1.8rem auto 2.6rem;padding:0 3rem;position:relative}
.folio-head{display:flex;gap:1rem;align-items:baseline;margin:0 0 .45rem .2rem;font-family:"Inter",system-ui,sans-serif;font-size:13px;color:var(--desk-dim)}
.flabel{font-size:15px;color:#f0e2c3;font-weight:600}
.facs{margin-left:auto;color:#d9a77a;text-decoration:none;border-bottom:1px dotted #d9a77a}
.facs:hover{color:#ffcf9e}
.leaf-wrap{container-type:inline-size}
.leaf{position:relative;aspect-ratio:2.218/1;isolation:isolate;
  padding:3.9cqw 0 4.4cqw;display:flex;flex-direction:column;color:var(--ink)}
.paper-sh{position:absolute;inset:0;z-index:-1;pointer-events:none;
  filter:drop-shadow(0 0 .07cqw rgba(105,62,20,.9)) drop-shadow(0 6px 14px rgba(0,0,0,.55)) drop-shadow(0 1px 2px rgba(0,0,0,.4))}
.paper{position:absolute;inset:0;clip-path:var(--shape,inset(0 round 1cqw));
  background-color:var(--paper);
  background-image:var(--stains),
    radial-gradient(ellipse at 50% 45%,var(--paper-hi) 0%,rgba(239,220,179,0) 65%),
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 .45  0 0 0 0 .32  0 0 0 0 .15  0 0 0 .22 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
  box-shadow:inset 0 0 3.2cqw rgba(140,90,30,.45),inset 0 0 .6cqw rgba(110,70,20,.35)}
.leaf.verso .paper{transform:scaleY(-1)}
.rule{position:absolute;top:0;bottom:0;width:calc(var(--gut) * .62);pointer-events:none;
  background:linear-gradient(90deg,transparent 0 6%,var(--rule-red) 6% 20%,transparent 20% 30%,var(--rule-red) 30% 40%,
    var(--rule-ochre) 40% 62%,var(--rule-red) 62% 72%,transparent 72% 86%,var(--rule-red) 86% 96%,transparent 96%);opacity:.82;
  mix-blend-mode:multiply}
.rule-l{left:calc(var(--lm) + var(--gut) * .14)}
.rule-r{right:calc(var(--rm) + var(--gut) * .14)}

.lines{position:relative;flex:1}
.row{display:grid;grid-template-columns:var(--lm) var(--gut) minmax(0,1fr) var(--gut) var(--rm);
  height:1.97cqw;align-items:end;position:relative}
.tx{grid-column:3;align-self:stretch;font-size:1.46cqw;line-height:1;white-space:nowrap;position:relative;min-width:0;
  font-weight:600;letter-spacing:-.005em}
.tx-in{position:absolute;left:0;bottom:.2em;height:1em;display:inline-block;transform-origin:0 50%;white-space:nowrap}
.ml{grid-column:1;position:relative;align-self:stretch}
.mr{grid-column:5;position:relative;align-self:stretch}
.mstack{position:absolute;left:0;right:0;top:.15cqw;padding:0 .7cqw;display:flex;flex-direction:column;gap:.2cqw}
.ml .mstack{align-items:center;text-align:center}
.mr .mstack{align-items:flex-start;text-align:left}
.mnote{font-size:1.04cqw;line-height:1.36;color:var(--ink-soft);white-space:normal;overflow-wrap:break-word;max-width:100%;font-weight:500;
  border-radius:3px;transition:background .15s}
.mnote.furniture{white-space:nowrap}
.mtop,.mbottom{position:absolute;left:calc(var(--lm) + var(--gut));right:calc(var(--rm) + var(--gut));display:flex;
  justify-content:center;gap:2cqw;flex-wrap:wrap}
.mtop{top:.9cqw}
.mbottom{bottom:1.3cqw}
.mtop .mnote,.mbottom .mnote{white-space:nowrap;max-width:60%}
.js .mtop,.js .mbottom{display:block}
.js .mtop .mnote,.js .mbottom .mnote{position:absolute;top:0}
.lnno{position:absolute;left:-3.4cqw;width:2.4cqw;text-align:right;bottom:.45cqw;
  font:500 .78cqw/1 "Inter",system-ui,sans-serif;color:var(--desk-dim);display:none;font-variant-numeric:tabular-nums}
body.lnos .lnno{display:block}

/* ---------- manuscript ink ---------- */
.red{color:var(--vermilion)}
.red .red{color:inherit}
.anchor-up,.anchor-down{position:relative;display:inline-block;width:0;height:0;vertical-align:baseline}
.up-t,.down-t{position:absolute;left:0;transform:translateX(-50%);white-space:nowrap;font-size:.7em;line-height:1;
  pointer-events:auto}
.up-t{bottom:.74em}
.down-t{top:.42em}
.subst{position:relative}
.subst.has-del>.anchor-up>.up-t,.subst.has-del>.anchor-down>.down-t{transform:translateX(calc(-50% - .3em))}
.subst.insitu>.del{position:absolute;left:50%;top:0;line-height:normal;transform:translateX(-50%);z-index:0}
.subst.insitu>.add-insitu{position:relative;z-index:1}
.del-lightened{opacity:.32}
.subst.insitu>.del-lightened{opacity:.28;filter:blur(.25px)}
.del-smudge-out{opacity:.5;filter:blur(.7px);background:radial-gradient(ellipse,rgba(60,40,20,.28),transparent 70%)}
.del-supra-mark{text-decoration:overline dotted var(--ink) .14em;text-decoration-skip-ink:none}
.del-infra-mark{text-decoration:underline dotted var(--ink) .14em;text-underline-offset:.32em;text-decoration-skip-ink:none}
.del-supra-equal{position:relative}
.del-supra-equal::before{content:"=";position:absolute;left:50%;bottom:1.95em;transform:translateX(-50%);
  font:700 .62em/1 "Inter",system-ui,sans-serif;color:var(--ink);pointer-events:none}
.choice .corr{display:none}
.space{display:inline-block;height:.4em;vertical-align:baseline}
.gap{color:rgba(120,90,50,.35);letter-spacing:.05em}
.mnote-inline{font-size:.8em}

/* ---------- editorial layer (body.ed-on) ---------- */
.ed{display:none}
body.ed-on .ed{display:inline-block}
body.ed-on .ed-flag{display:inline-block}
.ed-flag .up-t{font:600 .62em/1 "Inter",system-ui,sans-serif;color:#fff;background:var(--indigo);padding:.18em .45em;border-radius:1em;
  bottom:1.02em;transform:none;letter-spacing:.02em}
.caret{position:relative;display:inline-block;width:0;height:0;font-size:0;color:var(--ink-soft);vertical-align:baseline}
body.ed-on .caret{color:var(--indigo)}
.caret::before{content:"";position:absolute;left:-.34cqw;top:.12cqw;width:.68cqw;height:.48cqw;background:currentColor;
  -webkit-mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 7'><path d='M1 6.2 L5 1 L9 6.2' fill='none' stroke='black' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'/></svg>") center/contain no-repeat;mask:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 7'><path d='M1 6.2 L5 1 L9 6.2' fill='none' stroke='black' stroke-width='1.7' stroke-linecap='round' stroke-linejoin='round'/></svg>") center/contain no-repeat}
.ins-note{display:none}
body.reading .caret{display:none}
body.reading .ins-note{display:inline}
body.reading .mnote:not(.furniture){display:none}
body.ed-on.reading .ins-note{background:rgba(45,74,124,.10);box-shadow:0 0 0 .07em rgba(45,74,124,.22);border-radius:.2em}
.ed-fn{color:var(--indigo);font:700 .55em/0 "Inter",sans-serif;vertical-align:baseline;position:relative;top:-.95em;margin:0 .08em;cursor:help}
body.ed-on .supplied{color:var(--indigo);text-decoration:underline dotted color-mix(in srgb,var(--indigo) 70%,transparent);text-underline-offset:.28em}
body:not(.ed-on) .supplied{color:var(--indigo);opacity:.0;font-size:0}
body:not(.ed-on).reading .supplied{opacity:1;font-size:inherit;color:inherit}
body.ed-on .unclear{background:var(--ochre-wash);border-radius:.25em;box-shadow:0 0 0 .08em var(--ochre-wash)}
body.ed-on .choice{text-decoration:underline wavy color-mix(in srgb,var(--verdigris) 75%,transparent) .06em;text-underline-offset:.3em;text-decoration-skip-ink:none}
body.ed-on .surplus{outline:.06em dashed color-mix(in srgb,var(--sepia) 55%,transparent);outline-offset:.03em;border-radius:.2em}
body.ed-on .quote{text-decoration:underline color-mix(in srgb,var(--lac) 60%,transparent) .075em;text-underline-offset:.14em;text-decoration-skip-ink:auto}
body.ed-on .lg{background:var(--saffron-wash);border-radius:.2em}
body.ed-on .gap{color:var(--sepia)}
body.ed-on .space{background:repeating-linear-gradient(90deg,transparent 0 .3em,color-mix(in srgb,var(--sepia) 45%,transparent) .3em .45em) bottom/100% .07em no-repeat}
body.ed-on .add .up-t,body.ed-on .add .down-t,body.ed-on .add-insitu{text-shadow:0 0 .35em rgba(47,125,100,.35)}
body.ed-on .add .up-t::after,body.ed-on .add .down-t::after{content:"";position:absolute;left:50%;width:.06em;height:.3em;background:var(--verdigris);opacity:.55}
body.ed-on .add .up-t::after{top:100%}
body.ed-on .add .down-t::after{bottom:100%}
body.ed-on .del-lightened,body.ed-on .del-smudge-out{text-decoration:line-through color-mix(in srgb,var(--lac) 65%,transparent) .07em}
body.ed-on .del-supra-mark,body.ed-on .del-infra-mark{text-decoration-color:var(--lac)}
body.ed-on .del-supra-equal::before{color:var(--lac)}
body.ed-on .mnote:not(.furniture){box-shadow:-.18cqw 0 0 color-mix(in srgb,var(--indigo) 55%,transparent);padding-left:.35cqw}
body.ed-on .mr .mnote:not(.furniture){box-shadow:-.18cqw 0 0 color-mix(in srgb,var(--indigo) 55%,transparent)}
body.ed-on .mtop .mnote,body.ed-on .mbottom .mnote{box-shadow:0 .14cqw 0 color-mix(in srgb,var(--indigo) 50%,transparent);padding:0 .2cqw}

/* reading mode: corrected text */
body.reading .choice .orig{display:none}
body.reading .choice .corr{display:inline}
body.reading .del,body.reading .surplus{display:none}
body.reading .anchor-up.add,body.reading .anchor-down.add,body.reading .anchor-up.mnote-inline,body.reading .anchor-down.mnote-inline{display:inline;width:auto;height:auto}
body.reading .add .up-t,body.reading .add .down-t,body.reading .mnote-inline .up-t,body.reading .mnote-inline .down-t{position:static;transform:none;font-size:inherit}
body.reading .add .up-t::after,body.reading .add .down-t::after{display:none}

/* linking highlight: a marginal note and its insertion point in the line */
.hl{background:rgba(45,74,124,.22)!important;border-radius:3px;outline:1px solid rgba(45,74,124,.45)}
.mnote[data-link]{cursor:pointer}
.mnote.pinned{outline:2px solid var(--vermilion)!important}
.caret.hl{background:none!important;outline:none!important;z-index:5;color:var(--vermilion)}
.caret.hl::after{content:"";position:absolute;left:-.13cqw;top:-1.55cqw;width:.26cqw;height:1.5cqw;border-radius:.2cqw;
  background:var(--vermilion);animation:caret-pulse 1.1s ease-in-out infinite}
@keyframes caret-pulse{0%,100%{box-shadow:0 0 0 .15cqw rgba(178,58,36,.45)}50%{box-shadow:0 0 0 .7cqw rgba(178,58,36,0)}}
.row.hl-row .tx{background:linear-gradient(transparent 8%,rgba(45,74,124,.11) 8% 96%,transparent 96%)}
#linkline{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:40;display:none;overflow:visible}
#linkline path{fill:none;stroke:var(--vermilion);stroke-width:1.6;stroke-dasharray:5 4;opacity:.85}
#linkline circle{fill:var(--vermilion)}

/* tooltip */
#tip{position:fixed;z-index:100;pointer-events:none;max-width:28rem;padding:.45rem .65rem;border-radius:7px;
  background:#fbf3e1;color:#2a1e12;border:1px solid #c9a564;box-shadow:0 8px 24px rgba(0,0,0,.35);
  font:13px/1.45 "Inter",system-ui,sans-serif;opacity:0;transition:opacity .12s}
#tip.on{opacity:1}
#tip b{color:var(--indigo)}

/* apparatus */
.apparatus{margin:.9rem .4rem 0;padding:.6rem 1rem .5rem;background:rgba(239,220,179,.08);border-left:3px solid var(--indigo);
  border-radius:0 6px 6px 0;font:13px/1.55 "Inter",system-ui,sans-serif;color:var(--desk-ink)}
.ap-h{font-weight:600;color:#c5d3ef;font-size:12px;letter-spacing:.06em;text-transform:uppercase}
.apparatus ol{margin:.3rem 0 0;padding-left:1.4rem}
.apparatus li.hl{background:rgba(120,150,210,.18)!important;outline:none}

@media (max-width:800px){.folio,.intro{padding:0 1rem}.bar h1{max-width:100%}}

@media print{
  @page{size:A4 landscape;margin:8mm}
  body{background:#fff}
  .bar,.legend,.intro,.facs,#tip{display:none!important}
  .folio{break-after:page;page-break-after:always;margin:0 auto;padding:0;max-width:none}
  .folio-head{color:#555}.flabel{color:#222}
  .paper-sh{filter:none}
  .paper,.red,.rule{-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .apparatus{color:#222;background:none}
  .lnno{color:#999}
}
"""

JS = r"""
(function(){
  const B=document.body; B.classList.add('js');
  const leaves=[...document.querySelectorAll('.leaf')];
  const fs=el=>parseFloat(getComputedStyle(el).fontSize)||16;

  /* --- fit each manuscript line to the writing block, as the scribe did --- */
  function fit(){
    const rows=[];
    leaves.forEach(l=>l.querySelectorAll('.tx').forEach(tx=>{
      const inn=tx.firstElementChild; inn.style.transform=''; inn.style.wordSpacing=''; inn.style.letterSpacing='';
      rows.push({tx,inn});
    }));
    rows.forEach(r=>{r.avail=r.tx.clientWidth-1; r.nat=r.inn.getBoundingClientRect().width; r.f=fs(r.tx);
      r.spaces=(r.inn.innerText.match(/ /g)||[]).length; r.last=!r.tx.parentElement.nextElementSibling;});
    rows.forEach(r=>{
      if(!r.nat) return;
      const d=r.avail-r.nat;
      if(d>0 && !(r.last && d>r.avail*.25)){
        if(r.spaces) r.inn.style.wordSpacing=Math.min(d/r.spaces,r.f*.9)+'px';
        else r.inn.style.letterSpacing=Math.min(d/Math.max(r.inn.innerText.length,1),r.f*.4)+'px';
      }
    });
    rows.forEach(r=>{r.nat2=r.inn.getBoundingClientRect().width;});
    rows.forEach(r=>{ if(r.nat2>r.avail+.5) r.inn.style.transform='scaleX('+(r.avail/r.nat2).toFixed(4)+')'; });
    placeMargins();
  }

  /* --- keep marginal notes from overlapping, place top/bottom notes over their anchors --- */
  function placeMargins(){
    leaves.forEach(leaf=>{
      const L=leaf.getBoundingClientRect();
      ['.ml .mstack','.mr .mstack'].forEach(sel=>{
        let last=-1e9;
        leaf.querySelectorAll(sel).forEach(st=>{
          st.style.transform='';
          if(!st.childElementCount) return;
          const r=st.getBoundingClientRect(); const top=r.top-L.top;
          let shift=0; if(top<last+2) shift=last+2-top;
          if(shift) st.style.transform='translateY('+shift+'px)';
          last=top+shift+r.height;
        });
      });
      ['.mtop','.mbottom'].forEach(sel=>{
        const box=leaf.querySelector(sel); if(!box) return;
        const notes=[...box.children]; if(!notes.length) return;
        const R=box.getBoundingClientRect();
        let rows=[]; let maxBottom=0;
        notes.forEach(n=>{
          n.style.left='0px'; n.style.top='0px';
          const w=n.getBoundingClientRect().width, h=n.getBoundingClientRect().height;
          const a=leaf.querySelector('.caret[data-link="'+n.dataset.link+'"]');
          let cx=R.width/2;
          if(a){const ar=a.getBoundingClientRect(); cx=ar.left-R.left;}
          let x=Math.max(0,Math.min(R.width-w,cx-w/2));
          let row=0;
          while(rows[row] && rows[row]>x-6) row++;
          rows[row]=x+w;
          const y = sel==='.mtop' ? row*h*1.05 : -row*h*1.05 - h;
          n.style.left=x+'px'; n.style.top=y+'px';
        });
      });
    });
  }

  /* --- toggles --- */
  const st=k=>{try{return localStorage.getItem('msv2:'+k)}catch(e){return null}};
  const ss=(k,v)=>{try{localStorage.setItem('msv2:'+k,v)}catch(e){}};
  function bindToggle(id,cls,def){
    const el=document.getElementById(id); if(!el) return;
    const v=st(cls); el.checked = v===null ? def : v==='1';
    B.classList.toggle(cls,el.checked);
    el.addEventListener('change',()=>{B.classList.toggle(cls,el.checked); ss(cls,el.checked?'1':'0'); fit();});
  }
  bindToggle('t-ed','ed-on',true);
  bindToggle('t-ln','lnos',false);
  const mode=st('mode')||'dipl';
  function setMode(m){B.classList.toggle('reading',m==='read');
    document.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.mode===m));ss('mode',m);}
  document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',()=>{setMode(b.dataset.mode);fit();}));
  setMode(mode);
  const lg=document.getElementById('t-legend'), legend=document.querySelector('.legend');
  lg&&lg.addEventListener('click',()=>legend.classList.toggle('open'));

  /* --- navigation --- */
  const sel=document.getElementById('goto');
  sel&&sel.addEventListener('change',()=>{const t=document.getElementById(sel.value); t&&t.scrollIntoView();});
  const folios=[...document.querySelectorAll('.folio')];
  if('IntersectionObserver' in window && sel){
    const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting) sel.value=e.target.id;});},{rootMargin:'-45% 0px -50% 0px'});
    folios.forEach(f=>io.observe(f));
  }
  document.addEventListener('keydown',e=>{
    if(e.target.closest('input,select,textarea')) return;
    if(e.key!=='j'&&e.key!=='k') return;
    const y=window.scrollY+80; let i=folios.findIndex(f=>f.offsetTop>y)-1; if(i<-1) i=folios.length-1; if(i<0) i=0;
    const t=e.key==='j'?folios[Math.min(i+1,folios.length-1)]:folios[Math.max(i-1,0)]; t.scrollIntoView();
  });

  /* --- linked highlighting: marginal note <-> insertion point --- */
  const NS='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(NS,'svg'); svg.id='linkline';
  const path=document.createElementNS(NS,'path'), dot=document.createElementNS(NS,'circle');
  dot.setAttribute('r','3.5'); svg.append(path,dot); document.body.appendChild(svg);
  let active=null, pinned=null;
  const members=id=>[...document.querySelectorAll('[data-link="'+id+'"]')];
  function clearHL(){
    document.querySelectorAll('.hl,.hl-row,.pinned').forEach(x=>x.classList.remove('hl','hl-row','pinned'));
    svg.style.display='none'; active=null;
  }
  function drawLine(){
    if(!active){svg.style.display='none';return;}
    const els=members(active);
    const c=els.find(x=>x.classList.contains('caret'));
    const n=els.find(x=>x.classList.contains('mnote'))||els.find(x=>x.tagName==='LI');
    if(!c||!n||!c.offsetParent||!n.offsetParent){svg.style.display='none';return;}
    const box=c.closest('.folio'); if(svg.parentNode!==box) box.appendChild(svg);
    const B=box.getBoundingClientRect();
    const rel=r=>({left:r.left-B.left,right:r.right-B.left,top:r.top-B.top,bottom:r.bottom-B.top,width:r.width,height:r.height});
    const cr=rel(c.getBoundingClientRect()), nr=rel(n.getBoundingClientRect());
    const f=parseFloat(getComputedStyle(c.closest('.tx')||c).fontSize)||16;
    const cx=cr.left, cy=cr.top+f*.12;
    let x,y;
    if(n.closest('.ml')){x=nr.right+2;y=nr.top+nr.height/2;}
    else if(n.closest('.mr')){x=nr.left-2;y=nr.top+nr.height/2;}
    else if(n.closest('.mtop')){x=nr.left+nr.width/2;y=nr.bottom+1;}
    else if(n.closest('.mbottom')){x=nr.left+nr.width/2;y=nr.top-1;}
    else {x=nr.left+nr.width/2;y=nr.top;}
    const horiz=!!(n.closest('.ml')||n.closest('.mr'));
    const d=horiz?`M${x},${y} C${(x+cx)/2},${y} ${(x+cx)/2},${cy} ${cx},${cy}`
                 :`M${x},${y} C${x},${(y+cy)/2} ${cx},${(y+cy)/2} ${cx},${cy}`;
    path.setAttribute('d',d); dot.setAttribute('cx',cx); dot.setAttribute('cy',cy);
    svg.style.display='block';
  }
  function showHL(id){
    if(active===id) return;
    clearHL(); active=id;
    const els=members(id); els.forEach(x=>x.classList.add('hl'));
    const c=els.find(x=>x.classList.contains('caret'));
    if(c){const r=c.closest('.row'); r&&r.classList.add('hl-row');}
    if(pinned===id) els.forEach(x=>x.classList.contains('mnote')&&x.classList.add('pinned'));
    drawLine();
  }
  document.addEventListener('click',e=>{
    const ln=e.target.closest('[data-link]');
    if(!ln||!ln.dataset.link){ if(pinned){pinned=null; clearHL();} return; }
    const id=ln.dataset.link;
    if(pinned===id){pinned=null; clearHL(); return;}
    pinned=id; active=null; showHL(id);
    // bring the other end into view if it is off screen
    const other=members(id).find(x=>x!==ln && !x.contains(ln));
    if(other){const r=other.getBoundingClientRect();
      if(r.top<60||r.bottom>innerHeight-20) other.scrollIntoView({block:'center',behavior:'smooth'});}
  });
  window.addEventListener('resize',()=>{ if(active) drawLine(); });

  /* --- tooltip --- */
  const tip=document.getElementById('tip'); let cur=null;
  document.addEventListener('mouseover',e=>{
    const t=e.target.closest('[data-tip]');
    const ln=e.target.closest('[data-link]');
    if(!pinned){ if(ln&&ln.dataset.link) showHL(ln.dataset.link); else if(active) clearHL(); }
    if(t){cur=t; tip.textContent=t.dataset.tip; tip.classList.add('on');} else {cur=null; tip.classList.remove('on');}
  });
  document.addEventListener('mousemove',e=>{ if(!cur) return;
    const w=tip.offsetWidth,h=tip.offsetHeight; let x=e.clientX+14,y=e.clientY+18;
    if(x+w>innerWidth-8) x=innerWidth-w-8; if(y+h>innerHeight-8) y=e.clientY-h-12;
    tip.style.left=x+'px'; tip.style.top=y+'px';});

  let to; window.addEventListener('resize',()=>{clearTimeout(to); to=setTimeout(fit,150);});
  (document.fonts&&document.fonts.ready?document.fonts.ready:Promise.resolve()).then(fit);
  fit();
})();
"""

LEGEND = [
    ('<span class="red">॥ १ ॥</span>', "Red ink (rubrication) — as in the manuscript"),
    ('<span class="supplied">ऽ</span>', "Supplied by the editor (indigo)"),
    ('<span class="unclear">ध्मां</span>', "Unclear reading (ochre wash)"),
    ('<span class="choice"><span class="orig">ब</span><span class="corr">व</span></span>', "Orthographic correction — manuscript reading shown; hover for correction (verdigris)"),
    ('<span class="surplus"><span class="red">।</span></span>', "Surplus: written but superfluous (dashed sepia)"),
    ('<span class="quote">उपासनीयं</span>', "Quotation; hover for source (lac underline)"),
    ('<span class="lg">प्रणिपत्य</span>', "Mūla verse (saffron wash)"),
    ('<span class="del del-lightened">ष</span>', "Deletion (lightened / smudged / marked)"),
    ('<span class="subst has-del" style="margin-top:.6em"><span class="del del-supra-mark">श</span><span class="anchor-up add"><span class="up-t">स</span></span></span>', "Supralinear addition / correction (above the line)"),
    ('<span class="caret"></span>&nbsp;', "Caret under the line: where a marginal note belongs (hover or click to link); in Reading mode the note is woven in"),
    ('<span class="gap">◌</span>', "Lost akṣara (damage)"),
    ('<sup class="ed ed-fn" style="display:inline">1</sup>', "Editorial note — listed below the folio"),
]


def build_html(ctx, title, subtitle, pdf_rel, stats):
    pages_html = [render_page(p, pdf_rel) for p in ctx.pages]
    opts = "".join(
        f'<option value="p{p.seq}">{escape(folio_label(p.n))} · {escape(p.n)}</option>'
        for p in ctx.pages if p.n and (p.lines or p.apparatus)
    )
    legend = "".join(f'<li><span class="sw">{sw}</span>{escape(t)}</li>' for sw, t in LEGEND)
    head = f"""<!doctype html>
<html lang="sa">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+Devanagari:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
<style>{leaf_styles(ctx.pages)}</style>
</head>
<body class="ed-on">
<div class="bar ui">
  <h1 title="{attr(title)}">{escape(title)}</h1>
  <span class="seg" role="group" aria-label="Text mode">
    <button data-mode="dipl" aria-pressed="true" title="Text exactly as written in the manuscript">Manuscript</button>
    <button data-mode="read" aria-pressed="false" title="Corrections applied, deletions and surplus hidden">Reading</button>
  </span>
  <label><input type="checkbox" id="t-ed" checked> Editorial layer</label>
  <label><input type="checkbox" id="t-ln"> Line numbers</label>
  <button id="t-legend" type="button">Legend</button>
  <span class="sp"></span>
  <label>Folio <select id="goto">{opts}</select></label>
</div>
<div class="legend ui"><ul>{legend}</ul></div>
<div class="intro ui">
  <p class="t">{escape(title)}</p>
  <p>{escape(subtitle)}</p>
  <p>{stats} · hover any marked reading for details · keys <b>j</b>/<b>k</b> move between folios</p>
</div>
<main>
"""
    tail = '</main><div id="tip" class="ui"></div><script>' + JS + "</script></body></html>"
    return head + "".join(pages_html) + tail


# ---------------------------------------------------------------- main ---

def find_pdf(infile):
    stem = os.path.splitext(os.path.basename(infile))[0]
    d = os.path.dirname(os.path.abspath(infile))
    for _ in range(6):
        cand = os.path.join(d, stem + ".pdf")
        if os.path.exists(cand):
            return cand
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return None


def convert(infile, outfile, pdf=None, only=None):
    root = ET.parse(infile).getroot()

    biblio = {}
    for b in root.iter(TEI + "bibl"):
        bid = b.get(XMLID)
        if not bid:
            continue
        t = (b.findtext(TEI + "title") or "").strip()
        a = (b.findtext(TEI + "author") or "").strip()
        biblio[bid] = ", ".join(x for x in (a, t) if x) or bid

    title = (root.findtext(f".//{TEI}titleStmt/{TEI}title") or "Manuscript").strip()
    title = re.sub(r"\s+", " ", title)
    src = re.sub(r"\s+", " ", " ".join(root.find(f".//{TEI}sourceDesc").itertext()).strip()) \
        if root.find(f".//{TEI}sourceDesc") is not None else ""
    editor = (root.findtext(f".//{TEI}respStmt/{TEI}name") or "").strip()
    subtitle = src + (f" Transcribed by {editor}." if editor else "")

    body = root.find(f".//{TEI}text/{TEI}body")
    if body is None:
        sys.exit("No <text><body> found.")

    ctx = Context(biblio)
    b = Builder(ctx)
    b.children(body)
    b.close_line()

    if only:
        ctx.pages = [p for p in ctx.pages if p.n in only]

    pdf_rel = None
    if pdf:
        pdf_rel = os.path.relpath(os.path.abspath(pdf), os.path.dirname(os.path.abspath(outfile)))
        pdf_rel = pdf_rel.replace(os.sep, "/")

    n_pages = sum(1 for p in ctx.pages if p.n)
    n_lines = sum(len(p.lines) for p in ctx.pages)
    stats = f"{n_pages} folio sides · {n_lines} lines"

    html = build_html(ctx, title, subtitle, pdf_rel, stats)
    with open(outfile, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Wrote {outfile}  ({stats})")

    txtfile = os.path.splitext(outfile)[0] + ".txt"
    with open(txtfile, "w", encoding="utf-8") as fh:
        fh.write(reading_text(body))
    print(f"Wrote {txtfile}")

    for w in ctx.warnings:
        print("warning:", w, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="TEI (Saktumiva) → manuscript-like HTML + reading text")
    ap.add_argument("input", help="TEI XML transcription")
    ap.add_argument("output", nargs="?", help="output HTML (default: <input stem>_manuscript.html in the current directory)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pdf", help="facsimile PDF to link each folio to (default: <input stem>.pdf found in a parent directory)")
    g.add_argument("--no-pdf", action="store_true", help="do not link to a facsimile PDF")
    ap.add_argument("--pages", help="render only these folio sides, e.g. 0001_2,0002_1 or 0010_1-0012_2")
    a = ap.parse_args()

    out = a.output or os.path.splitext(os.path.basename(a.input))[0] + "_manuscript.html"
    pdf = None if a.no_pdf else (a.pdf or find_pdf(a.input))
    only = None
    if a.pages:
        only = set()
        for part in a.pages.split(","):
            if "-" in part:
                lo, hi = part.split("-", 1)
                only.add((lo, hi))
            else:
                only.add(part.strip())
        ranges = [x for x in only if isinstance(x, tuple)]
        only = {x for x in only if isinstance(x, str)}
        if ranges:
            only = _RangeSet(only, ranges)
    convert(a.input, out, pdf, only)


class _RangeSet:
    def __init__(self, names, ranges):
        self.names, self.ranges = names, ranges

    def __contains__(self, n):
        return n in self.names or any(lo <= n <= hi for lo, hi in self.ranges)


if __name__ == "__main__":
    main()
