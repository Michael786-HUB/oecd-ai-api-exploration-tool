# app.py

import streamlit as st
import json
from scripts.oecd_class import OECDDataFetcher
import anthropic
import os
import re
from html import unescape
from datetime import datetime
import pandas as pd
import subprocess
import sys

def open_folder_dialog_subprocess():
    """
    Opens a native folder dialog using a subprocess to avoid threading issues on macOS.
    Returns the selected folder path or None if cancelled/error.
    """
    # Create a small Python script that opens the dialog
    dialog_script = '''
import tkinter as tk
from tkinter import filedialog
import sys
import os

root = tk.Tk()
root.withdraw()
root.wm_attributes('-topmost', 1)

selected_path = filedialog.askdirectory(
    title="Select Output Folder",
    initialdir=sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~")
)

root.destroy()

# Print selected path to stdout
if selected_path:
    print(selected_path)
'''

    try:
        # Run the dialog script in a subprocess
        result = subprocess.run(
            [sys.executable, '-c', dialog_script, os.path.expanduser("~")],
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
        )

        selected_path = result.stdout.strip()
        return selected_path if selected_path else None
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        st.error(f"Error opening folder dialog: {str(e)}")
        return None

def clean_html_description(html_text):
    """
    Clean HTML tags and entities from description text.
    Converts HTML to readable plain text while preserving structure.
    """
    if not html_text:
        return ""

    # Unescape HTML entities first (&gt; -> >, &nbsp; -> space, etc.)
    text = unescape(html_text)

    # Replace common block elements with newlines
    text = re.sub(r'</p>\s*<p>', '\n\n', text)
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</li>\s*<li>', '\n• ', text)
    text = re.sub(r'<li>', '\n• ', text)
    text = re.sub(r'</h\d>', '\n\n', text)
    text = re.sub(r'<h\d[^>]*>', '\n**', text)

    # Remove all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Clean up excessive whitespace
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()

    return text

# Page config
st.set_page_config(
    page_title="OECD Data Explorer",
    page_icon="📊",
    layout="wide"
)

# Load the categorized catalog
@st.cache_data
def load_catalog():
    """Load the structured catalog (cached so it only loads once)"""
    with open('data/catalogs/oecd_dataset_catalog_with_dimensions.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# Load country codes
@st.cache_data
def load_country_codes():
    """Load country name to code mappings"""
    with open('data/country_codes.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# Initialize the data fetcher
@st.cache_resource
def get_fetcher():
    """Initialize the fetcher (cached so it persists across reruns)"""
    import os
    output_dir = "outputs"
    # Ensure output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    return OECDDataFetcher(output_dir=output_dir)

@st.cache_resource
def anthropic_client():

    api_key = st.secrets.get("ANTHROPIC_API_KEY")

    if not api_key:
        st.error("Anthropic API key not found in secrets. Please add it to proceed.")

    return anthropic.Anthropic(api_key=api_key)

def build_catalog_summary(catalog):
    """
    Build a detailed summary string of the catalog with actual dataset IDs for Claude.
    """
    summary_lines = []
    for category, cat_data in catalog.items():
        summary_lines.append(f"\n## {category}")
        datasets = cat_data["datasets"]

        # List datasets with their IDs, names, and descriptions
        # Increased from 15 to 25 to give AI more options
        for dataset_id, metadata in list(datasets.items())[:25]:
            name = metadata['name'][:60]  # Truncate long names
            desc = metadata.get('description', '')[:100]  # Short description snippet
            summary_lines.append(f"  - `{dataset_id}`: {name}")
            if desc:
                # Clean up description for display
                clean_desc = desc.replace('\n', ' ').strip()
                summary_lines.append(f"    → {clean_desc}...")

        if len(datasets) > 25:
            summary_lines.append(f"  ... and {len(datasets) - 25} more datasets")

    return "\n".join(summary_lines)

def ask_ai_librarian(user_question, catalog, client, conversation_history=None):
    """
    Send a user question to Claude and get dataset recommendations.
    Supports multi-turn conversations by accepting conversation history.
    
    """

    catalog_summary = build_catalog_summary(catalog)

    # Check if user mentioned specific dataset IDs
    mentioned_ids = extract_dataset_ids_from_query(user_question)
    if mentioned_ids:
        valid_mentioned, _ = validate_dataset_ids(mentioned_ids, catalog)
        if valid_mentioned:
            # Add detailed info about mentioned datasets to the prompt
            dataset_details = lookup_dataset_details(valid_mentioned, catalog)
            catalog_summary = dataset_details + "\n\n" + catalog_summary

    system_prompt = f""" You are a friendly, knowledgeable, and helpful OECD data librarian. Think of yourself as a helpful librarian who genuinely enjoys helping users discover insights in data, and has expert knowledge on the OECD database


Users will come to you with diverse questions, some simple and some complex, about the data collected by the OECD. Some users are simply looking to know what datasets are available, some users already know what data they’re looking for and they need the data available for exportation, and some users are looking to explore complex relationships like causation, correlation, and trends across countries and time periods. 


Example #1 ----> "I am looking to see if countries that spend the most on foreign aid also have high unemployment rates."


Example #2 —---> “Is there any data on health care spending in Canada”


               Available OECD datasets:
               {catalog_summary}


               YOUR APPROACH:


               1. **Be conversational and thoughtful**: Start by briefly acknowledging their question and that you’re evaluating their request.


               2. **Only ask for clarity IF needed**: If a question is vague or could be interpreted multiple ways, ask a clarifying question. For example:
                  - "Are you interested in comparing specific countries, or looking at OECD-wide trends?"
                  - "Would you like current data, or are you interested in trends over time?"
                  - "Are you focusing on a particular age group, sector, or demographic?"


               3. **Think through your recommendations**: When you suggest datasets, explain your reasoning like a real librarian would:
                  - What specific insights can be drawn from each dataset
                  - How different datasets might complement each other
                  - Segment the question from the user to target their specific requirements. For example,
                           "Foreign aid can be found in this dataset" and "Unemployment rates are covered in this other dataset"
                  - Interesting patterns or comparisons the data might reveal

                  IMPORTANT FOR CATEGORY QUERIES: If the user asks about a general topic or category (e.g., "Public Governance datasets",
                  "health data", "economic indicators"), show ALL available datasets in that category, not just 2-3 examples.
                  The goal is to help users find their SPECIFIC datapoint quickly, so comprehensiveness is valuable.
                  You can list up to 10-15 datasets if multiple options exist - this helps users see all their choices.


               4. **Provide engaging detail**: Don't just list datasets - help users understand how each dataset can be used to get the data they need:
                  - What key indicators or metrics it contains
                  - What time periods it covers
                  - What types of analysis it enables
                  - How it might answer their specific question


               5. **Be precise with dataset IDs** (CRITICAL - DO NOT VIOLATE):
                  - ONLY use EXACT dataset IDs that appear in the catalog above
                  - Each ID must be copied EXACTLY as shown (including @ symbols and underscores)
                  - NEVER create, modify, or guess dataset IDs
                  - NEVER recommend a dataset unless you can see its EXACT ID in the catalog
                  - If you cannot find a matching dataset, say so explicitly - DO NOT invent one
                  - Format: Always wrap IDs in backticks like `DSD_XXX@DF_YYY`
                  - Double-check: Before recommending, verify the ID exists in the catalog text above

               RESPONSE FORMAT:

               [Start with a brief, conversational acknowledgment of their question]
		  
               [Then provide a list of datasets that relevent to the query:]
		
               OECD Datasets that can help answer your question:

               1. **Dataset Name** (`EXACT_DATASET_ID_FROM_CATALOG`)
                  - **Category**: [Category name]
                  - **What it offers**: [Detailed explanation of what specific data/insights this provides]
                  - **Why it's relevant**: [How it addresses their question, what they can learn from it]

               2. **Dataset Name** (`EXACT_DATASET_ID_FROM_CATALOG`)
                  - **Category**: [Category name]
                  - **What it offers**: [Detailed explanation]
                  - **Why it's relevant**: [Connection to their question]

               [End with a helpful note about how these datasets work together or what analysis they enable]

               IMPORTANT: If the user mentions specific countries or time periods, you MUST add hidden filter hint comments at the END of your response (after all other content). These help pre-fill the download form:

               COUNTRY CODES (use ISO 3-letter codes):
               - United States → USA
               - Canada → CAN
               - United Kingdom → GBR
               - Germany → DEU
               - France → FRA
               - Japan → JPN
               - Australia → AUS
               - Multiple countries: separate with commas (USA,CAN,GBR)

               TIME PERIODS:
               - "2024 data" → START_YEAR=2024, END_YEAR=2024
               - "2020 to 2023" → START_YEAR=2020, END_YEAR=2023
               - "since 2015" → START_YEAR=2015, END_YEAR=2025
               - "recent data" → START_YEAR=2020, END_YEAR=2025
               - "last decade" → START_YEAR=2015, END_YEAR=2025

               FORMAT (add these exact comments at the very end of your response):
               <!-- FILTER_HINTS:COUNTRIES=USA,CAN -->
               <!-- FILTER_HINTS:START_YEAR=2020 -->
               <!-- FILTER_HINTS:END_YEAR=2024 -->

               Example: If user asks "US healthcare spending 2020-2023", end your response with:
               <!-- FILTER_HINTS:COUNTRIES=USA -->
               <!-- FILTER_HINTS:START_YEAR=2020 -->
               <!-- FILTER_HINTS:END_YEAR=2023 -->

               Remember: Be warm, engaging, and genuinely helpful - like a knowledgeable colleague who loves talking about data!
               """

    
    try:
        # Build messages list from conversation history if available
        if conversation_history:
            messages = [{"role": msg["role"], "content": msg["content"]}
                       for msg in conversation_history]
        else:
            messages = [{"role": "user", "content": user_question}]

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=messages
        )

        response_text = message.content[0].text
        return response_text
    
    except Exception as e:
        return f"Error communicating message to claude"

def extract_dataset_ids(response_text):
    """
    Extract dataset IDs from Claude's response.
    Matches patterns like: DSD_XXX@DF_YYY, DATASET_NAME, etc.
    """

    import re

    # Updated pattern to match uppercase, lowercase, numbers, underscores, and @
    pattern = r'`([A-Za-z0-9_@]+)`'
    matches = re.findall(pattern, response_text)

    # Filter to keep only valid-looking dataset IDs
    dataset_ids = [m for m in matches if "@" in m or "DSD_" in m or "DF_" in m or "SEEA_" in m]

    return dataset_ids

def extract_dataset_ids_from_query(query_text):
    """
    Extract potential dataset IDs from user query (without backticks).
    More lenient pattern to catch dataset mentions in natural language.
    """
    import re

    # Pattern matches dataset IDs even without backticks
    # Matches: DSD_XXX@DF_YYY or similar patterns
    pattern = r'\b([A-Z][A-Z0-9_]*(?:@[A-Z][A-Z0-9_]*)?)\b'
    matches = re.findall(pattern, query_text)

    # Filter to keep only valid-looking dataset IDs
    dataset_ids = [m for m in matches if "@" in m or m.startswith("DSD_") or m.startswith("DF_") or m.startswith("SEEA_")]

    return dataset_ids

def validate_dataset_ids(dataset_ids, catalog):
    """
    Validate that dataset IDs exist in the catalog.
    Returns tuple: (valid_ids, invalid_ids)
    """
    valid_ids = []
    invalid_ids = []

    for dataset_id in dataset_ids:
        # Check if dataset exists in any category
        found = False
        for category, cat_data in catalog.items():
            if dataset_id in cat_data["datasets"]:
                valid_ids.append(dataset_id)
                found = True
                break

        if not found:
            invalid_ids.append(dataset_id)

    return valid_ids, invalid_ids

def lookup_dataset_details(dataset_ids, catalog):
    """
    Look up detailed information for specific dataset IDs.
    Returns formatted string with dataset details for AI context.
    """
    details = []

    for dataset_id in dataset_ids:
        for category, cat_data in catalog.items():
            if dataset_id in cat_data["datasets"]:
                metadata = cat_data["datasets"][dataset_id]
                name = metadata.get('name', 'Unknown')
                desc = metadata.get('description', 'No description available')[:200]
                agency = metadata.get('agency', 'Unknown')

                detail_text = f"""
**USER-MENTIONED DATASET (PRIORITIZE THIS):**
- ID: `{dataset_id}`
- Name: {name}
- Category: {category}
- Agency: {agency}
- Description: {desc}...

This dataset was explicitly mentioned by the user. Make this your TOP RECOMMENDATION.
"""
                details.append(detail_text)
                break

    return "\n".join(details) if details else ""

def extract_filter_hints(response_text):
    """
    Extract filter hints from AI response (countries, time periods, etc.).
    Returns dict with filter suggestions.
    """
    import re

    hints = {}

    # Extract country hints
    country_pattern = r'<!-- FILTER_HINTS:COUNTRIES=([A-Z,]+) -->'
    country_match = re.search(country_pattern, response_text)
    if country_match:
        countries = country_match.group(1).split(',')
        hints['countries'] = [c.strip() for c in countries]

    # Extract start year hint
    start_year_pattern = r'<!-- FILTER_HINTS:START_YEAR=(\d{4}) -->'
    start_year_match = re.search(start_year_pattern, response_text)
    if start_year_match:
        hints['start_year'] = start_year_match.group(1)

    # Extract end year hint
    end_year_pattern = r'<!-- FILTER_HINTS:END_YEAR=(\d{4}) -->'
    end_year_match = re.search(end_year_pattern, response_text)
    if end_year_match:
        hints['end_year'] = end_year_match.group(1)

    return hints
                   
def search_datasets(catalog, search_term):
    """
    Search for datasets across all categories by ID or name.
    Returns list of (category, dataset_id, metadata) tuples.
    """
    results = []
    search_lower = search_term.lower()
    
    for category, cat_data in catalog.items():
        for dataset_id, metadata in cat_data["datasets"].items():
            # Search in ID or name
            if (search_lower in dataset_id.lower() or 
                search_lower in metadata['name'].lower()):
                results.append((category, dataset_id, metadata))
    
    return results

def find_dataset_by_id(catalog, dataset_id):
    """
    Find a dataset using the dataset_id and catalogs
    """

    for category, cat_data in catalog.items():
        if dataset_id in cat_data["datasets"]:
            return category, cat_data["datasets"][dataset_id]

    return None, None


# ============================================================================
# DATAFRAME OPTIMIZATION FUNCTIONS - Reduce token usage for AI analysis
# ============================================================================

# Columns that should NEVER be dropped - they provide critical context for analysis
PROTECTED_CONTEXT_COLUMNS = [
    # Country/geographic identifiers - CRITICAL for knowing what data is about
    'DONOR', 'Donor',
    'REF_AREA', 'Reference area', 'Reference Area',
    'RECIPIENT', 'Recipient',
    'COUNTRY', 'Country',
    'LOCATION', 'Location',
    # Units and currencies
    'UNIT_MEASURE', 'Unit of measure', 'Unit',
    'CURRENCY', 'Currency',
    'UNIT_MULT', 'Unit multiplier',
    'POWERCODE', 'Power code',
    # Price context
    'PRICE_BASE', 'Price base', 'Prices',
    'BASE_PER', 'Base period',
    # Measure and flow context
    'MEASURE', 'Measure',
    'FLOW_TYPE', 'Flow type', 'Flow',
    'SECTOR', 'Sector',
    # Transformations
    'TRANSFORMATION', 'Transformation'
]


def is_protected_column(col_name):
    """Check if a column name matches any protected context column."""
    col_lower = col_name.lower()
    for protected in PROTECTED_CONTEXT_COLUMNS:
        if protected.lower() in col_lower or col_lower in protected.lower():
            return True
    return False


def drop_hardcoded_columns(df):
    """
    Drop columns that are known to be unhelpful for analysis.
    These are typically SDMX structural metadata columns.
    """
    columns_to_drop = ['STRUCTURE_NAME', 'STRUCTURE_ID', 'STRUCTURE']
    existing_cols_to_drop = [col for col in columns_to_drop if col in df.columns]

    if existing_cols_to_drop:
        df = df.drop(columns=existing_cols_to_drop)

    return df


def drop_sdmx_id_columns(df):
    """
    Drop columns that contain SDMX identifiers (dataset IDs, agency codes).
    These columns typically have values like 'DSD_XXX@DF_YYY' or 'OECD'.
    """
    cols_to_drop = []

    for col in df.columns:
        # Sample first non-null values
        sample_values = df[col].dropna().head(5).astype(str).tolist()

        if not sample_values:
            continue

        # Check if values look like SDMX IDs
        sdmx_patterns = 0
        for val in sample_values:
            # SDMX dataset IDs contain @ symbol (e.g., DSD_XXX@DF_YYY)
            if '@' in val and 'DSD' in val.upper():
                sdmx_patterns += 1
            # Agency codes are short uppercase strings like OECD, IMF, etc.
            elif val.isupper() and len(val) <= 10 and val.isalpha():
                sdmx_patterns += 1

        # If most values match SDMX patterns, drop the column
        if sdmx_patterns >= len(sample_values) * 0.8:
            cols_to_drop.append(col)

    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    return df


def drop_single_country_columns(df):
    """
    If the dataframe has only one unique country, drop country-related columns.
    The country name is already known, so these columns add no value.

    EXCEPTION: Protected columns (DONOR, REF_AREA, etc.) are KEPT because they
    provide critical context for the AI analyst.
    """
    # Common country column names
    country_col_patterns = ['REF_AREA', 'Reference area', 'Reference Area',
                            'COUNTRY', 'Country', 'country', 'GEO', 'Geo']

    # Find country columns
    country_cols = [col for col in df.columns
                    if any(pattern.lower() in col.lower() for pattern in country_col_patterns)]

    if not country_cols:
        return df

    # Check if there's only one unique country value
    for col in country_cols:
        if df[col].nunique() == 1:
            # Only one country - drop non-protected country columns
            cols_to_drop = [c for c in df.columns
                           if any(pattern.lower() in c.lower() for pattern in country_col_patterns)
                           and not is_protected_column(c)]  # Don't drop protected columns!
            if cols_to_drop:
                df = df.drop(columns=cols_to_drop)
                print(f"Dropped single-country columns: {cols_to_drop}")
            break

    return df


def drop_single_value_columns(df):
    """
    Drop columns where all values are identical (only 1 unique value).
    These columns provide no analytical value.

    EXCEPTION: Protected context columns (UNIT_MEASURE, PRICE_BASE, etc.) are
    kept even with single values - they provide critical context for analysis.
    """
    cols_to_drop = []
    protected_kept = []

    for col in df.columns:
        if df[col].nunique() <= 1:
            # Check if this is a protected context column
            if is_protected_column(col):
                protected_kept.append(col)
                continue  # Don't drop protected columns
            cols_to_drop.append(col)

    if protected_kept:
        print(f"Protected single-value columns kept: {protected_kept}")

    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)

    return df


