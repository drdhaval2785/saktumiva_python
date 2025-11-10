#!/usr/bin/env python3
# tei_to_manuscript_final3.py
# Adds: clickable footnotes, quote tooltip, kāṇḍa split, add tooltips (no arrows)

import xml.etree.ElementTree as ET
from html import escape
import sys

SKIP_NOTE_IDS = {"HND", "CSP", "FR"}  # skip completely

def localname(tag):
    if not tag:
        return ""
    if isinstance(tag, str):
        return tag.split("}")[-1] if "}" in tag else tag
    return str(tag).split("}")[-1]

class Page:
    def __init__(self, pid):
        self.id = pid
        self.html_parts = []
        self.footnotes = []
        self.fn_counter = 1
    def add(self, html): self.html_parts.append(html)
    def add_foot(self, txt):
        num = self.fn_counter
        self.fn_counter += 1
        fid = f"fn{num}"
        self.footnotes.append((num, txt))
        return f'<sup id="ref{num}"><a href="#{fid}" title="Jump to note {num}">{num}</a></sup>'

# ---------- Render helpers ----------

def render_lb(el):
    n = el.attrib.get("n", "")
    br = el.attrib.get("break", "yes")
    dash = "-" if br == "no" else ""
    return f'<br/><span class="linenum">{escape(n)}</span>{dash}'

def render_add(el):
    place = el.attrib.get("place", "")
    tooltip = place if place else "supplied"
    text = ''.join(escape(t) for t in el.itertext())
    return f'<span class="add" title="{tooltip}">{text}</span>'

def render_del(el):
    return f'<span class="del">{"".join(escape(t) for t in el.itertext())}</span>'

def render_unclear(el):
    return f'<span class="unclear">{"".join(escape(t) for t in el.itertext())}</span>'

def render_supplied(el):
    return f'<sup class="supplied">{"".join(escape(t) for t in el.itertext())}</sup>'

def render_choice(el):
    orig = el.find(".//{*}orig")
    corr = el.find(".//{*}corr")
    if corr is not None and orig is not None:
        return f'<span class="choice" title="orig: {escape("".join(orig.itertext()))}">{escape("".join(corr.itertext()))}</span>'
    return ''.join(render_element(c) for c in el)

def render_quote(el):
    src = el.attrib.get("source", "")
    title = f'title="{escape(src)}"' if src else ""
    out = []
    if el.text: out.append(escape(el.text))
    for c in el:
        tag = localname(c.tag)
        if tag == "lb":
            out.append(render_lb(c))
        elif tag == "unclear":
            out.append(render_unclear(c))
        else:
            out.append(render_element(c))
        if c.tail: out.append(escape(c.tail))
    return f'<span class="quote" {title}>{"".join(out)}</span>'

def render_element(el, page=None):
    """Recursively render TEI -> HTML preserving all unmarked text."""
    tag = localname(el.tag)
    out = ""

    # --- pre-text ---
    if el.text:
        out += escape(el.text)

    # --- tag handling ---
    if tag == "lb":
        return render_lb(el)
    elif tag == "add":
        return render_add(el)
    elif tag == "del":
        return render_del(el)
    elif tag == "unclear":
        return render_unclear(el)
    elif tag == "supplied":
        return render_supplied(el)
    elif tag == "choice":
        return render_choice(el)
    elif tag == "quote":
        return render_quote(el)
    elif tag == "subst":
        del_el = el.find(".//{*}del")
        add_el = el.find(".//{*}add")
        return (render_del(del_el) if del_el is not None else "") + (render_add(add_el) if add_el is not None else "")
    elif tag == "note":
        nid = el.attrib.get("id", "")
        resp = el.attrib.get("resp", "")
        if nid in SKIP_NOTE_IDS:
            return ""
        if resp == "editorial" and page:
            return page.add_foot(''.join(el.itertext()).strip())
        return ""
    elif tag == "pb":
        n = el.attrib.get("n", "?")
        return f'</div></div><div class="folio"><div class="folio-inner"><div class="page-number">{escape(n)}</div>'
    elif tag == "div":
        # mid-line insertion → split line into a/b
        if el.attrib.get("type") == "kāṇḍa":
            kid = el.attrib.get("id", "")
            part = el.attrib.get("part", "")
            if part:
                label = f"{kid}{part}"
            else:
                label = kid
            out += f'<h2 class="kanda">{escape(label)}</h2>'
    elif tag == "hi":
        rend = el.attrib.get("rend", "")
        inner = ''.join(render_element(c) for c in el)
        if rend == "redfont":
            return f'<span class="redfont">{inner}</span>'
        return inner

    # --- children recursion ---
    for c in el:
        out += render_element(c, page)
        if c.tail:
            out += escape(c.tail)
    return out

