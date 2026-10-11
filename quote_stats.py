#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from collections import Counter
import sys
import re

def extract_source_value(raw):
    """
    Normalize the source attribute.
    Examples:
        "#AMAR" -> "AMAR"
        "AMAR"   -> "AMAR"
        "#ABCH#XYZ" -> ABCH/XYZ (if multiple appear)
    """
    if not raw:
        return None
    
    parts = re.split(r"[ ,;]+", raw.strip())
    clean_parts = [p.lstrip("#") for p in parts if p.lstrip("#")]
    
    if not clean_parts:
        return None
    
    return "/".join(clean_parts)


def count_quote_sources(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    counter = Counter()

    for q in root.iter('quote'):
        raw_source = q.get('source')
        src = extract_source_value(raw_source)
        if src:
            counter[src] += 1

    return counter


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 quote_stats.py input.xml")
        sys.exit(1)

    xml_path = sys.argv[1]
    counts = count_quote_sources(xml_path)

    # Sort: count DESC, then source ASC
    sorted_items = sorted(counts.items(), key=lambda x: (-x[1], x[0]))

    for source, count in sorted_items:
        print(f"{source}\t{count}")
