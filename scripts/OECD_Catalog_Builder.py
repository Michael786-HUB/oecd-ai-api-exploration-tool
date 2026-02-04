"""
OECD Catalog Builder
====================

Consolidated module for building and managing OECD dataset catalogs.

This module provides comprehensive functionality for:
- Fetching dataset metadata from OECD SDMX API
- Extracting dimension structures with rate limiting
- Cleaning HTML from descriptions
- Merging version information
- Resumable batch processing with checkpoints
- Error recovery and retry mechanisms

Main Components:
    OECDCatalogBuilder: Primary class for all catalog operations

Usage:
    # As a module
    from OECD_Catalog_Builder import OECDCatalogBuilder

    builder = OECDCatalogBuilder(output_dir="./data")
    catalog = builder.build_complete_catalog()

    # As a CLI tool
    python OECD_Catalog_Builder.py --help

Author: OECD Research Tool
Last Updated: 2026-02-04
"""

import requests
import xml.etree.ElementTree as ET
import json
import re
from html import unescape
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Set, Optional
import time
import sys


class OECDCatalogBuilder:
    """
    Main class for building and managing OECD dataset catalogs.

    This class handles:
    - Fetching dataset metadata from OECD SDMX API
    - Parsing XML responses (SDMX v2.1 and v3.0)
    - Extracting dimension structures with rate limiting
    - HTML cleaning and data validation
    - Progress checkpointing for resumable operations
    - Error handling and retry logic

    Attributes:
        output_dir (Path): Directory for output files
        rate_limit (int): Maximum API requests per hour (default: 60)
        session (requests.Session): HTTP session for API requests
        catalog (dict): Main catalog data structure
        log_file (Path): Path to log file
    """

    # SDMX XML namespaces for v2.1 and v3.0
    NAMESPACES_V21 = {
        'message': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message',
        'structure': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure',
        'common': 'http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common'
    }

    NAMESPACES_V30 = {
        'str': 'http://www.sdmx.org/resources/sdmxml/schemas/v3_0/structure',
        'com': 'http://www.sdmx.org/resources/sdmxml/schemas/v3_0/common'
    }

    # Combined namespaces for dimension extraction
    NAMESPACES_ALL = {**NAMESPACES_V21, **NAMESPACES_V30}

    # OECD API endpoints
    CATALOG_URL = "https://sdmx.oecd.org/public/rest/dataflow/All"
    DATASTRUCTURE_URL = "https://sdmx.oecd.org/public/rest/datastructure/{agency}/{dsd_id}"

    # Rate limiting
    REQUESTS_PER_HOUR = 60
    BATCH_SIZE = 60

    def __init__(self, output_dir: str = ".", rate_limit: int = 60, verbose: bool = True):
        """
        Initialize the catalog builder.

        Args:
            output_dir: Directory for output files (default: current directory)
            rate_limit: Maximum API requests per hour (default: 60)
            verbose: Enable console logging (default: True)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.rate_limit = rate_limit
        self.verbose = verbose
        self.session = requests.Session()
        self.catalog = {}

        # Output file paths
        self.log_file = self.output_dir / "catalog_builder_log.txt"
        self.checkpoint_file = self.output_dir / "checkpoint.json"
        self.failed_file = self.output_dir / "failed_dsds.json"

        # Initialize logging
        self._init_log()

    # ═══════════════════════════════════════════════════════════════════════
    # LOGGING & UTILITIES
    # ═══════════════════════════════════════════════════════════════════════

    def _init_log(self):
        """Initialize log file with header."""
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("OECD Catalog Builder - Execution Log\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n\n")

    def log(self, message: str, to_console: bool = None):
        """
        Log a message to file and optionally console.

        Args:
            message: Message to log
            to_console: Override verbose setting for this message
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"

        # Console output
        if to_console is None:
            to_console = self.verbose
        if to_console:
            print(log_msg)

        # File output
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + "\n")

    # ═══════════════════════════════════════════════════════════════════════
    # CORE CATALOG BUILDING
    # ═══════════════════════════════════════════════════════════════════════

    def fetch_catalog(self) -> Dict:
        """
        Fetch all OECD datasets with their metadata from the SDMX API.

        Returns:
            Dictionary: {dataset_id: {name, description, agency, version}}

        Raises:
            requests.exceptions.RequestException: If API request fails
            ET.ParseError: If XML parsing fails
        """
        self.log("Fetching dataset catalog from OECD API...")
        self.log(f"URL: {self.CATALOG_URL}")

        try:
            response = self.session.get(self.CATALOG_URL, timeout=60)
            response.raise_for_status()

            self.log(f"✓ Response received ({len(response.content)} bytes)")

            # Parse XML
            catalog = self._parse_catalog_xml(response.content)

            self.log(f"✓ Successfully extracted {len(catalog)} datasets")

            return catalog

        except requests.exceptions.RequestException as e:
            self.log(f"✗ Error fetching data: {e}")
            raise
        except ET.ParseError as e:
            self.log(f"✗ Error parsing XML: {e}")
            raise

    def _parse_catalog_xml(self, xml_content: bytes) -> Dict:
        """
        Parse SDMX XML to extract dataset metadata.

        Args:
            xml_content: Raw XML response from API

        Returns:
            Dictionary of dataset metadata
        """
        root = ET.fromstring(xml_content)
        ET.register_namespace('xml', 'http://www.w3.org/XML/1998/namespace')

        catalog = {}

        # Find all Dataflow elements
        dataflows = root.findall('.//structure:Dataflow', self.NAMESPACES_V21)

        self.log(f"✓ Found {len(dataflows)} datasets")
        self.log("Extracting metadata...")

        for dataflow in dataflows:
            # Get dataset ID and agency
            dataset_id = dataflow.get('id')
            agency_id = dataflow.get('agencyID')
            version = dataflow.get('version')

            # Get name (preferably in English)
            name_element = dataflow.find(
                './/common:Name[@{http://www.w3.org/XML/1998/namespace}lang="en"]',
                self.NAMESPACES_V21
            )
            if name_element is None:
                name_element = dataflow.find('.//common:Name', self.NAMESPACES_V21)

            name = name_element.text if name_element is not None else "No name"

            # Get description (preferably in English)
            desc_element = dataflow.find(
                './/common:Description[@{http://www.w3.org/XML/1998/namespace}lang="en"]',
                self.NAMESPACES_V21
            )
            if desc_element is None:
                desc_element = dataflow.find('.//common:Description', self.NAMESPACES_V21)

            description = desc_element.text if desc_element is not None else "No description available"

            # Store in catalog
            catalog[dataset_id] = {
                "name": name,
                "description": description,
                "agency": agency_id,
                "version": version
            }

            # Show examples
            if len(catalog) <= 3:
                self.log(f"Example {len(catalog)}: {dataset_id} - {name[:60]}...")

        return catalog

    def save_catalog(self, catalog: Dict, filename: str):
        """
        Save catalog to JSON file.

        Args:
            catalog: Catalog dictionary to save
            filename: Output filename (in output_dir)
        """
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)

        self.log(f"✓ Saved catalog to: {filepath}")

    def search_catalog(self, catalog: Dict, search_term: str) -> Dict:
        """
        Search for datasets by keyword in name or description.

        Args:
            catalog: Catalog dictionary to search
            search_term: Keyword to search for

        Returns:
            Dictionary of matching datasets
        """
        results = {}
        search_lower = search_term.lower()

        for dataset_id, metadata in catalog.items():
            name_match = search_lower in metadata['name'].lower()
            desc_match = search_lower in metadata['description'].lower()

            if name_match or desc_match:
                results[dataset_id] = metadata

        return results

    # ═══════════════════════════════════════════════════════════════════════
    # DIMENSION EXTRACTION
    # ═══════════════════════════════════════════════════════════════════════

    def extract_unique_dsds(self, catalog: Dict) -> Dict[str, str]:
        """
        Extract unique Data Structure Definition (DSD) IDs from catalog.

        Args:
            catalog: Catalog dictionary (may be hierarchical or flat)

        Returns:
            Dict mapping DSD_ID -> agency
        """
        dsd_to_agency = {}

        # Handle both flat and hierarchical catalog structures
        if any(isinstance(v, dict) and 'datasets' in v for v in catalog.values()):
            # Hierarchical structure (categorized)
            for category, cat_data in catalog.items():
                for dataset_id, metadata in cat_data.get("datasets", {}).items():
                    dsd_id = dataset_id.split('@')[0] if '@' in dataset_id else dataset_id
                    agency = metadata.get('agency', 'OECD')

                    if dsd_id not in dsd_to_agency:
                        dsd_to_agency[dsd_id] = agency
        else:
            # Flat structure
            for dataset_id, metadata in catalog.items():
                dsd_id = dataset_id.split('@')[0] if '@' in dataset_id else dataset_id
                agency = metadata.get('agency', 'OECD')

                if dsd_id not in dsd_to_agency:
                    dsd_to_agency[dsd_id] = agency

        return dsd_to_agency

    def fetch_dimension_structure(self, agency: str, dsd_id: str) -> List[Dict]:
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
        url = self.DATASTRUCTURE_URL.format(agency=agency, dsd_id=dsd_id)

        try:
            response = self.session.get(url, timeout=30)

            # Check for rate limiting
            if response.status_code == 429:
                self.log(f"  🚫 Rate limited (429) - stopping batch")
                raise requests.exceptions.HTTPError("Rate limit exceeded (429)", response=response)

            response.raise_for_status()

            # Parse dimensions from XML
            dimensions = self._parse_dimensions_xml(response.content)

            return dimensions

        except requests.exceptions.RequestException as e:
            self.log(f"  ❌ Network error for {dsd_id}: {str(e)}")
            raise
        except ET.ParseError as e:
            self.log(f"  ❌ XML parse error for {dsd_id}: {str(e)}")
            raise

    def _parse_dimensions_xml(self, xml_content: bytes) -> List[Dict]:
        """
        Parse dimension XML (supports both SDMX v2.1 and v3.0).

        Args:
            xml_content: Raw XML response from datastructure API

        Returns:
            List of dimension dictionaries sorted by position
        """
        root = ET.fromstring(xml_content)
        dimensions = []

        # Try both v2.1 and v3.0 namespace patterns
        dimension_paths = [
            ".//structure:Dimension",
            ".//str:Dimension",
            ".//structure:TimeDimension",
            ".//str:TimeDimension"
        ]

        for path in dimension_paths:
            elements = root.findall(path, self.NAMESPACES_ALL)
            if elements:
                for dim in elements:
                    dim_id = dim.get('id')
                    position = dim.get('position')

                    # Try to get name from both namespace versions
                    name = None
                    for ns_prefix in ['common', 'com']:
                        name_elem = dim.find(f"{ns_prefix}:Name", self.NAMESPACES_ALL)
                        if name_elem is not None:
                            name = name_elem.text
                            break

                    if dim_id and position:
                        dim_dict = {
                            'position': int(position),
                            'id': dim_id
                        }
                        if name:
                            dim_dict['name'] = name
                        dimensions.append(dim_dict)

                if dimensions:
                    break

        # Sort by position
        dimensions.sort(key=lambda x: x['position'])

        return dimensions

    def add_dimensions_to_catalog(self, catalog: Dict,
                                  progress_callback: Optional[callable] = None) -> Dict:
        """
        Add dimension information to all datasets in catalog with rate limiting.

        This method:
        - Extracts unique DSDs from the catalog
        - Fetches dimension structures in batches (respects rate limits)
        - Updates catalog with dimension information
        - Saves progress checkpoints for resumability
        - Handles errors and rate limiting gracefully

        Args:
            catalog: Catalog dictionary to enhance with dimensions
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            Updated catalog with dimension information
        """
        self.log("\n" + "="*80)
        self.log("DIMENSION EXTRACTION")
        self.log("="*80)

        start_time = datetime.now()

        # Extract unique DSDs
        self.log("\n📋 Step 1: Extracting unique DSDs from catalog...")
        dsd_to_agency = self.extract_unique_dsds(catalog)
        self.log(f"   Found {len(dsd_to_agency)} unique DSDs")

        # Load checkpoint if exists
        processed_dsds, failed_dsds = self._load_checkpoint()

        # Filter out already processed
        remaining_dsds = {k: v for k, v in dsd_to_agency.items()
                         if k not in processed_dsds}

        self.log(f"\n📊 Processing plan:")
        self.log(f"   Total unique DSDs: {len(dsd_to_agency)}")
        self.log(f"   Already processed: {len(processed_dsds)}")
        self.log(f"   Remaining: {len(remaining_dsds)}")

        if not remaining_dsds:
            self.log("\n✅ All DSDs already processed!")
            return catalog

        # Calculate batches
        total_batches = (len(remaining_dsds) + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        self.log(f"   Batches needed: {total_batches}")
        self.log(f"   Estimated time: ~{total_batches} hours")

        # Process in batches
        dsd_dimensions = {}
        batch_num = 0

        while remaining_dsds:
            dsd_list = list(remaining_dsds.items())
            batch_size = min(self.BATCH_SIZE, len(dsd_list))
            batch = dsd_list[:batch_size]

            batch_num += 1
            batch_start_time = datetime.now()

            self.log(f"\n🔄 Batch {batch_num}/{total_batches}")
            self.log(f"   Processing {len(batch)} DSDs")

            # Process batch
            for i, (dsd_id, agency) in enumerate(batch, 1):
                try:
                    self.log(f"   [{i}/{len(batch)}] Fetching {dsd_id} ({agency})...")

                    dimensions = self.fetch_dimension_structure(agency, dsd_id)

                    if dimensions:
                        dsd_dimensions[dsd_id] = dimensions
                        self.log(f"      ✓ Found {len(dimensions)} dimensions")
                    else:
                        self.log(f"      ⚠️  No dimensions found")

                    processed_dsds.add(dsd_id)

                    # Progress callback
                    if progress_callback:
                        progress_callback(len(processed_dsds), len(dsd_to_agency))

                    # Small delay to be nice to the API
                    time.sleep(1)

                except requests.exceptions.HTTPError as e:
                    if e.response and e.response.status_code == 429:
                        self.log(f"   🚫 Rate limit hit! Stopping batch early.")
                        break
                    else:
                        failed_dsds.append({
                            'dsd_id': dsd_id,
                            'agency': agency,
                            'error': str(e),
                            'timestamp': datetime.now().isoformat()
                        })
                        processed_dsds.add(dsd_id)

                except Exception as e:
                    failed_dsds.append({
                        'dsd_id': dsd_id,
                        'agency': agency,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    })
                    processed_dsds.add(dsd_id)

            # Save checkpoint
            self._save_checkpoint(processed_dsds, failed_dsds)
            self.log(f"   💾 Checkpoint saved")

            # Update remaining
            remaining_dsds = {k: v for k, v in dsd_to_agency.items()
                            if k not in processed_dsds}

            # Wait for rate limit reset if more DSDs remain
            if remaining_dsds:
                next_batch_time = batch_start_time + timedelta(hours=1)
                wait_seconds = (next_batch_time - datetime.now()).total_seconds()

                if wait_seconds > 0:
                    wait_minutes = int(wait_seconds // 60)
                    self.log(f"\n⏳ Waiting {wait_minutes} minutes for rate limit reset...")
                    self.log(f"   {len(remaining_dsds)} DSDs remaining")
                    time.sleep(wait_seconds)

        # Update catalog with dimensions
        self.log(f"\n📝 Updating catalog with dimensions...")
        catalog = self._merge_dimensions_into_catalog(catalog, dsd_dimensions)

        # Save failed DSDs
        if failed_dsds:
            with open(self.failed_file, 'w', encoding='utf-8') as f:
                json.dump(failed_dsds, f, indent=2)
            self.log(f"\n⚠️  Failed DSDs saved to: {self.failed_file}")
            self.log(f"   Failed count: {len(failed_dsds)}")

        # Summary
        duration = datetime.now() - start_time
        self.log(f"\n" + "="*80)
        self.log("DIMENSION EXTRACTION SUMMARY")
        self.log("="*80)
        self.log(f"Total DSDs: {len(dsd_to_agency)}")
        self.log(f"Successfully processed: {len(processed_dsds) - len(failed_dsds)}")
        self.log(f"Failed: {len(failed_dsds)}")
        self.log(f"Duration: {duration}")
        self.log("="*80)

        # Clean up checkpoint
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
            self.log("🗑️  Checkpoint file removed")

        return catalog

    def _merge_dimensions_into_catalog(self, catalog: Dict,
                                      dsd_dimensions: Dict[str, List[Dict]]) -> Dict:
        """
        Merge dimension information into catalog.

        Args:
            catalog: Catalog dictionary
            dsd_dimensions: Dict mapping DSD_ID -> list of dimensions

        Returns:
            Updated catalog
        """
        updated_count = 0

        # Handle both flat and hierarchical structures
        if any(isinstance(v, dict) and 'datasets' in v for v in catalog.values()):
            # Hierarchical
            for category, cat_data in catalog.items():
                for dataset_id, metadata in cat_data.get("datasets", {}).items():
                    dsd_id = dataset_id.split('@')[0] if '@' in dataset_id else dataset_id

                    if dsd_id in dsd_dimensions:
                        metadata['dimensions'] = dsd_dimensions[dsd_id]
                        updated_count += 1
        else:
            # Flat
            for dataset_id, metadata in catalog.items():
                dsd_id = dataset_id.split('@')[0] if '@' in dataset_id else dataset_id

                if dsd_id in dsd_dimensions:
                    metadata['dimensions'] = dsd_dimensions[dsd_id]
                    updated_count += 1

        self.log(f"✅ Updated {updated_count} datasets with dimension information")

        return catalog

    # ═══════════════════════════════════════════════════════════════════════
    # CATALOG ENHANCEMENT
    # ═══════════════════════════════════════════════════════════════════════

    def clean_html_descriptions(self, catalog: Dict) -> Dict:
        """
        Remove HTML tags from all descriptions in catalog.

        Args:
            catalog: Catalog dictionary

        Returns:
            Catalog with cleaned descriptions
        """
        self.log("\n🧹 Cleaning HTML from descriptions...")

        total_datasets = 0
        cleaned_datasets = 0

        # Handle both flat and hierarchical structures
        if any(isinstance(v, dict) and 'datasets' in v for v in catalog.values()):
            # Hierarchical
            for category, cat_data in catalog.items():
                for dataset_id, metadata in cat_data.get('datasets', {}).items():
                    total_datasets += 1
                    original_desc = metadata.get('description', '')

                    if '<' in original_desc and '>' in original_desc:
                        cleaned_desc = self._clean_html_text(original_desc)
                        metadata['description'] = cleaned_desc
                        cleaned_datasets += 1
        else:
            # Flat
            for dataset_id, metadata in catalog.items():
                total_datasets += 1
                original_desc = metadata.get('description', '')

                if '<' in original_desc and '>' in original_desc:
                    cleaned_desc = self._clean_html_text(original_desc)
                    metadata['description'] = cleaned_desc
                    cleaned_datasets += 1

        self.log(f"✅ Cleaned {cleaned_datasets} of {total_datasets} descriptions")

        return catalog

    def _clean_html_text(self, html_text: str) -> str:
        """
        Clean HTML tags and entities from text.

        Args:
            html_text: Text containing HTML

        Returns:
            Plain text without HTML
        """
        if not html_text:
            return ""

        # Unescape HTML entities
        text = unescape(html_text)

        # Replace block elements with newlines
        text = re.sub(r'</p>\s*<p>', '\n\n', text)
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'</li>\s*<li>', '\n• ', text)
        text = re.sub(r'<li>', '\n• ', text)
        text = re.sub(r'</h\d>', '\n\n', text)
        text = re.sub(r'<h\d[^>]*>', '\n**', text)

        # Remove all remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Clean up whitespace
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = text.strip()

        return text

    def merge_versions(self, target_catalog: Dict, source_catalog: Dict) -> Dict:
        """
        Merge version information from source catalog into target catalog.

        Args:
            target_catalog: Catalog to update
            source_catalog: Catalog with version information

        Returns:
            Updated target catalog
        """
        self.log("\n🔧 Merging version information...")

        updated_count = 0
        missing_count = 0

        # Handle both flat and hierarchical structures
        if any(isinstance(v, dict) and 'datasets' in v for v in target_catalog.values()):
            # Hierarchical target
            for category, cat_data in target_catalog.items():
                for dataset_id, metadata in cat_data.get('datasets', {}).items():
                    if dataset_id in source_catalog:
                        version = source_catalog[dataset_id].get('version', '1.0')
                        metadata['version'] = version
                        updated_count += 1
                    else:
                        metadata['version'] = '1.0'
                        missing_count += 1
        else:
            # Flat target
            for dataset_id, metadata in target_catalog.items():
                if dataset_id in source_catalog:
                    version = source_catalog[dataset_id].get('version', '1.0')
                    metadata['version'] = version
                    updated_count += 1
                else:
                    metadata['version'] = '1.0'
                    missing_count += 1

        self.log(f"✅ Updated {updated_count} datasets with versions")
        if missing_count > 0:
            self.log(f"⚠️  Set {missing_count} datasets to default version (1.0)")

        return target_catalog

    # ═══════════════════════════════════════════════════════════════════════
    # PROGRESS & ERROR HANDLING
    # ═══════════════════════════════════════════════════════════════════════

    def _save_checkpoint(self, processed_dsds: Set[str], failed_dsds: List[Dict]):
        """Save progress checkpoint for resumability."""
        checkpoint = {
            'processed_dsds': list(processed_dsds),
            'failed_dsds': failed_dsds,
            'timestamp': datetime.now().isoformat()
        }

        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, indent=2)

    def _load_checkpoint(self) -> Tuple[Set[str], List[Dict]]:
        """Load progress from checkpoint if exists."""
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint = json.load(f)

            processed = set(checkpoint.get('processed_dsds', []))
            failed = checkpoint.get('failed_dsds', [])
            timestamp = checkpoint.get('timestamp', 'unknown')

            self.log(f"📂 Resuming from checkpoint: {timestamp}")
            self.log(f"   Already processed: {len(processed)} DSDs")
            self.log(f"   Previously failed: {len(failed)} DSDs")

            return processed, failed

        return set(), []

    def extract_rate_limited_dsds_from_log(self, log_path: Optional[Path] = None) -> Set[str]:
        """
        Parse log file to extract DSDs that failed with 429 rate limit errors.

        Args:
            log_path: Path to log file (defaults to builder's log file)

        Returns:
            Set of DSD IDs that were rate limited
        """
        if log_path is None:
            log_path = self.log_file

        rate_limited_dsds = set()

        if not log_path.exists():
            return rate_limited_dsds

        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '429' in line and ('Too Many Requests' in line or 'Rate limit' in line):
                    # Extract DSD ID from line
                    match = re.search(r'for ([A-Za-z0-9_@]+):', line)
                    if match:
                        dsd_id = match.group(1)
                        rate_limited_dsds.add(dsd_id)

        return rate_limited_dsds

    def retry_failed_dsds(self, catalog: Dict, dsd_filter: Optional[Set[str]] = None) -> Dict:
        """
        Retry dimension extraction for failed DSDs.

        Args:
            catalog: Catalog to update
            dsd_filter: Optional set of specific DSD IDs to retry (defaults to all failed)

        Returns:
            Updated catalog
        """
        if not self.failed_file.exists():
            self.log("✅ No failed DSDs to retry")
            return catalog

        # Load failed DSDs
        with open(self.failed_file, 'r', encoding='utf-8') as f:
            failed_dsds = json.load(f)

        # Filter by specific DSDs if provided
        if dsd_filter:
            failed_dsds = [f for f in failed_dsds if f['dsd_id'] in dsd_filter]

        if not failed_dsds:
            self.log("✅ No matching failed DSDs to retry")
            return catalog

        self.log(f"🔄 Retrying {len(failed_dsds)} failed DSDs...")

        # Create DSD to agency mapping
        dsd_to_agency = {f['dsd_id']: f['agency'] for f in failed_dsds}

        # Clear checkpoint to force retry
        if self.checkpoint_file.exists():
            checkpoint = json.load(open(self.checkpoint_file))
            processed = set(checkpoint.get('processed_dsds', []))
            # Remove failed DSDs from processed list
            for dsd_id in dsd_to_agency.keys():
                processed.discard(dsd_id)
            checkpoint['processed_dsds'] = list(processed)
            with open(self.checkpoint_file, 'w') as f:
                json.dump(checkpoint, f, indent=2)

        # Run dimension extraction for these DSDs only
        # (This will use the existing batch processing logic)
        return self.add_dimensions_to_catalog(catalog)

    def validate_catalog(self, catalog: Dict) -> Dict[str, any]:
        """
        Validate catalog structure and completeness.

        Args:
            catalog: Catalog to validate

        Returns:
            Dictionary with validation results
        """
        validation = {
            'total_datasets': 0,
            'missing_names': 0,
            'missing_descriptions': 0,
            'missing_agencies': 0,
            'missing_versions': 0,
            'has_dimensions': 0,
            'missing_dimensions': 0,
            'errors': []
        }

        # Handle both flat and hierarchical structures
        datasets = []
        if any(isinstance(v, dict) and 'datasets' in v for v in catalog.values()):
            # Hierarchical
            for category, cat_data in catalog.items():
                datasets.extend(cat_data.get('datasets', {}).items())
        else:
            # Flat
            datasets = catalog.items()

        for dataset_id, metadata in datasets:
            validation['total_datasets'] += 1

            if not metadata.get('name'):
                validation['missing_names'] += 1
            if not metadata.get('description'):
                validation['missing_descriptions'] += 1
            if not metadata.get('agency'):
                validation['missing_agencies'] += 1
            if not metadata.get('version'):
                validation['missing_versions'] += 1

            if metadata.get('dimensions'):
                validation['has_dimensions'] += 1
            else:
                validation['missing_dimensions'] += 1

        return validation

    # ═══════════════════════════════════════════════════════════════════════
    # HIGH-LEVEL WORKFLOWS
    # ═══════════════════════════════════════════════════════════════════════

    def build_complete_catalog(self, include_dimensions: bool = True,
                              clean_html: bool = True) -> Dict:
        """
        Complete pipeline: fetch → dimensions → clean → save.

        This is the main method for building a complete catalog from scratch.

        Args:
            include_dimensions: Whether to fetch dimension structures (default: True)
            clean_html: Whether to clean HTML from descriptions (default: True)

        Returns:
            Complete catalog dictionary
        """
        self.log("\n" + "="*80)
        self.log("BUILDING COMPLETE OECD CATALOG")
        self.log("="*80)

        # Step 1: Fetch initial catalog
        self.log("\n📥 Step 1: Fetching initial catalog...")
        catalog = self.fetch_catalog()
        self.save_catalog(catalog, "oecd_catalog_v2.json")

        # Step 2: Add dimensions (optional, time-consuming)
        if include_dimensions:
            self.log("\n📐 Step 2: Adding dimension structures...")
            catalog = self.add_dimensions_to_catalog(catalog)

        # Step 3: Clean HTML (optional)
        if clean_html:
            self.log("\n🧹 Step 3: Cleaning HTML...")
            catalog = self.clean_html_descriptions(catalog)

        # Step 4: Save final catalog
        self.log("\n💾 Step 4: Saving final catalog...")
        filename = "oecd_catalog_complete.json"
        self.save_catalog(catalog, filename)

        # Validation
        self.log("\n✅ Step 5: Validating catalog...")
        validation = self.validate_catalog(catalog)
        self.log(f"   Total datasets: {validation['total_datasets']}")
        if include_dimensions:
            self.log(f"   With dimensions: {validation['has_dimensions']}")
            self.log(f"   Without dimensions: {validation['missing_dimensions']}")

        self.log("\n" + "="*80)
        self.log("✅ CATALOG BUILD COMPLETE")
        self.log("="*80)
        self.log(f"Output: {self.output_dir / filename}")

        return catalog


