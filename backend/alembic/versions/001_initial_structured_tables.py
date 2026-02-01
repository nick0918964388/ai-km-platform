"""Initial structured tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create vehicles table
    op.create_table(
        'vehicles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vehicle_code', sa.String(20), nullable=False),
        sa.Column('vehicle_type', sa.String(50), nullable=False),
        sa.Column('manufacturer', sa.String(100), nullable=True),
        sa.Column('manufacture_year', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('depot', sa.String(50), nullable=True),
        sa.Column('last_maintenance_date', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('vehicle_code')
    )
    op.create_index('idx_vehicles_code', 'vehicles', ['vehicle_code'])
    op.create_index('idx_vehicles_depot', 'vehicles', ['depot'])
    op.create_index('idx_vehicles_status', 'vehicles', ['status'])

    # Create fault_records table
    op.create_table(
        'fault_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vehicle_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('fault_code', sa.String(30), nullable=False),
        sa.Column('fault_date', sa.DateTime(), nullable=False),
        sa.Column('fault_type', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('resolution', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('reported_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_fault_vehicle', 'fault_records', ['vehicle_id'])
    op.create_index('idx_fault_date', 'fault_records', ['fault_date'])
    op.create_index('idx_fault_type', 'fault_records', ['fault_type'])
    op.create_index('idx_fault_status', 'fault_records', ['status'])

    # Create maintenance_records table
    op.create_table(
        'maintenance_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vehicle_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('maintenance_code', sa.String(30), nullable=False),
        sa.Column('maintenance_type', sa.String(50), nullable=False),
        sa.Column('maintenance_date', sa.DateTime(), nullable=False),
        sa.Column('completed_date', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('work_performed', sa.Text(), nullable=True),
        sa.Column('labor_hours', sa.Numeric(10, 2), nullable=True),
        sa.Column('labor_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('technician', sa.String(100), nullable=True),
        sa.Column('supervisor', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_maintenance_vehicle', 'maintenance_records', ['vehicle_id'])
    op.create_index('idx_maintenance_date', 'maintenance_records', ['maintenance_date'])
    op.create_index('idx_maintenance_type', 'maintenance_records', ['maintenance_type'])
    op.create_index('idx_maintenance_status', 'maintenance_records', ['status'])

    # Create usage_records table
    op.create_table(
        'usage_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vehicle_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('record_date', sa.Date(), nullable=False),
        sa.Column('mileage', sa.Integer(), nullable=True),
        sa.Column('operating_hours', sa.Numeric(10, 2), nullable=True),
        sa.Column('trips_count', sa.Integer(), nullable=True),
        sa.Column('route', sa.String(100), nullable=True),
        sa.Column('fuel_consumption', sa.Numeric(10, 2), nullable=True),
        sa.Column('electricity_consumption', sa.Numeric(12, 2), nullable=True),
        sa.Column('notes', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_usage_vehicle', 'usage_records', ['vehicle_id'])
    op.create_index('idx_usage_date', 'usage_records', ['record_date'])
    op.create_index('idx_usage_vehicle_date', 'usage_records', ['vehicle_id', 'record_date'])

    # Create parts_inventory table
    op.create_table(
        'parts_inventory',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('part_number', sa.String(50), nullable=False),
        sa.Column('part_name', sa.String(200), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('quantity_on_hand', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('minimum_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=True),
        sa.Column('supplier', sa.String(200), nullable=True),
        sa.Column('location', sa.String(100), nullable=True),
        sa.Column('last_restock_date', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('part_number')
    )
    op.create_index('idx_parts_number', 'parts_inventory', ['part_number'])
    op.create_index('idx_parts_category', 'parts_inventory', ['category'])
    op.create_index('idx_parts_low_stock', 'parts_inventory', ['quantity_on_hand', 'minimum_quantity'])

    # Create parts_used table
    op.create_table(
        'parts_used',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('maintenance_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('part_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('part_number', sa.String(50), nullable=False),
        sa.Column('part_name', sa.String(200), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('unit_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('total_cost', sa.Numeric(12, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['maintenance_id'], ['maintenance_records.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['part_id'], ['parts_inventory.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_parts_used_maintenance', 'parts_used', ['maintenance_id'])
    op.create_index('idx_parts_used_part', 'parts_used', ['part_id'])

    # Create cost_records table
    op.create_table(
        'cost_records',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vehicle_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('record_date', sa.Date(), nullable=False),
        sa.Column('cost_type', sa.String(50), nullable=False),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('amount', sa.Numeric(14, 2), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='TWD'),
        sa.Column('reference_id', sa.String(50), nullable=True),
        sa.Column('vendor', sa.String(200), nullable=True),
        sa.Column('invoice_number', sa.String(50), nullable=True),
        sa.Column('approved_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cost_vehicle', 'cost_records', ['vehicle_id'])
    op.create_index('idx_cost_date', 'cost_records', ['record_date'])
    op.create_index('idx_cost_type', 'cost_records', ['cost_type'])
    op.create_index('idx_cost_type_date', 'cost_records', ['cost_type', 'record_date'])
    op.create_index('idx_cost_vehicle_date', 'cost_records', ['vehicle_id', 'record_date'])


def downgrade() -> None:
    op.drop_table('cost_records')
    op.drop_table('parts_used')
    op.drop_table('parts_inventory')
    op.drop_table('usage_records')
    op.drop_table('maintenance_records')
    op.drop_table('fault_records')
    op.drop_table('vehicles')
