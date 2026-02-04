"""
Retry dimension extraction for DSDs that failed due to rate limiting.

This script:
1. Loads failed_dsds.json
2. Filters DSDs that failed with 429 errors
3. Retries dimension extraction for those DSDs only
4. Updates the main catalog with any newly retrieved dimensions
"""

import json
from pathlib import Path
from extract_dimensions import DimensionExtractor

def load_rate_limited_dsds(failed_path: Path) -> dict:
    """
    Load DSDs that failed due to rate limiting.

    Returns:
        Dict mapping DSD_ID -> agency for rate-limited DSDs
    """
    with open(failed_path, 'r', encoding='utf-8') as f:
        failed_dsds = json.load(f)

    rate_limited = {}
    for item in failed_dsds:
        error = item['error']
        if '429' in error or 'Rate limit' in error:
            rate_limited[item['dsd_id']] = item['agency']

    return rate_limited

def main():
    """Main execution."""
    base_dir = Path(__file__).parent.parent / "data/catalogs"

    failed_path = base_dir / "failed_dsds.json"
    catalog_path = base_dir / "oecd_dataset_catalog_by_category.json"

    print("="*80)
    print("Retry Failed Dimension Extractions (429 Rate Limit)")
    print("="*80)
    print()

    # Load rate-limited DSDs
    print("📋 Loading rate-limited DSDs from failed_dsds.json...")
    rate_limited_dsds = load_rate_limited_dsds(failed_path)
    print(f"   Found {len(rate_limited_dsds)} DSDs that failed with 429 errors")
    print()

    if not rate_limited_dsds:
        print("✅ No rate-limited DSDs to retry!")
        return

    # Show first 10 DSDs
    print("   Sample DSDs to retry:")
    for i, dsd in enumerate(sorted(rate_limited_dsds.keys())[:10], 1):
        print(f"   {i}. {dsd}")
    if len(rate_limited_dsds) > 10:
        print(f"   ... and {len(rate_limited_dsds) - 10} more")
    print()

    # Create a custom extractor that only processes these DSDs
    print("🚀 Starting retry extraction...")
    print(f"   This will take approximately {(len(rate_limited_dsds) // 60) + 1} hours")
    print()

    class RetryExtractor(DimensionExtractor):
        """Custom extractor that only processes specified DSDs."""

        def __init__(self, catalog_path: str, retry_dsds: dict):
            super().__init__(catalog_path, test_mode=False)
            self.retry_dsds = retry_dsds

        def extract_unique_dsds(self) -> dict:
            """Override to return only the DSDs we want to retry."""
            return self.retry_dsds

    # Run the extraction
    try:
        extractor = RetryExtractor(str(catalog_path), rate_limited_dsds)
        extractor.run()

        print()
        print("="*80)
        print("✅ Retry extraction complete!")
        print("="*80)
        print()
        print("Next steps:")
        print("1. Check the updated catalog:")
        print("   data/catalogs/oecd_dataset_catalog_with_dimensions.json")
        print()
        print("2. If there are still failures, check:")
        print("   data/catalogs/failed_dsds.json")
        print()

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Progress has been saved.")
        print("   Run this script again to resume from checkpoint.")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
