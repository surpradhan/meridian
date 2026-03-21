"""
Seed Data for View Registry

Initializes the view registry with sample database views and join relationships.
This provides test/demo data for Phase 1 development.

In production, this data would come from actual database metadata extraction.
"""

from app.views.models import ColumnSchema, ViewSchema, JoinRelationship
from app.views.registry import ViewRegistry


def initialize_registry(registry: ViewRegistry) -> None:
    """
    Initialize a registry with sample views and joins.

    Populates the registry with views across three domains:
    - Sales: Transaction and master data for sales operations
    - Finance: General ledger and accounting data
    - Operations: Inventory and logistics data

    Args:
        registry: ViewRegistry instance to populate
    """

    # ==================== SALES DOMAIN ====================

    # Sales fact table
    sales_fact = ViewSchema(
        name="sales_fact",
        view_type="fact",
        domain="sales",
        description="Daily sales transactions with amounts, quantities, and dates. "
        "Central fact table for all sales analysis.",
        columns=[
            ColumnSchema(
                name="sale_id",
                data_type="INT",
                is_nullable=False,
                is_primary_key=True,
                description="Unique identifier for each sale",
            ),
            ColumnSchema(
                name="customer_id",
                data_type="INT",
                is_nullable=False,
                is_foreign_key=True,
                description="Reference to customer dimension",
            ),
            ColumnSchema(
                name="product_id",
                data_type="INT",
                is_nullable=False,
                is_foreign_key=True,
                description="Reference to product dimension",
            ),
            ColumnSchema(
                name="amount",
                data_type="DECIMAL(12,2)",
                is_nullable=False,
                description="Sale amount in USD",
            ),
            ColumnSchema(
                name="quantity",
                data_type="INT",
                is_nullable=False,
                description="Number of units sold",
            ),
            ColumnSchema(
                name="date",
                data_type="DATE",
                is_nullable=False,
                description="Date of the sale",
            ),
        ],
        row_count=1000000,
    )
    registry.register_view(sales_fact)

    # Customer dimension
    customer_dim = ViewSchema(
        name="customer_dim",
        view_type="dimension",
        domain="sales",
        description="Master data for all customers. "
        "Contains demographic and classification information.",
        columns=[
            ColumnSchema(
                name="customer_id",
                data_type="INT",
                is_nullable=False,
                is_primary_key=True,
                description="Unique customer identifier",
            ),
            ColumnSchema(
                name="name",
                data_type="VARCHAR(255)",
                is_nullable=False,
                description="Customer company or person name",
            ),
            ColumnSchema(
                name="region",
                data_type="VARCHAR(50)",
                is_nullable=False,
                description="Geographic region (NORTH, SOUTH, EAST, WEST)",
            ),
            ColumnSchema(
                name="segment",
                data_type="VARCHAR(50)",
                is_nullable=False,
                description="Customer segment (ENTERPRISE, MID_MARKET, SMB)",
            ),
        ],
        row_count=50000,
    )
    registry.register_view(customer_dim)

    # Product dimension
    product_dim = ViewSchema(
        name="product_dim",
        view_type="dimension",
        domain="sales",
        description="Master data for all products. "
        "Contains pricing and classification information.",
        columns=[
            ColumnSchema(
                name="product_id",
                data_type="INT",
                is_nullable=False,
                is_primary_key=True,
                description="Unique product identifier",
            ),
            ColumnSchema(
                name="name",
                data_type="VARCHAR(255)",
                is_nullable=False,
                description="Product name or SKU",
            ),
            ColumnSchema(
                name="category",
                data_type="VARCHAR(100)",
                is_nullable=False,
                description="Product category",
            ),
            ColumnSchema(
                name="price",
                data_type="DECIMAL(10,2)",
                is_nullable=False,
                description="Current list price",
            ),
        ],
        row_count=10000,
    )
    registry.register_view(product_dim)

    # Register sales joins
    registry.register_join(
        JoinRelationship(
            source_view="sales_fact",
            target_view="customer_dim",
            source_columns=["customer_id"],
            target_columns=["customer_id"],
            relationship_type="many_to_one",
            description="Each sale belongs to one customer",
        )
    )

    registry.register_join(
        JoinRelationship(
            source_view="sales_fact",
            target_view="product_dim",
            source_columns=["product_id"],
            target_columns=["product_id"],
            relationship_type="many_to_one",
            description="Each sale is for one product",
        )
    )

    # ==================== FINANCE DOMAIN ====================

    # Ledger fact table
    ledger_fact = ViewSchema(
        name="ledger_fact",
        view_type="fact",
        domain="finance",
        description="General ledger transactions. "
        "Contains all debit and credit entries for accounting.",
        columns=[
            ColumnSchema(
                name="transaction_id",
                data_type="INT",
                is_nullable=False,
                is_primary_key=True,
                description="Unique transaction identifier",
            ),
            ColumnSchema(
                name="account_id",
                data_type="INT",
                is_nullable=False,
                is_foreign_key=True,
                description="Reference to account dimension",
            ),
            ColumnSchema(
                name="amount",
                data_type="DECIMAL(15,2)",
                is_nullable=False,
                description="Transaction amount",
            ),
            ColumnSchema(
                name="debit_credit",
                data_type="VARCHAR(10)",
                is_nullable=False,
                description="Transaction type (DEBIT or CREDIT)",
            ),
            ColumnSchema(
                name="date",
                data_type="DATE",
                is_nullable=False,
                description="Date of transaction",
            ),
        ],
        row_count=5000000,
    )
    registry.register_view(ledger_fact)

    # Account dimension
    account_dim = ViewSchema(
        name="account_dim",
        view_type="dimension",
        domain="finance",
        description="Chart of accounts master data. "
        "Contains all accounts for the general ledger.",
        columns=[
            ColumnSchema(
                name="account_id",
                data_type="INT",
                is_nullable=False,
                is_primary_key=True,
                description="Unique account identifier",
            ),
            ColumnSchema(
                name="account_number",
                data_type="VARCHAR(20)",
                is_nullable=False,
                description="Account code (e.g., 1000, 2000, 3000)",
            ),
            ColumnSchema(
                name="account_type",
                data_type="VARCHAR(50)",
                is_nullable=False,
                description="Account type (ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE)",
            ),
        ],
        row_count=500,
    )
    registry.register_view(account_dim)

    # Register finance joins
    registry.register_join(
        JoinRelationship(
            source_view="ledger_fact",
            target_view="account_dim",
            source_columns=["account_id"],
            target_columns=["account_id"],
            relationship_type="many_to_one",
            description="Each ledger entry is recorded to one account",
        )
    )

    # ==================== OPERATIONS DOMAIN ====================

    # Inventory fact table
    inventory_fact = ViewSchema(
        name="inventory_fact",
        view_type="fact",
        domain="operations",
        description="Current inventory levels by warehouse and product. "
        "Updated daily with stock movements.",
        columns=[
            ColumnSchema(
                name="inventory_id",
                data_type="INT",
                is_nullable=False,
                is_primary_key=True,
                description="Unique inventory record identifier",
            ),
            ColumnSchema(
                name="warehouse_id",
                data_type="INT",
                is_nullable=False,
                is_foreign_key=True,
                description="Reference to warehouse dimension",
            ),
            ColumnSchema(
                name="product_id",
                data_type="INT",
                is_nullable=False,
                is_foreign_key=True,
                description="Reference to product dimension",
            ),
            ColumnSchema(
                name="quantity_on_hand",
                data_type="INT",
                is_nullable=False,
                description="Current quantity in stock",
            ),
        ],
        row_count=50000,
    )
    registry.register_view(inventory_fact)

    # Warehouse dimension
    warehouse_dim = ViewSchema(
        name="warehouse_dim",
        view_type="dimension",
        domain="operations",
        description="Master data for all warehouses. "
        "Contains location and capacity information.",
        columns=[
            ColumnSchema(
                name="warehouse_id",
                data_type="INT",
                is_nullable=False,
                is_primary_key=True,
                description="Unique warehouse identifier",
            ),
            ColumnSchema(
                name="name",
                data_type="VARCHAR(255)",
                is_nullable=False,
                description="Warehouse name",
            ),
            ColumnSchema(
                name="location",
                data_type="VARCHAR(255)",
                is_nullable=False,
                description="Warehouse location (city, state)",
            ),
            ColumnSchema(
                name="capacity",
                data_type="INT",
                is_nullable=False,
                description="Maximum storage capacity",
            ),
        ],
        row_count=20,
    )
    registry.register_view(warehouse_dim)

    # Shipment fact table
    shipment_fact = ViewSchema(
        name="shipment_fact",
        view_type="fact",
        domain="operations",
        description="Inter-warehouse shipments and transfers. "
        "Tracks inventory movement between locations.",
        columns=[
            ColumnSchema(
                name="shipment_id",
                data_type="INT",
                is_nullable=False,
                is_primary_key=True,
                description="Unique shipment identifier",
            ),
            ColumnSchema(
                name="origin_warehouse_id",
                data_type="INT",
                is_nullable=False,
                is_foreign_key=True,
                description="Source warehouse",
            ),
            ColumnSchema(
                name="dest_warehouse_id",
                data_type="INT",
                is_nullable=False,
                is_foreign_key=True,
                description="Destination warehouse",
            ),
            ColumnSchema(
                name="product_id",
                data_type="INT",
                is_nullable=False,
                is_foreign_key=True,
                description="Product being shipped",
            ),
            ColumnSchema(
                name="quantity",
                data_type="INT",
                is_nullable=False,
                description="Quantity shipped",
            ),
            ColumnSchema(
                name="shipment_date",
                data_type="DATE",
                is_nullable=False,
                description="Date of shipment",
            ),
        ],
        row_count=100000,
    )
    registry.register_view(shipment_fact)

    # Register operations joins
    registry.register_join(
        JoinRelationship(
            source_view="inventory_fact",
            target_view="warehouse_dim",
            source_columns=["warehouse_id"],
            target_columns=["warehouse_id"],
            relationship_type="many_to_one",
            description="Each inventory record belongs to one warehouse",
        )
    )

    registry.register_join(
        JoinRelationship(
            source_view="inventory_fact",
            target_view="product_dim",
            source_columns=["product_id"],
            target_columns=["product_id"],
            relationship_type="many_to_one",
            description="Each inventory record tracks one product",
        )
    )

    registry.register_join(
        JoinRelationship(
            source_view="shipment_fact",
            target_view="warehouse_dim",
            source_columns=["origin_warehouse_id"],
            target_columns=["warehouse_id"],
            relationship_type="many_to_one",
            description="Each shipment originates from one warehouse",
        )
    )

    registry.register_join(
        JoinRelationship(
            source_view="shipment_fact",
            target_view="product_dim",
            source_columns=["product_id"],
            target_columns=["product_id"],
            relationship_type="many_to_one",
            description="Each shipment contains one product type",
        )
    )
