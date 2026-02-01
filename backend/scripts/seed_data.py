"""
Seed script for structured data tables.
Populates test data for development and demo.
"""

import asyncio
import sys
from datetime import datetime, date, timedelta
from uuid import uuid4
import random

# Add parent directory to path for imports
sys.path.insert(0, '/Users/nickall/Projects/ai-km-platform/backend')

from app.db.session import async_session_maker
from app.models.structured import (
    Vehicle,
    FaultRecord,
    MaintenanceRecord,
    UsageRecord,
    PartsUsed,
    PartsInventory,
    CostRecord,
)


# Sample data
VEHICLES = [
    {"vehicle_code": "EMU801", "vehicle_type": "EMU800系列", "manufacturer": "日立", "manufacture_year": 2012, "depot": "新竹機務段"},
    {"vehicle_code": "EMU802", "vehicle_type": "EMU800系列", "manufacturer": "日立", "manufacture_year": 2012, "depot": "新竹機務段"},
    {"vehicle_code": "EMU803", "vehicle_type": "EMU800系列", "manufacturer": "日立", "manufacture_year": 2013, "depot": "新竹機務段"},
    {"vehicle_code": "EMU804", "vehicle_type": "EMU800系列", "manufacturer": "日立", "manufacture_year": 2013, "depot": "台中機務段"},
    {"vehicle_code": "EMU805", "vehicle_type": "EMU800系列", "manufacturer": "日立", "manufacture_year": 2014, "depot": "台中機務段"},
    {"vehicle_code": "TEMU2001", "vehicle_type": "TEMU2000型", "manufacturer": "日立", "manufacture_year": 2018, "depot": "花蓮機務段"},
    {"vehicle_code": "TEMU2002", "vehicle_type": "TEMU2000型", "manufacturer": "日立", "manufacture_year": 2018, "depot": "花蓮機務段"},
    {"vehicle_code": "EMC301", "vehicle_type": "EMC300型", "manufacturer": "川崎重工", "manufacture_year": 2020, "depot": "高雄機務段"},
    {"vehicle_code": "EMC302", "vehicle_type": "EMC300型", "manufacturer": "川崎重工", "manufacture_year": 2020, "depot": "高雄機務段"},
    {"vehicle_code": "EMC303", "vehicle_type": "EMC300型", "manufacturer": "川崎重工", "manufacture_year": 2021, "depot": "高雄機務段"},
]

FAULT_TYPES = ["轉向架", "煞車系統", "電氣系統", "空調系統", "門機系統", "推進系統", "集電弓"]
SEVERITY_LEVELS = ["critical", "major", "minor"]
MAINTENANCE_TYPES = ["scheduled", "unscheduled", "emergency"]

PARTS = [
    {"part_number": "BRK-001", "part_name": "煞車來令片", "category": "煞車系統", "unit_price": 15000},
    {"part_number": "BRK-002", "part_name": "煞車碟盤", "category": "煞車系統", "unit_price": 45000},
    {"part_number": "ELE-001", "part_name": "主變流器模組", "category": "電氣系統", "unit_price": 850000},
    {"part_number": "ELE-002", "part_name": "輔助電源裝置", "category": "電氣系統", "unit_price": 320000},
    {"part_number": "AIR-001", "part_name": "空調壓縮機", "category": "空調系統", "unit_price": 180000},
    {"part_number": "AIR-002", "part_name": "冷媒", "category": "空調系統", "unit_price": 5000},
    {"part_number": "DOO-001", "part_name": "車門馬達", "category": "門機系統", "unit_price": 65000},
    {"part_number": "DOO-002", "part_name": "門機控制器", "category": "門機系統", "unit_price": 42000},
    {"part_number": "BOG-001", "part_name": "轉向架軸承", "category": "轉向架", "unit_price": 120000},
    {"part_number": "BOG-002", "part_name": "避震器", "category": "轉向架", "unit_price": 85000},
    {"part_number": "PAN-001", "part_name": "集電弓碳條", "category": "集電弓", "unit_price": 8500},
    {"part_number": "PAN-002", "part_name": "集電弓彈簧", "category": "集電弓", "unit_price": 12000},
]


async def seed_vehicles(session) -> dict:
    """Seed vehicles and return id mapping"""
    vehicle_map = {}
    for v in VEHICLES:
        vehicle = Vehicle(
            id=uuid4(),
            status="active",
            last_maintenance_date=date.today() - timedelta(days=random.randint(30, 180)),
            **v
        )
        session.add(vehicle)
        vehicle_map[v["vehicle_code"]] = vehicle.id
    await session.flush()
    print(f"✅ Created {len(VEHICLES)} vehicles")
    return vehicle_map


async def seed_parts_inventory(session) -> dict:
    """Seed parts inventory and return id mapping"""
    part_map = {}
    for p in PARTS:
        part = PartsInventory(
            id=uuid4(),
            quantity_on_hand=random.randint(5, 50),
            minimum_quantity=random.randint(3, 10),
            supplier=random.choice(["日立", "川崎重工", "台灣鐵路工業"]),
            location=random.choice(["A區倉庫", "B區倉庫", "C區倉庫"]),
            **p
        )
        session.add(part)
        part_map[p["part_number"]] = (part.id, p["part_name"], p["unit_price"])
    await session.flush()
    print(f"✅ Created {len(PARTS)} parts in inventory")
    return part_map


