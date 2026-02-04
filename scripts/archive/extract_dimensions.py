"""
Extract dimension structures from OECD datastructure API.

This script:
1. Extracts unique DSD IDs from the catalog
2. Fetches dimension metadata for each DSD from the OECD API
3. Updates the catalog with dimension information
4. Handles rate limiting (60 requests/hour)
5. Saves progress after each batch (resumable)
"""

import json
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timedelta
import time
from typing import Dict, List, Tuple, Set
import sys

class DimensionExtractor:
    """Extract and cache dimension structures from OECD API."""

    # OECD API allows 60 requests per hour
    REQUESTS_PER_HOUR = 60
    BATCH_SIZE = 60

    # XML namespaces for SDMX v2.1 and v3.0
    NAMESPACES = {
        'structure': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure',
        'str': 'http://www.sdmx.org/resources/sdmxml/schemas/v3_0/structure',
        'common': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common',
        'com': 'http://www.sdmx.org/resources/sdmxml/schemas/v3_0/common'
    }

    def __init__(self, catalog_path: str, test_mode: bool = False):
        """
        Initialize the extractor.

        Args:
            catalog_path: Path to the catalog JSON file
            test_mode: If True, only process first 3 datasets
        """
        self.catalog_path = Path(catalog_path)
        self.base_dir = self.catalog_path.parent
        self.test_mode = test_mode

        # Output paths
        self.output_catalog_path = self.base_dir / "oecd_dataset_catalog_with_dimensions.json"
        self.log_path = self.base_dir / "dimension_extraction_log.txt"
        self.failed_path = self.base_dir / "failed_dsds.json"
        self.checkpoint_path = self.base_dir / "extraction_checkpoint.json"

        # Load catalog
        with open(self.catalog_path, 'r', encoding='utf-8') as f:
            self.catalog = json.load(f)

        # Initialize tracking
        self.session = requests.Session()
        self.failed_dsds = []
        self.processed_dsds = set()
        self.start_time = None

    def log(self, message: str, to_console: bool = True):
        """Log a message to file and optionally console."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"

        if to_console:
            print(log_msg)

        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(log_msg + "\n")

    def extract_unique_dsds(self) -> Dict[str, str]:
        """
        Extract unique DSD IDs and their agencies from the catalog.

        Returns:
            Dict mapping DSD_ID -> agency
        """
        dsd_to_agency = {}

        for category, cat_data in self.catalog.items():
            for dataset_id, metadata in cat_data["datasets"].items():
                # Extract DSD (part before @)
                if '@' in dataset_id:
                    dsd_id = dataset_id.split('@')[0]
                else:
                    dsd_id = dataset_id

                agency = metadata.get('agency', 'OECD')

                # Store first occurrence of each DSD
                if dsd_id not in dsd_to_agency:
                    dsd_to_agency[dsd_id] = agency

        return dsd_to_agency

    def fetch_dimensions(self, agency: str, dsd_id: str) -> List[Dict]:
        """
        Fetch dimension structure from OECD datastructure API.

        Args:
            agency: Agency code (e.g., OECD.ELS.HD)
            dsd_id: Data Structure Definition ID (e.g., DSD_SHA)

        Returns:
            List of dimensions with position, id, and optionally name

        Raises:
            requests.exceptions.HTTPError: If rate limited (429) or other HTTP error
        """
        url = f"https://sdmx.oecd.org/public/rest/datastructure/{agency}/{dsd_id}"

        try:
            response = self.session.get(url, timeout=30)

            # Check for rate limiting specifically
            if response.status_code == 429:
                self.log(f"  🚫 Rate limited (429) - stopping batch")
                raise requests.exceptions.HTTPError("Rate limit exceeded (429)", response=response)

            response.raise_for_status()

            # Parse XML
            root = ET.fromstring(response.content)
            dimensions = []

            # Try both v2.1 and v3.0 namespace patterns
            dimension_paths = [
                ".//structure:Dimension",
                ".//str:Dimension",
                ".//structure:TimeDimension",
                ".//str:TimeDimension"
            ]

            for path in dimension_paths:
                elements = root.findall(path, self.NAMESPACES)
                if elements:
                    for dim in elements:
                        dim_id = dim.get('id')
                        position = dim.get('position')

                        # Try to get name
                        name = None
                        for ns_prefix in ['common', 'com']:
                            name_elem = dim.find(f"{ns_prefix}:Name", self.NAMESPACES)
                            if name_elem is not None:
                                name = name_elem.text
                                break

                        if dim_id and position:
                            dimensions.append({
                                'position': int(position),
                                'id': dim_id,
                                'name': name
                            })

                    if dimensions:
                        break

            # Sort by position
            dimensions.sort(key=lambda x: x['position'])

            # Remove name if None for cleaner output
            for dim in dimensions:
                if dim['name'] is None:
                    del dim['name']

            return dimensions

        except requests.exceptions.RequestException as e:
            self.log(f"  ❌ Network error for {dsd_id}: {str(e)}")
            raise
        except ET.ParseError as e:
            self.log(f"  ❌ XML parse error for {dsd_id}: {str(e)}")
            raise
        except Exception as e:
            self.log(f"  ❌ Unexpected error for {dsd_id}: {str(e)}")
            raise

    def save_checkpoint(self, processed_dsds: Set[str], failed_dsds: List[Dict]):
        """Save progress checkpoint."""
        checkpoint = {
            'processed_dsds': list(processed_dsds),
            'failed_dsds': failed_dsds,
            'timestamp': datetime.now().isoformat()
        }

        with open(self.checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, indent=2)

    def load_checkpoint(self) -> Tuple[Set[str], List[Dict]]:
        """Load progress from checkpoint if exists."""
        if self.checkpoint_path.exists():
            with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)

            processed = set(checkpoint.get('processed_dsds', []))
            failed = checkpoint.get('failed_dsds', [])
            timestamp = checkpoint.get('timestamp', 'unknown')

            self.log(f"📂 Resuming from checkpoint: {timestamp}")
            self.log(f"   Already processed: {len(processed)} DSDs")
            self.log(f"   Previously failed: {len(failed)} DSDs")

            return processed, failed

        return set(), []

    def update_catalog_with_dimensions(self, dsd_dimensions: Dict[str, List[Dict]]):
        """
        Update catalog with dimension information.

        Args:
            dsd_dimensions: Dict mapping DSD_ID -> list of dimensions
        """
        updated_count = 0

        for category, cat_data in self.catalog.items():
            for dataset_id, metadata in cat_data["datasets"].items():
                # Extract DSD
                if '@' in dataset_id:
                    dsd_id = dataset_id.split('@')[0]
                else:
                    dsd_id = dataset_id

                # Add dimensions if available
                if dsd_id in dsd_dimensions:
                    metadata['dimensions'] = dsd_dimensions[dsd_id]
                    updated_count += 1

        self.log(f"✅ Updated {updated_count} datasets with dimension information")

    def run(self):
        """Main execution flow."""
        self.start_time = datetime.now()

        # Initialize log
        self.log("="*80)
        self.log("OECD Dimension Extraction Script")
        self.log("="*80)
        self.log(f"Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"Test mode: {self.test_mode}")

        # Extract unique DSDs
        self.log("\n📋 Step 1: Extracting unique DSDs from catalog...")
        dsd_to_agency = self.extract_unique_dsds()
        self.log(f"   Found {len(dsd_to_agency)} unique DSDs")

        if self.test_mode:
            # Test with first 3 DSDs
            test_dsds = {
                'DSD_SHA': 'OECD.ELS.HD',
                'DSD_NAAG': 'OECD.SDD.NAD',
                'DSD_FUA_CLIM': 'OECD.CFE.EDS'
            }
            dsd_to_agency = {k: v for k, v in dsd_to_agency.items() if k in test_dsds}
            self.log(f"   TEST MODE: Processing only {len(dsd_to_agency)} DSDs")

        # Load checkpoint
        self.processed_dsds, self.failed_dsds = self.load_checkpoint()

        # Filter out already processed
        remaining_dsds = {k: v for k, v in dsd_to_agency.items()
                         if k not in self.processed_dsds}

        self.log(f"\n📊 Processing plan:")
        self.log(f"   Total unique DSDs: {len(dsd_to_agency)}")
        self.log(f"   Already processed: {len(self.processed_dsds)}")
        self.log(f"   Remaining: {len(remaining_dsds)}")

        if not remaining_dsds:
            self.log("\n✅ All DSDs already processed!")
            return

        # Calculate batches
        dsd_list = list(remaining_dsds.items())
        total_batches = (len(dsd_list) + self.BATCH_SIZE - 1) // self.BATCH_SIZE

        estimated_hours = total_batches
        self.log(f"   Batches needed: {total_batches}")
        self.log(f"   Estimated time: ~{estimated_hours} hours")

        # Process in batches (continue until all DSDs are processed)
        dsd_dimensions = {}
        batch_num = 0

        while True:
            # Recalculate remaining DSDs each iteration
            remaining_dsds = {k: v for k, v in dsd_to_agency.items()
                            if k not in self.processed_dsds}

            if not remaining_dsds:
                self.log(f"\n✅ All DSDs processed!")
                break

            # Get next batch
            dsd_list = list(remaining_dsds.items())
            total_remaining = len(dsd_list)
            batch_size = min(self.BATCH_SIZE, total_remaining)
            batch = dsd_list[:batch_size]

            batch_num += 1
            batch_start_time = datetime.now()

            self.log(f"\n🔄 Batch {batch_num}")
            self.log(f"   Remaining DSDs: {total_remaining}")
            self.log(f"   Processing next {len(batch)} DSDs")

            # Process batch - stop if rate limited
            rate_limited = False
            for i, (dsd_id, agency) in enumerate(batch, 1):
                try:
                    self.log(f"   [{i}/{len(batch)}] Fetching {dsd_id} ({agency})...")

                    dimensions = self.fetch_dimensions(agency, dsd_id)

                    if dimensions:
                        dsd_dimensions[dsd_id] = dimensions
                        self.log(f"      ✓ Found {len(dimensions)} dimensions")
                    else:
                        self.log(f"      ⚠️  No dimensions found")

                    self.processed_dsds.add(dsd_id)

                    # Small delay to be nice to the API
                    time.sleep(1)

                except requests.exceptions.HTTPError as e:
                    # Check if it's a rate limit error (429)
                    if e.response and e.response.status_code == 429:
                        self.log(f"   🚫 Rate limit hit! Stopping batch early.")
                        self.log(f"   Processed {i-1} of {len(batch)} DSDs in this batch")
                        rate_limited = True
                        # Don't mark this DSD as processed - we'll retry it next time
                        break
                    else:
                        # Other HTTP error - mark as failed
                        self.failed_dsds.append({
                            'dsd_id': dsd_id,
                            'agency': agency,
                            'error': str(e),
                            'timestamp': datetime.now().isoformat()
                        })
                        self.processed_dsds.add(dsd_id)

                except Exception as e:
                    # Other error - mark as failed
                    self.failed_dsds.append({
                        'dsd_id': dsd_id,
                        'agency': agency,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    })
                    self.processed_dsds.add(dsd_id)

            # Save checkpoint after batch
            self.save_checkpoint(self.processed_dsds, self.failed_dsds)
            self.log(f"   💾 Checkpoint saved")

            # Check if there are more DSDs to process
            remaining_after_batch = {k: v for k, v in dsd_to_agency.items()
                                    if k not in self.processed_dsds}

            # Wait for rate limit reset if there are more DSDs to process
            if remaining_after_batch:
                next_batch_time = batch_start_time + timedelta(hours=1)
                wait_seconds = (next_batch_time - datetime.now()).total_seconds()

                if wait_seconds > 0:
                    wait_minutes = int(wait_seconds // 60)
                    self.log(f"\n⏳ Waiting {wait_minutes} minutes for rate limit reset...")
                    self.log(f"   {len(remaining_after_batch)} DSDs remaining")
                    self.log(f"   Next batch starts at: {next_batch_time.strftime('%H:%M:%S')}")
                    time.sleep(wait_seconds)
                else:
                    self.log(f"\n✓ Rate limit window passed, continuing immediately...")

        # Update catalog
        self.log(f"\n📝 Step 2: Updating catalog with dimensions...")
        self.update_catalog_with_dimensions(dsd_dimensions)

        # Save updated catalog
        self.log(f"\n💾 Step 3: Saving updated catalog...")
        with open(self.output_catalog_path, 'w', encoding='utf-8') as f:
            json.dump(self.catalog, f, indent=2, ensure_ascii=False)
        self.log(f"   Saved to: {self.output_catalog_path}")

        # Save failed DSDs
        if self.failed_dsds:
            with open(self.failed_path, 'w', encoding='utf-8') as f:
                json.dump(self.failed_dsds, f, indent=2)
            self.log(f"\n⚠️  Failed DSDs saved to: {self.failed_path}")
            self.log(f"   Failed count: {len(self.failed_dsds)}")

        # Final summary
        duration = datetime.now() - self.start_time
        self.log(f"\n" + "="*80)
        self.log("SUMMARY")
        self.log("="*80)
        self.log(f"Total DSDs: {len(dsd_to_agency)}")
        self.log(f"Successfully processed: {len(self.processed_dsds) - len(self.failed_dsds)}")
        self.log(f"Failed: {len(self.failed_dsds)}")
        self.log(f"Duration: {duration}")
        self.log(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.log("="*80)

        # Clean up checkpoint on success
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
            self.log("🗑️  Checkpoint file removed (extraction complete)")

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract OECD dimension structures")
    parser.add_argument('--test', action='store_true',
                       help='Test mode: only process 3 DSDs')
    parser.add_argument('--catalog', type=str,
                       default='data/catalogs/oecd_dataset_catalog_by_category.json',
                       help='Path to catalog file')

    args = parser.parse_args()

    try:
        extractor = DimensionExtractor(args.catalog, test_mode=args.test)
        extractor.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Progress has been saved.")
        print("   Run the script again to resume from checkpoint.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
