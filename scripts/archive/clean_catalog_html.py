"""
Script to clean HTML from the OECD dataset catalog JSON file.
This permanently updates the catalog file to have plain text descriptions.
"""

import json
import re
from html import unescape
import sys
from pathlib import Path

def clean_html_description(html_text):
    """
    Clean HTML tags and entities from description text.
    Converts HTML to readable plain text while preserving structure.
    """
    if not html_text:
        return ""

    # Unescape HTML entities first (&gt; -> >, &nbsp; -> space, etc.)
    text = unescape(html_text)

    # Replace common block elements with newlines
    text = re.sub(r'</p>\s*<p>', '\n\n', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</li>\s*<li>', '\n• ', text)
    text = re.sub(r'<li>', '\n• ', text)
    text = re.sub(r'</h\d>', '\n\n', text)
    text = re.sub(r'<h\d[^>]*>', '\n**', text)

    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Clean up excessive whitespace
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()

    return text

def clean_catalog_file(input_path, output_path=None, backup=True):
    """
    Clean HTML from all descriptions in the catalog file.

    Args:
        input_path: Path to the catalog JSON file
        output_path: Path for output (defaults to same as input)
        backup: Whether to create a backup of the original file
    """
    input_path = Path(input_path)

    if not input_path.exists():
        print(f"❌ Error: File not found: {input_path}")
        sys.exit(1)

    # Set output path
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)

    # Create backup if requested
    if backup and output_path == input_path:
        backup_path = input_path.with_suffix('.json.backup')
        print(f"📦 Creating backup: {backup_path}")
        with open(input_path, 'r', encoding='utf-8') as f:
            backup_content = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(backup_content)

    # Load the catalog
    print(f"📖 Loading catalog from: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    # Clean all descriptions
    total_datasets = 0
    cleaned_datasets = 0

    print("🧹 Cleaning HTML from descriptions...")
    for category, cat_data in catalog.items():
        for dataset_id, metadata in cat_data['datasets'].items():
            total_datasets += 1

            original_desc = metadata.get('description', '')

            # Check if description contains HTML
            if '<' in original_desc and '>' in original_desc:
                cleaned_desc = clean_html_description(original_desc)
                metadata['description'] = cleaned_desc
                cleaned_datasets += 1

                if cleaned_datasets <= 3:  # Show first 3 examples
                    print(f"\n  ✓ Cleaned: {dataset_id}")
                    print(f"    Before: {original_desc[:100]}...")
                    print(f"    After:  {cleaned_desc[:100]}...")

    # Save the cleaned catalog
    print(f"\n💾 Saving cleaned catalog to: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n✅ Done!")
    print(f"   Total datasets: {total_datasets}")
    print(f"   Cleaned datasets: {cleaned_datasets}")
    print(f"   Unchanged datasets: {total_datasets - cleaned_datasets}")

    if backup and output_path == input_path:
        print(f"\n💡 Tip: Original file backed up to {backup_path}")
        print(f"   To restore: mv {backup_path} {input_path}")

if __name__ == "__main__":
    # Default catalog path
    catalog_path = Path(__file__).parent.parent / "data/catalogs/oecd_dataset_catalog_by_category.json"

    print("=" * 60)
    print("OECD Catalog HTML Cleaner")
    print("=" * 60)
    print()

    # Ask for confirmation
    print(f"This will clean HTML from descriptions in:")
    print(f"  {catalog_path}")
    print()
    response = input("Continue? (yes/no): ").strip().lower()

    if response in ['yes', 'y']:
        clean_catalog_file(catalog_path)
    else:
        print("\n❌ Cancelled")
        sys.exit(0)
