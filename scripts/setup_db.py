#!/usr/bin/env python
"""Initialize MERIDIAN database with sample data."""

import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path("meridian.db")

def setup_database():
    """Create tables and insert sample data."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Sales domain tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customer_dim (
            customer_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            region TEXT NOT NULL,
            segment TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_dim (
            product_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_fact (
            sale_id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            quantity INTEGER NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customer_dim(customer_id),
            FOREIGN KEY (product_id) REFERENCES product_dim(product_id)
        )
    """)

    # Finance domain tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_dim (
            account_id INTEGER PRIMARY KEY,
            account_number TEXT NOT NULL,
            account_type TEXT NOT NULL,
            description TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ledger_fact (
            transaction_id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            debit_credit TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES account_dim(account_id)
        )
    """)

    # Operations domain tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS warehouse_dim (
            warehouse_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            location TEXT NOT NULL,
            capacity INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_fact (
            inventory_id INTEGER PRIMARY KEY,
            warehouse_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity_on_hand INTEGER NOT NULL,
            FOREIGN KEY (warehouse_id) REFERENCES warehouse_dim(warehouse_id),
            FOREIGN KEY (product_id) REFERENCES product_dim(product_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shipment_fact (
            shipment_id INTEGER PRIMARY KEY,
            origin_warehouse_id INTEGER NOT NULL,
            dest_warehouse_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            shipment_date TEXT NOT NULL,
            FOREIGN KEY (origin_warehouse_id) REFERENCES warehouse_dim(warehouse_id),
            FOREIGN KEY (dest_warehouse_id) REFERENCES warehouse_dim(warehouse_id),
            FOREIGN KEY (product_id) REFERENCES product_dim(product_id)
        )
    """)

    # Insert sample data
    print("Inserting sample data...")

    # Customers
    customers = [
        (1, "Acme Corp", "WEST", "Enterprise"),
        (2, "Beta Inc", "EAST", "Mid-market"),
        (3, "Gamma Ltd", "WEST", "SMB"),
        (4, "Delta Co", "NORTH", "Enterprise"),
        (5, "Epsilon LLC", "SOUTH", "SMB"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO customer_dim VALUES (?, ?, ?, ?)",
        customers
    )

    # Products
    products = [
        (101, "Widget A", "Electronics", 99.99),
        (102, "Widget B", "Electronics", 149.99),
        (103, "Gadget X", "Hardware", 299.99),
        (104, "Gadget Y", "Hardware", 199.99),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO product_dim VALUES (?, ?, ?, ?)",
        products
    )

    # Sales
    sales = [
        (1, 1, 101, 5000.0, 50, "2024-01-15"),
        (2, 1, 102, 3000.0, 20, "2024-01-16"),
        (3, 2, 101, 2000.0, 20, "2024-01-17"),
        (4, 3, 103, 4500.0, 15, "2024-01-18"),
        (5, 4, 104, 6000.0, 30, "2024-01-19"),
        (6, 5, 102, 1500.0, 10, "2024-01-20"),
        (7, 1, 104, 3500.0, 17, "2024-01-21"),
        (8, 2, 103, 5500.0, 18, "2024-01-22"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO sales_fact VALUES (?, ?, ?, ?, ?, ?)",
        sales
    )

    # Accounts
    accounts = [
        (1001, "1000-001", "REVENUE", "Main sales account"),
        (1002, "1000-002", "EXPENSE", "Operating expenses"),
        (1003, "2000-001", "ASSET", "Cash account"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO account_dim VALUES (?, ?, ?, ?)",
        accounts
    )

    # Ledger entries
    ledger = [
        (1, 1001, 5000.0, "CREDIT", "2024-01-15"),
        (2, 1002, 1000.0, "DEBIT", "2024-01-15"),
        (3, 1001, 3000.0, "CREDIT", "2024-01-16"),
        (4, 1003, 2000.0, "DEBIT", "2024-01-17"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO ledger_fact VALUES (?, ?, ?, ?, ?)",
        ledger
    )

    # Warehouses
    warehouses = [
        (1, "Warehouse A", "Los Angeles", 10000),
        (2, "Warehouse B", "Chicago", 8000),
        (3, "Warehouse C", "New York", 12000),
        (4, "Dallas DC", "Dallas", 9000),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO warehouse_dim VALUES (?, ?, ?, ?)",
        warehouses
    )

    # Inventory
    inventory = [
        (1, 1, 101, 500),
        (2, 1, 102, 300),
        (3, 2, 103, 450),
        (4, 2, 104, 600),
        (5, 3, 101, 250),
        (6, 3, 102, 400),
        (7, 4, 103, 320),
        (8, 4, 104, 180),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO inventory_fact VALUES (?, ?, ?, ?)",
        inventory
    )

    # Shipments
    shipments = [
        (1, 1, 2, 101, 100, "2024-01-15"),
        (2, 1, 3, 102, 50, "2024-01-16"),
        (3, 2, 3, 103, 200, "2024-01-17"),
        (4, 2, 1, 104, 75, "2024-01-18"),
        (5, 3, 1, 101, 150, "2024-01-19"),
        (6, 3, 2, 102, 80, "2024-01-20"),
        (7, 1, 2, 103, 120, "2024-01-21"),
        (8, 2, 3, 104, 90, "2024-01-22"),
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO shipment_fact VALUES (?, ?, ?, ?, ?, ?)",
        shipments
    )

    conn.commit()
    conn.close()
    print(f"✅ Database initialized at {DB_PATH}")
    print("Sample data inserted successfully!")

if __name__ == "__main__":
    setup_database()
