import sys
from lxml import etree
from collections import defaultdict

def generate_dtd_with_enums(xml_file_path):
    """
    Generates a basic DTD skeleton from an XML file's structure, 
    inferring attribute value enumerations.
    """
    try:
        tree = etree.parse(xml_file_path)
        root = tree.getroot()
        
        # Stores relationships and potential enum values: 
        # {tag: {'children': set(), 'attributes': {attr_name: set(values), ...}, 'has_pcdata': bool}}
        tag_info = defaultdict(lambda: {'children': set(), 'attributes': defaultdict(set), 'has_pcdata': False})

        for elem in root.iter():
            # Track PCDATA presence
            if elem.text and elem.text.strip():
                tag_info[elem.tag]['has_pcdata'] = True
            
            # Track Parent-Child relationships
            parent = elem.getparent()
            if parent is not None:
                tag_info[parent.tag]['children'].add(elem.tag)
            
            # Track Attribute values for enumeration
            for attr_name, attr_value in elem.attrib.items():
                tag_info[elem.tag]['attributes'][attr_name].add(attr_value)

        dtd_lines = []
        
        # 1. Element Declarations
        # Root element declaration
        root_children = sorted(list(tag_info[root.tag]['children']))
        dtd_lines.append(f"<!ELEMENT {root.tag} ({(', '.join(root_children))})>\n")

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

        dtd_lines.append("\n<!-- Attribute Definitions (Enumerations inferred from data) -->")
        
        # 2. Attribute List Declarations
        for tag, info in sorted(tag_info.items()):
            for attr_name, values in sorted(info['attributes'].items()):
                if len(values) > 1 and len(values) < 20: # Heuristic: if few unique values, assume an ENUM
                    # Create the enumeration list in DTD format: (val1 | val2 | ...)
                    enum_list = " | ".join(f'"{v}"' for v in sorted(values))
                    attr_type = f"({enum_list})"
                else:
                    # Otherwise, assume general character data
                    attr_type = "CDATA"
                
                # All attributes are assumed #REQUIRED in this auto-generator
                dtd_lines.append(f"<!ATTLIST {tag} {attr_name} {attr_type} #REQUIRED>")
                
        print("\n--- Generated DTD Skeleton with Enumerations ---")
        print("\n".join(dtd_lines))
        print("------------------------------------------------")

    except etree.XMLSyntaxError as e:
        print(f"Error parsing XML file: {e}")
    except IOError as e:
        print(f"Error reading file: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python generate_dtd.py <path_to_xml_file>")
        sys.exit(1)
    
    # sys.argv expects a list, so pass it directly to handle the path extraction internally
    generate_dtd_with_enums(sys.argv[1])
