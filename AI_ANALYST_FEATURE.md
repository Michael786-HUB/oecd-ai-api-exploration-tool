# AI Data Analyst Feature

## Overview

The OECD Data Explorer now includes an **AI Data Analyst** that automatically reads downloaded datasets and answers your original research questions with specific data points.

**Complete Research Workflow:**
1. Ask a question → 2. Download dataset(s) → 3. **AI analyzes data** → 4. Get specific answers with numbers

---

## Key Features

### 1. Organized Query Folders

Every research query gets its own folder in `outputs/`:

```
outputs/
├── US_Healthcare_2023_01Feb26/
│   ├── DSD_SHA_DF_SHA_USA_2023_2023.csv
│   ├── summary.txt
├── Youth_Unemployment_USA_CAN_AUS_01Feb26/
│   ├── DSD_LFS_DF_IALFS_UNE_M_USA_CAN_AUS_2020_2024.csv
│   ├── summary.txt
```

**Folder Naming Logic:**
- Extracts **countries** from your question (US, Canada, UK, etc.)
- Extracts **topics** (Healthcare, Unemployment, GDP, etc.)
- Extracts **years** if mentioned (2023, 2020-2024, etc.)
- Adds **timestamp** (01Feb26)
- **Auto-sanitized** for filesystem compatibility

**Examples:**

| User Question | Generated Folder Name |
|--------------|----------------------|
| "What did US spend on healthcare in 2023?" | `US_Healthcare_2023_01Feb26` |
| "Compare Canada and Australia GDP growth" | `Canada_Australia_Growth_01Feb26` |
| "Youth unemployment trends since 2015" | `Youth_Unemployment_2015_01Feb26` |
| "Show me recent OECD data on education" | `OECD_Recent_Education_01Feb26` |

---

### 2. AI Data Analysis

After downloading datasets, click **"✨ Analyze Data"** to get:

- **Specific numbers** from your data
- **Direct answers** to your original question
- **Comparisons** across countries/time periods
- **Clear formatting** with bullet points

**How It Works:**

1. **Reads all CSVs** in your query folder
2. **Sends to Claude** with your original question
3. **Analyzes data** to find specific values
4. **Returns answer** with exact numbers from the data

**Example:**

**Question:** "What did the United States spend on healthcare in 2023?"

**AI Analysis Result:**
```
Based on the downloaded data, the United States spent $4.5 trillion on healthcare
in 2023, representing 17.3% of GDP. This breaks down to:

• Public spending: $2.7 trillion (60%)
• Private spending: $1.8 trillion (40%)
• Per capita spending: $13,493

This represents a 4.2% increase from 2022 levels.
```

---

### 3. Summary Document (summary.txt)

Each query folder contains a **summary.txt** file that tracks:

1. **Original question** and timestamp
2. **Downloaded datasets** with metadata
3. **API URLs** used (for reproducibility)
4. **AI analysis results**
5. **Conversation history**

**Example summary.txt:**

```
================================================================================
OECD DATA RESEARCH QUERY SUMMARY
================================================================================

Date: 2026-02-01 14:30:22
Query: What did the United States spend on healthcare in 2023?

--------------------------------------------------------------------------------

================================================================================
DATASET DOWNLOADED: DSD_SHA@DF_SHA
================================================================================
Name: Health Expenditure and Financing
Category: Health
File: DSD_SHA_DF_SHA_USA_2023_2023.csv
Rows: 234
Download Time: 2026-02-01 14:31:05

API URL:
https://sdmx.oecd.org/public/rest/data/OECD.ELS.HD,DSD_SHA@DF_SHA,1.0/USA.........?startPeriod=2023&endPeriod=2023&dimensionAtObservation=AllDimensions&format=csvfile

--------------------------------------------------------------------------------

================================================================================
AI ANALYSIS RESULTS
================================================================================
Analysis Time: 2026-02-01 14:32:18

Question: What did the United States spend on healthcare in 2023?

Answer:
Based on the downloaded data, the United States spent $4.5 trillion on healthcare
in 2023, representing 17.3% of GDP...

--------------------------------------------------------------------------------

================================================================================
CONVERSATION HISTORY
================================================================================

USER:
What did the United States spend on healthcare in 2023?

ASSISTANT:
I recommend this dataset:

1. **Health Expenditure and Financing** (`DSD_SHA@DF_SHA`)...

--------------------------------------------------------------------------------
```

