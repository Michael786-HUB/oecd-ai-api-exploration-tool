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
		  
               [Then provide your recommendations:]
		
               I recommend these datasets:


               1. **Dataset Name** (`EXACT_DATASET_ID_FROM_CATALOG`)
                  - **Category**: [Category name]
                  - **What it offers**: [Detailed explanation of what specific data/insights this provides]
                  - **Why it's relevant**: [How it addresses their question, what they can learn from it]
                  - **Key features**: [Time coverage, countries included, main indicators, etc.]


               2. **Dataset Name** (`EXACT_DATASET_ID_FROM_CATALOG`)
                  - **Category**: [Category name]
                  - **What it offers**: [Detailed explanation]
                  - **Why it's relevant**: [Connection to their question]
                  - **Key features**: [Notable characteristics]


               [End with a helpful note about how these datasets work together or what analysis they enable]

               IMPORTANT: If the user mentions specific countries or time periods in their question, include special metadata sections at the end of your response:

               <!-- FILTER_HINTS:COUNTRIES=USA,CAN,GBR -->
               <!-- FILTER_HINTS:START_YEAR=2020 -->
               <!-- FILTER_HINTS:END_YEAR=2024 -->

               COUNTRY CODES: Use 3-letter ISO codes (USA, CAN, GBR, DEU, FRA, JPN, etc.).
               Common mappings:
               - United States/America/US → USA
               - Canada → CAN
               - United Kingdom/Britain/UK → GBR
               - Germany → DEU
               - France → FRA
               - Japan → JPN
               - Australia → AUS
               - Mexico → MEX
               - China → CHN
               - India → IND

               TIME PERIODS: Extract start and end years from user queries:
               - "2024 data" → START_YEAR=2024, END_YEAR=2024
               - "2020 to 2023" → START_YEAR=2020, END_YEAR=2023
               - "since 2015" → START_YEAR=2015, END_YEAR=2024 (current year)
               - "recent data" → START_YEAR=2020, END_YEAR=2024 (last 5 years)
               - "last decade" → START_YEAR=2014, END_YEAR=2024

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

