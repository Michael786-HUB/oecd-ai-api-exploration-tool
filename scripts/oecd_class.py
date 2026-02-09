# oecd_data_fetcher.py

import requests
import pandas as pd
from typing import Dict, List, Optional, Union, Tuple
import json
import re
from io import StringIO

# ============= URL VALIDATION =============

class OECDURLValidator:
    """
    Validates OECD API URLs before making requests.
    Helps catch common errors like wrong dimension counts or invalid parameters.
    """

    STRUCTURE_URL = "https://sdmx.oecd.org/public/rest/dataflow"

    @staticmethod
    def validate_url_components(
        agency: str,
        dataset_id: str,
        version: str,
        dimension_filter: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        expected_dimensions: Optional[int] = None
    ) -> Tuple[bool, List[str]]:
        """
        Validate URL components before building the API URL.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # 1. Validate agency
        if not agency or not isinstance(agency, str):
            errors.append("Agency is required and must be a string")
        elif not re.match(r'^[A-Z0-9_.]+$', agency):
            errors.append(f"Agency '{agency}' contains invalid characters. Expected format: OECD.XXX.YYY")

        # 2. Validate dataset_id
        if not dataset_id or not isinstance(dataset_id, str):
            errors.append("Dataset ID is required and must be a string")
        elif '@' not in dataset_id and not dataset_id.startswith('DSD_'):
            errors.append(f"Dataset ID '{dataset_id}' may be invalid. Expected format: DSD_XXX@DF_YYY or similar")

        # 3. Validate version
        if version:
            if not re.match(r'^\d+\.\d+$', version):
                errors.append(f"Version '{version}' is invalid. Expected format: X.Y (e.g., 1.0)")

        # 4. Validate dimension filter
        if dimension_filter:
            if dimension_filter != 'all':
                # Count dots to determine dimension count
                dot_count = dimension_filter.count('.')
                filter_dimension_count = dot_count + 1

                # Check for invalid characters
                if not re.match(r'^[A-Za-z0-9_+.*]+$', dimension_filter):
                    errors.append(f"Dimension filter contains invalid characters")

                # Validate against expected dimensions if provided
                if expected_dimensions and filter_dimension_count != expected_dimensions:
                    errors.append(
                        f"Dimension filter has {filter_dimension_count} dimensions "
                        f"(found {dot_count} dots), but dataset expects {expected_dimensions} dimensions"
                    )

        # 5. Validate date range
        if start_date:
            if not re.match(r'^\d{4}(-\d{2})?(-\d{2})?$', start_date):
                errors.append(f"Start date '{start_date}' is invalid. Expected: YYYY or YYYY-MM or YYYY-MM-DD")

        if end_date:
            if not re.match(r'^\d{4}(-\d{2})?(-\d{2})?$', end_date):
                errors.append(f"End date '{end_date}' is invalid. Expected: YYYY or YYYY-MM or YYYY-MM-DD")

        if start_date and end_date:
            try:
                if int(start_date[:4]) > int(end_date[:4]):
                    errors.append(f"Start date ({start_date}) is after end date ({end_date})")
            except ValueError:
                pass

        return len(errors) == 0, errors

    @staticmethod
    def build_and_validate_url(
        agency: str,
        dataset_id: str,
        version: str = "1.0",
        dimension_filter: Optional[str] = None,
        start_date: str = "2000",
        end_date: str = "2024",
        expected_dimensions: Optional[int] = None,
        format: str = "csvfile"
    ) -> Tuple[Optional[str], List[str]]:
        """
        Build and validate an OECD API URL.

        Returns:
            Tuple of (url_or_none, list_of_errors)
        """
        BASE_URL = "https://sdmx.oecd.org/public/rest/data"

        # Validate components
        is_valid, errors = OECDURLValidator.validate_url_components(
            agency=agency,
            dataset_id=dataset_id,
            version=version,
            dimension_filter=dimension_filter,
            start_date=start_date,
            end_date=end_date,
            expected_dimensions=expected_dimensions
        )

        if not is_valid:
            return None, errors

        # Build data selection
        data_selection = dimension_filter if dimension_filter else "all"

        # Build URL
        url = (
            f"{BASE_URL}/{agency},{dataset_id},{version}/"
            f"{data_selection}?"
            f"startPeriod={start_date}&endPeriod={end_date}"
            f"&dimensionAtObservation=AllDimensions&format={format}"
        )

        return url, []

    @staticmethod
    def fetch_dataset_structure(
        agency: str,
        dataset_id: str,
        version: str = "1.0",
        timeout: int = 30
    ) -> Optional[Dict]:
        """
        Fetch the structure/dimension info for a dataset.
        Returns dimension names and count.

        This is a lightweight call (~5-20KB response) that returns metadata only.
        """
        url = (
            f"https://sdmx.oecd.org/public/rest/dataflow/{agency}/{dataset_id}/{version}"
            f"?references=all&detail=referencepartial"
        )

        headers = {
            'Accept': 'application/vnd.sdmx.structure+json; charset=utf-8; version=1.0'
        }

        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()

            # Extract dimension info from the response
            dimensions = []
            dimension_count = 0

            # Navigate the SDMX-JSON structure to find dimensions
            if 'data' in data:
                structures = data.get('data', {}).get('dataStructures', [])
                if structures:
                    components = structures[0].get('dataStructureComponents', {})
                    dim_list = components.get('dimensionList', {}).get('dimensions', [])
                    dimensions = [d.get('id') for d in dim_list]
                    dimension_count = len(dimensions)

            return {
                'agency': agency,
                'dataset_id': dataset_id,
                'version': version,
                'dimension_count': dimension_count,
                'dimensions': dimensions
            }

        except Exception as e:
            print(f"Error fetching structure for {dataset_id}: {e}")
            return None


# ============= THE CLASS =============

class OECDDataFetcher:
    """
    Simple OECD data fetcher with URL validation.
    """

    BASE_URL = "https://sdmx.oecd.org/public/rest/data"

    def __init__(self, output_dir: str = "outputs", validate_urls: bool = True):
        self.output_dir = output_dir
        self.session = requests.Session()
        self.validate_urls = validate_urls
        self.validator = OECDURLValidator()
    
    def get_dataset(
        self,
        agency: str,
        dataset_id: str,
        version: str = "1.0",
        dimension_filter: Optional[str] = None,
        countries: Optional[str] = None,
        freq: Optional[str] = None,
        start_date: str = "2000",
        end_date: str = "2024",
        save_csv: bool = True,
        expected_dimensions: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch OECD dataset with URL validation.

        Args:
            agency: OECD agency code (e.g., "OECD.CFE.EDS")
            dataset_id: Dataset identifier (e.g., "DSD_FUA_CLIM@DF_DROUGHT")
            version: Dataset version (e.g., "1.0")
            dimension_filter: Dot-separated dimension values (e.g., "A.USA+CAN.B1GQ").
                            If provided, this is used directly. Otherwise, uses legacy filters.
            countries: Country codes joined by + (e.g., "AUS+CAN+USA"). None for all countries.
            freq: Frequency filter (A=Annual, Q=Quarterly, M=Monthly). Default is None (no filter).
            start_date: Start year (e.g., "2020")
            end_date: End year (e.g., "2024")
            save_csv: Whether to save as CSV file
            expected_dimensions: Number of dimensions this dataset has (for validation)

        Returns:
            DataFrame with the fetched data

        Raises:
            ValueError: If URL validation fails
            requests.HTTPError: If API request fails
        """

        # Build the data selection part of the URL
        if dimension_filter:
            # Use the dimension filter directly - the UI ensures correct positioning
            data_selection = dimension_filter

            # Log what filter is being applied
            non_empty_parts = [p for p in dimension_filter.split('.') if p.strip()]
            if non_empty_parts:
                print(f"📋 Applying dimension filter: {len(non_empty_parts)} value(s)")
        else:
            # No dimension filter - use 'all' keyword (safest per OECD API docs)
            # Time period filtering via startPeriod/endPeriod still works with 'all'
            data_selection = "all"

        # Validate URL components before making request
        if self.validate_urls:
            is_valid, errors = self.validator.validate_url_components(
                agency=agency,
                dataset_id=dataset_id,
                version=version,
                dimension_filter=data_selection if dimension_filter else None,
                start_date=start_date,
                end_date=end_date,
                expected_dimensions=expected_dimensions
            )

            if not is_valid:
                error_msg = "URL validation failed:\n  - " + "\n  - ".join(errors)
                print(f"⚠️ {error_msg}")
                # Continue anyway but warn - validation is advisory

        url = (
            f"{self.BASE_URL}/{agency},{dataset_id},{version}/"
            f"{data_selection}?"
            f"startPeriod={start_date}&endPeriod={end_date}"
            f"&dimensionAtObservation=AllDimensions&format=csvfile"
        )

        print(f"Fetching from: {url}")
        
        try:
            # Make the API request
            response = self.session.get(url, timeout=60)
            response.raise_for_status()
            
            # Convert response text to DataFrame
            df = pd.read_csv(StringIO(response.text))

            print(f"✓ Fetched {len(df)} rows, {len(df.columns)} columns")

            # Debug: show what parameters were received
            print(f"DEBUG: countries param={countries}, dimension_filter param={dimension_filter}")

            # Post-download filtering: if countries specified but no dimension filter,
            # filter the DataFrame by REF_AREA column
            if countries and not dimension_filter:
                country_list = countries.split("+")
                print(f"DEBUG: Attempting post-download filter for countries: {country_list}")

                # Look for country column (REF_AREA is the standard OECD column name)
                country_col = None
                for col in ['REF_AREA', 'LOCATION', 'COUNTRY', 'COU', 'DONOR']:
                    if col in df.columns:
                        country_col = col
                        break

                if country_col:
                    original_rows = len(df)
                    # Show unique values in the column to debug matching
                    unique_vals = df[country_col].unique()[:10]
                    print(f"DEBUG: Found column '{country_col}' with values like: {unique_vals}")
                    df = df[df[country_col].isin(country_list)]
                    print(f"📋 Filtered by countries: {original_rows} → {len(df)} rows ({len(country_list)} countries)")
                else:
                    print(f"⚠️ Could not find country column to filter. Available columns: {df.columns.tolist()}")

            # Post-download filtering: if frequency specified but no dimension filter
            if freq and not dimension_filter:
                freq_col = None
                for col in ['FREQ', 'FREQUENCY']:
                    if col in df.columns:
                        freq_col = col
                        break

                if freq_col:
                    original_rows = len(df)
                    df = df[df[freq_col] == freq]
                    print(f"📋 Filtered by frequency '{freq}': {original_rows} → {len(df)} rows")

            # Save to CSV if requested
            if save_csv:
                # Build filename with country indicator if countries were filtered
                country_suffix = ""
                if countries:
                    country_count = len(countries.split("+"))
                    if country_count <= 3:
                        country_suffix = f"_{countries.replace('+', '_')}"
                    else:
                        country_suffix = f"_{country_count}countries"

                filename = f"{self.output_dir}/{dataset_id.replace('@', '_')}{country_suffix}_{start_date}_{end_date}.csv"
                df.to_csv(filename, index=False)
                print(f"✓ Saved to: {filename}")
            
            return df
            
        except Exception as e:
            print(f"✗ Error: {e}")
            raise


# ============= USING THE CLASS =============

if __name__ == "__main__":
    # Step 1: Create an instance of the fetcher class
    fetcher = OECDDataFetcher()

    # Step 2: Call the get_dataset method with your parameters
    df = fetcher.get_dataset(
        agency="OECD.ITF",
        dataset_id="DSD_ST@DF_STFAT",
        version="1.0",
        freq="Q",
        start_date="2021",
        end_date="2024"
    )

    # Step 3: Now you have the data in df, do whatever you want with it
    print("\nFirst 10 rows:")
    print(df.head(10))

    print("\nColumn names:")
    print(df.columns.tolist())

    print("\nDataset shape:")
    print(f"Rows: {len(df)}, Columns: {len(df.columns)}")