async def seed_fault_records(session, vehicle_map: dict):
    """Seed fault records"""
    faults_created = 0
    for code, vehicle_id in vehicle_map.items():
        # Create 3-8 fault records per vehicle
        for _ in range(random.randint(3, 8)):
            fault_date = datetime.now() - timedelta(days=random.randint(1, 365))
            status = random.choice(["open", "in_progress", "resolved"])
            fault = FaultRecord(
                id=uuid4(),
                vehicle_id=vehicle_id,
                fault_code=f"F-{random.randint(10000, 99999)}",
                fault_date=fault_date,
                fault_type=random.choice(FAULT_TYPES),
                severity=random.choice(SEVERITY_LEVELS),
                status=status,
                description=f"車輛 {code} 於營運中發生異常，需進行檢修",
                resolution="已完成檢修並恢復正常" if status == "resolved" else None,
                resolved_at=fault_date + timedelta(days=random.randint(1, 14)) if status == "resolved" else None,
                reported_by=random.choice(["張技師", "李技師", "王技師", "陳技師"]),
            )
            session.add(fault)
            faults_created += 1
    await session.flush()
    print(f"✅ Created {faults_created} fault records")


async def seed_maintenance_records(session, vehicle_map: dict, part_map: dict):
    """Seed maintenance records and parts used"""
    maintenance_created = 0
    parts_used_created = 0
    
    for code, vehicle_id in vehicle_map.items():
        # Create 5-12 maintenance records per vehicle
        for _ in range(random.randint(5, 12)):
            maintenance_date = datetime.now() - timedelta(days=random.randint(1, 365))
            status = random.choice(["pending", "in_progress", "completed"])
            maintenance = MaintenanceRecord(
                id=uuid4(),
                vehicle_id=vehicle_id,
                maintenance_code=f"M-{random.randint(10000, 99999)}",
                maintenance_type=random.choice(MAINTENANCE_TYPES),
                maintenance_date=maintenance_date,
                completed_date=maintenance_date + timedelta(days=random.randint(1, 7)) if status == "completed" else None,
                status=status,
                description=f"車輛 {code} 定期/非定期檢修",
                work_performed="完成各項檢修作業" if status == "completed" else None,
                labor_hours=random.uniform(2, 24),
                labor_cost=random.uniform(5000, 50000),
                technician=random.choice(["張技師", "李技師", "王技師", "陳技師"]),
                supervisor=random.choice(["林主任", "黃主任"]),
            )
            session.add(maintenance)
            await session.flush()
            maintenance_created += 1
            
            # Add 1-5 parts used per maintenance
            if status == "completed":
                used_parts = random.sample(list(part_map.items()), random.randint(1, 5))
                for part_number, (part_id, part_name, unit_price) in used_parts:
                    qty = random.randint(1, 4)
                    parts_used = PartsUsed(
                        id=uuid4(),
                        maintenance_id=maintenance.id,
                        part_id=part_id,
                        part_number=part_number,
                        part_name=part_name,
                        quantity=qty,
                        unit_cost=unit_price,
                        total_cost=unit_price * qty,
                    )
                    session.add(parts_used)
                    parts_used_created += 1
    
    await session.flush()
    print(f"✅ Created {maintenance_created} maintenance records")
    print(f"✅ Created {parts_used_created} parts used records")


async def seed_usage_records(session, vehicle_map: dict):
    """Seed usage records"""
    usage_created = 0
    for code, vehicle_id in vehicle_map.items():
        # Create 30 days of usage records
        for days_ago in range(30):
            record_date = date.today() - timedelta(days=days_ago)
            usage = UsageRecord(
                id=uuid4(),
                vehicle_id=vehicle_id,
                record_date=record_date,
                mileage=random.randint(200, 800),
                operating_hours=random.uniform(8, 18),
                trips_count=random.randint(4, 12),
                route=random.choice(["西部幹線", "東部幹線", "南迴線", "北迴線"]),
                electricity_consumption=random.uniform(500, 2000),
            )
            session.add(usage)
            usage_created += 1
    await session.flush()
    print(f"✅ Created {usage_created} usage records")


async def seed_cost_records(session, vehicle_map: dict):
    """Seed cost records"""
    cost_created = 0
    cost_types = ["labor", "parts", "external", "other"]
    
    for code, vehicle_id in vehicle_map.items():
        # Create 10-20 cost records per vehicle
        for _ in range(random.randint(10, 20)):
            record_date = date.today() - timedelta(days=random.randint(1, 365))
            cost_type = random.choice(cost_types)
            cost = CostRecord(
                id=uuid4(),
                vehicle_id=vehicle_id,
                record_date=record_date,
                cost_type=cost_type,
                category=random.choice(FAULT_TYPES),
                description=f"車輛 {code} {cost_type} 費用",
                amount=random.uniform(5000, 500000),
                reference_id=f"REF-{random.randint(10000, 99999)}",
                vendor=random.choice(["日立", "川崎重工", "台灣鐵路工業", None]),
                approved_by=random.choice(["林主任", "黃主任", "處長"]),
            )
            session.add(cost)
            cost_created += 1
    await session.flush()
    print(f"✅ Created {cost_created} cost records")


async def main():
    print("🚀 Starting seed data creation...")
    print("=" * 50)
    
    async with async_session_maker() as session:
        try:
            # Seed in order (respecting foreign keys)
            vehicle_map = await seed_vehicles(session)
            part_map = await seed_parts_inventory(session)
            await seed_fault_records(session, vehicle_map)
            await seed_maintenance_records(session, vehicle_map, part_map)
            await seed_usage_records(session, vehicle_map)
            await seed_cost_records(session, vehicle_map)
            
            await session.commit()
            print("=" * 50)
            print("✅ All seed data created successfully!")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Error: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