def normalize_column_name(col_name):
    """
    Normalize a column name for comparison.
    Converts to lowercase and replaces underscores with spaces.
    """
    return col_name.lower().replace('_', ' ').strip()


def is_id_column(col_name):
    """
    Check if a column name looks like an ID column (uppercase with underscores).
    Examples: UNIT_MEASURE, REF_AREA, FLOW_TYPE
    """
    # ID columns are typically all uppercase with underscores
    if col_name.isupper() and '_' in col_name:
        return True
    # Or just all uppercase
    if col_name.isupper() and len(col_name) > 2:
        return True
    return False


def is_text_description_column(col_name):
    """
    Check if a column name looks like a text description (readable).
    Examples: "Unit of measure", "Reference Area", "Flow Type"
    """
    # Text descriptions have spaces and mixed/title case
    if ' ' in col_name:
        return True
    # Or they're in Title Case without underscores
    if col_name[0].isupper() and not col_name.isupper() and '_' not in col_name:
        return True
    return False


def column_has_id_values(df, col):
    """
    Check if a column contains ID/code values (short codes, numbers, uppercase).

    ID values look like: "106", "USA", "USD", "ODA_GNI", "TOTAL"
    Description values look like: "Imputed Multilateral ODA", "United States", "US Dollars"

    Returns True if values appear to be IDs/codes rather than descriptions.

    EXCEPTION: Protected context columns (UNIT_MEASURE, PRICE_BASE, etc.) are
    never treated as ID columns - their values are critical context even if short.
    """
    # Protected columns should never be treated as ID columns
    if is_protected_column(col):
        return False

    sample_values = df[col].dropna().head(20).astype(str).tolist()

    if not sample_values:
        return False

    id_indicators = 0
    for val in sample_values:
        val = val.strip()

        # Pure numbers are IDs
        if val.isdigit():
            id_indicators += 1
            continue

        # Short uppercase strings are likely codes (USA, USD, ODA)
        if len(val) <= 10 and val.isupper() and val.replace('_', '').replace('-', '').isalnum():
            id_indicators += 1
            continue

        # Codes with underscores (ODA_GNI, FLOW_TYPE)
        if '_' in val and val.isupper():
            id_indicators += 1
            continue

        # Very short values (1-3 chars) are likely codes
        if len(val) <= 3 and val.isalnum():
            id_indicators += 1
            continue

    # If more than 70% of values look like IDs, it's an ID column
    return id_indicators >= len(sample_values) * 0.7


