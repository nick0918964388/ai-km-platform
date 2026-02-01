# Data Model: 結構化資料查詢

**Feature**: 003-structured-data-query
**Date**: 2026-02-01

## Entity Relationship Diagram

```
┌─────────────────┐       ┌──────────────────┐
│    Vehicle      │───┬───│   FaultRecord    │
│ (車輛基本資料)   │   │   │  (故障歷程)       │
└─────────────────┘   │   └──────────────────┘
                      │
                      ├───┌──────────────────┐
                      │   │MaintenanceRecord │
                      │   │  (檢修歷程)       │
                      │   └────────┬─────────┘
                      │            │
                      │            │
                      ├───┌──────────────────┐
                      │   │   UsageRecord    │
                      │   │  (使用歷程)       │
                      │   └──────────────────┘
                      │
                      └───┌──────────────────┐
                          │   CostRecord     │
                          │  (維修成本)       │
                          └──────────────────┘

┌──────────────────┐       ┌──────────────────┐
│MaintenanceRecord │───────│    PartsUsed     │
│  (檢修歷程)       │       │  (用料歷程)       │
└──────────────────┘       └────────┬─────────┘
                                    │
                           ┌────────┴─────────┐
                           │  PartsInventory  │
                           │   (零件庫存)      │
                           └──────────────────┘
```

---

## Entities

### 1. Vehicle (車輛基本資料)

**Table Name**: `vehicles`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | 主鍵 |
| vehicle_code | VARCHAR(20) | UNIQUE, NOT NULL, INDEX | 車輛編號 (如 EMU801) |
| vehicle_type | VARCHAR(50) | NOT NULL | 車型 (如 EMU800 系列) |
| manufacturer | VARCHAR(100) | | 製造商 |
| manufacture_year | INTEGER | | 製造年份 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'active' | 狀態: active/maintenance/retired |
| depot | VARCHAR(50) | INDEX | 所屬機務段 |
| last_maintenance_date | DATE | | 最後保養日期 |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | 建立時間 |
| updated_at | TIMESTAMP | NOT NULL | 更新時間 |

**Indexes**:
- `idx_vehicles_code` ON (vehicle_code)
- `idx_vehicles_depot` ON (depot)
- `idx_vehicles_status` ON (status)

---

### 2. FaultRecord (故障歷程)

**Table Name**: `fault_records`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | 主鍵 |
| vehicle_id | UUID | FK → vehicles.id, INDEX | 車輛 ID |
| fault_code | VARCHAR(30) | NOT NULL | 故障編號 |
| fault_date | TIMESTAMP | NOT NULL, INDEX | 故障發生時間 |
| fault_type | VARCHAR(50) | NOT NULL, INDEX | 故障類型 (如 轉向架、煞車、電氣) |
| severity | VARCHAR(20) | NOT NULL | 嚴重程度: critical/major/minor |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'open' | 處理狀態: open/in_progress/resolved |
| description | TEXT | | 故障描述 |
| resolution | TEXT | | 處理方式 |
| resolved_at | TIMESTAMP | | 解決時間 |
| reported_by | VARCHAR(100) | | 回報人員 |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | 建立時間 |
| updated_at | TIMESTAMP | NOT NULL | 更新時間 |

**Indexes**:
- `idx_fault_vehicle` ON (vehicle_id)
- `idx_fault_date` ON (fault_date)
- `idx_fault_type` ON (fault_type)
- `idx_fault_status` ON (status)

---

### 3. MaintenanceRecord (檢修歷程)

**Table Name**: `maintenance_records`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | 主鍵 |
| vehicle_id | UUID | FK → vehicles.id, INDEX | 車輛 ID |
| maintenance_code | VARCHAR(30) | NOT NULL | 檢修編號 |
| maintenance_date | DATE | NOT NULL, INDEX | 檢修日期 |
| maintenance_type | VARCHAR(50) | NOT NULL | 檢修類型: routine/corrective/preventive |
| technician_id | VARCHAR(50) | INDEX | 執行技師 ID |
| technician_name | VARCHAR(100) | | 技師姓名 |
| status | VARCHAR(20) | NOT NULL, DEFAULT 'scheduled' | 狀態: scheduled/in_progress/completed |
| work_hours | DECIMAL(5,2) | | 工時 |
| notes | TEXT | | 檢修備註 |
| completed_at | TIMESTAMP | | 完成時間 |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | 建立時間 |
| updated_at | TIMESTAMP | NOT NULL | 更新時間 |

**Indexes**:
- `idx_maintenance_vehicle` ON (vehicle_id)
- `idx_maintenance_date` ON (maintenance_date)
- `idx_maintenance_technician` ON (technician_id)

---

### 4. UsageRecord (使用歷程)

**Table Name**: `usage_records`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | 主鍵 |
| vehicle_id | UUID | FK → vehicles.id, INDEX | 車輛 ID |
| record_date | DATE | NOT NULL, INDEX | 紀錄日期 |
| mileage | DECIMAL(10,2) | | 運行里程 (公里) |
| running_hours | DECIMAL(8,2) | | 運行時數 |
| trip_count | INTEGER | | 營運班次數 |
| route | VARCHAR(100) | | 營運路線 |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | 建立時間 |

**Indexes**:
- `idx_usage_vehicle` ON (vehicle_id)
- `idx_usage_date` ON (record_date)

