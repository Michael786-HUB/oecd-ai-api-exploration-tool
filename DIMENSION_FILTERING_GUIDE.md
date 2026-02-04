# Dimension Filtering Guide

## Overview

The OECD Data Explorer now supports **precision dimension filtering** for 518 datasets (35% of the catalog). This allows you to construct exact API queries instead of using wildcards, resulting in faster downloads and more targeted data.

## What Are Dimensions?

Dimensions are the structural components of OECD datasets. Each dimension represents a specific aspect of the data, such as:

- **REF_AREA**: Geographic area/country (e.g., USA, CAN, GBR)
- **FREQ**: Data frequency (A=Annual, Q=Quarterly, M=Monthly)
- **MEASURE**: What is being measured (varies by dataset)
- **TIME_PERIOD**: Time reference (usually handled by date filters)
- **UNIT_MEASURE**: Unit of measurement
- And many more dataset-specific dimensions

## How Dimension Filtering Works

### API URL Structure

The OECD API uses positional dimension filtering:

```
https://sdmx.oecd.org/public/rest/data/{agency},{dataset},{version}/{dim1}.{dim2}.{dim3}...?startPeriod=2000&endPeriod=2024
```

**Example:**
```
.../OECD.SDD.NAD,DSD_NAAG@DF_NAAG,1.0/A.USA+CAN.B1GQ.?startPeriod=2010&endPeriod=2024
```

This translates to:
- **Position 1** (FREQ): `A` = Annual frequency
- **Position 2** (REF_AREA): `USA+CAN` = United States and Canada
- **Position 3** (MEASURE): `B1GQ` = Gross domestic product

## Using Dimension Filters in the App

### For Datasets WITH Dimensions (518 datasets)

1. **Navigate to a dataset** via AI Librarian or Browse Datasets tab

2. **Look for the Dimension Filters section**
   - If available, you'll see: "This dataset has **X dimensions**"
   - Each dimension shows its position, name, and ID

3. **Fill in dimension values**
   - **Leave blank** to include all values for that dimension
   - **Specify exact codes** separated by `+` for multiple values
   - Example: `USA+CAN+MEX` for multiple countries

4. **Common dimension patterns:**
   - **REF_AREA** (Country): `USA`, `CAN+MEX`, `GBR`
   - **FREQ** (Frequency): `A`, `Q`, `M`
   - **MEASURE**: Check dataset documentation for valid codes
   - Other dimensions: Dataset-specific (check OECD docs)

5. **Preview the query**
   - Expand "Preview API Query" to see what will be requested
   - Shows: `A.USA+CAN.B1GQ....` etc.

6. **Download**
   - Click "Download Dataset"
   - Data is filtered precisely by your dimension selections

### For Datasets WITHOUT Dimensions (949 datasets)

The app falls back to **legacy filtering mode**:

1. **Country Filter** (radio buttons):
   - All countries
   - OECD countries only
   - Non-OECD countries only
   - Specific countries (multiselect)

2. **Frequency Filter** (optional checkbox):
   - Annual (A)
   - Quarterly (Q)
   - Monthly (M)

3. **Time Period**: Start year and end year

## Examples

### Example 1: Domestic Tourism Data

**Dataset**: `DSD_TOURISM_DOM@DF_DOMESTIC`

**Dimensions (6)**:
1. REF_AREA: `USA+CAN+MEX` (North American countries)
2. MEASURE: `` (leave blank for all measures)
3. UNIT_MEASURE: `` (leave blank for all units)
4. VISITOR_TYPE: `` (leave blank for all visitor types)
5. ACCOMMODATION_TYPE: `` (leave blank for all accommodation)

**Resulting query**: `USA+CAN+MEX.....`

This fetches all tourism measures for USA, Canada, and Mexico across all other dimensions.

### Example 2: GDP Data

**Dataset**: `DSD_NAAG@DF_NAAG`

**Dimensions (3)**:
1. FREQ: `A` (Annual data only)
2. REF_AREA: `USA` (United States only)
3. MEASURE: `B1GQ` (Gross Domestic Product)

**Resulting query**: `A.USA.B1GQ`

This fetches annual GDP data for the United States only.

### Example 3: Mixed Filtering

**Dimensions**:
1. FREQ: `Q` (Quarterly)
2. REF_AREA: `` (All countries)
3. MEASURE: `UNEMP+EMP` (Unemployment and Employment)

**Resulting query**: `Q..UNEMP+EMP`

Quarterly unemployment and employment data for all available countries.

## Benefits of Dimension Filtering

### 🚀 Faster Downloads
- Request only the data you need
- Smaller dataset sizes
- Reduced API response time

### 🎯 Precision
- Exact data selection
- No need to filter CSV after download
- Get exactly what you ask for

### 📊 Better Understanding
- See the structure of each dataset
- Understand what dimensions are available
- Learn how data is organized

### 💾 Efficiency
- Less storage needed for downloaded files
- Faster data processing
- Cleaner CSV files

## Tips

1. **Start broad, then narrow**
   - First try leaving most dimensions blank to see what's available
   - Then refine to specific values

2. **Check dataset documentation**
   - For dataset-specific dimensions, check OECD documentation
   - OECD Data Explorer web interface shows valid codes

3. **Use the preview**
   - Always check "Preview API Query" before downloading
   - Verify your dimension filter looks correct

4. **Combine multiple values**
   - Use `+` to combine: `USA+CAN+GBR`
   - No spaces around the `+`

5. **Leave blanks for wildcards**
   - Blank dimension = all values
   - Useful when you don't know specific codes

6. **Test with small date ranges first**
   - Use `2023` to `2024` to test your dimension filter
   - Then expand to full date range once confirmed

## Troubleshooting

### "Dimensions not available for this dataset"
- 65% of datasets don't have dimension metadata yet
- Use legacy filtering (country + frequency filters)
- The dimension extraction script is still running to add more

### Download fails with dimension filters
- Check dimension codes are valid for that dataset
- Try leaving more dimensions blank
- Verify country codes are correct (3-letter ISO codes)
- Check OECD documentation for valid dimension values

### Empty dataset returned
- The combination of dimension values might not exist
- Try broadening your filter (leave more dimensions blank)
- Check date range has data for those dimensions

### API returns error
- Verify dimension order matches positions
- Check for typos in dimension values
- Ensure `+` separators have no spaces

## Finding Valid Dimension Codes

1. **OECD Data Explorer**
   - Visit: https://data-explorer.oecd.org/
   - Browse the dataset
   - Check available dimension values in the interface

2. **SDMX Dataflow Browser**
   - OECD provides codelist documentation
   - Check agency documentation pages

3. **Trial and Error**
   - Start with common codes (USA, CAN, etc.)
   - Leave dimensions blank to get all data
   - Inspect CSV to see what values exist

## Current Status

- **Total datasets**: 1,467
- **Datasets with dimensions**: 518 (35.3%)
- **Datasets pending**: 949 (64.7% - dimension extraction in progress)

The retry script is currently running to extract dimensions for the remaining 259 datasets that failed due to rate limiting. Check back later for updates!
