# Dimension Extraction Script Improvements

## Changes Made

### 1. **Smart Rate Limit Detection**

**Problem:** The script was processing all 60 DSDs in a batch even after hitting the rate limit (429 error), wasting time on requests that would all fail.

**Solution:**
- Script now detects 429 errors immediately
- Stops the current batch as soon as rate limit is hit
- Waits 1 hour for rate limit reset
- Resumes from where it left off

**Before:**
```
[1/60] ✓ Success
[2/60] ✓ Success
...
[20/60] ✓ Success
[21/60] ❌ 429 Rate Limited
[22/60] ❌ 429 Rate Limited
...
[60/60] ❌ 429 Rate Limited  ← Wasted 40 requests!
💾 Checkpoint saved
⏳ Waiting 60 minutes...
```

**After:**
```
[1/60] ✓ Success
[2/60] ✓ Success
...
[20/60] ✓ Success
[21/60] 🚫 Rate limited (429) - stopping batch
💾 Checkpoint saved (20 processed)
⏳ Waiting 60 minutes...
```

### 2. **Continuous Processing Loop**

**Problem:** Script calculated batches upfront based on total DSDs, but didn't adapt if some batches finished early due to rate limiting.

**Solution:**
- Changed from fixed `for batch_num in range(total_batches)` loop
- Now uses `while True` loop that recalculates remaining DSDs each iteration
- Automatically adapts to early batch termination
- Continues until all DSDs are processed

**Benefits:**
- More resilient to interruptions
- Better progress tracking
- Cleaner resumption logic

### 3. **Better Error Handling**

**Changes:**
- 429 errors don't mark DSDs as "processed" - they'll be retried
- Other HTTP errors (404, 500, etc.) still mark DSDs as failed
- Clear distinction between retriable and permanent failures

### 4. **Improved Logging**

**New log messages:**
```
🔄 Batch 3
   Remaining DSDs: 350
   Processing next 60 DSDs

[15/60] Fetching DSD_EXAMPLE (OECD.ENV.EPI)...
   🚫 Rate limited (429) - stopping batch
   Processed 14 of 60 DSDs in this batch
💾 Checkpoint saved

⏳ Waiting 55 minutes for rate limit reset...
   336 DSDs remaining
   Next batch starts at: 23:15:00
```

## Performance Improvements

### Time Savings

**Scenario:** Hit rate limit after 20 DSDs

**Before:**
- Process 20 successful requests: ~20 seconds
- Try 40 failed requests: ~40 seconds
- Total wasted time per batch: ~40 seconds
- Over 7 batches: ~5 minutes wasted

**After:**
- Process 20 successful requests: ~20 seconds
- Stop immediately on 429
- Total wasted time: 0 seconds

### More Efficient API Usage

- No more hammering the API with requests after hitting the limit
- Better API citizenship
- Reduces chance of being temporarily blocked

## Testing

### Test Case 1: Normal Flow
```bash
python scripts/extract_dimensions.py --test
```
Expected: Processes 3 DSDs successfully without hitting rate limit

### Test Case 2: Resume After Rate Limit
The script will automatically handle this during full extraction when it hits the OECD rate limit.

## Migration Notes

**No action needed!** The improvements are backward compatible:
- Existing checkpoints work with the new version
- Can resume in-progress extractions seamlessly
- Same command-line interface

## Technical Details

### Rate Limit Detection
```python
if response.status_code == 429:
    self.log(f"  🚫 Rate limited (429) - stopping batch")
    raise requests.exceptions.HTTPError("Rate limit exceeded (429)", response=response)
```

### Batch Loop
```python
while True:
    # Recalculate remaining DSDs
    remaining_dsds = {k: v for k, v in dsd_to_agency.items()
                     if k not in self.processed_dsds}

    if not remaining_dsds:
        break

    # Process next batch...
```

### Smart Wait Logic
```python
# Only wait if there are more DSDs to process
if remaining_after_batch:
    wait_seconds = (next_batch_time - datetime.now()).total_seconds()

    if wait_seconds > 0:
        time.sleep(wait_seconds)
    else:
        # Rate limit window already passed, continue immediately
        continue
```

## Expected Runtime

With the improvements, the script should:
- Hit rate limit after ~20-40 requests (varies by OECD load)
- Wait 1 hour between batches
- Complete ~20-40 DSDs per hour (instead of trying all 60)
- Total time: Still ~10-12 hours (but more efficient)

The total time is similar, but now:
- No wasted API calls
- Better error recovery
- Cleaner logs
- More resilient operation
