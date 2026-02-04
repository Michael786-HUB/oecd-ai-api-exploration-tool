# UX Improvements Changelog

## Overview

Four major user experience improvements added to the OECD Data Explorer:

1. **Dropdown filters for Country and Frequency dimensions** (replaces free text)
2. **Smart country pre-filtering from AI context** (auto-applies country filters)
3. **Smart time period pre-filling from AI context** (auto-applies year ranges)
4. **API request counter** (tracks 60/hour rate limit)

---

## 1. Dropdown Filters for Common Dimensions

### Problem
Users had to manually type country codes (e.g., "USA", "CAN") and frequency codes (e.g., "A", "Q") which:
- Required knowledge of correct codes
- Was error-prone (typos like "US" instead of "USA")
- Wasn't user-friendly

### Solution
**Country Dimension (REF_AREA)**: Multiselect dropdown
- Shows friendly country names (e.g., "United States", "Canada")
- Automatically converts to API codes (e.g., USA, CAN)
- Includes all OECD and non-OECD countries from country_codes.json
- Special "[All Countries]" option for no filtering

**Frequency Dimension (FREQ)**: Single select dropdown
- Options: "Annual", "Quarterly", "Monthly"
- Automatically converts to API codes (A, Q, M)
- Special "[All Frequencies]" option

**Other Dimensions**: Still use text input
- For dataset-specific dimensions (MEASURE, UNIT_MEASURE, etc.)
- Shows helpful placeholders and hints

### Code Changes

