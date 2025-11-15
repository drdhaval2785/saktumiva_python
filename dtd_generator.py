import sys
from lxml import etree
from collections import defaultdict

def generate_dtd_skeleton_from_file(xml_file_path):
    """Generates a basic DTD skeleton from an XML file's structure."""
    try:
        tree = etree.parse(xml_file_path)
        root = tree.getroot()
        tag_info = defaultdict(lambda: {'children': set(), 'attributes': set(), 'has_pcdata': False})
        
        for elem in root.iter():
            tag_info[elem.tag]['attributes'].update(elem.attrib.keys())
            if elem.text and elem.text.strip():
                tag_info[elem.tag]['has_pcdata'] = True
            
            parent = elem.getparent()
            if parent is not None:
                tag_info[parent.tag]['children'].add(elem.tag)

        # Start building the DTD string
        # Note: This is a simplification. Cardinality (+, *) is not inferred.
        dtd_lines = [f"<!ELEMENT {root.tag} ({(', '.join(sorted(tag_info[root.tag]['children'])))})>"]
        
        for tag, info in sorted(tag_info.items()):
            if tag == root.tag:
                continue
                
            children_list = sorted(list(info['children']))
            if children_list:
                content_model = f"({', '.join(children_list)})" 
            elif info['has_pcdata']:
                content_model = "(#PCDATA)"
            else:
                content_model = "EMPTY" 
                
            dtd_lines.append(f"<!ELEMENT {tag} {content_model}>")

        dtd_lines.append("\n<!-- Attribute Definitions (placeholders, must be refined manually) -->")
        for tag, info in sorted(tag_info.items()):
            for attr in sorted(list(info['attributes'])):
                dtd_lines.append(f"<!ATTLIST {tag} {attr} CDATA #REQUIRED>")
                
        print("\n--- Generated DTD Skeleton ---")
        print("\n".join(dtd_lines))
        print("------------------------------")

    except etree.XMLSyntaxError as e:
        print(f"Error parsing XML file: {e}")
    except IOError as e:
        print(f"Error reading file: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python generate_dtd.py <path_to_xml_file>")
        sys.exit(1)
    
    xml_file_path = sys.argv[1]
    generate_dtd_skeleton_from_file(xml_file_path)
