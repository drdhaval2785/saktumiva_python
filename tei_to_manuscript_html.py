#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TEI XML → Manuscript-style HTML converter (v4)
Fixes:
- preserves main text (not just markup)
- no duplicated <sic>/<corr>
- margin notes visible
"""

import xml.etree.ElementTree as ET

def tei_to_html_v4(tei_file, html_file):
    ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
    tree = ET.parse(tei_file)
    root = tree.getroot()

    # --- CSS + HTML header ---
    html_parts = [
        '<!DOCTYPE html><html lang="sa"><head><meta charset="UTF-8">',
        '<title>Manuscript Layout Preview</title>',
        '<style>',
        '''
        body {
            background: #f8f2e4;
            font-family: 'Noto Serif Devanagari', serif;
            padding: 2em;
        }
        .folio {
            position: relative;
            margin: 3em auto;
            width: 65%;
            min-height: 85vh;
            background: #fffdf8;
            border: 1px solid #c9b899;
            box-shadow: 0 0 20px rgba(0,0,0,0.25);
            box-sizing: border-box;
        }
        .folio-inner {
            position: relative;
            z-index: 3; /* ensure above background */
            margin: 6em 5em;
            line-height: 1.9em;
            color: #2a1e0e;
            font-size: 1.2em;
        }
        .margin-note {
            position: absolute;
            z-index: 4; /* make visible */
            background: rgba(255, 253, 190, 0.9);
            font-size: 0.85em;
            padding: 0.4em 0.6em;
            border-radius: 0.4em;
            max-width: 20%;
            box-shadow: 0 0 6px rgba(0,0,0,0.1);
        }
        .margin-top { top: 0.5em; left: 25%; right: 25%; text-align: center; }
        .margin-bottom { bottom: 0.5em; left: 25%; right: 25%; text-align: center; }
        .margin-left { top: 25%; left: 1em; text-align: right; }
        .margin-right { top: 25%; right: 1em; text-align: left; }

        add, del, corr, sic {
            display: inline;
            white-space: nowrap;
        }
        add { color: #156915; }
        del { color: #a11; text-decoration: line-through; }
        sic { color: #999; }
        corr { color: #0066cc; font-weight: 600; }

        head { display:block; text-align:center; font-weight:bold; margin-bottom:1em; font-size:1.4em; }

        p {
            text-align: justify;
            text-indent: 2em;
            margin: 0.8em 0;
        }

        .folio::before {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, #fffdf8 0%, #f9f5e9 100%);
            z-index: 1;
            border-radius: 0.3em;
        }
        ''',
        '</style></head><body>'
    ]

    def render_children(elem):
        """Recursively render XML children preserving text and tails"""
        out = []
        if elem.text:
            out.append(elem.text)
        for child in elem:
            tag = child.tag.split('}')[-1]
            if tag == 'add':
                out.append(f'<add>{child.text or ""}</add>')
            elif tag == 'del':
                out.append(f'<del>{child.text or ""}</del>')
            elif tag == 'choice':
                sic = child.find('tei:sic', ns)
                corr = child.find('tei:corr', ns)
                if sic is not None and corr is not None:
                    out.append(f'<sic>{sic.text or ""}</sic>/<corr>{corr.text or ""}</corr>')
            elif tag not in ['note']:  # skip margin notes here
                out.append(render_children(child))
            if child.tail:
                out.append(child.tail)
        return ''.join(out)

    # --- page divisions ---
    for div in root.findall('.//tei:div', ns):
        html_parts.append('<div class="folio">')

        # Margin notes
        for note in div.findall('.//tei:note', ns):
            place = note.attrib.get('place', '')
            txt = (note.text or '').strip()
            html_parts.append(f'<div class="margin-note margin-{place}">{txt}</div>')

        html_parts.append('<div class="folio-inner">')

        # Head
        head = div.find('tei:head', ns)
        if head is not None and head.text:
            html_parts.append(f'<head>{head.text}</head>')

        for p in div.findall('tei:p', ns):
            rendered = render_children(p)
            if rendered.strip():
                html_parts.append(f'<p>{rendered}</p>')

        html_parts.append('</div></div>')

    html_parts.append('</body></html>')

    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(''.join(html_parts))

    print(f"✅ HTML manuscript written to {html_file}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert TEI XML → manuscript HTML (v4)")
    parser.add_argument("input", help="Input TEI XML file")
    parser.add_argument("output", help="Output HTML file")
    args = parser.parse_args()
    tei_to_html_v4(args.input, args.output)
