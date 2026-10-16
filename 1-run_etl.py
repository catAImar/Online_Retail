# Code to run this in the terminal: 
#   python 1-run_etl.py

from pathlib import Path
import subprocess
import sys

# Locate the notebook
folder = Path(__file__).resolve().parent
etl_script = folder / "1-online_retail_etl.py"

print("Starting the ETL process...")

# Run notebook
subprocess.run(
    [sys.executable, str(etl_script)],
    cwd=folder,
    check=True
)

print("ETL completed successfully.")