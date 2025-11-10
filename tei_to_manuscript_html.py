import xml.etree.ElementTree as ET
from html import escape
import sys

def localname(tag):
    """Return tag name without namespace braces."""
    if not tag:
        return ""
    if isinstance(tag, str):
        return tag.split('}')[-1] if '}' in tag else tag
    return str(tag).split('}')[-1]

def render_element(el):
    """Recursively render TEI element to HTML, preserving text and tails."""
    tag = localname(el.tag)
    html = ""

    # Prepend the element's own text (before children)
    if el.text:
        html += escape(el.text)

    # Tag-specific handling
    if tag == "pb":
        n = el.attrib.get("n", "")
        html += f'</div></div><div class="folio"><div class="folio-inner"><div class="page-number">{escape(n)}</div>'
    elif tag == "lb":
        n = el.attrib.get("n", "")
        br = el.attrib.get("break", "yes")
        dash = "-" if br == "no" else ""
        html += f'<br/><span class="linenum">{escape(n)}</span>{dash}'
    elif tag == "choice":
        orig = el.find(".//{*}orig")
        corr = el.find(".//{*}corr")
        if corr is not None and orig is not None:
            html += f'<span class="choice" title="orig: {escape(orig.text or "")}">{escape(corr.text or "")}</span>'
    elif tag == "subst":
        del_el = el.find(".//{*}del")
        add_el = el.find(".//{*}add")
        if del_el is not None:
            html += f'<span class="del">{escape("".join(del_el.itertext()))}</span>'
        if add_el is not None:
            place = add_el.attrib.get("place", "")
            cls = f"add add-{place}" if place else "add"
            html += f'<span class="{cls}">{escape("".join(add_el.itertext()))}</span>'
    elif tag == "add":
        place = el.attrib.get("place", "")
        cls = f"add add-{place}" if place else "add"
        html += f'<span class="{cls}">{escape("".join(el.itertext()))}</span>'
    elif tag == "del":
        html += f'<span class="del">{escape("".join(el.itertext()))}</span>'
    elif tag == "unclear":
        html += f'<span class="unclear">{escape("".join(el.itertext()))}</span>'
    elif tag == "supplied":
        html += f'<span class="supplied">{escape("".join(el.itertext()))}</span>'
    elif tag == "quote":
        src = el.attrib.get("source", "")
        html += f'<span class="quote" title="{escape(src)}">{escape("".join(el.itertext()))}</span>'
    elif tag == "note":
        place = el.attrib.get("place", "left")
        resp = el.attrib.get("resp", "")
        text = "".join(el.itertext())
        if resp == "editorial":
            html += f'<sup class="footnote" title="{escape(text)}">[{escape(el.attrib.get("id","*"))}]</sup>'
        else:
            html += f'<span class="note note-{place}">{escape(text)}</span>'
    elif tag == "hi":
        rend = el.attrib.get("rend", "")
        inner = "".join(render_element(c) for c in el)
        if rend == "redfont":
            html += f'<span class="redfont">{inner}</span>'
        else:
            html += inner
    else:
        # Generic element: render children normally
        for c in el:
            html += render_element(c)

    # Append tail text (after the element)
    if el.tail:
        html += escape(el.tail)

    return html

def tei_to_html(tei_file, html_file):
    tree = ET.parse(tei_file)
    root = tree.getroot()
    ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
    body = root.find('.//tei:text/tei:body', ns)

    html_parts = [
        "<!DOCTYPE html><html lang='sa'><head><meta charset='utf-8'>",
        "<title>Manuscript Layout</title><style>",
        """
        body { background:#f8f2e4; font-family:'Noto Serif Devanagari',serif;
               padding:2em; margin:0; }
        .folio { background:#fffdf8; border:1px solid #c9b899;
                 box-shadow:0 0 10px rgba(0,0,0,0.25);
                 margin:3em auto; width:65%; padding:3em; position:relative; }
        .folio-inner { line-height:1.9em; font-size:1.2em; color:#2a1e0e; }
        .page-number { position:absolute; top:0.5em; right:1em; color:#777; font-size:0.8em; }
        .unclear { background:#fee; color:#a00; }
        .choice { background:#eef; color:#006; border-bottom:1px dotted #006; }
        .del { text-decoration:line-through; color:#a00; opacity:0.6; }
        .add { color:#060; } .add-supralinear { vertical-align:super; font-size:0.8em; }
        .supplied { font-style:italic; color:#555; }
        .quote { color:#004080; background:#eef; padding:0 2px; }
        .note-left,.note-right,.note-top,.note-bottom {
            background:#f0f0d0; font-size:0.8em; padding:0.2em 0.4em;
            border-radius:0.3em; margin:0.3em; }
        .linenum { color:#aaa; font-size:0.8em; display:inline-block; width:2em; text-align:right; }
        .footnote { color:#933; cursor:help; }
        """,
        "</style></head><body><div class='folio'><div class='folio-inner'>"
    ]

    for c in body:
        html_parts.append(render_element(c))

    html_parts.append("</div></div></body></html>")

    with open(html_file, "w", encoding="utf-8") as f:
        f.write("".join(html_parts))
    print(f"✅ Wrote {html_file}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert TEI XML → manuscript HTML (v4)")
    parser.add_argument("input", help="Input TEI XML file")
    parser.add_argument("output", help="Output HTML file")
    args = parser.parse_args()
    tei_to_html(args.input, args.output)
