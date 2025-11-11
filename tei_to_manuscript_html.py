#!/usr/bin/env python3
# tei_to_manuscript_html.py
# Adds <caesura>, <gap>, <sic> support to working renderer.

import xml.etree.ElementTree as ET
from html import escape

SKIP_NOTE_IDS = {"HND", "CSP", "FR", "FOLIO"}
BIBLIO = {}


def localname(tag):
    if not tag:
        return ""
    return tag.split("}")[-1] if "}" in tag else tag


class Page:
    def __init__(self, pid):
        self.id = pid
        self.html_parts = []
        self.footnotes = []
        self.fn_counter = 1

    def add(self, html):
        self.html_parts.append(html)

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
    if br == "no":
        return f'-<br/><span class="linenum">{escape(n)}</span>'
    return f'<br/><span class="linenum">{escape(n)}</span>'


def render_add(el):
    place = el.attrib.get("place", "")
    tooltip = place if place else "supplied"
    text = ''.join(escape(t) for t in el.itertext())
    return f'<span class="add" title="{tooltip}">{text}</span>'


def render_del(el):
    return f'<span class="del">{"".join(escape(t) for t in el.itertext())}</span>'


def render_unclear(el, page=None):
    out = ""
    if el.text:
        out += escape(el.text)
    for c in el:
        out += render_element(c, page)
        if c.tail:
            out += escape(c.tail)
    return f'<span class="unclear">{out}</span>'


def render_supplied(el):
    return f'<span class="supplied">{"".join(escape(t) for t in el.itertext())}</span>'


def render_surplus(el):
    reason = el.attrib.get("reason", "")
    tooltip = f' title="{escape(reason)}"' if reason else ""
    return f'<span class="surplus"{tooltip}>{"".join(escape(t) for t in el.itertext())}</span>'


def render_choice(el):
    orig = el.find(".//{*}orig")
    corr = el.find(".//{*}corr")
    if corr is not None and orig is not None:
        return f'<span class="choice" title="orig: {escape("".join(orig.itertext()))}">{escape("".join(corr.itertext()))}</span>'
    return ''.join(render_element(c) for c in el)


def render_quote(el):
    src = el.attrib.get("source", "")
    tooltip = ""

    if src:
        parts = src.split()
        items = []
        for part in parts:
            if part.startswith("#"):
                key = part[1:]
                if key in BIBLIO:
                    items.append(BIBLIO[key])
            else:
                items.append(part)
        tooltip = "; ".join(items)
    title = f'title="{escape(tooltip)}"' if tooltip else ""

    out = []
    if el.text:
        out.append(escape(el.text))
    for c in el:
        tag = localname(c.tag)
        if tag == "lb":
            out.append(render_lb(c))
        else:
            out.append(render_element(c))
        if c.tail:
            out.append(escape(c.tail))
    return f'<span class="quote" {title}>{"".join(out)}</span>'


# ---------- Recursive renderer ----------

def render_element(el, page=None):
    tag = localname(el.tag)
    out = ""

    reason = el.attrib.get("reason")
    if reason:
        out += f'<span title="{escape(reason)}">'

    text_before = escape(el.text) if el.text else ""

    if tag == "lb":
        return render_lb(el)
    elif tag == "add":
        return render_add(el)
    elif tag == "del":
        return render_del(el)
    elif tag == "unclear":
        return render_unclear(el, page)
    elif tag == "supplied":
        return render_supplied(el)
    elif tag == "surplus":
        return render_surplus(el)
    elif tag == "choice":
        return render_choice(el)
    elif tag == "quote":
        return render_quote(el)
    elif tag == "subst":
        del_el = el.find(".//{*}del")
        add_el = el.find(".//{*}add")
        parts = []
        if del_el is not None:
            parts.append(render_del(del_el))
        if add_el is not None:
            parts.append(render_add(add_el))
        return "".join(parts)

    # ---------- NEW TAGS ----------
    elif tag == "caesura":
        return '<span class="caesura" title="caesura">‖</span>'

    elif tag == "gap":
        reason = el.attrib.get("reason", "illegible")
        unit = el.attrib.get("unit", "")
        qty = el.attrib.get("quantity", "")
        tooltip = f"{qty} {unit} {reason}".strip()
        return f'<span class="gap" title="{escape(tooltip)}">[...]</span>'

    elif tag == "sic":
        return f'<span class="sic" title="as in manuscript">{"".join(escape(t) for t in el.itertext())}</span>'
    # ------------------------------

    # ---------- FIXED NOTE HANDLING ----------
    elif tag == "note":
        nid = el.attrib.get("id", "")
        resp = el.attrib.get("resp", "")
        place = el.attrib.get("place", "")

        if nid in SKIP_NOTE_IDS:
            return ""

        if resp == "editorial" and page:
            return page.add_foot(''.join(el.itertext()).strip())

        inner = ""
        if el.text:
            inner += escape(el.text)
        for c in el:
            inner += render_element(c, page)
            if c.tail:
                inner += escape(c.tail)
        return f'<span class="note" data-place="{escape(place)}">{inner}</span>'
    # ----------------------------------------

    elif tag == "pb":
        n = el.attrib.get("n", "?")
        return f'<hr/><div class="page-number">Page {escape(n)}</div>'
    elif tag == "div":
        head = el.find("./{*}head")
        if head is not None:
            out += f"<h2>{escape(''.join(head.itertext()))}</h2>"
        for c in el:
            if localname(c.tag) != "head":
                out += render_element(c, page)
                if c.tail:
                    out += escape(c.tail)
        return out

    # Verse (<lg>)
    elif tag == "lg":
        xmlid = el.attrib.get("{http://www.w3.org/XML/1998/namespace}id", "")
        out = f"<span class='verse' data-id='{xmlid}'>{text_before}"
        for c in el:
            out += render_element(c, page)
            if c.tail:
                out += escape(c.tail)
        out += "</span>"
        return out

    # Commentary (<p>)
    elif tag == "p":
        xmlid = el.attrib.get("{http://www.w3.org/XML/1998/namespace}id", "")
        classes = []
        data_target = ""
        if xmlid.startswith("c"):
            classes.append("commentary")
            base = xmlid.split("-")[0].replace("c", "v")
            data_target = f" data-target='{base}'"
        out = f"<span class='{' '.join(classes)}'{data_target}>{text_before}"
        for c in el:
            out += render_element(c, page)
            if c.tail:
                out += escape(c.tail)
        out += "</span>"
        return out

    for c in el:
        out += render_element(c, page)
        if c.tail:
            out += escape(c.tail)

    if el.attrib.get("reason"):
        out += "</span>"

    return text_before + out


