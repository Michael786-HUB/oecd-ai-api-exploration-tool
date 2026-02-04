import requests
import pandas as pd
from io import StringIO

# Define API query URL (CSV with labels format)
url = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD.SEEA,DSD_AEA@DF_AEA,1.2/FRA..EMISSIONS.T_CO2E+T......?dimensionAtObservation=AllDimensions"

# Fetch data
response = requests.get(url)

# Load into pandas DataFrame
df = pd.read_csv(StringIO(response.text))

# Display first few rows
print(df.head())