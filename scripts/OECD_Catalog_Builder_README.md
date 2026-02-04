# OECD Catalog Builder

**A comprehensive, consolidated module for building and managing OECD dataset catalogs.**

## Overview

The OECD Catalog Builder provides a unified interface for fetching, processing, and enhancing OECD dataset metadata from the SDMX API. It consolidates functionality from multiple scripts into a single, maintainable module.

## Features

✅ **Complete Catalog Building Pipeline**
- Fetch all datasets from OECD SDMX API
- Extract dimension structures with rate limiting
- Clean HTML from descriptions
- Merge version information
- Save to JSON format

✅ **Robust Error Handling**
- Automatic retry mechanisms
- Rate limit detection and handling
- Progress checkpointing (resumable operations)
- Detailed logging

✅ **Flexible Usage**
- Use as Python module
- Use as command-line tool
- Class-based or functional API
- Support for both flat and hierarchical catalogs

✅ **XML Parsing**
- Supports SDMX v2.1 and v3.0 schemas
- Handles multiple namespace formats
- Robust dimension extraction

## Installation

No additional dependencies beyond standard library:
```bash
pip install requests
```

## Quick Start

### As a Python Module

```python
from scripts.OECD_Catalog_Builder import OECDCatalogBuilder

# Build complete catalog (includes dimensions)
builder = OECDCatalogBuilder(output_dir="./data")
catalog = builder.build_complete_catalog()

# Result saved to: ./data/oecd_catalog_complete.json
```

### As a Command-Line Tool

```bash
# Build complete catalog
python scripts/OECD_Catalog_Builder.py --output ./data

# Build basic catalog (no dimensions, fast)
python scripts/OECD_Catalog_Builder.py --output ./data --no-dimensions

# Resume interrupted build
python scripts/OECD_Catalog_Builder.py --output ./data --resume

# Retry failed DSDs
python scripts/OECD_Catalog_Builder.py --output ./data --retry-failed
```

## Usage Examples

### Example 1: Basic Catalog (Fast)

Build a catalog without dimension structures (completes in ~30 seconds):

```python
from scripts.OECD_Catalog_Builder import fetch_catalog_only

catalog = fetch_catalog_only(output_dir="./data")
# Output: ./data/oecd_catalog_basic.json
```

**Use case:** Quick catalog refresh, exploring available datasets

### Example 2: Complete Catalog with Dimensions

Build a full catalog with dimension structures (may take several hours due to rate limiting):

```python
from scripts.OECD_Catalog_Builder import OECDCatalogBuilder

builder = OECDCatalogBuilder(output_dir="./data")
catalog = builder.build_complete_catalog(
    include_dimensions=True,
    clean_html=True
)
```

**Use case:** Production catalog with full metadata

### Example 3: Step-by-Step Processing

Build catalog step-by-step with custom logic:

```python
from scripts.OECD_Catalog_Builder import OECDCatalogBuilder

builder = OECDCatalogBuilder(output_dir="./data", verbose=True)

# Step 1: Fetch base catalog
catalog = builder.fetch_catalog()
builder.save_catalog(catalog, "step1_base.json")

# Step 2: Add dimensions (resumable, takes time)
catalog = builder.add_dimensions_to_catalog(catalog)
builder.save_catalog(catalog, "step2_with_dimensions.json")

# Step 3: Clean HTML
catalog = builder.clean_html_descriptions(catalog)
builder.save_catalog(catalog, "step3_cleaned.json")

# Step 4: Validate
validation = builder.validate_catalog(catalog)
print(f"Total datasets: {validation['total_datasets']}")
print(f"With dimensions: {validation['has_dimensions']}")
```

**Use case:** Custom processing, debugging, validation at each step

### Example 4: Search Catalog

Search for specific datasets:

```python
from scripts.OECD_Catalog_Builder import OECDCatalogBuilder
import json

builder = OECDCatalogBuilder(output_dir="./data")

# Load existing catalog
with open("./data/oecd_catalog_complete.json") as f:
    catalog = json.load(f)

# Search for health-related datasets
results = builder.search_catalog(catalog, "health")

for dataset_id, metadata in results.items():
    print(f"{dataset_id}: {metadata['name']}")
```