# ---------- Converter ----------

def tei_to_html(infile, outfile):
    ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
    root = ET.parse(infile).getroot()

    for bibl in root.findall(".//tei:listBibl//tei:bibl", ns):
        bid = bibl.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
        if not bid:
            continue
        title = bibl.findtext("tei:title", "", ns).strip()
        author = bibl.findtext("tei:author", "", ns).strip()
        if title and author:
            BIBLIO[bid] = f"{title} – {author}"
        else:
            BIBLIO[bid] = title or author

    body = root.find('.//tei:text/tei:body', ns)
    if body is None:
        print("No <body>")
        return

    pages, current = [], Page("start")
    pages.append(current)

    for child in list(body):
        tag = localname(child.tag)
        if tag == "pb":
            current = Page(child.attrib.get("n", "?"))
            pages.append(current)
            continue
        frag = render_element(child, current)
        if frag.strip():
            current.add(frag)

    html = [
        "<!doctype html><html lang='sa'><head><meta charset='utf-8'><title>Manuscript</title><style>",
        """
        body { background:#ffffff; font-family:'Noto Serif Devanagari',serif; margin:0; padding:2rem; }
        .folio { width:90%; margin:1rem auto; background:#ffffff; border:none; box-shadow:none; padding:1rem; position:relative; }
        .folio-inner { line-height:1.9; font-size:1.1rem; color:#2a1e0e; }
        .page-number { text-align:center; font-weight:bold; margin:0.5em 0;}
        .linenum { display:inline-block; width:2.4em; text-align:right; margin-right:0.5em; color:#aaa; font-size:0.8rem;}
        .add { background:cyan; cursor:help; }
        .del { background:#F5F5F5; color:gray; text-decoration:line-through gray 1.5px; text-decoration-skip-ink:none; display:inline-block; white-space:pre; transform:translateY(-0.05em); }
        .unclear { background:yellow; padding:0 0.15em; border-radius:3px; }
        .quote  { color:blue; border-radius:3px; padding:0 0.15em; cursor:help; }
        .choice { background:pink; border-bottom:1px dotted #b55; }
        .supplied { background:violet; }
        .verse { color:green; display:inline; }
        .verse * { color:inherit; }
        .surplus { background:tan !important; text-decoration:line-through 2px gray; text-decoration-skip-ink:none; display:inline-block; position:relative; transform:translateY(-0.15em); }
        .commentary { color:#2a1e0e; }
        .note { background:#fdf6e3; border-left:2px solid #aaa; padding-left:0.3em; margin-left:0.3em; display:inline-block; }

        .caesura { color:#666; font-weight:bold; margin:0 0.2em; }
        .gap { color:#999; font-style:italic; cursor:help; }
        .sic { color:#d00; font-style:italic; }
        """,
        "</style></head><body>"
    ]

    for i, pg in enumerate(pages):
        if i == 0 and not any(s.strip() for s in pg.html_parts):
            continue
        html.append("<div class='folio'><div class='folio-inner'>")
        html.append(' '.join(pg.html_parts))
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
    parser = argparse.ArgumentParser(description="Convert TEI XML → manuscript HTML with <caesura>, <gap>, <sic> support")
    parser.add_argument("input", help="Input TEI XML file")
    parser.add_argument("output", help="Output HTML file")
    args = parser.parse_args()
    tei_to_html(args.input, args.output)
