#!/usr/bin/env python
# coding: utf-8

## Online Retail — ETL Assessment


# pip install pandas



# 0. Setup — libraries and the explicit CSV location
import pandas as pd
import sqlite3
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from IPython.display import display

file_path = Path(r"C:\Users\Lenovo\Desktop\Artefact_Assessments\online_retail.csv")
db_path = file_path.parent / "online_retail.db"

# print("CSV:", file_path)


# ## 1. Data Ingestion

# 1.1. Implement a data ingestion process to fetch the dataset from its source (e.g., CSV file, database)
# Read the dataset from the CSV file on my computer & keep identifiers as strings to preserve their original format
df = pd.read_csv(file_path, dtype={
    "InvoiceNo": "string", 
    "StockCode": "string",
    "CustomerID": "string"})
# print("Count:", len(df))
# df.head()


# 1.2. Load the dataset into a suitable storage system (e.g., relational database, data warehouse)
# Load the original data into a relational database (SQLite), to later compare the source and the cleaned version.

conn = sqlite3.connect(db_path)

df.to_sql("raw_online_retail", conn, if_exists="replace", index=False)

# Read data to make sure it appears in the database.
# print("Count:", len(pd.read_sql("SELECT * FROM raw_online_retail", conn)))
# display(pd.read_sql("SELECT * FROM raw_online_retail LIMIT 10", conn))

conn.close()


# ## 2. Data Cleaning and Validation

# 2.1. Develop a data cleaning pipeline to handle missing values, duplicates, and outliers.

rows_before = len(df)

# Remove spaces and treat empty text as missing.
for column in ["InvoiceNo", "StockCode", "Description", "CustomerID", "Country"]:
    df[column] = (
        df[column]
        .astype("string")
        .str.strip()
        .replace("", pd.NA))

# Treat Customer IDs as identifiers, not numbers. For example, "17850.0" becomes "17850"
df["CustomerID"] = df["CustomerID"].str.replace(
    r"\.0$", "", regex=True)

# Keep useful transactions even when descriptive information is missing.
df["CustomerID"] = df["CustomerID"].fillna("UNKNOWN")
df["Description"] = df["Description"].fillna("Unknown product")
df["Country"] = df["Country"].fillna("Unknown")

# Inspect duplicates before removing them.
duplicates = df.duplicated()
duplicates_removed = int(duplicates.sum())

# print("\duplicate rows to remove:", duplicates_removed)
# display(df.loc[duplicates].head(10))

# Keep the first occurrence and remove repeated copies.
df = df.drop_duplicates()

# Convert datatypes
df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
df["UnitPrice"] = pd.to_numeric(df["UnitPrice"], errors="coerce")
df["InvoiceDate"] = pd.to_datetime(
                                    df["InvoiceDate"],
                                    format="%Y-%m-%d %H:%M:%S",
                                    errors="coerce")


# Compare how many rows would be flagged at different quantity limits.
# Include both large positive and large negative quantities.
quantity_size = df["Quantity"].abs()

above_50 = (quantity_size > 50).sum()
above_100 = (quantity_size > 100).sum()
above_200 = (quantity_size > 200).sum()
above_500 = (quantity_size > 500).sum()

comparison = pd.DataFrame({
    "Quantity limit": [50, 100, 200, 500],
    "Rows flagged": [above_50, above_100, above_200, above_500]})

comparison["Percentage of rows"] = (
    comparison["Rows flagged"] / len(df) * 100
).round(2)

# print("Total rows:", len(df))
# display(comparison)


# Review transactions involving more than 100 units.
# Keep them: large sales, cancellations and adjustments may be legitimate.
quantity_threshold = 100

df["QuantityOutlier"] = (
    df["Quantity"].abs() > quantity_threshold
).astype(int)

# print("Rows flagged:", df["QuantityOutlier"].sum())
# print("Total rows retained:", len(df))

# display(
#     df.loc[df["QuantityOutlier"] == 1]
#     .sort_values("Quantity", key=lambda values: values.abs(), ascending=False)
#     .head(10)
# )



# # Confirm the number of rows after removing duplicates.
# print("Rows before cleaning:", rows_before)
# print("Duplicate rows removed:", duplicates_removed)
# print("Rows after cleaning:", len(df))

# print(
#     "Row counts reconcile:",
#     rows_before == len(df) + duplicates_removed
# )