**Use case:** Finding relevant datasets programmatically

### Example 5: Merge Version Information

Update catalog with version info from another source:

```python
from scripts.OECD_Catalog_Builder import OECDCatalogBuilder
import json

builder = OECDCatalogBuilder(output_dir="./data")

# Load catalogs
with open("./data/target_catalog.json") as f:
    target = json.load(f)
with open("./data/source_with_versions.json") as f:
    source = json.load(f)

# Merge versions
updated = builder.merge_versions(target, source)
builder.save_catalog(updated, "merged_catalog.json")
```

**Use case:** Updating existing catalogs with new metadata

### Example 6: Retry Failed Extractions

Recover from failed dimension extractions:

```python
from scripts.OECD_Catalog_Builder import OECDCatalogBuilder
import json

builder = OECDCatalogBuilder(output_dir="./data")

# Load existing catalog
with open("./data/oecd_catalog_incomplete.json") as f:
    catalog = json.load(f)

# Retry only rate-limited DSDs
rate_limited = builder.extract_rate_limited_dsds_from_log()
catalog = builder.retry_failed_dsds(catalog, dsd_filter=rate_limited)

builder.save_catalog(catalog, "catalog_with_retries.json")
```

**Use case:** Recovering from interrupted builds, network issues

### Example 7: Progress Tracking

Monitor long-running operations:

```python
from scripts.OECD_Catalog_Builder import OECDCatalogBuilder

def progress_callback(current, total):
    percent = (current / total) * 100
    print(f"Progress: {current}/{total} ({percent:.1f}%)")

builder = OECDCatalogBuilder(output_dir="./data")
catalog = builder.fetch_catalog()

catalog = builder.add_dimensions_to_catalog(
    catalog,
    progress_callback=progress_callback
)
```

**Use case:** Monitoring batch processing, showing progress bars

## API Reference

### OECDCatalogBuilder Class

#### Constructor
```python
OECDCatalogBuilder(output_dir=".", rate_limit=60, verbose=True)
```
- `output_dir`: Directory for output files
- `rate_limit`: Max API requests per hour (default: 60)
- `verbose`: Enable console logging

#### Core Methods

**`fetch_catalog() -> Dict`**
- Fetch all datasets from OECD API
- Returns: `{dataset_id: {name, description, agency, version}}`
- Time: ~30 seconds

**`add_dimensions_to_catalog(catalog, progress_callback=None) -> Dict`**
- Add dimension structures to all datasets
- Respects rate limiting (60 requests/hour)
- Resumable via checkpoints
- Time: Several hours (depends on catalog size)

**`clean_html_descriptions(catalog) -> Dict`**
- Remove HTML tags from descriptions
- Preserves text structure
- Time: < 1 minute

**`merge_versions(target_catalog, source_catalog) -> Dict`**
- Merge version info from source into target
- Default version: "1.0" for missing entries

**`save_catalog(catalog, filename)`**
- Save catalog to JSON file in output_dir
- Pretty-printed with proper encoding

**`search_catalog(catalog, search_term) -> Dict`**
- Search datasets by keyword
- Case-insensitive
- Searches name and description fields

#### High-Level Methods

**`build_complete_catalog(include_dimensions=True, clean_html=True) -> Dict`**
- Complete pipeline: fetch → dimensions → clean → save
- Returns complete catalog dictionary
- Saves to: `oecd_catalog_complete.json`

**`validate_catalog(catalog) -> Dict`**
- Validate catalog structure and completeness
- Returns statistics about missing fields

#### Error Recovery

**`retry_failed_dsds(catalog, dsd_filter=None) -> Dict`**
- Retry dimension extraction for failed DSDs
- Optional filter for specific DSDs

**`extract_rate_limited_dsds_from_log(log_path=None) -> Set`**
- Parse log file for rate-limited DSDs
- Returns set of DSD IDs to retry

