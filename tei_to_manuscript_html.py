import xml.etree.ElementTree as ET


def localname(tag):
    """Return the tag name without namespace URI, safe for all Python versions."""
    if tag is None:
        return ''
    if isinstance(tag, str):
        return tag.split('}')[-1] if '}' in tag else tag
    try:
        # Python 3.12+ QName objects
        return tag.localname
    except AttributeError:
        return str(tag).split('}')[-1]


def tei_to_html(xml_path, html_path):
    NS = {'tei': 'http://www.tei-c.org/ns/1.0'}
    tree = ET.parse(xml_path)
    root = tree.getroot()

    html = [
        '<!DOCTYPE html><html lang="sa"><head><meta charset="UTF-8">',
        '<title>Meghadūtam Manuscript Layout</title>',
        """<style>
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
        }
        .folio-inner {
            position: relative;
            z-index: 2;
            margin: 6em 5em;
            line-height: 1.9em;
            color: #2a1e0e;
            font-size: 1.2em;
        }
        head {
            display:block;
            text-align:center;
            font-weight:bold;
            margin-bottom:1em;
            font-size:1.4em;
        }
        p {
            text-align: justify;
            text-indent: 2em;
            margin: 0.8em 0;
        }

        add, del, corr, sic {
            display:inline;
            white-space:nowrap;
        }
        add { color:#156915; }
        del { color:#a11; text-decoration:line-through; }
        corr { color:#0066cc; font-weight:600; }
        sic { color:#999; }

        /* keyboard-style arrows */
        .arrow-top::before    { content: "↑ "; color:#777; font-weight:bold; }
        .arrow-bottom::before { content: "↓ "; color:#777; font-weight:bold; }
        .arrow-left::before   { content: "← "; color:#777; font-weight:bold; }
        .arrow-right::before  { content: "→ "; color:#777; font-weight:bold; }

        /* soft manuscript paper look */
        .folio::before {
            content:"";
            position:absolute;
            inset:0;
            background:linear-gradient(135deg,#fffdf8 0%,#f9f5e9 100%);
            border-radius:0.3em;
            z-index:1;
        }
        </style></head><body>
        """
    ]

    body = root.find('.//tei:body', NS)
    if body is None:
        print("No <body> found in TEI file.")
        return

    # Split content into folios based on <pb>
    folio_open = False
    for child in list(body):
        tag = localname(child.tag)
        if tag == "pb":
            # Close previous folio if open
            if folio_open:
                html.append('</div></div>')
            # Start new folio
            folio_open = True
            n = child.attrib.get('n', '?')
            html.append(f'<div class="folio"><div class="folio-inner">')
        elif tag == "head":
            html.append(f"<head>{(child.text or '').strip()}</head>")
        elif tag == "p":
            segs = []
            for elem in child:
                subt = localname(elem.tag)
                text = (elem.text or '').strip()
                if subt == 'add':
                    place = elem.attrib.get('place', '')
                    arrow_class = f"arrow-{place}" if place else ''
                    segs.append(f"<add class='{arrow_class}'>{text}</add>")
                elif subt == 'del':
                    segs.append(f"<del>{text}</del>")
                elif subt == 'corr':
                    segs.append(f"<corr>{text}</corr>")
                elif subt == 'sic':
                    segs.append(f"<sic>{text}</sic>")
                else:
                    segs.append(text)
            # Include tail text between inline tags
            full_text = ''.join(segs)
            if child.text and not full_text.strip():
                full_text = child.text
            html.append(f"<p>{full_text}</p>")

    if folio_open:
        html.append('</div></div>')

    html.append('</body></html>')

    with open(html_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(html))

    print(f"✅ HTML manuscript generated: {html_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert TEI XML → manuscript HTML (v4)")
    parser.add_argument("input", help="Input TEI XML file")
    parser.add_argument("output", help="Output HTML file")
    args = parser.parse_args()
    tei_to_html(args.input, args.output)