# # Check whether any missing values remain.
# print("\nMissing values after cleaning:")
# display(df.isna().sum().rename("Missing count").to_frame())

# # Inspect a sample of the cleaned data.
# print("\nCleaned data preview:")
# display(df.head(10))



# 2.2. Validate the integrity and consistency of the data during the cleaning process.
required_fields = [
    "InvoiceNo", "StockCode", "InvoiceDate", "Quantity", "UnitPrice"
]

invalid = df[required_fields].isna().any(axis=1)
rejected = df.loc[invalid].copy()
df = df.loc[~invalid].copy()

# display(rejected.head(10))

# # Check consistency after cleaning.
# print("Duplicates remaining:", df.duplicated().sum())
# print("Negative prices:", (df["UnitPrice"] < 0).sum())
# print("Zero prices:", (df["UnitPrice"] == 0).sum())
# print("Non-whole quantities:", (df["Quantity"] % 1 != 0).sum())

# print("\nPrice records to review:")
# display(df.loc[df["UnitPrice"] <= 0].head(10))

# print("Rows retained:", len(df))
# display(df.head(10))


# ## 3. Data Transformation


# 3. Prepare the cleaned data for analysis.
# Note: Numeric and date conversions were completed in section 2.1

# Keep negative amounts so returns and cancellations can reduce sales totals
df["SalesAmount"] = (df["Quantity"] * df["UnitPrice"]).round(2)

# Identify negative quantities and cancellation invoices
df["IsReturn"] = (
    (df["Quantity"] < 0)
    | df["InvoiceNo"].str.startswith("C", na=False)
).astype(int)

# Keep the transaction date separately for possible daily analysis
df["SalesDate"] = df["InvoiceDate"].dt.normalize()

# Standardize descriptions
df["Description"] = df["Description"].str.upper()

# print("Rows after transformation:", len(df))

# display(df.dtypes.rename("Data type").to_frame())

# display(df[[
#         "InvoiceNo", "Description", "Quantity", "UnitPrice",
#         "SalesAmount", "IsReturn", "SalesDate"
#     ]].head(10)
# )


# ## 4. Data Warehouse Design


# 4. Create tables: 
#   products and customers describe each sale;
#   fact_sales stores one row per invoice line.

with sqlite3.connect(db_path) as conn:
    conn.execute("PRAGMA foreign_keys = ON")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS dim_product (
        StockCode TEXT PRIMARY KEY,
        Description TEXT
    );

    CREATE TABLE IF NOT EXISTS dim_customer (
        CustomerKey TEXT PRIMARY KEY
    );

    CREATE TABLE IF NOT EXISTS fact_sales (
        SalesLineID INTEGER PRIMARY KEY,
        InvoiceNo TEXT,
        StockCode TEXT,
        CustomerKey TEXT,
        Country TEXT,
        InvoiceDate TEXT,
        SalesDate TEXT,
        Quantity INTEGER,
        UnitPrice REAL,
        SalesAmount REAL,
        IsReturn INTEGER,
        QuantityOutlier INTEGER,
        FOREIGN KEY (StockCode) REFERENCES dim_product(StockCode),
        FOREIGN KEY (CustomerKey) REFERENCES dim_customer(CustomerKey)
    );
    """)

#Note: country is being kept in fact_sales table because many Customers are missing

# # Check created tables
# display(pd.read_sql_query("""
#         SELECT name
#         FROM sqlite_master
#         WHERE type = 'table'
#           AND name IN ('dim_product', 'dim_customer', 'fact_sales')
#         ORDER BY name
#     """, conn))


# ## 5. ETL Process

# 5.1. Load the prepared data into the warehouse.

# Keep one description per product
products = df[["StockCode", "Description"]].drop_duplicates(
    "StockCode", keep="last")

# Keep one record per customer identifier
customers = df[["CustomerID"]].drop_duplicates()
customers = customers.rename(columns={"CustomerID": "CustomerKey"})

# Keep one sales record per cleaned invoice line
sales = df[[
    "InvoiceNo", "StockCode", "CustomerID", "Country",
    "InvoiceDate", "SalesDate", "Quantity", "UnitPrice",
    "SalesAmount", "IsReturn", "QuantityOutlier"
    ]].copy()

sales = sales.rename(columns={"CustomerID": "CustomerKey"})

