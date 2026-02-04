import requests # For making HTTP requests
import xml.etree.ElementTree as ET # For parsing XML
import json 

def get_oecd_dataset_catalog():
    """
    Fetch all OECD datasets with their metadata.
    Returns a dictionary: {dataset_id: {name, description, agency}}
    """
    
    url = "https://sdmx.oecd.org/public/rest/dataflow/All"
    
    print(f"Fetching dataset catalog from OECD API...")
    print(f"URL: {url}\n")
    
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        print(f"✓ Response received ({len(response.content)} bytes)")
        
        # Parse XML
        root = ET.fromstring(response.content)
        
        # Define XML namespaces
        namespaces = {
            'message': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message',
            'structure': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure',
            'common': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common'
        }

        ET.register_namespace('xml', 'http://www.w3.org/XML/1998/namespace')
        
        catalog = {}
        
        # Find all Dataflow elements
        dataflows = root.findall('.//structure:Dataflow', namespaces)
        
        print(f"✓ Found {len(dataflows)} datasets\n")
        print("Extracting metadata...\n")
        
        for dataflow in dataflows:
            # Get dataset ID and agency
            dataset_id = dataflow.get('id')
            agency_id = dataflow.get('agencyID')
            version = dataflow.get('version')
            
            # Get name (usually in English)
            name_element = dataflow.find('.//common:Name[@{http://www.w3.org/XML/1998/namespace}lang="en"]', namespaces)
            if name_element is None:
                # Fallback to any name if English not available
                name_element = dataflow.find('.//common:Name', namespaces)
            
            name = name_element.text if name_element is not None else "No name"
            
            # Get description (usually in English)
            desc_element = dataflow.find('.//common:Description[@{http://www.w3.org/XML/1998/namespace}lang="en"]', namespaces)
            if desc_element is None:
                # Fallback to any description
                desc_element = dataflow.find('.//common:Description', namespaces)
            
            description = desc_element.text if desc_element is not None else "No description available"
            
            # Store in catalog
            catalog[dataset_id] = {
                "name": name,
                "description": description,
                "agency": agency_id,
                "version": version
            }
            
            # Print first few as examples
            if len(catalog) <= 5:
                print(f"Example {len(catalog)}:")
                print(f"  ID: {dataset_id}")
                print(f"  Name: {name[:80]}...")
                print(f"  Agency: {agency_id}\n")
        
        print(f"\n✓ Successfully extracted {len(catalog)} datasets")
        
        return catalog
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching data: {e}")
        return {}
    except ET.ParseError as e:
        print(f"✗ Error parsing XML: {e}")
        return {}


def save_catalog(catalog, filename="oecd_dataset_catalog_v2.json"):
    """Save catalog to JSON file"""
    output_path = "/Users/Micha/Documents/Documents/OCED Research Tool"
    filepath = f"{output_path}/{filename}"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Saved catalog to: {filepath}")


def search_catalog(catalog, search_term):
    """Search for datasets by keyword"""
    results = {}
    search_lower = search_term.lower()
    
    for dataset_id, metadata in catalog.items():
        name_match = search_lower in metadata['name'].lower()
        desc_match = search_lower in metadata['description'].lower()
        
        if name_match or desc_match:
            results[dataset_id] = metadata
    
    return results


# ============= RUN IT =============

if __name__ == "__main__":
    
    # Fetch the catalog
    catalog = get_oecd_dataset_catalog()
    
    # Save to JSON file
    if catalog:
        save_catalog(catalog)
        
        # Test: Search for your SDG dataset
        print("\n" + "="*60)
        print("Testing: Search for 'sustainable development'")
        print("="*60)
        
        results = search_catalog(catalog, "sustainable development")
        
        for dataset_id, metadata in results.items():
            print(f"\nDataset: {dataset_id}")
            print(f"Name: {metadata['name']}")
            print(f"Description: {metadata['description'][:200]}...")
            print(f"Agency: {metadata['agency']}")
        
        # Check if your specific dataset is there
        if "DSD_SDG@DF_SDG_G_10" in catalog:
            print("\n" + "="*60)
            print("✓ Found your SDG dataset!")
            print("="*60)
            sdg = catalog["DSD_SDG@DF_SDG_G_10"]
            print(f"Name: {sdg['name']}")
            print(f"Description: {sdg['description']}")
        else:
            print("\n✗ DSD_SDG@DF_SDG_G_10 not found in catalog")