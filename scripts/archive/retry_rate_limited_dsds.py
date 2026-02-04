"""
Retry DSDs that failed due to rate limiting (429 errors).

This script:
1. Parses the extraction log to find DSDs that failed with 429 errors
2. Removes them from the checkpoint so they'll be retried
3. Updates the checkpoint file
"""

import json
import re
from pathlib import Path

def extract_rate_limited_dsds(log_path: Path) -> set:
    """
    Parse the log file and extract DSDs that failed with 429 errors.

    Args:
        log_path: Path to the dimension extraction log file

    Returns:
        Set of DSD IDs that failed with 429 errors
    """
    rate_limited_dsds = set()

    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Look for lines with 429 errors
            if '429' in line and 'Too Many Requests' in line:
                # Extract the DSD ID from the line
                # Format: "Network error for DSD_XXX: 429 Client Error..."
                match = re.search(r'for ([A-Za-z0-9_@]+):', line)
                if match:
                    dsd_id = match.group(1)
                    rate_limited_dsds.add(dsd_id)

    return rate_limited_dsds

def update_checkpoint(checkpoint_path: Path, dsds_to_retry: set):
    """
    Update the checkpoint to remove DSDs that should be retried.

    Args:
        checkpoint_path: Path to the checkpoint file
        dsds_to_retry: Set of DSD IDs to remove from processed list
    """
    if not checkpoint_path.exists():
        print(f"❌ Checkpoint file not found: {checkpoint_path}")
        print("   The extraction may have completed or not started yet.")
        return

    # Load checkpoint
    with open(checkpoint_path, 'r', encoding='utf-8') as f:
        checkpoint = json.load(f)

    processed_dsds = set(checkpoint.get('processed_dsds', []))
    failed_dsds = checkpoint.get('failed_dsds', [])

    # Remove rate-limited DSDs from processed list
    original_count = len(processed_dsds)
    processed_dsds -= dsds_to_retry

    # Also remove them from failed list if they're there
    failed_dsds = [f for f in failed_dsds if f['dsd_id'] not in dsds_to_retry]

    removed_count = original_count - len(processed_dsds)

    # Update checkpoint
    checkpoint['processed_dsds'] = list(processed_dsds)
    checkpoint['failed_dsds'] = failed_dsds

    # Save updated checkpoint
    with open(checkpoint_path, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, indent=2)

    print(f"✅ Updated checkpoint:")
    print(f"   Removed {removed_count} DSDs from processed list")
    print(f"   Total DSDs to retry: {len(dsds_to_retry)}")
    print(f"   Remaining processed: {len(processed_dsds)}")

def main():
    """Main execution."""
    base_dir = Path(__file__).parent.parent / "data/catalogs"

    log_path = base_dir / "dimension_extraction_log.txt"
    checkpoint_path = base_dir / "extraction_checkpoint.json"

    print("="*60)
    print("Retry Rate-Limited DSDs")
    print("="*60)
    print()

    # Extract rate-limited DSDs from log
    print("📋 Step 1: Analyzing log file...")
    rate_limited_dsds = extract_rate_limited_dsds(log_path)

    print(f"   Found {len(rate_limited_dsds)} DSDs that failed with 429 errors")
    print()

    if not rate_limited_dsds:
        print("✅ No rate-limited DSDs found. Nothing to retry!")
        return

    # Show first 10 DSDs
    print("   Sample DSDs to retry:")
    for dsd in sorted(rate_limited_dsds)[:10]:
        print(f"   - {dsd}")
    if len(rate_limited_dsds) > 10:
        print(f"   ... and {len(rate_limited_dsds) - 10} more")
    print()

    # Update checkpoint
    print("📝 Step 2: Updating checkpoint...")
    update_checkpoint(checkpoint_path, rate_limited_dsds)
    print()

    print("="*60)
    print("✅ Done!")
    print("="*60)
    print()
    print("Next steps:")
    print("1. Run the extraction script again:")
    print("   python scripts/extract_dimensions.py")
    print()
    print("2. The script will automatically retry the rate-limited DSDs")
    print()

if __name__ == "__main__":
    main()