def column_has_description_values(df, col):
    """
    Check if a column contains descriptive text values.

    Description values are longer, have spaces, mixed case, readable text.

    Returns True if values appear to be descriptions rather than IDs.
    """
    sample_values = df[col].dropna().head(20).astype(str).tolist()

    if not sample_values:
        return False

    desc_indicators = 0
    for val in sample_values:
        val = val.strip()

        # Contains spaces = likely a description
        if ' ' in val and len(val) > 5:
            desc_indicators += 1
            continue

        # Mixed case with length > 10 = likely a description
        if len(val) > 10 and not val.isupper() and not val.islower():
            desc_indicators += 1
            continue

        # Long lowercase/titlecase strings = descriptions
        if len(val) > 15:
            desc_indicators += 1
            continue

    # If more than 50% of values look like descriptions, it's a description column
    return desc_indicators >= len(sample_values) * 0.5


def find_redundant_column_pairs(df):
    """
    Find pairs of columns where one contains ID/code values and the other
    contains readable text descriptions for the same dimension.

    Examples:
    - MEASURE (106, 205) vs Measure ("Imputed Multilateral ODA", "Bilateral ODA")
    - REF_AREA (USA, CAN) vs "Reference Area" ("United States", "Canada")

    Identifies pairs by:
    1. Matching normalized column names (UNIT_MEASURE ↔ "Unit of measure")
    2. Checking VALUES to determine which is ID vs description

    ALWAYS keeps the description column and drops the ID column.

    Returns a list of columns to drop (the ID columns, NOT the descriptions).
    """
    columns = list(df.columns)
    normalized_map = {}  # normalized_name -> list of original column names

    for col in columns:
        normalized = normalize_column_name(col)
        if normalized not in normalized_map:
            normalized_map[normalized] = []
        normalized_map[normalized].append(col)

    cols_to_drop = []

    for normalized, col_list in normalized_map.items():
        if len(col_list) > 1:
            # We have columns with matching normalized names
            # Check VALUES to determine which are IDs vs descriptions
            id_cols = [c for c in col_list if column_has_id_values(df, c)]
            desc_cols = [c for c in col_list if column_has_description_values(df, c)]

            # If we have both ID and description columns, DROP the ID columns
            if desc_cols and id_cols:
                cols_to_drop.extend(id_cols)
                print(f"Dropping ID column(s) {id_cols}, keeping description(s) {desc_cols}")
            # If we can't distinguish by values, fall back to column name heuristics
            elif len(col_list) > 1:
                # Prefer columns with spaces in name (more readable)
                id_by_name = [c for c in col_list if is_id_column(c)]
                text_by_name = [c for c in col_list if is_text_description_column(c)]
                if text_by_name and id_by_name:
                    cols_to_drop.extend(id_by_name)
                    print(f"Dropping ID column(s) {id_by_name} (by name), keeping {text_by_name}")

    return cols_to_drop


def drop_redundant_columns(df):
    """
    Drop redundant columns where we have both an ID column and a description column.

    Identifies pairs like:
    - MEASURE (values: 106, 205) vs Measure (values: "Imputed Multilateral ODA")
    - REF_AREA (values: USA) vs "Reference Area" (values: "United States")

    Keeps the description column (human-readable text), drops the ID column (codes).
    """
    cols_to_drop = find_redundant_column_pairs(df)

    if cols_to_drop:
        df = df.drop(columns=cols_to_drop)
        print(f"Dropped {len(cols_to_drop)} redundant ID columns: {cols_to_drop}")

    return df


def get_column_summary(df):
    """
    Generate a summary of columns and their unique values for AI to evaluate relevance.
    Returns a concise string representation.
    """
    summary_parts = []

    for col in df.columns:
        unique_count = df[col].nunique()
        sample_values = df[col].dropna().unique()[:3]  # First 3 unique values
        sample_str = ", ".join([str(v)[:30] for v in sample_values])
        summary_parts.append(f"- {col}: {unique_count} unique values (e.g., {sample_str})")

    return "\n".join(summary_parts)


def ai_select_relevant_columns(df, user_question, client):
    """
    Use AI to determine which columns are relevant to the user's question.
    Returns a list of column names to keep.
    """
    column_summary = get_column_summary(df)

    prompt = f"""You are analyzing a dataset to answer this question: "{user_question}"

Here are the columns available in the dataset:
{column_summary}

Which columns are ESSENTIAL to answer this question?
Consider:
- Columns containing the actual data/metrics being asked about
- Columns needed for filtering (countries, time periods, categories)
- Columns that provide necessary context (units, measures)

Return ONLY a comma-separated list of column names to KEEP. Do not include explanations.
Example response: TIME_PERIOD, OBS_VALUE, Reference Area, Unit of measure"""

    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Parse the response - split by comma and clean up
        suggested_cols = [col.strip() for col in response_text.split(',')]

        # Validate that suggested columns exist in the dataframe
        valid_cols = [col for col in suggested_cols if col in df.columns]

        # Always keep OBS_VALUE if it exists (this is typically the main data column)
        if 'OBS_VALUE' in df.columns and 'OBS_VALUE' not in valid_cols:
            valid_cols.append('OBS_VALUE')

        # ALWAYS keep protected context columns - they're essential for interpretation
        for col in df.columns:
            if is_protected_column(col) and col not in valid_cols:
                valid_cols.append(col)
                print(f"AI selection: forcing protected column: {col}")

        # If AI returned nothing useful, keep all columns
        if len(valid_cols) < 2:
            return list(df.columns)

        return valid_cols

    except Exception as e:
        # If AI call fails, return all columns
        return list(df.columns)


def limit_columns(df, max_cols=12):
    """
    Limit the dataframe to a maximum number of columns.
    Prioritizes keeping:
    1. Protected context columns (UNIT_MEASURE, PRICE_BASE, MEASURE, etc.) - ALWAYS kept
    2. Descriptive string columns (country names, measure types, indicators)
    3. Year columns (for time series data)
    4. Drops ID columns first
    """
    if len(df.columns) <= max_cols:
        return df

    # Categorize columns
    protected_cols = []  # Protected context columns - ALWAYS keep
    year_cols = []  # Columns that are years (2020, 2021, etc.)
    descriptive_cols = []  # String description columns (keep these!)
    id_cols = []  # ID/code columns (drop these first)
    other_cols = []

    for col in df.columns:
        col_str = str(col)

        # Protected context columns always come first
        if is_protected_column(col_str):
            protected_cols.append(col)
        # Year columns (4-digit numbers)
        elif col_str.isdigit() and len(col_str) == 4:
            year_cols.append(col)
        # Descriptive columns: have spaces, mixed case, or known patterns
        elif ' ' in col_str or (col_str[0].isupper() and not col_str.isupper()):
            descriptive_cols.append(col)
        # ID columns: all uppercase
        elif col_str.isupper() and len(col_str) > 2:
            id_cols.append(col)
        else:
            other_cols.append(col)

    # Build priority order: protected first, then descriptive, then years, then other
    # Protected columns are ALWAYS kept (never dropped)
    keep_cols = list(protected_cols)

    # Add descriptive columns
    slots_remaining = max_cols - len(keep_cols)
    if slots_remaining > 0:
        keep_cols.extend(descriptive_cols[:slots_remaining])

    # Add year columns (most recent first)
    year_cols_sorted = sorted(year_cols, key=lambda x: str(x), reverse=True)
    slots_for_years = max_cols - len(keep_cols)
    if slots_for_years > 0:
        keep_cols.extend(year_cols_sorted[:slots_for_years])

    # If still under limit, add other columns
    slots_left = max_cols - len(keep_cols)
    if slots_left > 0:
        keep_cols.extend(other_cols[:slots_left])

    # Reorder: protected first, then descriptive, then years in chronological order
    final_cols = [c for c in protected_cols if c in keep_cols]
    final_cols.extend([c for c in descriptive_cols if c in keep_cols and c not in final_cols])
    final_cols.extend(sorted([c for c in keep_cols if c in year_cols], key=lambda x: str(x)))
    final_cols.extend([c for c in keep_cols if c not in final_cols])

    print(f"Column limit: kept {len(final_cols)} cols - {len(protected_cols)} protected, {len([c for c in final_cols if c in descriptive_cols])} descriptive, {len([c for c in final_cols if c in year_cols])} years")

    return df[final_cols]


def find_time_column(df):
    """
    Find the time period column in the dataframe.
    Returns the column name or None if not found.
    """
    time_patterns = ['TIME_PERIOD', 'Time period', 'Time Period', 'YEAR', 'Year',
                     'DATE', 'Date', 'PERIOD', 'Period']

    for pattern in time_patterns:
        if pattern in df.columns:
            return pattern
        # Case-insensitive search
        for col in df.columns:
            if pattern.lower() == col.lower():
                return col

    return None


def find_value_column(df):
    """
    Find the observation/value column in the dataframe.
    Returns the column name or None if not found.
    """
    value_patterns = ['OBS_VALUE', 'Value', 'VALUE', 'Observation value',
                      'OBSERVATION', 'Observation']

    for pattern in value_patterns:
        if pattern in df.columns:
            return pattern
        for col in df.columns:
            if pattern.lower() == col.lower():
                return col

    return None


