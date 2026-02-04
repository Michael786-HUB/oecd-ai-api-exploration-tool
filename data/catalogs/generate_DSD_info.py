import requests
import xml.etree.ElementTree as ET

def test_datastructure(dataset_id, agency):
    """
    Test if we can extract dimension info from a dataset's datastructure.
    """
    # Build datastructure URL
    dsd_id = dataset_id.split('@')[0]
    url = f"https://sdmx.oecd.org/public/rest/datastructure/{agency}/{dsd_id}"
    
    print(f"\n{'='*80}")
    print(f"Testing: {dataset_id}")
    print(f"URL: {url}")
    print('='*80)
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        print(f"✓ Response received ({len(response.content)} bytes)")
        
        # Parse XML
        root = ET.fromstring(response.content)
        
        # Define namespaces
        namespaces = {
            'structure': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure',
            'str': 'http://www.sdmx.org/resources/sdmxml/schemas/v3_0/structure',
            'common': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common',
            'com': 'http://www.sdmx.org/resources/sdmxml/schemas/v3_0/common'
        }
        
        # Try both v2.1 and v3.0 namespaces
        dimensions_v2 = root.findall('.//structure:Dimension', namespaces)
        dimensions_v3 = root.findall('.//str:Dimension', namespaces)
        
        dimensions = dimensions_v2 if dimensions_v2 else dimensions_v3
        
        if not dimensions:
            print("⚠ No dimensions found - checking raw XML structure...")
            # Print first 1000 chars to see what's there
            print(response.text[:1000])
            return None
        
        print(f"✓ Found {len(dimensions)} dimensions\n")
        
        # Extract dimension info
        dim_info = []
        for dim in dimensions:
            dim_id = dim.get('id')
            position = dim.get('position')
            
            # Try to get dimension name
            name_elem = (dim.find('.//common:Name', namespaces) or 
                        dim.find('.//com:Name', namespaces))
            name = name_elem.text if name_elem is not None else "No name"
            
            dim_info.append({
                'position': int(position) if position else None,
                'id': dim_id,
                'name': name
            })
        
        # Sort by position
        dim_info.sort(key=lambda x: x['position'] if x['position'] else 999)
        
        # Display results
        print("Dimension Structure (in API order):")
        print("-" * 80)
        for dim in dim_info:
            pos = dim['position'] if dim['position'] else '?'
            print(f"  Position {pos}: {dim['id']:20} ({dim['name']})")
        
        print("\n" + "="*80)
        print("API KEY STRUCTURE:")
        key_parts = [dim['id'] for dim in dim_info]
        example_key = '.' + '.'.join(['?' for _ in key_parts])
        print(f"  {example_key}")
        print(f"  Example: .{'.'.join([dim['id'][:3].upper() for dim in dim_info[:5]])}")
        print("="*80)
        
        return dim_info
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Request error: {e}")
        return None
    except ET.ParseError as e:
        print(f"✗ XML parse error: {e}")
        return None
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return None


# Test on 3 different datasets
test_cases = [
    {
        "dataset_id": "DSD_FUA_CLIM@DF_CLIM_PROJ",
        "agency": "OECD.CFE.EDS"
    },
    {
        "dataset_id": "DSD_SHA@DF_SHA",
        "agency": "OECD.ELS.HD"
    },
    {
        "dataset_id": "DSD_NAAG@DF_NAAG",
        "agency": "OECD.SDD.NAD"
    }
]

print("TESTING DATASTRUCTURE EXTRACTION")
print("="*80)

results = {}
for test in test_cases:
    result = test_datastructure(test['dataset_id'], test['agency'])
    results[test['dataset_id']] = result

# Summary
print("\n\n" + "="*80)
print("SUMMARY")
print("="*80)

successful = sum(1 for r in results.values() if r is not None)
print(f"Successfully extracted: {successful}/{len(test_cases)}")

if successful == len(test_cases):
    print("\n✓ All tests passed! The datastructure endpoint contains what we need.")
    print("  You can proceed with the full extraction script.")
else:
    print("\n⚠ Some tests failed. Need to investigate the XML structure further.")