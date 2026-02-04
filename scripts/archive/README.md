# Archived Catalog Building Scripts

**Date Archived:** 2026-02-04
**Reason:** Consolidated into `OECD_Catalog_Builder.py`

## What Happened?

These scripts were consolidated into a single, unified module for better maintainability and cleaner codebase organization before publishing to GitHub.

All functionality from these scripts is now available in:
```
scripts/OECD_Catalog_Builder.py
```

## Archived Scripts

| Old Script | Functionality | New Location in OECD_Catalog_Builder.py |
|------------|---------------|------------------------------------------|
| `build_catalog.py` | Fetch dataset catalog from OECD API | `OECDCatalogBuilder.fetch_catalog()` |
| `extract_dimensions.py` | Extract dimension structures with rate limiting | `OECDCatalogBuilder.add_dimensions_to_catalog()` |
| `clean_catalog_html.py` | Remove HTML from descriptions | `OECDCatalogBuilder.clean_html_descriptions()` |
| `add_versions_to_catalog.py` | Merge version information | `OECDCatalogBuilder.merge_versions()` |
| `retry_rate_limited_dsds.py` | Recover from rate limiting | `OECDCatalogBuilder.extract_rate_limited_dsds_from_log()` |
| `retry_failed_dimensions.py` | Retry failed extractions | `OECDCatalogBuilder.retry_failed_dsds()` |

## Migration Guide

### Old Way (Multiple Scripts)
```python
# Step 1: Build catalog
from scripts.build_catalog import get_oecd_dataset_catalog, save_catalog
catalog = get_oecd_dataset_catalog()
save_catalog(catalog, "catalog_v2.json")

# Step 2: Extract dimensions
from scripts.extract_dimensions import DimensionExtractor
extractor = DimensionExtractor("catalog_v2.json")
extractor.run()

# Step 3: Clean HTML
from scripts.clean_catalog_html import clean_catalog_file
clean_catalog_file("catalog_v2.json")
```

### New Way (Single Module)
```python
from scripts.OECD_Catalog_Builder import OECDCatalogBuilder

# All-in-one
builder = OECDCatalogBuilder(output_dir="./data")
catalog = builder.build_complete_catalog()

# Or step-by-step
catalog = builder.fetch_catalog()
catalog = builder.add_dimensions_to_catalog(catalog)
catalog = builder.clean_html_descriptions(catalog)
builder.save_catalog(catalog, "catalog_complete.json")
```

### CLI Usage
```bash
# Old way: Multiple scripts
python scripts/build_catalog.py
python scripts/extract_dimensions.py
python scripts/clean_catalog_html.py

# New way: Single command
python scripts/OECD_Catalog_Builder.py --output ./data
```

## Benefits of Consolidation

1. **Single Source of Truth**: All catalog building logic in one place
2. **Better Code Organization**: Class-based design with clear method hierarchy
3. **Reduced Duplication**: Shared utilities and helper methods
4. **Easier Testing**: Single module to test instead of 6 scripts
5. **Improved Documentation**: Comprehensive docstrings in one place
6. **Backward Compatibility**: Standalone functions preserved for existing code
7. **Enhanced Features**: Progress callbacks, better error handling, validation

## These Files Are Safe to Delete

These archived scripts are kept for reference only. They can be safely deleted once you've verified that `OECD_Catalog_Builder.py` works for your use case.

To permanently remove:
```bash
cd scripts/archive
rm -rf *.py
```

## Need Help?

Refer to the main documentation:
- `scripts/OECD_Catalog_Builder.py` - Full source code with docstrings
- Module docstring for detailed API documentation
- Run `python scripts/OECD_Catalog_Builder.py --help` for CLI options
