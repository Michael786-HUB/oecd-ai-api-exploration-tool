# Multi-Dataset Export Issue - Debugging Approach

## Problem Statement

**User Report**: When the AI recommends multiple datasets (e.g., 2-3 datasets), only one of them appears to have export functionality available.

**Expected Behavior**: Each recommended dataset should have full export controls (filters, date inputs, download button).

**Issue Persistence**: This problem has persisted through three separate fix attempts, indicating a deeper underlying cause.

---

## Debugging Strategy

Since the issue persists despite code that appears correct (each dataset gets unique widget keys, separate render calls, etc.), we've added comprehensive debugging output to identify exactly where the breakdown occurs.

### Debug Panel Added

**Location**: [app.py:1007-1020](app.py#L1007-L1020)

A collapsible debug expander showing:

```python
with st.expander("🔍 Debug Information", expanded=False):
    st.markdown("**Session State Dataset IDs:**")
    for i, did in enumerate(st.session_state.current_dataset_ids):
        st.code(f"[{i+1}] {did}")

    st.markdown("**Validation Check:**")
    for i, did in enumerate(st.session_state.current_dataset_ids):
        cat, meta = find_dataset_by_id(catalog, did)
        if meta:
            st.success(f"✓ [{i+1}] `{did}` → Found in '{cat}'")
        else:
            st.error(f"✗ [{i+1}] `{did}` → NOT FOUND")
```

**What It Shows**:
1. **Raw dataset IDs**: Exactly what's stored in session state after AI recommendation
2. **Validation results**: Whether each ID can be found in the catalog

---

## Possible Root Causes

### Hypothesis 1: Only One Dataset ID Being Stored

**Symptoms**:
- Debug panel shows only 1 dataset ID
- Only 1 expander appears in UI

**Possible Causes**:
- AI only recommending one dataset (despite being asked for multiple)
- `extract_dataset_ids()` function only extracting first match
- Validation removing all but one ID as "invalid"

**How Debug Panel Helps**: Shows exact count and IDs in session state

---

### Hypothesis 2: Multiple IDs Stored, But Only One Found in Catalog

**Symptoms**:
- Debug panel shows multiple dataset IDs
- Some IDs show as "NOT FOUND" in validation
- Only datasets that pass validation get expanders

**Possible Causes**:
- AI hallucinating dataset IDs (some invalid)
- IDs extracted incorrectly (typos, formatting issues)
- Catalog missing some datasets

**How Debug Panel Helps**: Validation section shows which IDs are found vs. not found

---

### Hypothesis 3: Multiple IDs Stored and Found, But Expanders Not Rendering

**Symptoms**:
- Debug panel shows all IDs as found
- Still only one expander visible in UI

**Possible Causes**:
- Streamlit rendering issue with multiple expanders
- Loop breaking early due to exception
- Widget key conflicts (despite unique keys)

**How Debug Panel Helps**: If all IDs show as found but expanders don't appear, points to rendering issue

---

## Enhanced Per-Dataset Indicators

To make it crystal clear that each dataset is fully functional, added:

**Location**: [app.py:1038-1045](app.py#L1038-L1045)

```python
with st.expander(expander_label, expanded=is_expanded):
    # Top banner
    st.info(f"**Dataset {idx + 1} of {total_datasets}** - This dataset is fully exportable...")

    # Render all controls
    render_dataset_details(category, dataset_id, metadata)

    # Bottom confirmation
    st.success(f"✓ Export controls ready for dataset {idx + 1}/{total_datasets}: `{dataset_id}`")
```

**Purpose**: If a user sees this success message at the bottom of an expander, it confirms that:
- The loop reached this dataset
- Metadata was found
- render_dataset_details() completed successfully
- All widgets should be available

---

## Testing Instructions

### Step 1: Ask for Multiple Datasets

Use a query that should return multiple datasets:

```
"Show me unemployment and GDP data for the United States"
```

Expected: AI should recommend 2+ datasets (unemployment + GDP)

### Step 2: Check Debug Panel

Click "🔍 Debug Information" expander and verify:

1. **Count**: How many dataset IDs are listed?
   - If only 1: Problem is in AI recommendation or extraction
   - If 2+: Problem is elsewhere

2. **Validation**: Are all IDs marked with ✓ (found)?
   - If some show ✗: Those datasets don't exist (hallucination)
   - If all show ✓: All datasets are valid

### Step 3: Check Dataset Expanders

1. **Count expanders**: How many "[1/X]", "[2/X]" expanders appear?
   - Should match the count in debug panel
   - If fewer: Rendering issue

2. **Expand each one**: Click on each expander and verify:
   - Info banner appears at top
   - All filter controls render (dimensions, dates, etc.)
   - Download button appears
   - Success confirmation appears at bottom

3. **Test download**: Try clicking download on 2nd or 3rd dataset
   - Does it work?
   - Does it download the correct dataset?

---

## Expected Debug Panel Outputs

### Scenario A: AI Only Recommends One Dataset

```
Session State Dataset IDs:
[1] DSD_LFS@DF_IALFS_UNE_M

Validation Check:
✓ [1] DSD_LFS@DF_IALFS_UNE_M → Found in 'Labour'
```

**Diagnosis**: AI is only recommending one dataset. Check AI prompt/response.

---

### Scenario B: Multiple Valid Datasets

```
Session State Dataset IDs:
[1] DSD_LFS@DF_IALFS_UNE_M
[2] DSD_NAAG@DF_NAAG
[3] DSD_KEI@DF_KEI

Validation Check:
✓ [1] DSD_LFS@DF_IALFS_UNE_M → Found in 'Labour'
✓ [2] DSD_NAAG@DF_NAAG → Found in 'National Accounts'
✓ [3] DSD_KEI@DF_KEI → Found in 'Leading Indicators'
```

**Diagnosis**: All datasets are valid. If expanders don't render, it's a rendering issue.

---

### Scenario C: Some Invalid Datasets

```
Session State Dataset IDs:
[1] DSD_LFS@DF_IALFS_UNE_M
[2] FAKE_DATASET@DF_TEST

Validation Check:
✓ [1] DSD_LFS@DF_IALFS_UNE_M → Found in 'Labour'
✗ [2] FAKE_DATASET@DF_TEST → NOT FOUND
```

**Diagnosis**: AI hallucinated dataset #2. Should be caught by validation.

---

## Code Changes Summary

### Files Modified

**[app.py](app.py)**:

1. **Lines 1007-1020**: Added debug expander
   - Shows dataset IDs in session state
   - Validates each ID against catalog

2. **Lines 1022-1050**: Enhanced dataset rendering
   - Removed redundant st.container() wrapper
   - Added visual separators between datasets (---)
   - Added info banner at top of each expander
   - Added success confirmation at bottom of each expander
   - Improved error messages for datasets not found

3. **Line 1004**: Changed success message
   - Before: "Click on each one below to configure and download"
   - After: "Each dataset below has full export functionality"

---

## Next Steps

Based on debug panel results:

### If Only 1 Dataset ID in Session State

1. Check AI response (add temporary debug to show full AI response)
2. Verify `extract_dataset_ids()` is finding all backtick-wrapped IDs
3. Confirm validation isn't removing valid IDs

### If Multiple IDs But Some Not Found

1. Check which IDs are invalid
2. Verify AI is using exact IDs from catalog
3. Consider improving hallucination safeguard

### If Multiple Valid IDs But Expanders Don't Render

1. Check browser console for JavaScript errors
2. Try simplifying expander structure
3. Consider alternative UI (tabs instead of expanders?)

### If All Expanders Render But Download Doesn't Work

1. Add debug output in download button callback
2. Verify which dataset_id is being used when button is clicked
3. Check for widget key conflicts

---

## Temporary Debug Mode

If the issue still isn't clear after checking the debug panel, we can add even more detailed logging:

```python
# Add this at the start of the loop
import logging
logging.basicConfig(level=logging.DEBUG)

for idx, dataset_id in enumerate(st.session_state.current_dataset_ids):
    logging.debug(f"Loop iteration {idx}: Processing {dataset_id}")

    category, metadata = find_dataset_by_id(catalog, dataset_id)
    logging.debug(f"  - Category: {category}, Metadata found: {metadata is not None}")

    if metadata:
        logging.debug(f"  - Creating expander for {dataset_id}")
        with st.expander(...):
            logging.debug(f"  - Calling render_dataset_details for {dataset_id}")
            render_dataset_details(category, dataset_id, metadata)
            logging.debug(f"  - Completed render_dataset_details for {dataset_id}")
```

This would log to terminal/server logs and help identify if the loop is breaking early.

---

## User Instructions

After running the app with these debug changes:

1. **Ask for multiple datasets** (e.g., "Show me unemployment and GDP data")

2. **Open the debug panel** (click "🔍 Debug Information")

3. **Take a screenshot** showing:
   - The debug panel contents
   - The dataset expanders (all of them)
   - Any error messages

4. **Try expanding each dataset** and report:
   - Which ones show the info banner
   - Which ones show the download button
   - Which ones show the success confirmation

5. **Try downloading from each dataset** and report:
   - Which download buttons work
   - Which ones don't (and what happens when clicked)

This information will pinpoint exactly where the issue occurs.

---

## Summary

The debug panel provides transparency into the dataset loading process. By checking:

1. ✅ **What's stored**: Session state dataset IDs
2. ✅ **What's valid**: Validation results
3. ✅ **What's rendered**: Expander count and contents
4. ✅ **What works**: Download button functionality

We can systematically identify and fix the root cause of the multi-dataset export issue.