# ---------- Converter ----------

def tei_to_html(infile, outfile):
    ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
    root = ET.parse(infile).getroot()
    body = root.find('.//tei:text/tei:body', ns)
    if body is None:
        print("No <body>")
        return

    pages, current = [], Page("start")
    pages.append(current)

    for child in list(body):
        if localname(child.tag) == "pb":
            current = Page(child.attrib.get("n", "?"))
            pages.append(current)
            current.add(f'<div class="page-number">{escape(child.attrib.get("n", "?"))}</div>')
            continue
        frag = render_element(child, current)
        if frag.strip(): current.add(frag)

    # HTML output
    html = [
        "<!doctype html><html lang='sa'><head><meta charset='utf-8'><title>Manuscript</title><style>",
        """
        body { background:#f8f2e4; font-family:'Noto Serif Devanagari',serif; margin:0; padding:2rem;}
        .folio { width:70%; margin:2rem auto; background:#fffef9; border:1px solid #ccc;
                 box-shadow:0 5px 15px rgba(0,0,0,0.1); padding:2.5rem; position:relative; }
        .folio-inner { line-height:1.9; font-size:1.1rem; color:#2a1e0e; }
        .page-number { position:absolute; right:1rem; top:0.6rem; color:#555; font-size:0.9rem;}
        .linenum { display:inline-block; width:2.4em; text-align:right; margin-right:0.5em; color:#aaa; font-size:0.8rem;}
        .add { color:#b58900; background:#fff9d9; cursor:help; } /* yellow tone */
        .del { color:#777; text-decoration:line-through; }
        .unclear { color:#b00; padding:0 0.15em; border-radius:3px; }
        .quote  { color:#0044cc; background:#eaf1ff; border-radius:3px; padding:0 0.15em; cursor:help; }
        .choice { color:#5a2a00; background:#f7e8d9; border-bottom:1px dotted #b55; }
        .supplied { color:#666; font-style:italic;}
        .footnotes { margin-top:1rem; border-top:1px solid #ddd; padding-top:0.5rem; font-size:0.9rem;}
        .footnotes ol { padding-left:1.2em; }
        .footnotes li { margin:0.4em 0;}
        .legend { background:#fffbe6; border:1px solid #f0d890; padding:0.7rem 1rem; margin-bottom:1rem;
                  border-radius:6px; font-size:0.95rem;}
        .legend .item { margin:0.25rem 0;}
        """,
        "</style></head><body>"
    ]

    legend = """
	<div class="legend"><strong>Legend:</strong>
	  <div class="item"><span style="color:#b58900">Yellow</span> — Supplied from margin (hover to see placement)</div>
	  <div class="item"><span style="color:#0044cc">Blue</span> — Quotation (hover for source)</div>
	  <div class="item"><span style="color:#5a2a00">Brown</span> — Editorial choice</div>
	  <div class="item"><span style="color:#b00">Red</span> — Unclear text</div>
	  <div class="item"><span style="color:#777;text-decoration:line-through;">Gray strikethrough</span> — Deleted text</div>
	</div>    
	"""

    for i, pg in enumerate(pages):
        if i == 0 and not any(s.strip() for s in pg.html_parts):
            continue
        html.append("<div class='folio'><div class='folio-inner'>")
        if i <= 1: html.append(legend)
        html.append(''.join(pg.html_parts))
        if pg.footnotes:
            html.append('<div class="footnotes"><ol>')
            for num, f in pg.footnotes:
                fid = f"fn{num}"
                html.append(f'<li id="{fid}">{escape(f)} <a href="#ref{num}" title="Back to text">↩</a></li>')
            html.append("</ol></div>")
        html.append("</div></div>")

    html.append("</body></html>")
    open(outfile, "w", encoding="utf-8").write(''.join(html))
    print("✅ Wrote", outfile)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert TEI XML → manuscript HTML (v5)")
    parser.add_argument("input", help="Input TEI XML file")
    parser.add_argument("output", help="Output HTML file")
    args = parser.parse_args()
    tei_to_html(args.input, args.output)
