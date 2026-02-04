# oecd_data_fetcher.py

import requests
import pandas as pd
from typing import Dict, List, Optional, Union
import json
from io import StringIO

# ============= THE CLASS =============

class OECDDataFetcher:
    """
    Simple OECD data fetcher.
    """
    
    BASE_URL = "https://sdmx.oecd.org/public/rest/data"
    
    def __init__(self, output_dir: str = "outputs"):
        self.output_dir = output_dir
        self.session = requests.Session()
    
    def get_dataset(
        self,
        agency: str,
        dataset_id: str,
        version: str = "1.0",
        dimension_filter: Optional[str] = None,
        countries: Optional[str] = None,
        freq: Optional[str] = "A",
        start_date: str = "2000",
        end_date: str = "2024",
        save_csv: bool = True
    ) -> pd.DataFrame:
        """
        Fetch OECD dataset.

        Args:
            agency: OECD agency code
            dataset_id: Dataset identifier
            version: Dataset version
            dimension_filter: Dot-separated dimension values (e.g., "A.USA+CAN.B1GQ").
                            If provided, this is used directly. Otherwise, uses legacy filters.
            countries: Country codes joined by + (e.g., "AUS+CAN+USA"). None for all countries.
            freq: Frequency filter (A=Annual, Q=Quarterly, M=Monthly). Set to None to disable.
            start_date: Start year
            end_date: End year
            save_csv: Whether to save as CSV file
        """

        # Build the data selection part of the URL
        if dimension_filter:
            # Use the provided dimension filter directly
            data_selection = dimension_filter
        else:
            # Legacy mode: build from individual parameters
            country_param = countries if countries else ""
            freq_param = freq if freq else ""
            data_selection = f"{country_param}.{freq_param}......"

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