def pivot_dataframe_by_time(df, aggfunc='mean'):
    """
    Pivot the dataframe so that time periods become columns.

    Before pivot (many rows):
        Country | Indicator | TIME_PERIOD | OBS_VALUE
        USA     | GDP       | 2021        | 100
        USA     | GDP       | 2022        | 105
        USA     | GDP       | 2023        | 110
        CAN     | GDP       | 2021        | 50
        ...

    After pivot (compact):
        Country | Indicator | 2021 | 2022 | 2023
        USA     | GDP       | 100  | 105  | 110
        CAN     | GDP       | 50   | 52   | 55

    Args:
        df: The pandas DataFrame to pivot
        aggfunc: Aggregation function for duplicate values ('mean', 'sum', 'first')

    Returns:
        Pivoted DataFrame with time periods as columns, or original if pivot fails
    """
    time_col = find_time_column(df)
    value_col = find_value_column(df)

    if not time_col or not value_col:
        print(f"Pivot skipped: time_col={time_col}, value_col={value_col}")
        return df

    # Check if we have enough time periods to make pivoting worthwhile
    unique_times = df[time_col].nunique()
    if unique_times < 2:
        print(f"Pivot skipped: only {unique_times} unique time period(s)")
        return df

    # Identify dimension columns (everything except time and value)
    dimension_cols = [col for col in df.columns if col not in [time_col, value_col]]

    if not dimension_cols:
        print("Pivot skipped: no dimension columns found")
        return df

    try:
        # Ensure value column is numeric
        df[value_col] = pd.to_numeric(df[value_col], errors='coerce')

        # Create pivot table
        pivoted = df.pivot_table(
            index=dimension_cols,
            columns=time_col,
            values=value_col,
            aggfunc=aggfunc
        ).reset_index()

        # Flatten column names if they're multi-level
        if hasattr(pivoted.columns, 'levels'):
            pivoted.columns = [str(col) if not isinstance(col, tuple) else str(col[-1])
                              for col in pivoted.columns]

        # Convert ALL column names to strings and clean up format
        new_cols = []
        for col in pivoted.columns:
            col_str = str(col)  # Ensure it's a string first
            # Clean up numeric-looking column names (e.g., "2021.0" → "2021")
            if col_str.replace('.', '').replace('-', '').isdigit():
                if '.' in col_str:
                    col_str = col_str.split('.')[0]
            new_cols.append(col_str)
        pivoted.columns = new_cols

        original_rows = len(df)
        pivoted_rows = len(pivoted)
        reduction = ((original_rows - pivoted_rows) / original_rows * 100) if original_rows > 0 else 0

        print(f"Pivot: {original_rows} rows → {pivoted_rows} rows ({reduction:.1f}% reduction)")
        print(f"Time periods as columns: {unique_times} years")

        return pivoted

    except Exception as e:
        print(f"Pivot failed: {str(e)}")
        return df


def optimize_dataframe_for_analysis(df, user_question, client=None, use_ai_selection=True, max_columns=12, pivot_by_time=True):
    """
    Apply all optimization steps to reduce dataframe size before AI analysis.

    Steps:
    1. Drop hardcoded unhelpful columns (STRUCTURE_NAME, STRUCTURE_ID, STRUCTURE)
    2. Drop SDMX ID columns (dataset IDs, agency codes)
    3. Drop columns with only 1 unique value
    4. Drop redundant uppercase ID columns (keep text descriptions)
    5. Drop country columns if only one country is present
    6. Optionally use AI to select only relevant columns
    7. Pivot dataframe so time periods become columns (reduces rows significantly)
    8. Limit columns (prioritizes descriptive text columns over IDs)

    Args:
        df: The pandas DataFrame to optimize
        user_question: The user's original question (for AI relevance filtering)
        client: Anthropic client (optional, needed for AI selection)
        use_ai_selection: Whether to use AI to filter columns (default True)
        max_columns: Maximum number of columns to keep (default 12, prioritizes descriptive cols)
        pivot_by_time: Whether to pivot time periods into columns (default True)

    Returns:
        Optimized DataFrame with reduced columns and rows
    """
    original_cols = len(df.columns)
    original_rows = len(df)

    # Step 1: Drop hardcoded columns
    df = drop_hardcoded_columns(df)

    # Step 2: Drop SDMX ID columns (dataset IDs, agency codes)
    df = drop_sdmx_id_columns(df)

    # Step 3: Drop single-value columns
    df = drop_single_value_columns(df)

    # Step 4: Drop redundant uppercase columns (keep text descriptions)
    df = drop_redundant_columns(df)

    # Step 5: Drop country columns if only one country
    df = drop_single_country_columns(df)

    # Step 6: AI-powered column selection (optional) - do BEFORE pivot
    if use_ai_selection and client is not None:
        relevant_cols = ai_select_relevant_columns(df, user_question, client)
        df = df[relevant_cols]

    # Step 7: Pivot by time period (makes years into columns)
    if pivot_by_time:
        df = pivot_dataframe_by_time(df)

    # Step 8: Ensure columns are under the limit
    if len(df.columns) > max_columns:
        df = limit_columns(df, max_columns)

    # Log optimization results
    optimized_cols = len(df.columns)
    optimized_rows = len(df)
    col_reduction = ((original_cols - optimized_cols) / original_cols * 100) if original_cols > 0 else 0
    row_reduction = ((original_rows - optimized_rows) / original_rows * 100) if original_rows > 0 else 0

    print(f"DataFrame optimization: {original_cols} cols → {optimized_cols} cols ({col_reduction:.1f}% reduction)")
    print(f"DataFrame optimization: {original_rows} rows → {optimized_rows} rows ({row_reduction:.1f}% reduction)")

    return df


def estimate_tokens(text):
    """
    Estimate the number of tokens in a text string.
    Uses a rough approximation: ~4 characters per token for English text.
    For structured data like CSVs, it's closer to ~3 characters per token.
    """
    if not text:
        return 0
    # Use 3.5 chars/token as a middle ground for CSV data
    return len(text) / 3.5


def estimate_dataframe_tokens(df):
    """
    Estimate tokens for a dataframe when converted to string.
    Returns estimated token count.
    """
    df_string = df.to_string(index=False)
    return estimate_tokens(df_string), len(df_string)


def format_token_cost(tokens, cost_per_million=3.0):
    """
    Format token count with estimated cost.
    Default cost is $3/million tokens (Claude Sonnet input pricing).
    """
    cost = (tokens / 1_000_000) * cost_per_million
    return f"{int(tokens):,} tokens (~${cost:.4f})"


def generate_query_folder_name(user_question):
    """
    Generate a clean folder name from user question.
    Format: Countries_Topic_StartYear_EndYear_MMDD

    Examples:
    - "What did US spend on ODA in 2022 to 2025?" → "US_ODA_2022_2025_0208"
    - "Compare Canada and US GDP" → "CAN&US_GDP_0208"
    - "Australia healthcare from 2020 to 2024" → "AUS_Healthcare_2020_2024_0208"
    """
    import re
    from datetime import datetime

    # Common country names to extract
    country_map = {
        'united states': 'US', 'america': 'US', 'usa': 'US', 'us': 'US',
        'canada': 'CAN', 'can': 'CAN',
        'united kingdom': 'UK', 'britain': 'UK', 'uk': 'UK',
        'germany': 'DEU', 'deutschland': 'DEU',
        'france': 'FRA',
        'japan': 'JPN',
        'australia': 'AUS', 'aus': 'AUS',
        'mexico': 'MEX',
        'china': 'CHN',
        'india': 'IND',
        'italy': 'ITA',
        'spain': 'ESP',
        'korea': 'KOR', 'south korea': 'KOR',
        'brazil': 'BRA',
        'netherlands': 'NLD',
        'sweden': 'SWE',
        'norway': 'NOR',
        'denmark': 'DNK',
        'finland': 'FIN',
        'switzerland': 'CHE',
        'new zealand': 'NZL'
    }

    # Extract countries
    question_lower = user_question.lower()
    found_countries = []
    for country_name, short_name in country_map.items():
        if country_name in question_lower:
            if short_name not in found_countries:
                found_countries.append(short_name)

    # Extract years (4-digit numbers)
    years = re.findall(r'\b(20\d{2})\b', user_question)

    # Extract key topic words (remove common words)
    stopwords = {'what', 'did', 'the', 'in', 'on', 'for', 'is', 'are', 'show', 'me', 'data',
                 'about', 'from', 'to', 'and', 'or', 'of', 'a', 'an', 'how', 'much', 'many',
                 'have', 'compare', 'between', 'trends', 'trend', 'over', 'time', 'years'}
    words = re.findall(r'\b[a-z]+\b', question_lower)
    # Get topic words, excluding country names
    country_words = set(country_map.keys())
    topic_words = [w.capitalize() for w in words
                   if w not in stopwords and w not in country_words and len(w) > 2][:2]

    # Build folder name: Countries_Topic_Years_MMDD
    parts = []

    # 1. Countries first (joined with &) - limit to 3
    if found_countries:
        countries_str = "&".join(found_countries[:3])
        parts.append(countries_str)

    # 2. Topic description
    if topic_words:
        parts.append("_".join(topic_words))

    # 3. Time period (year range)
    if years:
        unique_years = sorted(set(years))
        if len(unique_years) == 1:
            parts.append(unique_years[0])
        elif len(unique_years) >= 2:
            parts.append(f"{unique_years[0]}_{unique_years[-1]}")

    # 4. Date as MMDD
    timestamp = datetime.now().strftime("%m%d")
    parts.append(timestamp)

    # Join with underscore and sanitize
    folder_name = "_".join(parts) if parts else f"Query_{timestamp}"

    # Remove any problematic characters (keep & for countries)
    folder_name = re.sub(r'[<>:"/\\|?*]', '', folder_name)

    # Limit length
    if len(folder_name) > 60:
        folder_name = folder_name[:60].rstrip('_')

    return folder_name

def create_query_folder(folder_name, base_dir="outputs"):
    """
    Create query folder and return path.

    Args:
        folder_name: Name of the query folder
        base_dir: Base directory for outputs (default: "outputs")

    Returns:
        Full path to created folder
    """
    folder_path = os.path.join(base_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

def update_summary_file(query_folder, user_question, dataset_info=None, analysis_result=None, conversation_history=None):
    """
    Create or update summary.txt file in query folder.

    Args:
        query_folder: Path to query folder
        user_question: Original user question
        dataset_info: Dict with dataset download info (optional)
        analysis_result: AI analysis result (optional)
        conversation_history: List of conversation messages (optional)
    """
    summary_path = os.path.join(query_folder, "summary.txt")

    # Check if file exists
    file_exists = os.path.exists(summary_path)

    with open(summary_path, 'a', encoding='utf-8') as f:
        if not file_exists:
            # Create new summary file
            f.write("=" * 80 + "\n")
            f.write("OECD DATA RESEARCH QUERY SUMMARY\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Query: {user_question}\n")
            f.write("\n" + "-" * 80 + "\n\n")

        # Add dataset info if provided
        if dataset_info:
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"DATASET DOWNLOADED: {dataset_info['dataset_id']}\n")
            f.write("=" * 80 + "\n")
            f.write(f"Name: {dataset_info['name']}\n")
            f.write(f"Category: {dataset_info['category']}\n")
            f.write(f"File: {dataset_info['filename']}\n")
            f.write(f"Rows: {dataset_info['rows']:,}\n")
            f.write(f"Download Time: {dataset_info['timestamp']}\n\n")
            f.write(f"API URL:\n{dataset_info['api_url']}\n")
            f.write("\n" + "-" * 80 + "\n")

        # Add analysis result if provided
        if analysis_result:
            f.write("\n" + "=" * 80 + "\n")
            f.write("AI ANALYSIS\n")
            f.write("=" * 80 + "\n")
            f.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"{analysis_result}\n")
            f.write("\n" + "-" * 80 + "\n")

        # Add conversation history if provided (only once, at the end)
        if conversation_history:
            f.write("\n" + "=" * 80 + "\n")
            f.write("CONVERSATION HISTORY\n")
            f.write("=" * 80 + "\n\n")
            for msg in conversation_history:
                role = msg['role'].upper()
                content = msg['content']
                f.write(f"{role}:\n{content}\n\n")
            f.write("-" * 80 + "\n")

