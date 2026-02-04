"""
Script to add version IDs from oecd_dataset_catalog_v2.json
to oecd_dataset_catalog_by_category.json
"""

import json
from pathlib import Path

def add_versions_to_categorized_catalog():
    """
    Add version information from v2 catalog to the categorized catalog.
    """

    # Define file paths
    base_dir = Path(__file__).parent.parent
    v2_catalog_path = base_dir / "oecd_dataset_catalog_v2.json"
    categorized_catalog_path = base_dir / "data/catalogs/oecd_dataset_catalog_by_category.json"

    # Load both catalogs
    print("📖 Loading catalogs...")
    with open(v2_catalog_path, 'r', encoding='utf-8') as f:
        v2_catalog = json.load(f)

    with open(categorized_catalog_path, 'r', encoding='utf-8') as f:
        categorized_catalog = json.load(f)

    # Create backup
    backup_path = categorized_catalog_path.with_suffix('.json.backup')
    print(f"📦 Creating backup: {backup_path.name}")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(categorized_catalog, f, indent=2, ensure_ascii=False)

    # Add versions
    print("\n🔧 Adding version information...")
    total_datasets = 0
    updated_datasets = 0
    missing_versions = []

    for category, cat_data in categorized_catalog.items():
        for dataset_id, metadata in cat_data["datasets"].items():
            total_datasets += 1

            # Check if this dataset exists in v2 catalog
            if dataset_id in v2_catalog:
                version = v2_catalog[dataset_id].get("version", "1.0")
                metadata["version"] = version
                updated_datasets += 1

                if updated_datasets <= 5:  # Show first 5 examples
                    print(f"  ✓ {dataset_id}: version {version}")
            else:
                # Dataset not found in v2 catalog, use default
                metadata["version"] = "1.0"
                missing_versions.append(dataset_id)
                if len(missing_versions) <= 3:
                    print(f"  ⚠️  {dataset_id}: not found in v2, using default 1.0")

    # Save updated catalog
    print(f"\n💾 Saving updated catalog...")
    with open(categorized_catalog_path, 'w', encoding='utf-8') as f:
        json.dump(categorized_catalog, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n✅ Done!")
    print(f"   Total datasets: {total_datasets}")
    print(f"   Updated with versions from v2: {updated_datasets}")
    print(f"   Set to default (1.0): {len(missing_versions)}")

    if missing_versions:
        print(f"\n📋 Datasets not found in v2 catalog (using version 1.0):")
        for dataset_id in missing_versions[:10]:  # Show first 10
            print(f"   - {dataset_id}")
        if len(missing_versions) > 10:
            print(f"   ... and {len(missing_versions) - 10} more")

    print(f"\n💡 Backup saved to: {backup_path}")
    print(f"   To restore: cp {backup_path} {categorized_catalog_path}")

if __name__ == "__main__":
    print("=" * 60)
    print("OECD Catalog Version Updater")
    print("=" * 60)
    print()

    add_versions_to_categorized_catalog()
