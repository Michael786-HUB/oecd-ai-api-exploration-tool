import json
import anthropic
import time

def categorize_datasets(catalog_path, api_key):
    """
    Use Claude to categorize OECD datasets based on their names and descriptions.
    """
    
    # Load the existing catalog
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)
    
    print(f"Loaded {len(catalog)} datasets")
    
    # Define categories from the OECD website
    categories = [
        "Agriculture and fisheries",
        "Development", 
        "Economy",
        "Education and skills",
        "Employment",
        "Environment and climate change",
        "Finance and investment",
        "Health",
        "Industry, business and entrepreneurship",
        "Public governance",
        "Regional, rural and urban development",
        "Science, technology and innovation",
        "Society",
        "Taxation",
        "Trade",
        "Transport"
    ]
    
    # Initialize Claude
    client = anthropic.Anthropic(api_key=api_key)
    
    # System prompt for categorization
    system_prompt = f"""You are an expert at categorizing OECD datasets.

Available categories:
{chr(10).join(f"- {cat}" for cat in categories)}

Given a dataset name and description, assign it to the MOST appropriate category.
Respond with ONLY the category name, nothing else.

If a dataset could fit multiple categories, choose the PRIMARY one.
If unsure, use your best judgment based on the main topic."""

    categorized_catalog = {}
    
    print(f"\nCategorizing datasets...\n")
    
    for i, (dataset_id, metadata) in enumerate(catalog.items(), 1):
        name = metadata['name']
        description = metadata['description'][:500]  # Limit description length
        
        # Create prompt for this dataset
        user_prompt = f"""Dataset: {name}

Description: {description}

Category:"""
        
        try:
            # Call Claude API
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            
            category = message.content[0].text.strip()
            
            # Validate category
            if category not in categories:
                # Try to match partial category name
                matched = False
                for valid_cat in categories:
                    if category.lower() in valid_cat.lower() or valid_cat.lower() in category.lower():
                        category = valid_cat
                        matched = True
                        break
                
                if not matched:
                    category = "Other"
            
            # Add to categorized catalog
            categorized_catalog[dataset_id] = {
                **metadata,
                "category": category
            }
            
            # Print progress
            if i % 10 == 0 or i <= 5:
                print(f"[{i}/{len(catalog)}] {dataset_id[:30]:30} → {category}")
            
            # Rate limiting - be nice to the API
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Error on {dataset_id}: {e}")
            categorized_catalog[dataset_id] = {
                **metadata,
                "category": "Uncategorized"
            }
    
    print(f"\n✓ Categorized {len(categorized_catalog)} datasets")
    
    # Show category distribution
    category_counts = {}
    for dataset in categorized_catalog.values():
        cat = dataset['category']
        category_counts[cat] = category_counts.get(cat, 0) + 1
    
    print("\nCategory distribution:")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:45} {count:3} datasets")
    
    return categorized_catalog


def restructure_by_category(categorized_catalog):
    """
    Restructure the catalog to group datasets by category.
    
    Returns:
    {
        "Health": {
            "datasets": {
                "DSD_SHA@DF_SHA": {...},
                ...
            }
        },
        ...
    }
    """
    
    structured = {}
    
    for dataset_id, metadata in categorized_catalog.items():
        category = metadata.get('category', 'Uncategorized')
        
        if category not in structured:
            structured[category] = {"datasets": {}}
        
        # Remove category from individual dataset metadata (it's redundant now)
        dataset_meta = {k: v for k, v in metadata.items() if k != 'category'}
        
        structured[category]["datasets"][dataset_id] = dataset_meta
    
    return structured


def save_catalogs(flat_catalog, structured_catalog, output_dir):
    """Save both flat and structured versions"""
    
    # Save flat version (with category field in each dataset)
    flat_path = f"{output_dir}/oecd_dataset_catalog_categorized.json"
    with open(flat_path, 'w', encoding='utf-8') as f:
        json.dump(flat_catalog, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved flat catalog to: {flat_path}")
    
    # Save structured version (grouped by category)
    structured_path = f"{output_dir}/oecd_dataset_catalog_by_category.json"
    with open(structured_path, 'w', encoding='utf-8') as f:
        json.dump(structured_catalog, f, indent=2, ensure_ascii=False)
    print(f"✓ Saved structured catalog to: {structured_path}")


# ============= RUN IT =============

if __name__ == "__main__":
    
    # Your paths
    catalog_path = "/Users/Micha/Documents/Documents/OCED Research Tool/oecd_dataset_catalog.json"
    output_dir = "/Users/Micha/Documents/Documents/OCED Research Tool"
    
    # Get Anthropic API key from environment variable
    import os
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("Set it with: export ANTHROPIC_API_KEY='your-key-here'")
        exit(1)
    
    # Categorize all datasets
    categorized = categorize_datasets(catalog_path, api_key)
    
    # Restructure by category
    structured = restructure_by_category(categorized)
    
    # Save both versions
    save_catalogs(categorized, structured, output_dir)
    
    print("\n" + "="*60)
    print("Done! You now have:")
    print("1. Flat catalog with categories added")
    print("2. Structured catalog grouped by category")
    print("="*60)