## Output Files

| File | Description | Size |
|------|-------------|------|
| `oecd_catalog_complete.json` | Complete catalog with all metadata | ~2-3 MB |
| `oecd_catalog_basic.json` | Basic catalog (no dimensions) | ~2 MB |
| `catalog_builder_log.txt` | Detailed execution log | Variable |
| `checkpoint.json` | Progress checkpoint (auto-deleted on completion) | Small |
| `failed_dsds.json` | Failed dimension extractions (if any) | Small |

## Rate Limiting

The OECD API has a rate limit of **60 requests per hour** for dimension structure queries.

The builder automatically:
- Tracks request count
- Pauses between batches (1 hour wait)
- Saves checkpoints every batch
- Resumes from last checkpoint

**Estimated Time for Complete Build:**
- Number of unique DSDs: ~500-600
- Batches needed: ~10
- Total time: **~10 hours**

**Tip:** Run overnight or use `--no-dimensions` for quick catalog refresh.

## Catalog Structure

### Flat Structure (Basic Catalog)
```json
{
  "DATASET_ID": {
    "name": "Dataset Name",
    "description": "Dataset description...",
    "agency": "OECD",
    "version": "1.0",
    "dimensions": [
      {"position": 0, "id": "LOCATION", "name": "Country"},
      {"position": 1, "id": "TIME", "name": "Time Period"}
    ]
  }
}
```

### Hierarchical Structure (Categorized)
```json
{
  "Economy": {
    "datasets": {
      "DATASET_ID": {
        "name": "...",
        "description": "...",
        "category": "Economy",
        "dimensions": [...]
      }
    }
  }
}
```

## Error Handling

### Common Issues

**1. Rate Limiting (429 Error)**
```
⚠️ Rate limited after 60 requests
✓ Progress saved to checkpoint
✓ Waiting 60 minutes before retry
```
**Solution:** Let the script wait, or resume later with `--resume`

**2. Network Timeout**
```
❌ Network error for DSD_XYZ: Timeout
✓ Marked as failed, continuing...
```
**Solution:** Use `--retry-failed` after completion

**3. XML Parse Error**
```
❌ XML parse error for DSD_ABC: Invalid format
✓ Logged to failed_dsds.json
```
**Solution:** These are rare; review failed_dsds.json for patterns

## Best Practices

### For Development
```python
# Test with small subset first
builder = OECDCatalogBuilder(output_dir="./test", verbose=True)
catalog = builder.fetch_catalog()
# Test with just first few datasets
```

### For Production
```bash
# Full build with all features
python scripts/OECD_Catalog_Builder.py \
  --output ./production_data \
  --rate-limit 60 \
  2>&1 | tee build.log
```

### For CI/CD
```bash
# Quick build without dimensions
python scripts/OECD_Catalog_Builder.py \
  --output ./data \
  --no-dimensions \
  --quiet
```

## Troubleshooting

### Build Takes Too Long
- Use `--no-dimensions` for fast catalog
- Dimensions take ~10 hours due to rate limiting
- Progress is saved; safe to interrupt and resume

### Out of Memory
- Reduce batch size in code: `BATCH_SIZE = 30`
- Process in chunks using checkpoints

### Checkpoint Not Resuming
- Check `checkpoint.json` exists in output_dir
- Verify file is valid JSON
- Logs show "Resuming from checkpoint" message

## Contributing

This module consolidates functionality from:
- `build_catalog.py`
- `extract_dimensions.py`
- `clean_catalog_html.py`
- `add_versions_to_catalog.py`
- `retry_rate_limited_dsds.py`
- `retry_failed_dimensions.py`

See `scripts/archive/README.md` for migration guide from old scripts.

## License

Part of the OECD Research Tool project.

## Support

- Check logs in `catalog_builder_log.txt`
- Review `failed_dsds.json` for failed extractions
- Run with `--help` for CLI options
- See source code docstrings for detailed API docs