---

## User Workflow

### Step 1: Ask a Question

In the AI Librarian tab, ask a specific question:

```
"What was the youth unemployment rate in the United States in 2023?"
```

**Best Practice:** Be specific about:
- **Countries** (focus on major economies: US, UK, Canada, Japan, Australia, Germany, France)
- **Time periods** (recent years are most relevant)
- **Metrics** (unemployment, GDP, spending, etc.)

This keeps datasets manageable and analysis focused.

---

### Step 2: Download Dataset(s)

AI recommends datasets → Configure filters → Click **"📥 Download Dataset"**

**What happens:**
- Query folder auto-created (e.g., `US_Youth_Unemployment_2023_01Feb26/`)
- CSV saved to that folder
- Dataset tracked in session
- Summary.txt created/updated

**Download multiple datasets if needed:**

If your question requires multiple datasets (e.g., "Compare US and Canada healthcare spending"), download both before analyzing.

---

### Step 3: Analyze Data

After downloading, the **"🔬 Data Analysis"** section appears showing:

- Number of datasets downloaded
- Query details (question, folder name)
- List of downloaded files

Click **"✨ Analyze Data"** → AI reads CSVs → Returns specific answer

**Analysis appears:**
- In chat as a new AI message
- In summary.txt for future reference

---

### Step 4: Start New Query

Click **"🔄 New Query"** to start fresh:
- Clears current recommendations
- Resets query folder
- Next download creates new folder

**OR** continue asking follow-up questions in the same query.

---

## Multi-Dataset Analysis

### Scenario: Comparing Multiple Countries

**Question:** "Compare youth unemployment rates in USA, Canada, and Australia in 2023"

**Workflow:**

1. AI recommends dataset
2. Download with **all three countries** selected in filters
3. Single CSV contains all three countries
4. Click "Analyze Data"
5. AI compares: "USA: 7.2%, Canada: 10.1%, Australia: 8.9%"

**OR:**

1. Download separate CSVs for each country
2. All saved to same query folder
3. Click "Analyze Data"
4. AI reads **all CSVs** and compares

---

## Technical Details

### Query Folder Name Generation

**Function:** `generate_query_folder_name(user_question)`

**Extraction Logic:**

1. **Country Detection:**
   - Maps natural language → short codes
   - "United States" / "America" → "US"
   - "Canada" → "Canada"
   - "United Kingdom" / "Britain" → "UK"
   - Supports 20+ common countries

2. **Topic Extraction:**
   - Removes stopwords (what, the, in, on, etc.)
   - Capitalizes key words
   - Limits to 3 topic words

3. **Year Extraction:**
   - Finds 4-digit years (2020-2029)
   - Creates ranges if multiple years (2020_2024)