# ═══════════════════════════════════════════════════════════════════════════
# STANDALONE FUNCTIONS (for backward compatibility)
# ═══════════════════════════════════════════════════════════════════════════

def build_catalog(output_dir: str = ".") -> Dict:
    """
    Quick function to build a complete catalog.

    Args:
        output_dir: Directory for output files

    Returns:
        Complete catalog dictionary
    """
    builder = OECDCatalogBuilder(output_dir=output_dir)
    return builder.build_complete_catalog()


def fetch_catalog_only(output_dir: str = ".") -> Dict:
    """
    Fetch catalog without dimensions (fast).

    Args:
        output_dir: Directory for output files

    Returns:
        Basic catalog dictionary
    """
    builder = OECDCatalogBuilder(output_dir=output_dir)
    catalog = builder.fetch_catalog()
    builder.save_catalog(catalog, "oecd_catalog_basic.json")
    return catalog


# ═══════════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Command-line interface for catalog operations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="OECD Catalog Builder - Build and manage OECD dataset catalogs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build complete catalog (with dimensions)
  python OECD_Catalog_Builder.py --output ./data

  # Build basic catalog (no dimensions, fast)
  python OECD_Catalog_Builder.py --output ./data --no-dimensions

  # Resume interrupted dimension extraction
  python OECD_Catalog_Builder.py --output ./data --resume

  # Retry failed DSDs
  python OECD_Catalog_Builder.py --output ./data --retry-failed
        """
    )

    parser.add_argument('--output', '-o', type=str, default=".",
                       help='Output directory for catalog files (default: current directory)')
    parser.add_argument('--no-dimensions', action='store_true',
                       help='Skip dimension extraction (faster)')
    parser.add_argument('--no-clean-html', action='store_true',
                       help='Skip HTML cleaning')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from checkpoint')
    parser.add_argument('--retry-failed', action='store_true',
                       help='Retry failed DSDs')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Minimal console output')
    parser.add_argument('--rate-limit', type=int, default=60,
                       help='API requests per hour (default: 60)')

    args = parser.parse_args()

    try:
        # Initialize builder
        builder = OECDCatalogBuilder(
            output_dir=args.output,
            rate_limit=args.rate_limit,
            verbose=not args.quiet
        )

        if args.retry_failed:
            # Retry failed DSDs
            print("🔄 Retrying failed DSDs...")
            # Load existing catalog
            catalog_path = Path(args.output) / "oecd_catalog_complete.json"
            if catalog_path.exists():
                with open(catalog_path, 'r') as f:
                    catalog = json.load(f)
                catalog = builder.retry_failed_dsds(catalog)
                builder.save_catalog(catalog, "oecd_catalog_complete.json")
            else:
                print("❌ No existing catalog found. Build one first.")
                sys.exit(1)
        else:
            # Build complete catalog
            catalog = builder.build_complete_catalog(
                include_dimensions=not args.no_dimensions,
                clean_html=not args.no_clean_html
            )

        print("\n✅ Success!")
        print(f"📁 Output directory: {args.output}")
        print(f"📊 Total datasets: {len(catalog)}")

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Progress has been saved.")
        print("   Run the script again with --resume to continue.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
