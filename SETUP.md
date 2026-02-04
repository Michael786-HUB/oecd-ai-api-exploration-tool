# OECD Research Tool - Setup Guide

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Anthropic Claude API key

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd OCED-Research-Tool
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API Key** 🔒

   The application requires an Anthropic Claude API key to function.

   **Option A: Using Streamlit Secrets (Recommended)**

   ```bash
   # Copy the example secrets file
   cp .streamlit/secrets.example.toml .streamlit/secrets.toml

   # Edit the secrets file and add your API key
   nano .streamlit/secrets.toml
   ```

   Add your API key:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-api03-your-actual-key-here"
   ```

   **Option B: Using Environment Variables**

   ```bash
   export ANTHROPIC_API_KEY="sk-ant-api03-your-actual-key-here"
   ```

4. **Run the application**
   ```bash
   streamlit run app.py
   ```

   The app will open in your browser at `http://localhost:8501`

---

## 🔑 Getting an Anthropic API Key

1. Go to [https://console.anthropic.com/](https://console.anthropic.com/)
2. Sign up or log in to your account
3. Navigate to **API Keys** section
4. Click **Create Key**
5. Copy your API key (starts with `sk-ant-api03-...`)

**Important:** Keep your API key secure! Never commit it to version control.

---

## 📁 Project Structure

```
OCED-Research-Tool/
├── app.py                          # Main Streamlit application
├── scripts/
│   ├── OECD_Catalog_Builder.py    # Catalog building module
│   ├── oecd_class.py               # OECD data fetcher
│   ├── categorize_datasets.py     # Dataset categorization
│   └── archive/                    # Archived old scripts
├── data/
│   ├── catalogs/                   # OECD dataset catalogs
│   ├── country_codes.json          # Country code mappings
│   └── oecd_dataset_catalog_v2.json
├── outputs/                        # User query results (auto-generated)
├── datasets/                       # Downloaded CSV files (auto-generated)
├── .streamlit/
│   ├── secrets.toml               # Your API key (NEVER commit!)
│   └── secrets.example.toml       # Template (safe to commit)
├── .gitignore                     # Protects secrets
└── README.md                      # Project documentation
```

---

## 🔒 Security Notes

### Protected Files (Never Committed to Git)

The following files are automatically ignored by `.gitignore`:

- ✅ `.streamlit/secrets.toml` - Your API keys
- ✅ `outputs/*` - User-generated query results
- ✅ `datasets/*` - Downloaded data files
- ✅ `__pycache__/` - Python cache
- ✅ `.DS_Store` - macOS system files
- ✅ `.claude/` - Claude Code session data
- ✅ `*.log` - Log files

### Files Safe to Commit

- ✅ `.streamlit/secrets.example.toml` - Template (no real keys)
- ✅ `.gitignore` - Protection rules
- ✅ `app.py` - Application code
- ✅ `scripts/*.py` - Python modules
- ✅ `data/*.json` - Small catalog files
- ✅ Documentation files

### Verify Protection

Run this command to verify your secrets are protected:
```bash
git check-ignore -v .streamlit/secrets.toml
```

Expected output:
```
.gitignore:10:.streamlit/secrets.toml    .streamlit/secrets.toml
```

---

## 🛠️ Development Setup

### Optional: Use Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (macOS/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running Tests

```bash
# Test catalog builder
python scripts/OECD_Catalog_Builder.py --help

# Test basic import
python -c "from scripts.OECD_Catalog_Builder import OECDCatalogBuilder; print('✓ Import successful')"
```

---

## 📚 Usage Examples

### Basic Usage

1. Start the app: `streamlit run app.py`
2. Enter your research question in the chat
3. Claude AI will search the OECD catalog and suggest datasets
4. Review and download datasets
5. Use "Analyze Data" button to get AI-powered insights

### Advanced: Building Custom Catalogs

```bash
# Build complete catalog with dimensions (~10 hours)
python scripts/OECD_Catalog_Builder.py --output ./data

# Build quick catalog without dimensions (~30 seconds)
python scripts/OECD_Catalog_Builder.py --output ./data --no-dimensions

# Resume interrupted build
python scripts/OECD_Catalog_Builder.py --output ./data --resume
```

---

## 🐛 Troubleshooting

### "API key not found" error

**Problem:** Application can't find your Anthropic API key

**Solution:**
1. Check `.streamlit/secrets.toml` exists
2. Verify API key is correctly formatted: `ANTHROPIC_API_KEY = "sk-ant-..."`
3. Restart the Streamlit app

### "Module not found" errors

**Problem:** Missing Python dependencies

**Solution:**
```bash
pip install streamlit anthropic pandas requests
```

### "Permission denied" when accessing files

**Problem:** File permissions issue

**Solution:**
```bash
chmod -R u+rw outputs/ datasets/
```

### Git shows secrets.toml as untracked

**Problem:** Secrets file might be committed by mistake

**Solution:**
```bash
# Remove from git (keeps local file)
git rm --cached .streamlit/secrets.toml

# Verify it's ignored
git check-ignore -v .streamlit/secrets.toml
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Ensure secrets are not committed
5. Submit a pull request

---

## 📄 License

[Add your license here]

---

## 💡 Support

For issues and questions:
- Check documentation in `scripts/OECD_Catalog_Builder_README.md`
- Review feature guides: `AI_ANALYST_FEATURE.md`, `DIMENSION_FILTERING_GUIDE.md`
- Create an issue on GitHub

---

## ⚠️ Important Reminders

1. **Never commit API keys** - They are protected by `.gitignore`
2. **Keep secrets.toml local** - Only `secrets.example.toml` should be in the repo
3. **Check git status** before committing to avoid exposing sensitive data
4. **Regenerate API key** immediately if accidentally exposed

---

**Last Updated:** 2026-02-04