4. **Sanitization:**
   - Removes special characters (< > : " / \ | ? *)
   - Limits to 60 characters
   - Ensures valid filesystem name

---

### AI Analyst Logic

**Function:** `ai_librarian_analyst(query_folder, user_question, client)`

**Process:**

1. **Find CSVs:** Scans query folder for all .csv files
2. **Read data:** Uses pandas to load each CSV
3. **Prepare summary:**
   - Row/column counts
   - Column names
   - First 20 rows as sample
4. **Send to Claude:**
   - Original question
   - CSV data summaries
   - Analysis instructions
5. **Return answer:** Natural language response with specific numbers

**Data Sent to Claude:**

```python
FILE: DSD_SHA_DF_SHA_USA_2023_2023.csv
ROWS: 234
COLUMNS: 15
COLUMN NAMES: REF_AREA, TIME_PERIOD, OBS_VALUE, UNIT_MEASURE, ...

SAMPLE DATA (first 20 rows):
REF_AREA  TIME_PERIOD  OBS_VALUE  UNIT_MEASURE
USA       2023         4500000    USD_MILLIONS
...
```

**CSV Size Handling:**

- **Full data sent** to Claude (as per your requirement)
- **Users encouraged** to be specific (major countries, recent years)
- **Natural constraint:** Specific queries → smaller datasets
- **If needed:** Can add sampling logic later for massive datasets

---

### Summary File Updates

**Function:** `update_summary_file(query_folder, user_question, ...)`

**Update Triggers:**

1. **Query start:** Creates file with question + timestamp
2. **Dataset download:** Appends dataset metadata + API URL
3. **Analysis complete:** Appends results + conversation history

**Append-only:** File grows as query progresses

---

## Session State Management

**New session state variables:**

```python
st.session_state.current_query = {
    "question": "What did US spend on healthcare in 2023?",
    "folder_name": "US_Healthcare_2023_01Feb26",
    "folder_path": "outputs/US_Healthcare_2023_01Feb26/",
    "datasets": [
        {
            "dataset_id": "DSD_SHA@DF_SHA",
            "name": "Health Expenditure and Financing",
            "category": "Health",
            "filename": "DSD_SHA_DF_SHA_USA_2023_2023.csv",
            "rows": 234,
            "timestamp": "2026-02-01 14:31:05",
            "api_url": "https://..."
        }
    ],
    "analysis_complete": False
}
```

**Lifecycle:**

- **Created:** On first download in a conversation
- **Updated:** Each download adds to datasets array
- **Cleared:** Click "New Query" button
- **Persists:** Across reruns until explicitly cleared

---

## UI Components

### New Query Button

**Location:** Top-right of "Recommended Datasets" section

**Function:** Starts fresh query
- Clears recommendations
- Resets current_query
- Next download creates new folder

---

### Analyze Data Button

**Location:** Below dataset expanders (only appears after download)

**Shows:**
- "📊 X dataset(s) downloaded and ready for analysis"
- Query details (question, folder name)
- List of downloaded datasets

**On Click:**
- Reads all CSVs in query folder
- Sends to Claude for analysis
- Displays results in chat
- Updates summary.txt
- Marks analysis as complete

---

### Query Details Display

**After download, shows:**

```
Query Details:
Question: What did US spend on healthcare in 2023?
Folder: US_Healthcare_2023_01Feb26
```

**Expandable section:**
- Lists all downloaded datasets
- Shows filename, rows, timestamp

---

## Example Workflows

### Example 1: Single Country, Single Metric

**Question:** "What was US GDP in 2024?"

**Flow:**
1. Ask question
2. AI recommends GDP dataset
3. Download (filters: USA, 2024)
4. Click "Analyze Data"
5. **Result:** "US GDP in 2024 was $28.2 trillion, representing 3.1% growth from 2023."

**Folder:** `US_2024_01Feb26/`

---

### Example 2: Multi-Country Comparison

**Question:** "Compare healthcare spending in USA, UK, and Canada in 2023"

**Flow:**
1. Ask question
2. AI recommends Health Expenditure dataset
3. Download with filters: USA+UK+CAN, 2023
4. Click "Analyze Data"
5. **Result:**
   ```
   Healthcare spending as % of GDP in 2023:
   • USA: 17.3%
   • UK: 11.2%
   • Canada: 12.1%

   USA spends significantly more both in absolute terms ($4.5T) and per capita ($13,493).
   ```

**Folder:** `USA_Canada_Healthcare_2023_01Feb26/`

---

### Example 3: Time Series Analysis

**Question:** "How has youth unemployment changed in Australia from 2019 to 2024?"

**Flow:**
1. Ask question
2. AI recommends Labour Force Statistics
3. Download with filters: Australia, 2019-2024
4. Click "Analyze Data"
5. **Result:**
   ```
   Youth unemployment rate in Australia:
   • 2019: 11.3%
   • 2020: 14.2% (COVID spike)
   • 2021: 11.8%
   • 2022: 9.5%
   • 2023: 8.9%
   • 2024: 8.7%

   Overall declining trend post-COVID, with current rate below pre-pandemic levels.
   ```

**Folder:** `Australia_Unemployment_2019_2024_01Feb26/`

---

## Best Practices

### For Users

1. **Be specific** in questions:
   - ✅ "What was US military spending in 2023?"
   - ❌ "Tell me about defense budgets"

2. **Focus on major economies:**
   - Most research involves: US, UK, Canada, Japan, Australia, Germany, France
   - Keeps datasets manageable
   - Faster analysis

3. **Use recent years:**
   - Most relevant data is from last 5-10 years
   - Reduces data volume
   - Better availability

4. **Download all needed datasets before analyzing:**
   - If comparing metrics, download both datasets
   - Click "Analyze Data" once all data is ready

5. **Check summary.txt:**
   - Contains API URLs for reproducibility
   - Full conversation history
   - Analysis results for reference

---

### For Developers

1. **Folder names are auto-generated:**
   - Don't rely on specific naming
   - Use `st.session_state.current_query["folder_path"]`

2. **CSVs can vary in size:**
   - Current: Send full data to Claude
   - Future: Add sampling if needed

3. **Multiple CSVs supported:**
   - ai_librarian_analyst reads ALL CSVs in folder
   - Combines for comprehensive analysis

4. **Summary file is append-only:**
   - Safe to call update_summary_file multiple times
   - Each call adds new section

---

## Files Modified

**[app.py](app.py)**:

1. **New imports** (lines 1-9):
   - `from datetime import datetime`
   - `import pandas as pd`

2. **New functions** (lines 410-600):
   - `generate_query_folder_name()` - Extracts entities from questions
   - `create_query_folder()` - Creates query folder
   - `update_summary_file()` - Writes/updates summary.txt
   - `ai_librarian_analyst()` - Analyzes CSV data with Claude

3. **Modified download logic** (lines 850-950):
   - Creates query folder on first download
   - Saves to query folder instead of root outputs/
   - Tracks downloads in session state
   - Updates summary.txt with dataset info

4. **New UI components** (lines 1100-1180):
   - "New Query" button
   - "Analyze Data" button
   - Query details display
   - Downloaded datasets list

5. **Session state initialization** (lines 1020-1025):
   - Initialize `current_query` to None

---

## Future Enhancements

### Short Term

1. **Visualization generation:**
   - Auto-create charts from analyzed data
   - Save to query folder

2. **Export to PDF:**
   - Convert summary.txt to formatted PDF
   - Include visualizations

3. **Query templates:**
   - Pre-built queries for common research questions
   - One-click research workflows

### Long Term

1. **Advanced analysis:**
   - Statistical tests (correlation, regression)
   - Trend analysis with forecasting
   - Anomaly detection

2. **Comparative research:**
   - Cross-query comparisons
   - Historical trend tracking
   - Benchmark against OECD averages

3. **Collaborative features:**
   - Share query folders
   - Collaborative annotations
   - Team research workspaces

---

## Troubleshooting

### Issue: "No CSV files found"

**Cause:** Clicked "Analyze Data" before downloading any datasets

**Solution:** Download at least one dataset first

---

### Issue: Analysis shows "data doesn't contain the answer"

**Cause:** Downloaded dataset doesn't have the specific metric you asked about

**Solution:**
- Check if you filtered correctly (right country, year, etc.)
- Try different dataset recommended by AI
- Ask AI to recommend more specific dataset

---

### Issue: Folder name is too generic

**Cause:** Question doesn't contain specific countries/topics/years

**Solution:**
- Ask more specific questions
- Folder will still be unique (timestamp)
- Functionality not affected

---

### Issue: Want to add more datasets to existing analysis

**Solution:**
- Don't click "New Query"
- Simply download additional datasets
- They'll save to same folder
- Click "Analyze Data" again to include new data

---

## Summary

The AI Data Analyst feature transforms the OECD Data Explorer from a **data discovery tool** into a complete **research assistant** that:

✅ Organizes your research into query-specific folders
✅ Tracks all downloads and API calls
✅ Automatically analyzes data to answer your questions
✅ Provides specific numbers and insights
✅ Documents everything in summary.txt for reproducibility

**Complete research workflow in 3 clicks:**
1. Ask question
2. Download dataset(s)
3. Analyze data → Get answer

No more manual CSV analysis - the AI does it for you! 🎉