# Store dates consistently in SQLite
sales["InvoiceDate"] = sales["InvoiceDate"].dt.strftime("%Y-%m-%d %H:%M:%S")
sales["SalesDate"] = sales["SalesDate"].dt.strftime("%Y-%m-%d")

with sqlite3.connect(db_path) as conn:
    conn.execute("PRAGMA foreign_keys = ON")

    # Replace the previous load so rerunning does not duplicate sales & delete sales first because they reference products and customers
    conn.execute("DELETE FROM fact_sales")
    conn.execute("DELETE FROM dim_product")
    conn.execute("DELETE FROM dim_customer")

    # Load products and customers before the sales that reference them
    products.to_sql("dim_product", conn, if_exists="append", index=False)
    customers.to_sql("dim_customer", conn, if_exists="append", index=False)
    sales.to_sql("fact_sales", conn, if_exists="append", index=False)

    # Confirm that each table contains the expected number of rows.
    for table, expected in [
        ("dim_product", len(products)),
        ("dim_customer", len(customers)),
        ("fact_sales", len(sales))
    ]:
        loaded = conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

        print(f"{table}: {loaded} rows | Expected: {expected}")
        assert loaded == expected, f"Row count mismatch in {table}"

    # print("\nLoaded sales preview:")
    # display(pd.read_sql_query(
    #     "SELECT * FROM fact_sales LIMIT 10", conn
    # ))


# My computer is in Portuguese, and also I don't have experience doing scheduling as I would do this on Databricks or Azure Data Factory not on my computer, hence I'm leaving the scheduling task undone. 
# Although I know I would have to use Windows Task Scheduler


# ## 6. Partitioning and Indexing


# Implement & evaluate partitioning and indexing strategies
# Indexing creates a lookup structure so the database can find matching rows without checking the whole table

# Speed up queries that filter sales by date - 
with sqlite3.connect(db_path) as conn:
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_sales_date
        ON fact_sales(SalesDate)
    """)

    conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sales_product
            ON fact_sales(StockCode)
        """)
    
    conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sales_customer
            ON fact_sales(CustomerKey)
        """)


    # print("Indexes on the sales table:")
    # display(pd.read_sql_query(
    #     "PRAGMA index_list('fact_sales')", conn
    # ))


# Partitioning is unavailable in SQLite, so it was not implemented. For a larger deployment using a database that supports partitioning, monthly partitions on SalesDate would be a good option.


# ## 7. Data Quality Monitoring


# Set up monitoring mechanisms to track data quality over time & Establish alerts for anomalies or issues detected during the ETL process.

run_time = datetime.now().isoformat(timespec="seconds")

missing_customers = int((df["CustomerID"] == "UNKNOWN").sum())
non_positive_prices = int((df["UnitPrice"] <= 0).sum())
large_quantities = int(df["QuantityOutlier"].sum())

with sqlite3.connect(db_path) as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quality_history (
            RunTime TEXT,
            RowsRetained INTEGER,
            RowsRejected INTEGER,
            MissingCustomers INTEGER,
            NonPositivePrices INTEGER,
            LargeQuantities INTEGER
        )
    """)

    conn.execute("""
        INSERT INTO quality_history VALUES (?, ?, ?, ?, ?, ?)
    """, (
        run_time, len(df), len(rejected),
        missing_customers, non_positive_prices, large_quantities))

    print("Latest quality checks:")
    display(pd.read_sql_query("""
        SELECT * FROM quality_history
        ORDER BY RunTime DESC
        LIMIT 10
    """, conn))

# Display alerts in the executed notebook.
print("\nQuality alerts:")

if df.empty:
    print("ALERT: No rows remain after cleaning.")

if len(rejected) > 0:
    print(f"ALERT: {len(rejected)} rows were rejected.")

if missing_customers > 0:
    print(f"REVIEW: {missing_customers} rows have an unknown customer.")

if non_positive_prices > 0:
    print(
        f"REVIEW: {non_positive_prices} rows have zero or negative prices. "
        "These records were retained for inspection.")

if large_quantities > 0:
    print(f"REVIEW: {large_quantities} rows exceed the quantity threshold.")

if (
    not df.empty
    and len(rejected) == 0
    and missing_customers == 0
    and non_positive_prices == 0
    and large_quantities == 0):

    print("No issues detected by these checks")



# ## 8. Data Versioning

# Only know how to do this using Git



# ## 9. Metadata Management

# Never done this before



# ## 10. Performance Optimization

# Only know how to analyze this in Databricks