def ai_librarian_analyst(query_folder, user_question, client):
    """
    Analyze downloaded CSV data and answer the user's original question.

    Args:
        query_folder: Path to folder containing CSVs
        user_question: Original user question
        client: Anthropic client

    Returns:
        Tuple of (analysis_result, stats_dict) where stats_dict contains:
        - total_rows: Total rows across all CSVs
        - total_cols: Total columns after optimization
        - char_count: Character count of data
        - estimated_tokens: Estimated token count
        - token_cost_str: Formatted token cost string
    """
    # Find all CSV files in the query folder
    csv_files = [f for f in os.listdir(query_folder) if f.endswith('.csv')]

    if not csv_files:
        return "No CSV files found in the query folder. Please download datasets first.", None

    # Read and prepare CSV data
    csv_data_summary = []
    optimization_report = []

    total_original_rows = 0
    total_optimized_rows = 0

    for csv_file in csv_files:
        csv_path = os.path.join(query_folder, csv_file)

        try:
            # Read the full CSV
            df = pd.read_csv(csv_path)
            original_shape = df.shape
            total_original_rows += original_shape[0]

            # Optimize the dataframe to reduce token usage (includes pivoting)
            df = optimize_dataframe_for_analysis(
                df,
                user_question,
                client=client,
                use_ai_selection=True,
                pivot_by_time=True
            )
            optimized_shape = df.shape
            total_optimized_rows += optimized_shape[0]

            # Track optimization stats
            cols_removed = original_shape[1] - optimized_shape[1]
            rows_reduced = original_shape[0] - optimized_shape[0]
            optimization_report.append(
                f"- {csv_file}: {original_shape[0]:,} → {optimized_shape[0]:,} rows "
                f"({rows_reduced:,} reduced), {original_shape[1]} → {optimized_shape[1]} cols"
            )

            # Save processed dataframe to output folder
            processed_filename = f"processed_{csv_file}"
            processed_path = os.path.join(query_folder, processed_filename)
            df.to_csv(processed_path, index=False)
            print(f"Saved processed dataframe: {processed_path}")

            # Convert optimized dataframe to string
            df_string = df.to_string(index=False)

            # Create file summary with column info for context
            # Convert all column names to strings (years become ints after pivot)
            columns_kept = ", ".join([str(col) for col in df.columns.tolist()])
            file_summary = f"""
                FILE: {csv_file}
                ROWS: {len(df):,}
                COLUMNS: {len(df.columns)} (optimized from {original_shape[1]})
                COLUMNS KEPT: {columns_kept}

                DATA:
                {df_string}
                """
            csv_data_summary.append(file_summary)

        except Exception as e:
            csv_data_summary.append(f"FILE: {csv_file}\nERROR: Could not read file - {str(e)}")

    # Combine all CSV summaries
    combined_data = "\n\n" + "=" * 80 + "\n\n".join(csv_data_summary)

    # Build optimization report string
    optimization_info = ""
    if optimization_report:
        optimization_info = "\n".join(optimization_report)

    # Calculate and display token statistics
    total_rows = sum([int(s.split("ROWS:")[1].split("\n")[0].strip().replace(",", ""))
                      for s in csv_data_summary if "ROWS:" in s])
    total_cols = sum([int(s.split("COLUMNS:")[1].split("(")[0].strip())
                      for s in csv_data_summary if "COLUMNS:" in s])

    # Estimate tokens for the full prompt
    prompt_tokens = estimate_tokens(combined_data)
    char_count = len(combined_data)
    token_cost_str = format_token_cost(prompt_tokens)

    # Calculate row reduction percentage
    row_reduction_pct = ((total_original_rows - total_optimized_rows) / total_original_rows * 100) if total_original_rows > 0 else 0

    # Build stats dictionary
    stats = {
        "original_rows": total_original_rows,
        "total_rows": total_rows,
        "total_cols": total_cols,
        "char_count": char_count,
        "estimated_tokens": int(prompt_tokens),
        "token_cost_str": token_cost_str,
        "row_reduction_pct": row_reduction_pct,
        "optimization_report": optimization_report
    }

    # Print stats to console
    print("\n" + "=" * 60)
    print("📊 DATAFRAME ANALYSIS - PRE-SUBMISSION STATS")
    print("=" * 60)
    print(f"Original Rows: {total_original_rows:,}")
    print(f"Optimized Rows: {total_rows:,} ({row_reduction_pct:.1f}% reduction)")
    print(f"Total Columns: {total_cols}")
    print(f"Character Count: {char_count:,}")
    print(f"Estimated Tokens: {token_cost_str}")
    print("=" * 60 + "\n")

    # Check row limit - don't send datasets larger than 20K rows
    MAX_ROWS = 20000
    if total_rows > MAX_ROWS:
        friendly_msg = f"""📊 **Dataset too large for analysis**

The optimized dataset still contains {total_rows:,} rows, which exceeds the {MAX_ROWS:,} row limit for AI analysis.

**Suggestions to reduce the dataset size:**
- Select fewer countries (try 1-3 specific countries instead of "All countries")
- Choose a shorter time period
- Apply more specific filters when downloading

The raw data has been saved to your output folder if you'd like to analyze it manually."""
        return friendly_msg, stats

    # Create analysis prompt
    analysis_prompt = f"""Role: You are a junior data analyst interpreting OECD data on behalf on a senior researcher.

USER QUESTION:
{user_question}

CRITICAL DATA INTERPRETATION RULES:
1. UNIT_MULT column indicates the multiplier:
   - UNIT_MULT = 6 means values are in MILLIONS (multiply displayed value by 1,000,000)
   - UNIT_MULT = 0 means values are ratios/percentages (use as-is)

2. NUMBER FORMATTING - Convert to readable billions/millions:
   - If UNIT_MULT=6 and value=15200, report as "$15.2 billion" (not "15,200 million")
   - If UNIT_MULT=6 and value=850, report as "$850 million"
   - If UNIT_MULT=0 and value=0.33, report as "0.33%" or "33%"

3. COLUMN USAGE - Use descriptive columns, NOT codes:
   - Use "Measure" or "Flow type" text values, NOT numeric codes like "1140" or "1010"
   - Use country names from "Reference area" column, NOT codes like "GBR" or "DEU"
   - If descriptive column is missing, describe what the measure represents

{optimization_info}

DATA:
{combined_data}

Format your response using the outline below:

**Data Overview**
Describe what data, time period, number of observations that were found

**Key Findings**

• [Finding with properly formatted number - e.g., "$15.2 billion" not "15200 million"]

• [Finding with properly formatted number]

• [Finding with properly formatted number]

• [Finding with properly formatted number]

**Limitations & Context**
One sentence about data caveats.

**What the Data Shows**
2-3 sentences with key insight.

Rules:
Format your response with an emphasis on clear, consise, and readable language. Below are examples that can help:

- Convert millions to billions when value >= 1000 (e.g., 15200 million = $15.2 billion)
- Use the correct currency symbol when providing values
- Never write "X million million" or "X,XXX million" - convert to billions
- Try to keep bullets SHORT

"""

    try:
        # Call Claude for analysis
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": analysis_prompt}],
            temperature=0.2
        )

        response_text = message.content[0].text

        return response_text, stats

    except Exception as e:
        error_msg = str(e).lower()
        # Provide user-friendly error messages
        if 'rate' in error_msg or 'limit' in error_msg or 'quota' in error_msg:
            friendly_msg = "⏳ The API is temporarily busy. Please wait a moment and try again."
        elif 'timeout' in error_msg or 'connection' in error_msg:
            friendly_msg = "🔌 Connection issue. Please check your internet and try again."
        else:
            friendly_msg = "📊 The analysis request couldn't be completed. Try removing some filters or selecting fewer countries to reduce the dataset size."
        return friendly_msg, stats