**Location**: [app.py:299-350](app.py#L299-L350)

```python
if dim_id == 'REF_AREA':
    # Country selection with dropdown
    country_data = load_country_codes()
    all_countries = {**country_data["OECD"], **country_data["Non-OECD"]}

    selected_countries = st.multiselect(
        f"**Position {dim_position}**: {dim_name}",
        options=["[All Countries]"] + sorted(all_countries.keys()),
        default=default_countries,  # Pre-filled from AI hints
        key=f"dim_{dataset_id}_{dim_id}"
    )

    # Convert to API format
    if not selected_countries or "[All Countries]" in selected_countries:
        value = ""
    else:
        codes = [all_countries[name] for name in selected_countries]
        value = "+".join(codes)  # e.g., "USA+CAN+MEX"

elif dim_id == 'FREQ':
    # Frequency dropdown
    freq_options = {
        "[All Frequencies]": "",
        "Annual": "A",
        "Quarterly": "Q",
        "Monthly": "M"
    }

    selected_freq = st.selectbox(
        f"**Position {dim_position}**: {dim_name}",
        options=list(freq_options.keys())
    )

    value = freq_options[selected_freq]
```

### Benefits
- ✅ No need to memorize country codes
- ✅ Zero typos - validated selections only
- ✅ Searchable dropdown (Streamlit feature)
- ✅ Multi-country selection made easy
- ✅ Clear "All" options for wildcards

---

## 2. Smart Country Pre-Filtering from AI

### Problem
When users asked the AI librarian questions like:
- "Show me healthcare data for Canada"
- "What unemployment data exists for USA and Mexico?"

The recommended datasets would require users to manually select countries again in the filter.

### Solution
**AI extracts countries** from user questions and **auto-fills** the country filter.

### How It Works

#### Step 1: Enhanced AI System Prompt

**Location**: [app.py:186-203](app.py#L186-L203)

```python
IMPORTANT: If the user mentions specific countries in their question,
include a special metadata section at the end of your response:

<!-- FILTER_HINTS:COUNTRIES=USA,CAN,GBR -->

Use this format ONLY if countries are explicitly mentioned.
Use 3-letter ISO country codes.

Common mappings:
- United States/America/US → USA
- Canada → CAN
- United Kingdom/Britain/UK → GBR
- Germany → DEU
- France → FRA
[etc.]
```

#### Step 2: Extract Filter Hints

**Location**: [app.py:248-263](app.py#L248-L263)

```python
def extract_filter_hints(response_text):
    """Extract filter hints from AI response."""
    import re

    hints = {}

    # Extract country hints
    country_pattern = r'<!-- FILTER_HINTS:COUNTRIES=([A-Z,]+) -->'
    country_match = re.search(country_pattern, response_text)

    if country_match:
        countries = country_match.group(1).split(',')
        hints['countries'] = [c.strip() for c in countries]

    return hints
```

#### Step 3: Store Hints in Session State

**Location**: [app.py:529-535](app.py#L529-L535)

```python
# Extract filter hints (countries, etc.)
filter_hints = extract_filter_hints(response)
if filter_hints:
    st.session_state.filter_hints = filter_hints
    st.info(f"💡 Detected filter suggestion: {', '.join(filter_hints.get('countries', []))}")
```

#### Step 4: Pre-fill Country Dropdown

**Location**: [app.py:307-314](app.py#L307-L314)

```python
# Check for pre-filled country hints from AI
default_countries = []
if "filter_hints" in st.session_state and "countries" in st.session_state.filter_hints:
    # Convert country codes to country names for the multiselect
    code_to_name = {v: k for k, v in all_countries.items()}
    for code in st.session_state.filter_hints["countries"]:
        if code in code_to_name:
            default_countries.append(code_to_name[code])

selected_countries = st.multiselect(
    ...,
    default=default_countries  # PRE-FILLED!
)
```

### Example Flow

1. **User asks**: "I need health expenditure data for Canada and Mexico"

2. **AI responds**:
   ```
   I recommend these datasets:

   1. **Health Expenditure and Financing** (`DSD_SHA@DF_SHA`)
      - Category: Health
      - What it offers: Comprehensive healthcare spending data...

   <!-- FILTER_HINTS:COUNTRIES=CAN,MEX -->
   ```

3. **App detects hint**: Shows info message
   ```
   💡 Detected filter suggestion: CAN, MEX
   ```

4. **Dataset filter pre-filled**:
   - Country dropdown automatically has "Canada" and "Mexico" selected
   - User can modify or proceed directly to download

### Benefits
- ✅ Saves user time - no re-entering countries
- ✅ Reduces errors - AI correctly maps "America" → "USA"
- ✅ Seamless UX - feels intelligent and helpful
- ✅ Optional - user can still change selections

---

## 3. Smart Time Period Pre-Filling from AI

### Problem
When users asked the AI librarian questions with specific timeframes like:
- "Show me US military spending in 2024"
- "GDP data from 2020 to 2023"
- "Recent unemployment trends since 2015"

The recommended datasets would still default to generic date ranges (2010-2024), requiring users to manually adjust the time period filters.

### Solution
**AI extracts time periods** from user questions and **auto-fills** the start/end year fields.

### How It Works

#### Step 1: Enhanced AI System Prompt for Time Periods

**Location**: [app.py:184-207](app.py#L184-L207)

```python
IMPORTANT: If the user mentions specific time periods, include metadata:

<!-- FILTER_HINTS:START_YEAR=2020 -->
<!-- FILTER_HINTS:END_YEAR=2024 -->

TIME PERIODS: Extract start and end years from questions:
- "2024 data" → START_YEAR=2024, END_YEAR=2024
- "2020 to 2023" → START_YEAR=2020, END_YEAR=2023
- "since 2015" → START_YEAR=2015, END_YEAR=2024 (current year)
- "recent data" → START_YEAR=2020, END_YEAR=2024 (last 5 years)
- "data from 2018" → START_YEAR=2018, END_YEAR=2024

Common patterns to recognize:
- "in [year]" / "[year] data" → single year
- "from [year1] to [year2]" → range
- "since [year]" → year to current
- "recent" / "latest" → last 5 years
```

#### Step 2: Enhanced Extract Filter Hints Function

**Location**: [app.py:296-326](app.py#L296-L326)

```python
def extract_filter_hints(response_text):
    """Extract filter hints from AI response (countries and time periods)."""
    import re

    hints = {}

    # Extract country hints
    country_pattern = r'<!-- FILTER_HINTS:COUNTRIES=([A-Z,]+) -->'
    country_match = re.search(country_pattern, response_text)
    if country_match:
        countries = country_match.group(1).split(',')
        hints['countries'] = [c.strip() for c in countries]

    # Extract start year
    start_year_pattern = r'<!-- FILTER_HINTS:START_YEAR=(\d{4}) -->'
    start_year_match = re.search(start_year_pattern, response_text)
    if start_year_match:
        hints['start_year'] = start_year_match.group(1)

    # Extract end year
    end_year_pattern = r'<!-- FILTER_HINTS:END_YEAR=(\d{4}) -->'
    end_year_match = re.search(end_year_pattern, response_text)
    if end_year_match:
        hints['end_year'] = end_year_match.group(1)

    return hints
```

#### Step 3: Pre-fill Date Input Fields

**Location**: [app.py:451-460](app.py#L451-L460)

```python
with col2:
    # Check for pre-filled start year from AI hints
    default_start = "2010"
    if "filter_hints" in st.session_state and "start_year" in st.session_state.filter_hints:
        default_start = st.session_state.filter_hints["start_year"]

    start_date = st.text_input("Start Year:", value=default_start, key=f"start_{dataset_id}")

with col3:
    # Check for pre-filled end year from AI hints
    default_end = "2024"
    if "filter_hints" in st.session_state and "end_year" in st.session_state.filter_hints:
        default_end = st.session_state.filter_hints["end_year"]

    end_date = st.text_input("End Year:", value=default_end, key=f"end_{dataset_id}")
```

#### Step 4: Enhanced Filter Suggestion Display

**Location**: [app.py:509-521](app.py#L509-L521)

```python
# Build filter suggestion message
suggestions = []
if 'countries' in filter_hints:
    suggestions.append(f"Countries: {', '.join(filter_hints['countries'])}")
if 'start_year' in filter_hints or 'end_year' in filter_hints:
    start = filter_hints.get('start_year', '?')
    end = filter_hints.get('end_year', '?')
    suggestions.append(f"Time period: {start}-{end}")

if suggestions:
    st.info(f"💡 Detected filter suggestions: {' | '.join(suggestions)}")
```

### Example Flow

1. **User asks**: "I need US military spending data for 2024"

2. **AI responds**:
   ```
   I recommend this dataset:

   1. **Annual government expenditure by function (COFOG)** (`DSD_NASEC10@DF_TABLE11`)
      - Category: Public governance
      - What it offers: Defense spending breakdown...

   <!-- FILTER_HINTS:COUNTRIES=USA -->
   <!-- FILTER_HINTS:START_YEAR=2024 -->
   <!-- FILTER_HINTS:END_YEAR=2024 -->
   ```

3. **App detects hints**: Shows combined info message
   ```
   💡 Detected filter suggestions: Countries: USA | Time period: 2024-2024
   ```

4. **Dataset filter pre-filled**:
   - Country dropdown: "United States" selected
   - Start Year: "2024"
   - End Year: "2024"
   - User can immediately download or adjust

### Additional Examples

**Example 1: Range Query**
- **User**: "Show me Canada GDP from 2015 to 2020"
- **AI outputs**: `START_YEAR=2015`, `END_YEAR=2020`, `COUNTRIES=CAN`
- **Result**: All three fields pre-filled

**Example 2: Since Query**
- **User**: "Unemployment trends since 2018"
- **AI outputs**: `START_YEAR=2018`, `END_YEAR=2024` (current year)
- **Result**: Start=2018, End=2024

**Example 3: Recent Data**
- **User**: "Show me recent health expenditure data"
- **AI outputs**: `START_YEAR=2020`, `END_YEAR=2024` (last 5 years)
- **Result**: Reasonable default for "recent"

### Benefits
- ✅ Saves user time - no manual date entry
- ✅ Contextual defaults - AI understands "recent", "since", etc.
- ✅ Combined filtering - works with country pre-filling
- ✅ Flexible - user can still modify years
- ✅ Clear visibility - shows detected time period in info message

---

## 4. API Request Counter

### Problem
OECD API has a strict 60 requests/hour limit. Users had no way to:
- Track how many requests they've made
- Know when they'd hit the limit
- See when the limit would reset

### Solution
**Persistent counter** displayed at the top of every page.

### Features

#### Visual Counter Display

**Location**: [app.py:456-487](app.py#L456-L487)

```python
def show_api_counter():
    """Display the API request counter."""
    from datetime import datetime

    remaining = st.session_state.api_counter_reset_time - datetime.now()
    minutes_remaining = int(remaining.total_seconds() / 60)

    count = st.session_state.api_counter
    limit = 60

    # Color based on usage
    if count >= limit:
        color = "🔴"
        status = "LIMIT REACHED"
    elif count >= 50:
        color = "🟡"
        status = "ALMOST FULL"
    elif count >= 30:
        color = "🟢"
        status = "MODERATE USE"
    else:
        color = "🟢"
        status = "AVAILABLE"
```

#### Display Elements

**Top of page shows:**
```
🟢 API Requests (OECD Limit: 60/hour)     Status              [Reset Counter]
15 / 60                                    AVAILABLE
↳ Resets in 45 min
```

**Color coding:**
- 🟢 Green: 0-29 requests (Available/Moderate)
- 🟡 Yellow: 50-59 requests (Almost Full)
- 🔴 Red: 60+ requests (Limit Reached)

#### Auto-Reset After 1 Hour

**Location**: [app.py:441-453](app.py#L441-L453)

```python
def init_api_counter():
    """Initialize or reset API request counter."""
    from datetime import datetime, timedelta

    if "api_counter" not in st.session_state:
        st.session_state.api_counter = 0
        st.session_state.api_counter_reset_time = datetime.now() + timedelta(hours=1)

    # Reset counter if an hour has passed
    if datetime.now() >= st.session_state.api_counter_reset_time:
        st.session_state.api_counter = 0
        st.session_state.api_counter_reset_time = datetime.now() + timedelta(hours=1)
```

#### Increment on API Call

**Location**: [app.py:484](app.app#L484)

```python
# Increment API counter BEFORE making the request
increment_api_counter()

# Call the API
df = fetcher.get_dataset(...)
```

#### Block Downloads at Limit

**Location**: [app.py:477-483](app.py#L477-L483)

```python
if st.session_state.api_counter >= 60:
    st.error("⚠️ API rate limit reached (60 requests/hour). Please wait for the counter to reset.")
    remaining = st.session_state.api_counter_reset_time - datetime.now()
    minutes = int(remaining.total_seconds() / 60)
    st.info(f"⏳ Counter resets in {minutes} minutes")
else:
    # Allow download
```

#### Manual Reset Button

Users can manually reset the counter if they know the hour has passed (handles page refreshes).

### Benefits
- ✅ **Visibility**: Always know request count
- ✅ **Prevention**: Stops downloads when limit reached
- ✅ **Planning**: See time until reset
- ✅ **Color coding**: Quick status at a glance
- ✅ **Automatic**: Resets after 1 hour
- ✅ **Persistent**: Survives page refreshes (session state)

---

## Testing

### Test 1: Dropdown Filters
```bash
streamlit run app.py
```

1. Navigate to a dataset with dimensions (e.g., "Domestic Tourism")
2. Look for REF_AREA dimension
3. Should see multiselect dropdown with country names
4. Select "United States" and "Canada"
5. Preview API query should show: `USA+CAN.....`

✅ Expected: Dropdown shown, codes correctly converted

### Test 2: Smart Pre-Filtering
```bash
streamlit run app.py
```

1. Go to AI Librarian tab
2. Ask: "Show me GDP data for Germany and France"
3. AI should recommend datasets
4. Check for info message: "💡 Detected filter suggestion: DEU, FRA"
5. Open a recommended dataset
6. REF_AREA dropdown should have "Germany" and "France" pre-selected

✅ Expected: Countries auto-filled

### Test 3: Smart Time Period Pre-Filling
```bash
streamlit run app.py
```

1. Go to AI Librarian tab
2. Ask: "Show me US military spending in 2024"
3. AI should recommend datasets
4. Check for info message: "💡 Detected filter suggestions: Countries: USA | Time period: 2024-2024"
5. Open a recommended dataset
6. Start Year field should show "2024"
7. End Year field should show "2024"
8. Country dropdown should have "United States" pre-selected

✅ Expected: Both countries AND time periods auto-filled

### Test 4: API Counter
```bash
streamlit run app.py
```

1. Check top of page for counter display
2. Should show: "0 / 60" with green indicator
3. Download a dataset
4. Counter should increment to "1 / 60"
5. Counter shows "Resets in X min"

✅ Expected: Counter increments, shows reset time

---

## File Changes Summary

**Modified Files:**

1. **[app.py](app.py)**
   - Added dropdown logic for REF_AREA and FREQ dimensions (lines 299-350)
   - Enhanced AI system prompt with filter hints for countries AND time periods (lines 184-207)
   - Added `extract_filter_hints()` function with year extraction (lines 296-326)
   - Added API counter functions (lines 441-487)
   - Updated main() to initialize and show counter (lines 489-496)
   - Added pre-fill logic for countries (lines 307-314)
   - Added pre-fill logic for start/end years (lines 451-460)
   - Enhanced filter suggestion display to show time periods (lines 509-521)
   - Added limit check before download (lines 477-483)
   - Store filter hints from AI response (lines 529-535)

**No New Files Created**

---

## Breaking Changes

**None** - All changes are additive and backward compatible.

- Datasets without dimensions still use legacy filtering
- AI responses without country mentions work as before
- Counter starts at 0 and doesn't affect existing functionality

---

## Future Enhancements

### Short Term
1. ~~Add more filter hints (frequency, date ranges)~~ ✅ **COMPLETED** - Time period pre-filling implemented
2. Persist counter across browser sessions (localStorage)
3. Add notification when approaching limit (at 55/60)
4. Add frequency pre-filling (e.g., "monthly data" → pre-select "Monthly")

### Long Term
1. Smart caching to reduce API calls
2. Batch downloads (use 1 API call for multiple datasets)
3. Download queue when limit reached
4. Historical usage analytics

---

## User Guide

### Using Country Dropdown

1. **Select countries** from the dropdown (searchable!)
2. **Multiple selection** - click to add more
3. **Remove** - click X on any country tag
4. **All countries** - select "[All Countries]" option

### Using Frequency Dropdown

1. **Single selection** - only one frequency at a time
2. **Options**: Annual, Quarterly, Monthly, or All

### Understanding API Counter

- **Green (0-29)**: Plenty of requests available
- **Yellow (50-59)**: Approaching limit, be mindful
- **Red (60+)**: Limit reached, wait for reset
- **Reset time**: Automatically shown (e.g., "Resets in 45 min")
- **Manual reset**: Use if counter seems stuck

### Smart Pre-Filtering

1. **Mention countries and/or time periods** in your AI question
   - Countries: "US", "Canada", "Germany", etc.
   - Time periods: "2024", "2020 to 2023", "since 2015", "recent data"
2. **Check for hint**: Look for "💡 Detected filter suggestions"
3. **Review pre-filled filters** when opening dataset
   - Country dropdown will have selections
   - Start/End year fields will be populated
4. **Modify if needed** - you can change any pre-filled values

---

## Examples

### Example 1: Country Dropdown

**Before (free text):**
```
Position 1: Reference Area
[Text input: USA+CAN] ← User had to type codes
```

**After (dropdown):**
```
Position 1: Reference Area
☐ [All Countries]
☑ United States          ← User-friendly names
☑ Canada
☐ United Kingdom
☐ Germany
[Search countries...]
```

**API Result**: Same (`USA+CAN`)

---

### Example 2: Smart Pre-Filtering

**User Question:**
> "I'm researching renewable energy adoption in Scandinavian countries"

**AI Response:**
```
I recommend these datasets:

1. **Renewable Energy** (`DSD_RENEW@DF_RENEW`)
   - Comprehensive renewable energy data
   - Covers production, capacity, and consumption

<!-- FILTER_HINTS:COUNTRIES=DNK,NOR,SWE,FIN,ISL -->
```

**Filter Pre-Filled:**
```
💡 Detected filter suggestion: DNK, NOR, SWE, FIN, ISL

Position 1: Reference Area
☑ Denmark
☑ Norway
☑ Sweden
☑ Finland
☑ Iceland
```

**User Experience**:
- Countries already selected
- Can immediately download
- Or modify selection first

---

### Example 3: API Counter in Action

**Session Timeline:**

```
10:00 AM - Start session
Counter: 🟢 0 / 60 (Resets in 60 min)

10:05 AM - Download dataset #1
Counter: 🟢 1 / 60 (Resets in 55 min)

10:15 AM - Download datasets #2-5
Counter: 🟢 5 / 60 (Resets in 45 min)

10:30 AM - Download datasets #6-35
Counter: 🟡 35 / 60 (Resets in 30 min) ← Turns yellow

10:45 AM - Download datasets #36-60
Counter: 🔴 60 / 60 (Resets in 15 min) ← Turns red

10:50 AM - Try to download dataset #61
Error: ⚠️ API rate limit reached (60 requests/hour).
       Please wait for the counter to reset.
       ⏳ Counter resets in 10 minutes

11:00 AM - Counter auto-resets
Counter: 🟢 0 / 60 (Resets in 60 min) ← Fresh start!
```

---

### Example 4: Combined Country + Time Period Pre-Filling

**User Question:**
> "I need US military spending data for 2024"

**AI Response:**
```
I recommend this dataset:

1. **Annual government expenditure by function (COFOG)** (`DSD_NASEC10@DF_TABLE11`)
   - What it offers: Government spending breakdown by function including defense
   - Coverage: OECD countries, annual data
   - Relevance: Defense spending (COFOG code 02) shows military expenditure

<!-- FILTER_HINTS:COUNTRIES=USA -->
<!-- FILTER_HINTS:START_YEAR=2024 -->
<!-- FILTER_HINTS:END_YEAR=2024 -->
```

**App Detection:**
```
💡 Detected filter suggestions: Countries: USA | Time period: 2024-2024
```

**Dataset Export Form (Pre-Filled):**
```
Download Parameters for: Annual government expenditure by function

Position 1: Reference Area (Country)
☑ United States               ← AUTO-FILLED

Position 2: Government Function
[Text input]                  ← User enters "02" for defense

Start Year: 2024              ← AUTO-FILLED
End Year: 2024                ← AUTO-FILLED

[Download CSV Button]
```

**User Experience:**
1. User asks question with country + year
2. AI recommends dataset
3. User clicks to open dataset
4. Sees pre-filled filters (country AND years)
5. Only needs to specify "02" for defense function
6. Clicks download - done!

**Time Saved**: ~30 seconds per dataset (no manual country selection, no date adjustment)

---

## Technical Notes

### Session State Variables

```python
st.session_state.api_counter: int                    # Request count
st.session_state.api_counter_reset_time: datetime    # When counter resets
st.session_state.filter_hints: dict                  # AI-extracted hints
```

### Filter Hints Format

```python
{
    'countries': ['USA', 'CAN', 'MEX'],  # List of ISO country codes
    'start_year': '2020',                 # Start year for time period
    'end_year': '2024',                   # End year for time period
    # Future: 'frequency': 'A', 'measure': 'GDP', etc.
}
```

### API Request Tracking

- Increments **before** actual API call
- Prevents race conditions
- Counts even if API call fails (to be safe)
- Resets automatically after 1 hour
- Persists in session (not localStorage)

---

## Migration Notes

**No action needed** - All changes are backward compatible.

Existing users will see:
1. Improved dropdowns (automatic)
2. API counter (automatic)
3. Smart country pre-filtering (when using AI librarian)
4. Smart time period pre-filling (when using AI librarian)

**No breaking changes to:**
- Existing catalog structure
- API URL construction
- Saved CSV files
- Download functionality
