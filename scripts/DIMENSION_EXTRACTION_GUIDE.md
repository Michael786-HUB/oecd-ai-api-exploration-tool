# OECD Dimension Extraction Guide

## Overview

This script extracts dimension structures from the OECD datastructure API and adds them to our catalog. This enables precise API queries instead of using wildcards.

## What It Does

1. **Extracts unique DSDs**: Parses ~1467 datasets to find ~800-1000 unique Data Structure Definitions
2. **Fetches dimensions**: Queries OECD API for each DSD to get dimension metadata (id, position, name)
3. **Updates catalog**: Adds dimension arrays to each dataset
4. **Handles rate limits**: Respects OECD's 60 requests/hour limit
5. **Saves progress**: Checkpoints after each batch (resumable if interrupted)

## Quick Start

### Test First (RECOMMENDED)

Always test on 3 datasets first to verify everything works:

```bash
cd /Users/Micha/Documents/Documents/OCED\ Research\ Tool
python scripts/extract_dimensions.py --test
```

This will process only 3 DSDs:
- `DSD_SHA` (OECD.ELS.HD)
- `DSD_NAAG` (OECD.SDD.NAD)
- `DSD_FUA_CLIM` (OECD.CFE.EDS)

Expected output:
```
[2026-01-30 15:30:00] ================================================================================
[2026-01-30 15:30:00] OECD Dimension Extraction Script
[2026-01-30 15:30:00] ================================================================================
[2026-01-30 15:30:00] Started at: 2026-01-30 15:30:00
[2026-01-30 15:30:00] Test mode: True
[2026-01-30 15:30:00]
[2026-01-30 15:30:00] 📋 Step 1: Extracting unique DSDs from catalog...
[2026-01-30 15:30:00]    Found 850 unique DSDs
[2026-01-30 15:30:00]    TEST MODE: Processing only 3 DSDs
...
```

### Full Extraction

Once test succeeds, run full extraction:

```bash
python scripts/extract_dimensions.py
```

**⚠️ WARNING**: This will take 15-20 hours to complete!

## Features

### Resumable

If the script is interrupted (Ctrl+C, crash, etc.), just run it again:

```bash
python scripts/extract_dimensions.py
```

It will automatically resume from the last checkpoint.

### Progress Tracking

The script creates several files:

- **Log**: `data/catalogs/dimension_extraction_log.txt`
  - Detailed progress log with timestamps
  - Shows which DSDs were processed
  - Records any errors

- **Checkpoint**: `data/catalogs/extraction_checkpoint.json`
  - Saves progress after each batch
  - Contains list of processed DSDs
  - Automatically deleted when extraction completes

- **Failed DSDs**: `data/catalogs/failed_dsds.json`
  - Lists any DSDs that couldn't be processed
  - Includes error messages
  - Only created if failures occur

- **Output Catalog**: `data/catalogs/oecd_dataset_catalog_with_dimensions.json`
  - Updated catalog with dimension information
  - Created at the end of extraction

### Rate Limiting

The script automatically handles OECD's 60 requests/hour limit:

- Processes 60 DSDs per batch
- Waits 1 hour between batches
- Shows countdown timer during wait

## Output Format

Each dataset in the catalog will have a new `dimensions` field:

```json
{
  "DSD_SHA@DF_SHA": {
    "name": "System of Health Accounts",
    "agency": "OECD.ELS.HD",
    "version": "1.0",
    "dimensions": [
      {"position": 1, "id": "REF_AREA", "name": "Reference Area"},
      {"position": 2, "id": "FREQ", "name": "Frequency"},
      {"position": 3, "id": "MEASURE", "name": "Measure"},
      {"position": 4, "id": "FINANCING_SCHEME"},
      {"position": 5, "id": "PROVIDER"},
      {"position": 6, "id": "FUNCTION"}
    ]
  }
}
```

## Troubleshooting

### Script Hangs During Wait

This is normal! The script waits 1 hour between batches to respect rate limits. You'll see:

```
⏳ Waiting 59 minutes for rate limit...
   Next batch starts at: 16:30:00
```

### Connection Errors

If you see network errors, the script will:
1. Log the error
2. Mark the DSD as failed
3. Continue with the next DSD

Failed DSDs are saved to `failed_dsds.json` for later review.

### Out of Memory

The script is designed to be memory-efficient, but if you encounter issues:
1. The checkpoint system means you won't lose progress
2. Just restart the script

### Want to Start Over

Delete the checkpoint file:

```bash
rm data/catalogs/extraction_checkpoint.json
```

Then run the script again.

## Usage in Application

Once extraction completes, update `app.py` to use the new catalog:

```python
# In app.py
@st.cache_data
def load_catalog():
    with open('data/catalogs/oecd_dataset_catalog_with_dimensions.json', 'r', encoding='utf-8') as f:
        return json.load(f)
```

Then you can build precise API URLs using the dimensions instead of wildcards!

## Command Line Options

```bash
# Test mode (3 DSDs only)
python scripts/extract_dimensions.py --test

# Full extraction
python scripts/extract_dimensions.py

# Custom catalog path
python scripts/extract_dimensions.py --catalog path/to/catalog.json
```

## Expected Timeline

- **Test mode**: ~2 minutes
- **Full extraction**: 15-20 hours
  - Depends on number of unique DSDs (usually 800-1000)
  - Each batch: 60 DSDs in ~5 minutes
  - Wait between batches: 1 hour
  - Total batches: ~15-17

## Notes

- The script is safe to interrupt (Ctrl+C)
- Progress is saved after each batch
- You can monitor progress in the log file
- The script handles both SDMX v2.1 and v3.0 formats