def render_dataset_details(category, dataset_id, dataset_meta):
    """Render dataset details and download interface"""
    
    st.markdown("---")
    st.subheader("Dataset Details")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown(f"**Name:** {dataset_meta['name']}")
        clean_desc = clean_html_description(dataset_meta['description'])
        st.markdown(f"**Description:** {clean_desc}")
    
    with col2:
        st.markdown(f"**Category:** {category}")
        st.markdown(f"**Dataset ID:** `{dataset_id}`")
        st.markdown(f"**Agency:** `{dataset_meta['agency']}`")
        st.markdown(f"**Version:** {dataset_meta.get('version', '1.0')}")
    
    # Download parameters
    st.markdown("---")
    st.subheader("Download Parameters")

    # Check if dimensions are available
    dimensions = dataset_meta.get('dimensions', [])
    dimension_values = {}
    country_filter = None
    freq = None

    if dimensions:
        # Dimension-based filtering (new method)
        st.subheader("🔍 Dimension Filters")
        st.markdown(f"This dataset has **{len(dimensions)} dimensions**. Specify values for precise data selection:")
        st.info("💡 **Tip**: Leave a dimension blank to get all values for that dimension. Use `+` to combine multiple values (e.g., `USA+CAN+MEX`).")

        # Display dimensions in a nice grid (2 per row)
        for i in range(0, len(dimensions), 2):
            cols = st.columns(2)

            for j, col in enumerate(cols):
                dim_idx = i + j
                if dim_idx < len(dimensions):
                    dim = dimensions[dim_idx]

                    with col:
                        dim_id = dim['id']
                        dim_name = dim.get('name', dim_id)
                        dim_position = dim['position']

                        # Handle special dimensions with dropdowns
                        if dim_id == 'REF_AREA':
                            # Country selection with dropdown
                            country_data = load_country_codes()
                            all_countries = {**country_data["OECD"], **country_data["Non-OECD"]}

                            # Check for pre-filled country hints from AI
                            default_countries = []
                            if "filter_hints" in st.session_state and "countries" in st.session_state.filter_hints:
                                # Convert country codes to country names for the multiselect
                                code_to_name = {v: k for k, v in all_countries.items()}
                                for code in st.session_state.filter_hints["countries"]:
                                    if code in code_to_name:
                                        default_countries.append(code_to_name[code])

                            selected_countries = st.multiselect(
                                f"**Position {dim_position}**: {dim_name}",
                                options=["[All Countries]"] + sorted(all_countries.keys()),
                                default=default_countries,
                                key=f"dim_{dataset_id}_{dim_id}",
                                help=f"Select one or more countries. Leave empty or select '[All Countries]' for all."
                            )

                            # Convert to API format (country codes joined by +)
                            if not selected_countries or "[All Countries]" in selected_countries:
                                value = ""
                            else:
                                codes = [all_countries[name] for name in selected_countries]
                                value = "+".join(codes)

                            dimension_values[dim_position] = value

                        elif dim_id == 'FREQ':
                            # Frequency selection with dropdown
                            freq_options = {
                                "[All Frequencies]": "",
                                "Annual": "A",
                                "Quarterly": "Q",
                                "Monthly": "M"
                            }

                            selected_freq = st.selectbox(
                                f"**Position {dim_position}**: {dim_name}",
                                options=list(freq_options.keys()),
                                key=f"dim_{dataset_id}_{dim_id}",
                                help="Select data frequency"
                            )

                            value = freq_options[selected_freq]
                            dimension_values[dim_position] = value

                        else:
                            # Other dimensions use text input
                            common_hints = {
                                'TIME_PERIOD': 'Usually handled by start/end date filters',
                                'MEASURE': 'Measure code - check dataset documentation',
                                'UNIT_MEASURE': 'Unit of measurement - check dataset documentation'
                            }

                            placeholder = common_hints.get(dim_id, "Leave blank for all values")
                            help_text = f"**Dimension ID**: `{dim_id}`\n**Position**: {dim_position}\n\nLeave blank to include all values, or specify one or more codes separated by `+`"

                            value = st.text_input(
                                f"**Position {dim_position}**: {dim_name}",
                                value="",
                                key=f"dim_{dataset_id}_{dim_id}",
                                placeholder=placeholder,
                                help=help_text
                            )

                            dimension_values[dim_position] = value

        st.markdown("---")

    else:
        # Legacy filtering (old method for datasets without dimensions)
        st.warning("⚠️ Dimensions not available for this dataset. Using legacy filter mode.")

        # Country selection
        st.markdown("**Country Filter**")
        country_data = load_country_codes()

        # Check for pre-filled country hints from AI
        default_country_option = "All countries"
        default_selected_names = []

        if "filter_hints" in st.session_state and "countries" in st.session_state.filter_hints:
            # AI suggested specific countries - pre-select them
            default_country_option = "Specific countries"
            all_countries = {**country_data["OECD"], **country_data["Non-OECD"]}
            code_to_name = {v: k for k, v in all_countries.items()}

            for code in st.session_state.filter_hints["countries"]:
                if code in code_to_name:
                    default_selected_names.append(code_to_name[code])

        country_option = st.radio(
            "Select countries:",
            options=["All countries", "OECD countries only", "Non-OECD countries only", "Specific countries"],
            index=["All countries", "OECD countries only", "Non-OECD countries only", "Specific countries"].index(default_country_option),
            key=f"country_opt_{dataset_id}",
            horizontal=True
        )

        selected_countries = []
        if country_option == "OECD countries only":
            selected_countries = list(country_data["OECD"].values())
            st.info(f"📍 Will fetch data for {len(selected_countries)} OECD member countries")
        elif country_option == "Non-OECD countries only":
            selected_countries = list(country_data["Non-OECD"].values())
            st.info(f"📍 Will fetch data for {len(selected_countries)} non-OECD countries and groups")
        elif country_option == "Specific countries":
            # Combine all countries for selection
            all_countries = {**country_data["OECD"], **country_data["Non-OECD"]}
            country_names = sorted(all_countries.keys())

            selected_names = st.multiselect(
                "Choose countries:",
                options=country_names,
                default=default_selected_names,  # PRE-FILLED from AI hints
                key=f"countries_{dataset_id}",
                help="Select one or more countries"
            )
            selected_countries = [all_countries[name] for name in selected_names]

            if selected_countries:
                st.info(f"📍 Selected: {', '.join(selected_names)}")
        else:
            st.info("📍 Will fetch data for all available countries")

        # Convert list to URL format (joined by +)
        country_filter = "+".join(selected_countries) if selected_countries else None

        st.markdown("---")

        # Checkbox to enable frequency filter
        use_freq = st.checkbox(
            "Filter by frequency (optional - not all datasets support this)",
            value=False,
            key=f"use_freq_{dataset_id}",
            help="Some datasets don't support frequency filtering. Leave unchecked if download fails."
        )

    # Time period selection (shown for both dimension and legacy modes)
    col1, col2, col3 = st.columns(3)

    with col1:
        # Only show frequency filter in legacy mode
        if not dimensions:
            if use_freq:
                freq_options = [None, "A", "Q", "M"]
                freq_labels = {None: "All frequencies", "A": "Annual", "Q": "Quarterly", "M": "Monthly"}
                freq = st.selectbox(
                    "Frequency:",
                    options=freq_options,
                    format_func=lambda x: freq_labels[x],
                    index=0,  # Default to "All frequencies"
                    key=f"freq_{dataset_id}"
                )
            else:
                freq = None
                st.info("Frequency filter disabled")
        else:
            st.info("💡 Use dimensions above to filter data")

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
    
    # Download button
    st.markdown("---")

    # Show preview of what will be queried (for both dimension and legacy modes)
    st.markdown("**🔍 API Query Preview**")

    if dimensions and dimension_values:
        # Dimension-based preview
        sorted_positions = sorted(dimension_values.keys())
        dim_parts = [dimension_values[pos] if dimension_values[pos] else "[all]" for pos in sorted_positions]
        preview_filter = ".".join(dim_parts)

        # Build full URL for dimension mode
        BASE_URL = "https://sdmx.oecd.org/public/rest/data"
        agency = dataset_meta['agency']
        version = dataset_meta.get('version', '1.0')
        full_url = (
            f"{BASE_URL}/{agency},{dataset_id},{version}/"
            f"{preview_filter}?"
            f"startPeriod={start_date}&endPeriod={end_date}"
            f"&dimensionAtObservation=AllDimensions&format=csvfile"
        )

        st.code(
            f"Data selection: {preview_filter}\n"
            f"Time period: {start_date} to {end_date}\n"
            f"Format: CSV\n\n"
            f"Full API URL:\n{full_url}",
            language="text"
        )
    else:
        # Legacy mode preview
        country_param = country_filter if country_filter else ""
        freq_param = freq if freq else ""
        legacy_filter = f"{country_param}.{freq_param}......"

        # Build full URL for legacy mode
        BASE_URL = "https://sdmx.oecd.org/public/rest/data"
        agency = dataset_meta['agency']
        version = dataset_meta.get('version', '1.0')
        full_url = (
            f"{BASE_URL}/{agency},{dataset_id},{version}/"
            f"{legacy_filter}?"
            f"startPeriod={start_date}&endPeriod={end_date}"
            f"&dimensionAtObservation=AllDimensions&format=csvfile"
        )

        st.code(
            f"Countries: {country_filter if country_filter else '[all]'}\n"
            f"Frequency: {freq if freq else '[all]'}\n"
            f"Time period: {start_date} to {end_date}\n"
            f"Format: CSV\n\n"
            f"Full API URL:\n{full_url}",
            language="text"
        )

    if st.button("📥 Download Dataset", type="primary", use_container_width=True, key=f"download_{dataset_id}"):
        # Check if user has exceeded rate limit
        if st.session_state.api_counter >= 60:
            st.error("⚠️ API rate limit reached (60 requests/hour). Please wait for the counter to reset.")
            remaining = st.session_state.api_counter_reset_time - datetime.now()
            minutes = int(remaining.total_seconds() / 60)
            st.info(f"⏳ Counter resets in {minutes} minutes")
        else:
            with st.spinner("Fetching data from OECD API..."):
                try:
                    # Ensure query folder exists
                    if "current_query" not in st.session_state or not st.session_state.current_query:
                        # Initialize query if not exists - find the LAST USER message, not the last message
                        user_question = "Data Query"
                        if st.session_state.messages:
                            # Find the most recent user message
                            for msg in reversed(st.session_state.messages):
                                if msg.get("role") == "user":
                                    user_question = msg["content"]
                                    break
                        folder_name = generate_query_folder_name(user_question)

                        # Use custom base directory from settings
                        base_dir = st.session_state.get("output_base_dir", "outputs")
                        folder_path = create_query_folder(folder_name, base_dir)

                        st.session_state.current_query = {
                            "question": user_question,
                            "folder_name": folder_name,
                            "folder_path": folder_path,
                            "datasets": []
                        }

                        # Initialize summary file
                        update_summary_file(folder_path, user_question)

                    # Get query folder
                    query_folder = st.session_state.current_query["folder_path"]

                    # Modify fetcher to use query folder
                    fetcher = OECDDataFetcher(output_dir=query_folder)

                    # Increment API counter BEFORE making the request
                    increment_api_counter()

                    # Build dimension filter string from user inputs
                    dim_filter = None
                    filter_str = "all"

                    # Debug output (to terminal)
                    print(f"DEBUG: dimensions={len(dimensions) if dimensions else 0}, dimension_values={dimension_values}, country_filter={country_filter}")

                    if dimension_values:
                        # Sort dimensions by position and create dot-separated string
                        sorted_positions = sorted(dimension_values.keys())
                        dim_parts = [dimension_values[pos] for pos in sorted_positions]
                        dim_filter = ".".join(dim_parts)
                        filter_str = dim_filter

                        # Check if filter has any actual values (not all empty)
                        has_values = any(part.strip() for part in dim_parts)
                        if not has_values:
                            dim_filter = None  # Use 'all' if no values specified
                            filter_str = "all"

                        print(f"DEBUG: Built dim_filter={dim_filter}, has_values={has_values}")

                    # Build API URL for summary
                    BASE_URL = "https://sdmx.oecd.org/public/rest/data"
                    agency = dataset_meta['agency']
                    version = dataset_meta.get('version', '1.0')

                    api_url = (
                        f"{BASE_URL}/{agency},{dataset_id},{version}/"
                        f"{filter_str}?"
                        f"startPeriod={start_date}&endPeriod={end_date}"
                        f"&dimensionAtObservation=AllDimensions&format=csvfile"
                    )

                    # Show what filter is being applied
                    if dim_filter:
                        st.caption(f"🔍 API Filter: `{dim_filter}`")
                    elif country_filter:
                        st.caption(f"🔍 Post-download filter: countries={country_filter}")
                    else:
                        st.caption("🔍 No filter applied - fetching all data")

                    # Call the API (with dimension count validation if available)
                    expected_dims = dataset_meta.get('dimension_count', None)

                    # Determine what to pass for countries/freq
                    # In legacy mode (no dimensions), use country_filter for post-download filtering
                    countries_param = country_filter if not dimensions else None
                    freq_param = freq if not dimensions else None
                    print(f"DEBUG: Passing to get_dataset: dim_filter={dim_filter}, countries={countries_param}, freq={freq_param}")

                    df = fetcher.get_dataset(
                        agency=dataset_meta['agency'],
                        dataset_id=dataset_id,
                        version=dataset_meta.get('version', '1.0'),
                        dimension_filter=dim_filter,
                        countries=countries_param,
                        freq=freq_param,
                        start_date=start_date,
                        end_date=end_date,
                        save_csv=True,
                        expected_dimensions=expected_dims
                    )

                    # Build filename - extract country info from dimension values or legacy filter
                    country_suffix = ""
                    countries_used = None

                    # Check dimension-aware mode first (REF_AREA in dimensions)
                    if dimensions and dimension_values:
                        for dim in dimensions:
                            if dim.get('id') == 'REF_AREA':
                                pos = dim.get('position')
                                if pos is not None and pos in dimension_values and dimension_values[pos]:
                                    countries_used = dimension_values[pos]
                                    break

                    # Fall back to legacy country filter
                    if not countries_used and country_filter:
                        countries_used = country_filter

                    if countries_used:
                        country_count = len(countries_used.split("+"))
                        if country_count <= 3:
                            country_suffix = f"_{countries_used.replace('+', '_')}"
                        else:
                            country_suffix = f"_{country_count}countries"

                    filename = f"{dataset_id.replace('@', '_')}{country_suffix}_{start_date}_{end_date}.csv"

                    # Track dataset in session state
                    dataset_record = {
                        "dataset_id": dataset_id,
                        "name": dataset_meta['name'],
                        "category": category,
                        "filename": filename,
                        "rows": len(df),
                        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        "api_url": api_url
                    }
                    st.session_state.current_query["datasets"].append(dataset_record)

                    # Update summary file with dataset info
                    update_summary_file(query_folder, st.session_state.current_query["question"], dataset_info=dataset_record)

                    # Success message
                    st.success(f"✅ Successfully downloaded {len(df)} rows!")
                    st.info(f"📊 API requests used: {st.session_state.api_counter}/60")
                    st.info(f"📁 Saved to folder: `{st.session_state.current_query['folder_name']}`")

                    # Show preview
                    st.subheader("Data Preview")
                    st.dataframe(df.head(20), use_container_width=True)

                    # Show stats
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Rows", f"{len(df):,}")
                    with col2:
                        st.metric("Columns", len(df.columns))
                    with col3:
                        st.metric("File Saved", filename)

                    st.info(f"💾 CSV file saved to: `{query_folder}/{filename}`")

                except Exception as e:
                    st.error(f"❌ Error downloading data: {str(e)}")
                    st.warning("""
                    **Possible reasons:**
                    - The dataset might not have data for the selected countries
                    - The dataset might not support the selected frequency (try disabling frequency filter)
                    - The date range might be invalid or no data exists for those years
                    - The OECD API might be temporarily unavailable
                    - The dataset structure might not match the filter combination

                    **Tip**: Try using "All countries" and disabling frequency filter first.
                    """)
                    with st.expander("Show full error details"):
                        st.exception(e)