---

### 5. PartsUsed (用料歷程)

**Table Name**: `parts_used`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | 主鍵 |
| maintenance_id | UUID | FK → maintenance_records.id, INDEX | 檢修紀錄 ID |
| part_id | UUID | FK → parts_inventory.id, INDEX | 零件 ID |
| part_code | VARCHAR(50) | NOT NULL | 零件編號 |
| part_name | VARCHAR(200) | NOT NULL | 零件名稱 |
| quantity | INTEGER | NOT NULL | 使用數量 |
| unit_price | DECIMAL(10,2) | | 單價 |
| total_price | DECIMAL(12,2) | | 總價 |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | 建立時間 |

**Indexes**:
- `idx_parts_used_maintenance` ON (maintenance_id)
- `idx_parts_used_part` ON (part_id)

---

### 6. CostRecord (維修成本)

**Table Name**: `cost_records`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | 主鍵 |
| vehicle_id | UUID | FK → vehicles.id, INDEX | 車輛 ID |
| period_start | DATE | NOT NULL | 統計期間起始 |
| period_end | DATE | NOT NULL | 統計期間結束 |
| labor_cost | DECIMAL(12,2) | NOT NULL, DEFAULT 0 | 工時成本 |
| material_cost | DECIMAL(12,2) | NOT NULL, DEFAULT 0 | 材料成本 |
| external_cost | DECIMAL(12,2) | NOT NULL, DEFAULT 0 | 外包成本 |
| total_cost | DECIMAL(12,2) | NOT NULL | 總成本 |
| cost_type | VARCHAR(30) | INDEX | 成本類別: routine/repair/overhaul |
| notes | TEXT | | 備註 |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | 建立時間 |
| updated_at | TIMESTAMP | NOT NULL | 更新時間 |

**Indexes**:
- `idx_cost_vehicle` ON (vehicle_id)
- `idx_cost_period` ON (period_start, period_end)

---

### 7. PartsInventory (零件庫存)

**Table Name**: `parts_inventory`

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PK | 主鍵 |
| part_code | VARCHAR(50) | UNIQUE, NOT NULL, INDEX | 零件編號 |
| part_name | VARCHAR(200) | NOT NULL | 零件名稱 |
| category | VARCHAR(50) | INDEX | 零件類別 |
| current_stock | INTEGER | NOT NULL, DEFAULT 0 | 現有庫存 |
| safety_stock | INTEGER | NOT NULL, DEFAULT 0 | 安全庫存 |
| unit | VARCHAR(20) | NOT NULL | 單位 |
| unit_price | DECIMAL(10,2) | | 單價 |
| location | VARCHAR(100) | | 存放位置 |
| supplier | VARCHAR(200) | | 供應商 |
| last_restock_date | DATE | | 最後補貨日期 |
| created_at | TIMESTAMP | NOT NULL, DEFAULT NOW() | 建立時間 |
| updated_at | TIMESTAMP | NOT NULL | 更新時間 |

**Indexes**:
- `idx_inventory_code` ON (part_code)
- `idx_inventory_category` ON (category)
- `idx_inventory_low_stock` ON (current_stock, safety_stock) WHERE current_stock <= safety_stock

---

## Validation Rules

### Vehicle
- `vehicle_code`: 必須符合格式 `^[A-Z]{3}[0-9]{3,4}$` (如 EMU801)
- `status`: 必須為 active/maintenance/retired 之一
- `manufacture_year`: 1990 - 當前年份

### FaultRecord
- `severity`: 必須為 critical/major/minor 之一
- `status`: 必須為 open/in_progress/resolved 之一
- `resolved_at`: 只有當 status = resolved 時才可填寫

### MaintenanceRecord
- `maintenance_type`: 必須為 routine/corrective/preventive 之一
- `status`: 必須為 scheduled/in_progress/completed 之一
- `work_hours`: 必須 >= 0

### PartsInventory
- `current_stock`: 必須 >= 0
- `safety_stock`: 必須 >= 0

---

## State Transitions

### FaultRecord Status
```
     ┌─────────┐
     │  open   │
     └────┬────┘
          │ assign technician
          v
   ┌──────────────┐
   │ in_progress  │
   └──────┬───────┘
          │ resolution completed
          v
    ┌───────────┐
    │ resolved  │
    └───────────┘
```

### MaintenanceRecord Status
```
   ┌───────────┐
   │ scheduled │
   └─────┬─────┘
         │ start work
         v
  ┌──────────────┐
  │ in_progress  │
  └──────┬───────┘
         │ finish work
         v
   ┌───────────┐
   │ completed │
   └───────────┘
```

---

## Sample Data

### Vehicle
```json
{
  "id": "uuid-v1",
  "vehicle_code": "EMU801",
  "vehicle_type": "EMU800 系列",
  "manufacturer": "日立製作所",
  "manufacture_year": 2012,
  "status": "active",
  "depot": "新左營機務段"
}
```

### FaultRecord
```json
{
  "id": "uuid-f1",
  "vehicle_id": "uuid-v1",
  "fault_code": "FLT-2025-0042",
  "fault_date": "2025-12-15T10:30:00Z",
  "fault_type": "轉向架",
  "severity": "major",
  "status": "resolved",
  "description": "轉向架異音，行駛時有異常震動"
}
```
