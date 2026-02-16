# OECD AI Research Tool

**An AI-powered data discovery and analysis platform for the OECD statistical database.**

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://oecd-research-tool.streamlit.app)
[![GitHub](https://img.shields.io/badge/GitHub-Repository-blue)](https://github.com/Michael786-HUB/oecd-ai-api-exploration-tool)

---

## The Problem

The OECD maintains one of the world's largest collections of international statistical data — over **1,400 datasets** spanning economics, development, health, education, trade, and more. For researchers, policy analysts, and academics, finding the right dataset is a challenge:

- **Discovery is hard**: Navigating the OECD's data portal requires knowing exactly which dataset you need, its ID, its structure, and which API filters to apply.
- **APIs are complex**: The OECD uses the SDMX standard — powerful but technical. Building a valid query URL requires understanding dimension positions, code lists, and filter syntax.
- **Analysis takes time**: Once you have the data, making sense of thousands of rows with coded values (e.g., `MEASURE=1010`, `FLOW_TYPE=1140`) requires domain knowledge and manual mapping.

This tool solves all three problems with AI.

---

## Who Is This For?

- **Researchers** exploring OECD data for academic papers or policy analysis
- **Policy analysts** who need quick access to international comparative statistics
- **Development professionals** working with ODA, aid flow, and governance data
- **Data journalists** looking for trends across OECD member countries
- **Anyone** who wants to query the OECD database using plain English

---

## How It Works

```
Ask a question in plain English
        |
        v
AI Librarian searches 1,400+ datasets and recommends the best matches
        |
        v
Filters are auto-applied (countries, years, dimensions)
        |
        v
Data is downloaded from OECD's SDMX API
        |
        v
AI Analyst reads the data and answers your original question with specific numbers
        |
        v
Results saved to an organized folder with full audit trail
```

### Example

> **You ask:** "How much did Canada and France spend on ODA between 2021 and 2023?"
>
> **AI Librarian** recommends DAC1 (Flows by provider), DAC2A (Disbursements by country), and DAC5 (Aid by sector) — with filters pre-set for CAN, FRA, 2021-2023.
>
> **AI Analyst** reads the downloaded data and responds:
> - Canada's total ODA rose from $6.3B in 2021 to $8.7B in 2023 (+38%)
> - France maintained steady ODA at ~$15B across the period
> - Both countries remained below the UN 0.7% GNI target

---

## Key Features

| Feature | Description |
|---------|-------------|
| **AI Librarian** | Natural language search across 1,467 OECD datasets with Claude |
| **Smart Filtering** | Auto-extracts countries, years, and dimensions from your question |
| **Dimension Filters** | SDMX-based precision filtering for 500+ datasets with structured dimensions |
| **AI Analyst** | Reads downloaded CSVs and provides formatted analysis with specific numbers |
| **Query Management** | Each query creates an organized folder with data, summary, and conversation history |
| **Hallucination Safeguards** | Multi-layer validation ensures AI only recommends real datasets |
| **Data Optimization** | Smart column/row reduction to keep analysis cost-efficient |
| **Browse Mode** | Category-based browsing of the full dataset catalog |

---

## Quick Start

### Prerequisites

- Python 3.8+
- [Anthropic API key](https://console.anthropic.com/)

### Install & Run

```bash
# Clone the repository
git clone https://github.com/Michael786-HUB/oecd-ai-api-exploration-tool.git
cd oecd-ai-api-exploration-tool

# Install dependencies
pip install -r requirements.txt

# Add your API key
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
# Edit secrets.toml: ANTHROPIC_API_KEY = "sk-ant-..."

# Run
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## Project Structure

```
oecd-ai-api-exploration-tool/
├── app.py                              # Main Streamlit application
├── requirements.txt                    # Python dependencies
├── scripts/
│   ├── oecd_class.py                  # OECD API client & URL builder
│   ├── OECD_Catalog_Builder.py        # Dataset catalog builder
│   └── categorize_datasets.py         # Dataset categorization
├── data/
│   ├── catalogs/                      # Dataset catalog with dimensions
│   └── country_codes.json             # ISO country code mappings
├── outputs/                           # Query results (auto-generated)
├── .streamlit/
│   ├── secrets.toml                   # API key (gitignored)
│   └── secrets.example.toml           # Template
└── docs/                              # Feature documentation
```

---

## OECD API URL Structure

The tool constructs SDMX REST API calls to the OECD. Here's how a URL is built:

```
https://sdmx.oecd.org/public/rest/data/{agency},{dataset},{version}/{filter}?startPeriod={year}&endPeriod={year}&dimensionAtObservation=AllDimensions&format=csvfile
```

**Example** — Canada ODA data for 2021:
```
https://sdmx.oecd.org/public/rest/data/OECD.DCD.FSD,DSD_DAC1@DF_DAC1,1.6/CAN._Z.....?startPeriod=2021&endPeriod=2021&dimensionAtObservation=AllDimensions&format=csvfile
```

| Component | Value | Meaning |
|-----------|-------|---------|
| Agency | `OECD.DCD.FSD` | Development Co-operation Directorate |
| Dataset | `DSD_DAC1@DF_DAC1` | DAC1: Flows by provider |
| Version | `1.6` | Dataset version |
| Filter | `CAN._Z.....` | Canada, aggregate sector, all other dimensions |
| Period | `2021` | Single year |

---

## Tech Stack

- **[Streamlit](https://streamlit.io/)** — Web UI
- **[Claude API](https://docs.anthropic.com/)** — AI librarian and analyst (Sonnet)
- **[Pandas](https://pandas.pydata.org/)** — Data processing and optimization
- **[OECD SDMX API](https://sdmx.oecd.org/)** — Data source

---

## Security

- API keys are stored in `.streamlit/secrets.toml` (gitignored)
- Downloaded data and outputs are gitignored
- No credentials are ever committed to the repository

---

## License

MIT

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and test locally
4. Submit a pull request

For issues and feature requests, use [GitHub Issues](https://github.com/Michael786-HUB/oecd-ai-api-exploration-tool/issues).