def generate_query_folder_name(user_question):
    """
    Generate a clean folder name from user question.
    Format: querysummary_terr_timeperiod_date

    Examples:
    - "What did US spend on healthcare in 2023?" → "Healthcare_US_2023_01Feb26"
    - "Compare Canada and Australia GDP" → "GDP_Canada_Australia_01Feb26"
    - "Youth unemployment trends from 2020 to 2024" → "Youth_Unemployment_2020_2024_01Feb26"
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
        'korea': 'KOR', 'south korea': 'KOR'
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
                 'about', 'from', 'to', 'and', 'or', 'of', 'a', 'an', 'how', 'much', 'many', 'have'}
    words = re.findall(r'\b[a-z]+\b', question_lower)
    topic_words = [w.capitalize() for w in words if w not in stopwords and len(w) > 3][:2]

    # Build folder name: querysummary_terr_timeperiod_date
    parts = []

    # 1. Query summary (topic words)
    if topic_words:
        parts.extend(topic_words)

    # 2. Territories (countries) - limit to 3
    if found_countries:
        parts.extend(found_countries[:3])

    # 3. Time period (year range)
    if years:
        unique_years = sorted(set(years))
        if len(unique_years) == 1:
            parts.append(unique_years[0])
        elif len(unique_years) == 2:
            parts.append(f"{unique_years[0]}_{unique_years[1]}")

    # 4. Date (timestamp)
    timestamp = datetime.now().strftime("%d%b%y")
    parts.append(timestamp)

    # Join and sanitize
    folder_name = "_".join(parts) if parts else f"Query_{timestamp}"

    # Remove any problematic characters
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
            f.write("AI ANALYSIS RESULTS\n")
            f.write("=" * 80 + "\n")
            f.write(f"Analysis Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"Question: {user_question}\n\n")
            f.write(f"Answer:\n{analysis_result}\n")
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
        Natural language answer with specific data points
    """
    # Find all CSV files in the query folder
    csv_files = [f for f in os.listdir(query_folder) if f.endswith('.csv')]

    if not csv_files:
        return "No CSV files found in the query folder. Please download datasets first."

    # Read and prepare CSV data
    csv_data_summary = []

    for csv_file in csv_files:
        csv_path = os.path.join(query_folder, csv_file)

        try:
            # Read CSV
            df = pd.read_csv(csv_path)

            # Get basic info
            rows, cols = df.shape

            # Get column names
            columns = df.columns.tolist()

            # Get sample data (first 20 rows)
            sample = df.head(20).to_string(index=False)

            # Create summary
            file_summary = f"""
FILE: {csv_file}
ROWS: {rows:,}
COLUMNS: {cols}
COLUMN NAMES: {', '.join(columns)}

SAMPLE DATA (first 20 rows):
{sample}
"""
            csv_data_summary.append(file_summary)

        except Exception as e:
            csv_data_summary.append(f"FILE: {csv_file}\nERROR: Could not read file - {str(e)}")

    # Combine all CSV summaries
    combined_data = "\n\n" + "=" * 80 + "\n\n".join(csv_data_summary)

    # Create analysis prompt
    analysis_prompt = f"""You are a data analyst helping answer a research question using OECD data.

ORIGINAL QUESTION:
{user_question}

DOWNLOADED DATA:
{combined_data}

INSTRUCTIONS:
1. Analyze the CSV data above to answer the original question
2. Provide SPECIFIC numbers, percentages, or values from the data
3. If comparing multiple countries or time periods, show the comparison clearly
4. If the data doesn't contain the answer, explain what's missing
5. Be concise but complete - aim for 3-5 sentences with key findings
6. Use clear formatting with bullet points if showing multiple values

Please analyze the data and answer the question with specific findings from the CSV data.
"""

    try:
        # Call Claude for analysis
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": analysis_prompt}]
        )

        response_text = message.content[0].text
        return response_text

    except Exception as e:
        return f"Error during AI analysis: {str(e)}"

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
                freq = st.selectbox(
                    "Frequency:",
                    options=["A", "Q", "M"],
                    format_func=lambda x: {"A": "Annual", "Q": "Quarterly", "M": "Monthly"}[x],
                    index=0,
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
                        # Initialize query if not exists
                        user_question = st.session_state.messages[-1]["content"] if st.session_state.messages else "Data Query"
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
                    if dimension_values:
                        # Sort dimensions by position and create dot-separated string
                        sorted_positions = sorted(dimension_values.keys())
                        dim_parts = [dimension_values[pos] for pos in sorted_positions]
                        dim_filter = ".".join(dim_parts)

                    # Build API URL for summary
                    BASE_URL = "https://sdmx.oecd.org/public/rest/data"
                    agency = dataset_meta['agency']
                    version = dataset_meta.get('version', '1.0')

                    if dimensions and dimension_values:
                        sorted_positions = sorted(dimension_values.keys())
                        dim_parts = [dimension_values[pos] if dimension_values[pos] else "" for pos in sorted_positions]
                        filter_str = ".".join(dim_parts)
                    else:
                        country_param = country_filter if country_filter else ""
                        freq_param = freq if freq else ""
                        filter_str = f"{country_param}.{freq_param}......"

                    api_url = (
                        f"{BASE_URL}/{agency},{dataset_id},{version}/"
                        f"{filter_str}?"
                        f"startPeriod={start_date}&endPeriod={end_date}"
                        f"&dimensionAtObservation=AllDimensions&format=csvfile"
                    )

                    # Call the API
                    df = fetcher.get_dataset(
                        agency=dataset_meta['agency'],
                        dataset_id=dataset_id,
                        version=dataset_meta.get('version', '1.0'),
                        dimension_filter=dim_filter,
                        countries=country_filter if not dimensions else None,
                        freq=freq if not dimensions else None,
                        start_date=start_date,
                        end_date=end_date,
                        save_csv=True
                    )

                    # Build filename
                    country_suffix = ""
                    if country_filter:
                        country_count = len(country_filter.split("+"))
                        if country_count <= 3:
                            country_suffix = f"_{country_filter.replace('+', '_')}"
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

    st.title("📊 OECD Data AI Librarian")

    # Show API counter at the top
    show_api_counter()
    st.markdown("---")

    # Load catalog
    catalog = load_catalog()
    
    # Create tabs
    tab1, tab2 = st.tabs(["🤖 AI Librarian", "📚 Browse Datasets"])
    
    # ========== TAB 1: AI LIBRARIAN ==========
    with tab1:
        st.markdown("### Ask the AI Librarian")
        st.markdown("Describe what data you're looking for, and I'll help you find the perfect datasets. Feel free to ask follow-up questions!")

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
            st.markdown("### 👋 Welcome to OECD Data AI Research Assistant!")

            st.info("""
            **Hello, I am your AI-powered research assistant** that helps you find, download, and analyze OECD data with specific answers to your questions.
            """)

            # Instructions
            with st.expander("📖 How to Use This Tool", expanded=True):
                st.markdown("""
                ### Complete Research Workflow

                **Step 1: Ask Your Question** 🤔
                - Be specific about countries, time periods, and metrics and what data you're looking for.
                - Examples:
                  - "What was US healthcare and foreign aid spending in 2023?"
                  - "Compare youth unemployment in Canada, Australia, and UK from 2020 to 2024 relative to their GNI index"
                  - "I am looking for data on GDP growth and inflation rates in Japan and Canada between 2023 and 2024"

                **Step 2: Download Dataset** 📥
                - I'll recommend relevant datasets that available in the OECD websitee
                - Click "Download Dataset" to save data to a query-specific folder
                - For me to read and analyse the datasets, they need to be exported. Choose a file location on the left-hand side
                - Note: Each dataset download counts as 1 API request. OECD allows 60 downloads per hour
                       
                **Step 3: Analyze Data** 🔬
                - After downloading, click "Analyse Data"
                - I'll read the CSV and provide specific answers with numbers
                - Results will be saved to summary.txt within the folder specified in Step 2, so you can save the results for later :)
                            
                IMPORTANT: AI MAY OCCASIONALLY HALLUCINATE AND MAKE THINGS UP :/
                If a dataset can't be exported, its possible the filters you selected don't have data (for example, if you put 2024 as the year, but the dataset selected is limited to 2023 only)

                ---

                ### Tips for Best Results

                ✅ **DO:**
                - Mention specific countries (US, UK, Canada, Japan, Australia, etc.)
                - Specify time periods ("2023", "2020 to 2024", "since 2015")
                - Focus on major economies for faster, smaller datasets
                - Ask follow-up questions to refine your search

                ❌ **AVOID:**
                - Vague questions without countries or timeframes
                - Requesting data from obscure countries (unless needed)
                - Very broad time ranges (increases data size)

                ---

                ### Where Your Data is Saved

                Each query creates a new folder:
                - **Format:** `TopicName_Countries_TimeRange_Date`
                - **Example:** `Healthcare_US_2023_01Feb26`
                - **Contains:** CSV files + summary.txt with API URLs & analysis
                - **Location:** Check sidebar to set your preferred folder location ➡️
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

            # API counter info
            st.markdown("**API Usage**")
            st.caption(f"Requests: {st.session_state.api_counter}/60 per hour")
        
        # Display chat history
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
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

            # Show "Analyze Data" button if datasets have been downloaded
            if st.session_state.current_query and st.session_state.current_query.get("datasets"):
                st.markdown("---")
                num_datasets = len(st.session_state.current_query["datasets"])

                col1, col2 = st.columns([2, 1])
                with col1:
                    st.markdown(f"### 🔬 Data Analysis")
                    st.info(f"📊 **{num_datasets} dataset(s) downloaded** and ready for analysis")
                with col2:
                    if st.button("✨ Analyze Data", type="primary", use_container_width=True, key="analyze_button"):
                        with st.spinner("🤖 AI analyzing your data..."):
                            client = anthropic_client()
                            query_folder = st.session_state.current_query["folder_path"]
                            question = st.session_state.current_query["question"]

                            # Call AI analyst
                            analysis_result = ai_librarian_analyst(query_folder, question, client)

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

                # Show summary info
                st.markdown("**Query Details:**")
                st.code(f"Question: {st.session_state.current_query['question']}")
                st.code(f"Folder: {st.session_state.current_query['folder_name']}")

                # List downloaded datasets
                with st.expander("📁 Downloaded Datasets", expanded=False):
                    for i, ds in enumerate(st.session_state.current_query["datasets"]):
                        st.markdown(f"**{i+1}. {ds['name']}**")
                        st.text(f"   File: {ds['filename']}")
                        st.text(f"   Rows: {ds['rows']:,}")
                        st.text(f"   Downloaded: {ds['timestamp']}")

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