# Initialize API request counter
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

def increment_api_counter():
    """Increment the API request counter."""
    st.session_state.api_counter += 1

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

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.metric(
            label=f"{color} API Requests (OECD Limit: 60/hour)",
            value=f"{count} / {limit}",
            delta=f"Resets in {minutes_remaining} min"
        )
    with col2:
        st.metric("Status", status)
    with col3:
        if st.button("🔄 Reset Counter", help="Manually reset the counter (use if you've waited an hour)"):
            st.session_state.api_counter = 0
            from datetime import datetime, timedelta
            st.session_state.api_counter_reset_time = datetime.now() + timedelta(hours=1)
            st.rerun()

# Main app
def main():
    # Initialize API counter
    init_api_counter()

    st.title("📊 OECD Data Explorer")
    st.caption("Download datasets from OECD and get AI-powered statistical summaries")
    st.markdown("---")

    # Load catalog
    catalog = load_catalog()

    # Create tabs
    tab1, tab2 = st.tabs(["🤖 Ask & Analyse", "📚 Browse Datasets"])

    # ========== TAB 1: AI LIBRARIAN ==========
    with tab1:
        st.markdown("### What data are you looking for?")
        st.markdown("Describe your question and I'll help you find, download, and analyze the relevant OECD datasets.")

        # Initialize chat history and dataset IDs in session state
        if "messages" not in st.session_state:
            st.session_state.messages = []
        if "current_dataset_ids" not in st.session_state:
            st.session_state.current_dataset_ids = []
        if "filter_hints" not in st.session_state:
            st.session_state.filter_hints = {}
        if "current_query" not in st.session_state:
            st.session_state.current_query = None
        if "output_base_dir" not in st.session_state:
            st.session_state.output_base_dir = "outputs"

        # Show welcome message and instructions if chat is empty
        if len(st.session_state.messages) == 0:
            st.markdown("### 👋 Welcome!")

            st.info("""
            **This tool downloads datasets from the OECD database and reads statistical summaries from them.**

            Ask a question → Download the data → Get AI-powered insights with specific numbers.
            """)

            # Instructions
            with st.expander("📖 How It Works", expanded=True):
                st.markdown("""
                ### Three Simple Steps

                1. Ask Your Question 🤔
                - Describe what data you need and what question you're trying to answer. Be specifc in your query (countries, time periods, metrics). This will help the AI recommend the right datasets and filters.
                - Examples:
                  - "US healthcare and ODA spending in 2023"
                  - "Compare youth unemployment in Canada and UK from 2020-2024"
                  - "GDP growth in Japan and Germany"

                2. Download Data 📥
                - The AI will recommend relevant datasets from the OECD datasets
                - Click "Download Dataset" to export the data as CSV files to your selected folder

                3. Analyse 🔬
                - Click "Analyze Data" to get insights
                - I'll read the data and answer your question with specific numbers
                - Results are saved to your output folder

                ---

                ### Tips for Best Results
                - Be specific: mention countries and time periods
                - Select 1-3 countries and smaller time frames for faster analysis (avoid do "All countries")
                - If the download fails, try again by removing all the filters

                ⚠️ *AI analysis is a helpful starting point but always verify important findings.*
                """)

            # Quick start examples
            with st.expander("💡 Quick Start Examples", expanded=False):
                st.markdown("""
                **Click any example to try it:**

                **Economic Data:**
                - "What was the GDP of France in 2023?"
                - "Compare inflation rates in US, UK, and Canada since 2020"

                **Social Data:**
                - "Show me youth unemployment rates in Australia for 2024"
                - "What did Germany spend on healthcare in 2022?"

                **Government Data:**
                - "US military spending from 2020 to 2024"
                - "Compare public education spending in Japan and Korea"

                **Just ask your question below!** ⬇️
                """)

        # Sidebar: Folder location selector
        with st.sidebar:
            st.markdown("### ⚙️ Settings")

            st.markdown("**Output Folder Location**")

            # Option to use default or custom folder
            folder_option = st.radio(
                "Choose folder location:",
                ["Default (outputs/)", "Custom folder"],
                key="folder_option",
                help="Select where query folders will be saved"
            )

            if folder_option == "Custom folder":
                # Initialize selected path in session state if not exists
                if "selected_folder_path" not in st.session_state:
                    st.session_state.selected_folder_path = ""

                # Button to open folder picker
                if st.button("📂 Browse for Folder", use_container_width=True):
                    try:
                        # Open folder dialog using subprocess (avoids threading issues on macOS)
                        selected_path = open_folder_dialog_subprocess()

                        # Store selected path
                        if selected_path:
                            st.session_state.selected_folder_path = selected_path
                            st.rerun()

                    except Exception as e:
                        st.error(f"❌ Error opening folder picker: {str(e)}")
                        st.info("💡 You can manually enter the path below as a fallback.")

                # Show selected path or allow manual entry
                if st.session_state.selected_folder_path:
                    st.text_input(
                        "Selected path:",
                        value=st.session_state.selected_folder_path,
                        key="display_selected_path",
                        disabled=True,
                        help="Path selected from folder browser"
                    )

                    # Button to confirm and set the folder
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        if st.button("✅ Use This Folder", type="primary", use_container_width=True):
                            try:
                                # Create directory if it doesn't exist
                                os.makedirs(st.session_state.selected_folder_path, exist_ok=True)
                                st.session_state.output_base_dir = st.session_state.selected_folder_path
                                st.success("✅ Folder set!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error: {str(e)}")

                    with col2:
                        if st.button("🔄 Choose Different", use_container_width=True):
                            st.session_state.selected_folder_path = ""
                            st.rerun()

                else:
                    st.caption("Click 'Browse for Folder' to select a location using your file explorer.")

                    # Fallback manual entry
                    with st.expander("⌨️ Or enter path manually", expanded=False):
                        manual_path = st.text_input(
                            "Folder path:",
                            key="manual_folder_input",
                            placeholder="/path/to/your/folder",
                            help="Enter absolute path to folder"
                        )
                        if manual_path and st.button("Set Manual Path", type="secondary"):
                            try:
                                os.makedirs(manual_path, exist_ok=True)
                                st.session_state.output_base_dir = manual_path
                                st.session_state.selected_folder_path = manual_path
                                st.success("✅ Folder set!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Invalid path: {str(e)}")

            else:
                st.session_state.output_base_dir = "outputs"

            # Show current location
            st.info(f"📁 Current location:\n`{st.session_state.output_base_dir}`")

            st.markdown("---")

        # Display chat history (strip internal hints from display)
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                # Remove FILTER_HINTS comments before displaying
                display_content = message["content"]
                display_content = re.sub(r'<!--\s*FILTER_HINTS:[^>]+-->\s*', '', display_content)
                st.markdown(display_content.strip())
        
        # Chat input
        if prompt := st.chat_input("Ask me anything about OECD data... (e.g., 'What data do you have on healthcare spending?')"):

            # PRE-QUERY VALIDATION: Check if user mentioned specific dataset IDs
            mentioned_ids = extract_dataset_ids_from_query(prompt)

            # Validate mentioned IDs
            if mentioned_ids:
                valid_mentioned, invalid_mentioned = validate_dataset_ids(mentioned_ids, catalog)

                # If user mentioned invalid dataset IDs, show error immediately
                if invalid_mentioned:
                    with st.chat_message("assistant"):
                        st.error(f"⚠️ Dataset not found: {', '.join(invalid_mentioned)}")
                        st.markdown(f"The dataset ID(s) you mentioned don't exist in the OECD catalog. Please check the ID and try again, or describe what data you're looking for and I'll help you find the right dataset.")

                    # Add to chat history
                    st.session_state.messages.append({"role": "user", "content": prompt})
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"⚠️ Dataset not found: {', '.join(invalid_mentioned)}. The dataset ID(s) you mentioned don't exist in the OECD catalog."
                    })
                    st.rerun()

            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": prompt})

            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)

            # Get AI response
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    client = anthropic_client()
                    # Pass full conversation history for multi-turn context
                    response = ask_ai_librarian(prompt, catalog, client,
                                              conversation_history=st.session_state.messages)
                    st.markdown(response)

            # Add assistant response to chat history
            st.session_state.messages.append({"role": "assistant", "content": response})

            # Extract dataset IDs from response
            dataset_ids = extract_dataset_ids(response)

            if dataset_ids:
                # Validate dataset IDs against catalog
                valid_ids, invalid_ids = validate_dataset_ids(dataset_ids, catalog)

                # Store only valid IDs
                if valid_ids:
                    st.session_state.current_dataset_ids = valid_ids

                    # Extract filter hints (countries, time periods, etc.)
                    filter_hints = extract_filter_hints(response)
                    if filter_hints:
                        st.session_state.filter_hints = filter_hints

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

                # Warn about invalid IDs
                if invalid_ids:
                    st.warning(f"⚠️ The AI suggested {len(invalid_ids)} dataset(s) that don't exist in our catalog: {', '.join(invalid_ids)}")

                # If ALL IDs were invalid, ask AI to try again
                if invalid_ids and not valid_ids:
                    st.error("❌ All suggested datasets were invalid. Let me search again...")

                    # Automatically retry with correction (shortened to save tokens)
                    correction_prompt = f"Dataset IDs {', '.join(invalid_ids)} don't exist. Search catalog again for valid exact IDs. Include filter hints if countries/time periods were mentioned."

                    # Add correction to conversation
                    st.session_state.messages.append({"role": "user", "content": correction_prompt})

                    # Get new response
                    with st.spinner("Searching for valid datasets..."):
                        retry_response = ask_ai_librarian(correction_prompt, catalog, client,
                                                         conversation_history=st.session_state.messages)

                        # Add to chat
                        st.session_state.messages.append({"role": "assistant", "content": retry_response})

                        # Extract and validate again
                        retry_ids = extract_dataset_ids(retry_response)
                        if retry_ids:
                            valid_retry_ids, invalid_retry_ids = validate_dataset_ids(retry_ids, catalog)
                            if valid_retry_ids:
                                st.session_state.current_dataset_ids = valid_retry_ids

                                # Re-extract filter hints from retry response
                                retry_filter_hints = extract_filter_hints(retry_response)
                                if retry_filter_hints:
                                    st.session_state.filter_hints = retry_filter_hints

                                st.success(f"✅ Found {len(valid_retry_ids)} valid dataset(s)!")

                st.rerun()

        # Display current dataset recommendations (persists across reruns)
        if st.session_state.current_dataset_ids:
            st.markdown("---")

            # Header with action buttons
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.markdown("### 📋 Recommended Datasets")
            with col2:
                # New Query button
                if st.button("🔄 New Query", key="new_query", help="Start a fresh query with new folder"):
                    st.session_state.current_dataset_ids = []
                    st.session_state.filter_hints = {}
                    st.session_state.current_query = None
                    st.rerun()
            with col3:
                if st.button("🗑️ Clear", key="clear_datasets"):
                    st.session_state.current_dataset_ids = []
                    st.session_state.filter_hints = {}
                    st.rerun()

            # Show count of exportable datasets
            total_datasets = len(st.session_state.current_dataset_ids)
            st.success(f"✅ **{total_datasets} dataset(s) ready for export** - Each dataset below has full export functionality")

            # DEBUG: Comprehensive debug info
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

            # Create separate sections for each dataset (not nested expanders)
            for idx, dataset_id in enumerate(st.session_state.current_dataset_ids):
                # Add visual separator between datasets
                if idx > 0:
                    st.markdown("---")

                category, metadata = find_dataset_by_id(catalog, dataset_id)

                if metadata:
                    # Expand the first dataset by default, collapse others
                    is_expanded = (idx == 0)

                    # Add number prefix to make it clear there are multiple
                    expander_label = f"[{idx + 1}/{total_datasets}] 📊 {metadata['name']} (`{dataset_id}`)"

                    with st.expander(expander_label, expanded=is_expanded):
                        # Show which dataset this is
                        st.info(f"**Dataset {idx + 1} of {total_datasets}** - This dataset is fully exportable with all controls below")

                        # Render export controls
                        render_dataset_details(category, dataset_id, metadata)

                        # Confirmation at bottom
                        st.success(f"✓ Export controls ready for dataset {idx + 1}/{total_datasets}: `{dataset_id}`")
                else:
                    st.error(f"❌ Dataset {idx + 1}/{total_datasets}: `{dataset_id}` not found in catalog")
                    st.warning(f"The AI suggested `{dataset_id}` but it doesn't exist in our current catalog.")

            # Show "Analyse Data" button if datasets have been downloaded
            if st.session_state.current_query and st.session_state.current_query.get("datasets"):
                st.markdown("---")
                num_datasets = len(st.session_state.current_query["datasets"])

                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"### 🔬 Data Analysis")
                    st.info(f"📊 **{num_datasets} dataset(s) downloaded** and ready for analysis")
                with col2:
                    if st.button("✨ Read Exports", type="primary", use_container_width=True, key="analyze_button"):
                        with st.spinner("🤖 AI analyzing your data..."):
                            client = anthropic_client()
                            query_folder = st.session_state.current_query["folder_path"]
                            question = st.session_state.current_query["question"]

                            # Call AI analyst (returns tuple of result and stats)
                            analysis_result, analysis_stats = ai_librarian_analyst(query_folder, question, client)

                            # Display token/optimization stats
                            if analysis_stats:
                                st.markdown("#### 📈 Data Optimization Stats")
                                col_a, col_b, col_c, col_d = st.columns(4)
                                with col_a:
                                    # Show row reduction with delta
                                    original = analysis_stats.get('original_rows', analysis_stats['total_rows'])
                                    optimized = analysis_stats['total_rows']
                                    delta = optimized - original if original != optimized else None
                                    st.metric("Rows", f"{optimized:,}", delta=f"{delta:,}" if delta else None)
                                with col_b:
                                    st.metric("Columns", analysis_stats['total_cols'])
                                with col_c:
                                    st.metric("Est. Tokens", f"{analysis_stats['estimated_tokens']:,}")
                                with col_d:
                                    reduction = analysis_stats.get('row_reduction_pct', 0)
                                    st.metric("Data Reduction", f"{reduction:.0f}%")

                                st.caption(f"💰 Approx. cost: {analysis_stats['token_cost_str']}")

                                # Show optimization details
                                if analysis_stats.get('optimization_report'):
                                    with st.expander("🔧 Optimization Details", expanded=False):
                                        for report_line in analysis_stats['optimization_report']:
                                            st.text(report_line)

                            # Display result in chat
                            with st.chat_message("assistant"):
                                st.markdown("### 📊 Analysis Results")
                                st.markdown(analysis_result)

                            # Add to chat history
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": f"### 📊 Analysis Results\n\n{analysis_result}"
                            })

                            # Update summary file with analysis
                            update_summary_file(
                                query_folder,
                                question,
                                analysis_result=analysis_result,
                                conversation_history=st.session_state.messages
                            )

                            # Mark analysis as complete
                            st.session_state.current_query["analysis_complete"] = True

                            st.success(f"✅ Analysis complete! Results saved to `{st.session_state.current_query['folder_name']}/summary.txt`")
                            st.rerun()

                # Show downloaded datasets (collapsed)
                with st.expander("📁 Downloaded Datasets", expanded=False):
                    st.caption(f"Saved to: `{st.session_state.current_query['folder_name']}`")
                    for i, ds in enumerate(st.session_state.current_query["datasets"]):
                        st.markdown(f"**{i+1}. {ds['name']}** ({ds['rows']:,} rows)")

    # ========== TAB 2: BROWSE DATASETS ==========
    with tab2:
        st.markdown("Browse datasets by category or search")
        
        # Search bar
        st.markdown("### 🔍 Search Datasets")
        search_term = st.text_input(
            "Search by dataset ID or name:",
            placeholder="e.g., DSD_AIR_GHG@DF_AIR_GHG or 'air emissions'",
            help="Enter dataset ID or keywords from the dataset name",
            key="browse_search"
        )
        
        # If searching, show search results
        if search_term:
            st.markdown("---")
            search_results = search_datasets(catalog, search_term)
            
            if search_results:
                st.success(f"Found {len(search_results)} matching dataset(s)")
                
                # Let user select from search results
                result_options = {}
                for category, dataset_id, metadata in search_results:
                    display_name = f"[{category}] {metadata['name'][:60]}... ({dataset_id})"
                    result_options[display_name] = (category, dataset_id, metadata)
                
                selected_result = st.selectbox(
                    "Select a dataset from search results:",
                    options=list(result_options.keys()),
                    key="search_select"
                )
                
                category, selected_dataset_id, dataset_meta = result_options[selected_result]
                render_dataset_details(category, selected_dataset_id, dataset_meta)
                
            else:
                st.warning(f"No datasets found matching '{search_term}'")
        
        # If not searching, show category browser
        else:
            st.markdown("---")
            
            # Sidebar - Category selection
            st.sidebar.header("📁 Categories")
            categories = sorted(catalog.keys())
            selected_category = st.sidebar.selectbox(
                "Select a category:",
                options=categories,
                index=0
            )
            
            # Show category info
            st.header(f"📂 {selected_category}")
            
            datasets = catalog[selected_category]["datasets"]
            st.markdown(f"*{len(datasets)} datasets available*")
            
            # Sort datasets alphabetically by name
            sorted_datasets = sorted(
                datasets.items(),
                key=lambda x: x[1]['name'].lower()
            )
            
            # Display datasets in this category
            st.subheader("Available Datasets")
            
            # Create dropdown options (alphabetically sorted)
            dataset_options = {}
            for dataset_id, meta in sorted_datasets:
                display_name = f"{meta['name'][:80]}..." if len(meta['name']) > 80 else meta['name']
                dataset_options[display_name] = dataset_id
            
            selected_dataset_name = st.selectbox(
                "Choose a dataset:",
                options=list(dataset_options.keys()),
                key="browse_select"
            )
            
            # Get the actual dataset ID
            selected_dataset_id = dataset_options[selected_dataset_name]
            dataset_meta = datasets[selected_dataset_id]
            
            render_dataset_details(selected_category, selected_dataset_id, dataset_meta)

if __name__ == "__main__":
    main()