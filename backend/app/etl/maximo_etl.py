"""Maximo → PostgreSQL ETL script.

Usage:
    python maximo_etl.py --sync assets
    python maximo_etl.py --sync pmwo
    python maximo_etl.py --sync cmwo
    python maximo_etl.py --sync fnm
    python maximo_etl.py --sync all
"""
import os
import base64
import argparse
import logging
from datetime import datetime
from typing import Optional

import requests
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
MAXIMO_URL   = os.environ.get("MAXIMO_URL",   "http://tra.webtw.xyz:8888/maximo")
MAXIMO_USER  = os.environ.get("MAXIMO_USER",  "MAX_NICK")
MAXIMO_PASS  = os.environ.get("MAXIMO_PASS",  "zaq1xsW2")
# Strip async driver prefix so psycopg2 can connect
_raw_db_url = os.environ.get("DATABASE_URL", "postgresql://aikm:aikm@postgres:5432/aikm")
DATABASE_URL = _raw_db_url.replace("postgresql+asyncpg://", "postgresql://") \
                           .replace("postgresql+psycopg2://", "postgresql://")

PAGE_SIZE = 100

def _headers():
    token = base64.b64encode(f"{MAXIMO_USER}:{MAXIMO_PASS}".encode()).decode()
    return {"Accept": "application/json", "maxauth": token}

def _get_all(path: str, select: str, where: Optional[str] = None):
    """Paginate through all records from a Maximo OSLC endpoint."""
    records = []
    url = f"{MAXIMO_URL}/oslc/os/{path}"
    params = {
        "oslc.select": select,
        "oslc.pageSize": PAGE_SIZE,
        "lean": "1",
    }
    if where:
        params["oslc.where"] = where
    page = 1
    while True:
        params["pageno"] = page
        resp = requests.get(url, headers=_headers(), params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        members = data.get("member", [])
        records.extend(members)
        log.info("  page %d: +%d records (total so far: %d)", page, len(members), len(records))
        next_page = data.get("responseInfo", {}).get("nextPage")
        if not next_page or len(members) < PAGE_SIZE:
            break
        page += 1
    return records


# ── Asset sync ───────────────────────────────────────────────────────────────
ASSET_SELECT = ",".join([
    "assetnum", "eq24", "EQ4", "EQ3", "EQ11",
    "EQ1", "EQ2", "EQ8", "STATUS", "status_description",
    "zz_cargroup", "zz_position", "eq9",
    "installdate", "EXPECTEDLIFE", "manufacturer",
    "FAILURECODE", "parent",
])

def sync_assets(conn):
    log.info("Syncing assets...")
    records = _get_all("mxasset", ASSET_SELECT, where='eq9 in ["車輛","車組"]')

    rows = []
    for r in records:
        rows.append((
            r.get("assetnum"),
            r.get("eq24"),
            r.get("EQ4") or r.get("eq4"),       # 車型
            r.get("EQ3") or r.get("eq3"),        # 車種
            r.get("EQ11") or r.get("eq11"),      # 車輛類別
            r.get("EQ1") or r.get("eq1"),        # 維修機廠
            r.get("EQ2") or r.get("eq2"),        # 配屬段別
            r.get("EQ8") or r.get("eq8"),        # 借用段別
            r.get("STATUS") or r.get("status"),
            r.get("status_description"),
            r.get("zz_cargroup"),
            r.get("zz_position"),
            r.get("eq9"),                        # 車輛/車組
            r.get("installdate"),
            r.get("EXPECTEDLIFE") or r.get("expectedlife"),
            r.get("manufacturer"),
            r.get("FAILURECODE") or r.get("failurecode"),
            r.get("parent"),
            datetime.now(),
        ))

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO maximo_assets (
                assetnum, eq24, vehicle_type, vehicle_class, vehicle_category,
                workshop, section, borrow_section, status, status_desc,
                car_group, position, record_type,
                install_date, expected_life, manufacturer,
                failure_code, parent_assetnum, synced_at
            ) VALUES %s
            ON CONFLICT (assetnum) DO UPDATE SET
                eq24=EXCLUDED.eq24,
                vehicle_type=EXCLUDED.vehicle_type,
                vehicle_class=EXCLUDED.vehicle_class,
                vehicle_category=EXCLUDED.vehicle_category,
                workshop=EXCLUDED.workshop,
                section=EXCLUDED.section,
                borrow_section=EXCLUDED.borrow_section,
                status=EXCLUDED.status,
                status_desc=EXCLUDED.status_desc,
                car_group=EXCLUDED.car_group,
                position=EXCLUDED.position,
                record_type=EXCLUDED.record_type,
                install_date=EXCLUDED.install_date,
                expected_life=EXCLUDED.expected_life,
                manufacturer=EXCLUDED.manufacturer,
                failure_code=EXCLUDED.failure_code,
                parent_assetnum=EXCLUDED.parent_assetnum,
                synced_at=EXCLUDED.synced_at
        """, rows)
    conn.commit()
    log.info("Assets synced: %d records", len(rows))


# ── PM Work Order sync (定期工單 1A/2A/3A/4A) ────────────────────────────────
PMWO_SELECT = ",".join([
    "wonum", "description", "status", "assetnum",
    "WORKTYPE", "OWNERGROUP", "WOL1",
    "reportdate", "ZZ_ACTSTART", "ZZ_ACTFINISH", "ZZ_LASTACTFINISH",
    "ZZ_CARIN", "ZZ_CAROUT", "FAILURECODE",
    # kilometers not always present — omit if causes error
])

def sync_pmwo(conn):
    log.info("Syncing PM work orders (定期工單)...")
    records = _get_all(
        "mxwo", PMWO_SELECT,
        where='WORKTYPE in ["1A","2A","3A","4A"]'
    )

    rows = []
    for r in records:
        rows.append((
            r.get("wonum"),
            r.get("description"),
            r.get("status"),
            r.get("assetnum"),
            r.get("WORKTYPE") or r.get("worktype"),
            r.get("OWNERGROUP") or r.get("ownergroup"),
            r.get("WOL1") or r.get("wol1"),          # 檢修段
            r.get("reportdate"),
            r.get("ZZ_ACTSTART") or r.get("zz_actstart"),
            r.get("ZZ_ACTFINISH") or r.get("zz_actfinish"),
            r.get("ZZ_LASTACTFINISH") or r.get("zz_lastactfinish"),
            r.get("ZZ_CARIN") or r.get("zz_carin"),
            r.get("ZZ_CAROUT") or r.get("zz_carout"),
            r.get("FAILURECODE") or r.get("failurecode"),
            datetime.now(),
        ))

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO maximo_pm_workorders (
                wonum, description, status, assetnum,
                work_type, owner_group, maintenance_section,
                report_date, act_start, act_finish, last_act_finish,
                car_in_result, car_out_result, failure_code, synced_at
            ) VALUES %s
            ON CONFLICT (wonum) DO UPDATE SET
                description=EXCLUDED.description,
                status=EXCLUDED.status,
                assetnum=EXCLUDED.assetnum,
                work_type=EXCLUDED.work_type,
                owner_group=EXCLUDED.owner_group,
                maintenance_section=EXCLUDED.maintenance_section,
                report_date=EXCLUDED.report_date,
                act_start=EXCLUDED.act_start,
                act_finish=EXCLUDED.act_finish,
                last_act_finish=EXCLUDED.last_act_finish,
                car_in_result=EXCLUDED.car_in_result,
                car_out_result=EXCLUDED.car_out_result,
                failure_code=EXCLUDED.failure_code,
                synced_at=EXCLUDED.synced_at
        """, rows)
    conn.commit()
    log.info("PM work orders synced: %d records", len(rows))


# ── CM Work Order sync (維修/臨修工單 T1/TR/CM) ──────────────────────────────
CMWO_SELECT = ",".join([
    "wonum", "description", "DESCRIPTION_LONGDESCRIPTION",
    "status", "assetnum", "WORKTYPE", "OWNERGROUP", "ZZ_MAINSECTION",
    "TICKETID", "reportdate", "actstart", "actfinish",
    "ZZ_TARGSTARTDATE", "ZZ_TARGCOMPDATE",
    "FAILURECODE", "ZZ_REPAIRPROC", "WORK_HRS",
])

def sync_cmwo(conn):
    log.info("Syncing CM work orders (維修工單)...")
    records = _get_all(
        "mxwo", CMWO_SELECT,
        where='WORKTYPE in ["T1","TR","CM","T2","T3"]'
    )

    rows = []
    for r in records:
        rows.append((
            r.get("wonum"),
            r.get("description"),
            r.get("DESCRIPTION_LONGDESCRIPTION") or r.get("description_longdescription"),
            r.get("status"),
            r.get("assetnum"),
            r.get("WORKTYPE") or r.get("worktype"),
            r.get("OWNERGROUP") or r.get("ownergroup"),
            r.get("ZZ_MAINSECTION") or r.get("zz_mainsection"),
            r.get("TICKETID") or r.get("ticketid"),
            r.get("reportdate"),
            r.get("actstart"),
            r.get("actfinish"),
            r.get("ZZ_TARGSTARTDATE") or r.get("zz_targstartdate"),
            r.get("ZZ_TARGCOMPDATE") or r.get("zz_targcompdate"),
            r.get("FAILURECODE") or r.get("failurecode"),
            r.get("ZZ_REPAIRPROC") or r.get("zz_repairproc"),
            r.get("WORK_HRS") or r.get("work_hrs"),
            datetime.now(),
        ))

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO maximo_cm_workorders (
                wonum, description, long_description,
                status, assetnum, work_type, owner_group, maintenance_section,
                ticket_id, report_date, act_start, act_finish,
                target_start_date, target_comp_date,
                failure_code, repair_proc, work_hours, synced_at
            ) VALUES %s
            ON CONFLICT (wonum) DO UPDATE SET
                description=EXCLUDED.description,
                long_description=EXCLUDED.long_description,
                status=EXCLUDED.status,
                assetnum=EXCLUDED.assetnum,
                work_type=EXCLUDED.work_type,
                owner_group=EXCLUDED.owner_group,
                maintenance_section=EXCLUDED.maintenance_section,
                ticket_id=EXCLUDED.ticket_id,
                report_date=EXCLUDED.report_date,
                act_start=EXCLUDED.act_start,
                act_finish=EXCLUDED.act_finish,
                target_start_date=EXCLUDED.target_start_date,
                target_comp_date=EXCLUDED.target_comp_date,
                failure_code=EXCLUDED.failure_code,
                repair_proc=EXCLUDED.repair_proc,
                work_hours=EXCLUDED.work_hours,
                synced_at=EXCLUDED.synced_at
        """, rows)
    conn.commit()
    log.info("CM work orders synced: %d records", len(rows))


# ── Fault Report (FNM / mxsr) sync ──────────────────────────────────────────
FNM_SELECT = ",".join([
    "ticketid", "ZZ_IMNUM", "description", "DESCRIPTION_LONGDESCRIPTION",
    "FR2CODE_LONGDESCRIPTION", "status", "status_description",
    "assetnum", "ZZ_INCIDENT_NEW", "ZZ_IM_LOCATION",
    "ZZ_TCMS", "ZZ_IM_GRADE", "ZZ_URGENCY", "ZZ_RESTRICTED_STATUS",
    "ZZ_PERSONBELONG", "ZZ_ENTRYDATE", "ZZ_IM_TIME",
    "reportdate", "ZZ_CONFIRM_BY", "ZZ_CONFIRM_DATE", "class",
])

def sync_fnm(conn):
    log.info("Syncing fault reports (FNM / mxsr)...")
    records = _get_all("mxsr", FNM_SELECT)

    rows = []
    for r in records:
        # Combine ZZ_ENTRYDATE + ZZ_IM_TIME if available, else use reportdate
        occurrence_date = r.get("ZZ_ENTRYDATE") or r.get("zz_entrydate") or r.get("reportdate")

        rows.append((
            r.get("ticketid"),
            r.get("ZZ_IMNUM") or r.get("zz_imnum"),
            r.get("description"),
            r.get("DESCRIPTION_LONGDESCRIPTION") or r.get("description_longdescription"),
            r.get("FR2CODE_LONGDESCRIPTION") or r.get("fr2code_longdescription"),
            r.get("status"),
            r.get("status_description"),
            r.get("assetnum"),
            r.get("ZZ_INCIDENT_NEW") or r.get("zz_incident_new"),
            r.get("ZZ_IM_LOCATION") or r.get("zz_im_location"),
            r.get("ZZ_TCMS") or r.get("zz_tcms"),
            r.get("ZZ_IM_GRADE") or r.get("zz_im_grade"),
            r.get("ZZ_URGENCY") or r.get("zz_urgency"),
            r.get("ZZ_RESTRICTED_STATUS") or r.get("zz_restricted_status"),
            r.get("ZZ_PERSONBELONG") or r.get("zz_personbelong"),
            occurrence_date,
            r.get("reportdate"),
            r.get("ZZ_CONFIRM_BY") or r.get("zz_confirm_by"),
            r.get("ZZ_CONFIRM_DATE") or r.get("zz_confirm_date"),
            r.get("class"),
            datetime.now(),
        ))

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO maximo_fault_reports (
                ticketid, im_num, description, fault_symptom, handling_desc,
                status, status_desc, assetnum,
                incident_class, fault_location, tcms_code,
                grade, urgency, restricted_status, report_unit,
                occurrence_date, report_date, confirm_by, confirm_date,
                class_type, synced_at
            ) VALUES %s
            ON CONFLICT (ticketid) DO UPDATE SET
                im_num=EXCLUDED.im_num,
                description=EXCLUDED.description,
                fault_symptom=EXCLUDED.fault_symptom,
                handling_desc=EXCLUDED.handling_desc,
                status=EXCLUDED.status,
                status_desc=EXCLUDED.status_desc,
                assetnum=EXCLUDED.assetnum,
                incident_class=EXCLUDED.incident_class,
                fault_location=EXCLUDED.fault_location,
                tcms_code=EXCLUDED.tcms_code,
                grade=EXCLUDED.grade,
                urgency=EXCLUDED.urgency,
                restricted_status=EXCLUDED.restricted_status,
                report_unit=EXCLUDED.report_unit,
                occurrence_date=EXCLUDED.occurrence_date,
                report_date=EXCLUDED.report_date,
                confirm_by=EXCLUDED.confirm_by,
                confirm_date=EXCLUDED.confirm_date,
                class_type=EXCLUDED.class_type,
                synced_at=EXCLUDED.synced_at
        """, rows)
    conn.commit()
    log.info("Fault reports synced: %d records", len(rows))


# ── Domain sync (全量 → maximo_domains) ─────────────────────────────────────

def sync_domains(conn):
    """Pull ALL Maximo domain values into maximo_domains table.

    Also backfills maximo_field_metadata.value_mapping for the 4 key domains
    so the legacy NL→SQL path keeps working.
    """
    import json as _json

    LEGACY_MAP = {
        # domainid → (table_name, column_name)  — kept for backward compat
        "WOSTATUS":   ("maximo_pm_workorders", "status"),
        "WORKTYPE":   ("maximo_pm_workorders", "work_type"),
        "EQ3":        ("maximo_assets", "vehicle_class"),
        "ASSETNUMEQ": ("maximo_assets", "status"),
    }

    log.info("Syncing ALL domain values...")
    try:
        records = _get_all("mxdomain", "domainid,value,description")
    except Exception as e:
        log.warning("Domain sync skipped (API error): %s", e)
        return

    rows = []
    legacy: dict = {}
    for r in records:
        did = r.get("domainid", "")
        val = r.get("value") or r.get("maxvalue", "")
        desc = r.get("description") or ""
        if did and val:
            rows.append((did, val, desc))
            if did in LEGACY_MAP:
                legacy.setdefault(did, {})[val] = desc

    with conn.cursor() as cur:
        # Upsert into maximo_domains (full domain store)
        execute_values(cur, """
            INSERT INTO maximo_domains (domainid, value, description, synced_at)
            VALUES %s
            ON CONFLICT (domainid, value) DO UPDATE
                SET description = EXCLUDED.description,
                    synced_at   = EXCLUDED.synced_at
        """, [(d, v, desc, datetime.now()) for d, v, desc in rows])

        # Backfill legacy field_metadata.value_mapping
        for domainid, mapping in legacy.items():
            table, col = LEGACY_MAP[domainid]
            cur.execute("""
                INSERT INTO maximo_field_metadata (table_name, column_name, value_mapping)
                VALUES (%s, %s, %s::jsonb)
                ON CONFLICT (table_name, column_name) DO UPDATE
                    SET value_mapping = EXCLUDED.value_mapping
            """, (table, col, _json.dumps(mapping, ensure_ascii=False)))

    conn.commit()
    log.info("Domain values synced: %d values across domains", len(rows))


# ── Attribute sync (欄位定義 → maximo_attr_metadata) ────────────────────────

# Maximo object → our PostgreSQL table(s)
OBJECT_TABLE_MAP = {
    "ASSET":     "maximo_assets",
    "WORKORDER": "maximo_workorders",   # covers both pm & cm; split in NL2SQL
    "SR":        "maximo_fault_reports",
}

# Attribute name → PostgreSQL column name overrides (ZZ_ custom fields)
ATTR_COLUMN_MAP = {
    # ASSET
    "EQ24":          "eq24",
    "EQ4":           "vehicle_type",
    "EQ3":           "vehicle_class",
    "EQ11":          "vehicle_category",
    "EQ1":           "workshop",
    "EQ2":           "section",
    "EQ8":           "borrow_section",
    "STATUS":        "status",
    "ZZ_CARGROUP":   "car_group",
    "ZZ_POSITION":   "position",
    "EQ9":           "record_type",
    "INSTALLDATE":   "install_date",
    "EXPECTEDLIFE":  "expected_life",
    "MANUFACTURER":  "manufacturer",
    # WORKORDER
    "WONUM":         "wonum",
    "DESCRIPTION":   "description",
    "ASSETNUM":      "assetnum",
    "WORKTYPE":      "work_type",
    "OWNERGROUP":    "owner_group",
    "WOL1":          "maintenance_section",
    "REPORTDATE":    "report_date",
    "ACTSTART":      "act_start",
    "ACTFINISH":     "act_finish",
    "ZZ_ACTSTART":   "act_start",
    "ZZ_ACTFINISH":  "act_finish",
    "ZZ_LASTACTFINISH": "last_act_finish",
    "ZZ_CARIN":      "car_in_result",
    "ZZ_CAROUT":     "car_out_result",
    "TICKETID":      "ticket_id",
    "ZZ_MAINSECTION": "maintenance_section",
    "ZZ_TARGSTARTDATE": "target_start_date",
    "ZZ_TARGCOMPDATE":  "target_comp_date",
    "FAILURECODE":   "failure_code",
    "ZZ_REPAIRPROC": "repair_proc",
    "WORK_HRS":      "work_hours",
    # SR
    "ZZ_IMNUM":      "im_num",
    "ZZ_INCIDENT_NEW": "incident_class",
    "ZZ_IM_LOCATION": "fault_location",
    "ZZ_TCMS":       "tcms_code",
    "ZZ_IM_GRADE":   "grade",
    "ZZ_URGENCY":    "urgency",
    "ZZ_RESTRICTED_STATUS": "restricted_status",
    "ZZ_PERSONBELONG": "report_unit",
    "ZZ_ENTRYDATE":  "occurrence_date",
    "ZZ_CONFIRM_BY": "confirm_by",
    "ZZ_CONFIRM_DATE": "confirm_date",
    "CLASS":         "class_type",
    "FR2CODE_LONGDESCRIPTION": "handling_desc",
}


def sync_attributes(conn):
    """Pull attribute definitions from maxattribute OSLC API.

    Stores into maximo_attr_metadata for dynamic schema generation in NL→SQL.
    Only imports attributes for the objects we actually query.
    """
    target_objects = list(OBJECT_TABLE_MAP.keys())
    where = "objectname in [" + ",".join(f'"{o}"' for o in target_objects) + "]"

    log.info("Syncing attribute metadata for objects: %s ...", target_objects)
    try:
        records = _get_all(
            "maxattribute",
            "objectname,attributename,title,domainid,persistent",
            where=where,
        )
    except Exception as e:
        log.warning("Attribute sync skipped (API error): %s", e)
        return

    rows = []
    for r in records:
        obj  = (r.get("objectname") or "").upper()
        attr = (r.get("attributename") or "").upper()
        if not obj or not attr:
            continue
        # Skip non-persistent (calculated/virtual) attributes
        if r.get("persistent") is False:
            continue
        pg_table  = OBJECT_TABLE_MAP.get(obj, "")
        pg_col    = ATTR_COLUMN_MAP.get(attr, attr.lower())
        disp_name = r.get("title") or attr
        domain_id = r.get("domainid") or None
        rows.append((obj, pg_table, attr, pg_col, disp_name, domain_id, datetime.now()))

    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO maximo_attr_metadata
                (object_name, pg_table, attribute_name, pg_column, display_name, domainid, synced_at)
            VALUES %s
            ON CONFLICT (object_name, attribute_name) DO UPDATE SET
                pg_table     = EXCLUDED.pg_table,
                pg_column    = EXCLUDED.pg_column,
                display_name = EXCLUDED.display_name,
                domainid     = EXCLUDED.domainid,
                synced_at    = EXCLUDED.synced_at
        """, rows)
    conn.commit()
    log.info("Attribute metadata synced: %d attributes", len(rows))


# ── Text generation for RAG ──────────────────────────────────────────────────
def generate_asset_text(row: dict) -> str:
    lines = [
        f"車輛資料：{row.get('eq24', row.get('assetnum'))}",
        f"車型：{row.get('vehicle_type', '未知')}（車種：{row.get('vehicle_class', '未知')}）",
        f"所屬車組：{row.get('car_group', '未知')}",
        f"配屬段別：{row.get('section', '未知')}，維修機廠：{row.get('workshop', '未知')}",
    ]
    if row.get("borrow_section"):
        lines.append(f"借用段別：{row['borrow_section']}")
    lines += [
        f"車輛狀態：{row.get('status_desc', row.get('status', '未知'))}",
        f"試運起始日期：{row.get('install_date', '未知')}",
        f"預期使用年限：{row.get('expected_life', '未知')} 年",
        f"記錄類型：{row.get('record_type', '未知')}",
    ]
    return "\n".join(lines)

def generate_pmwo_text(row: dict) -> str:
    lines = [
        f"定期工單：{row['wonum']}",
        f"車號：{row['assetnum']}",
        f"說明：{row.get('description', '')}",
        f"檢修級別：{row.get('work_type', '未知')}",
        f"狀態：{row.get('status', '未知')}",
        f"通報日期：{row.get('report_date', '未知')}",
    ]
    if row.get("act_start"):
        lines.append(f"檢修期間：{row['act_start']} ～ {row.get('act_finish', '未完工')}")
    if row.get("last_act_finish"):
        lines.append(f"上次檢修完工：{row['last_act_finish']}")
    if row.get("car_in_result"):
        lines.append(f"進廠結果：{row['car_in_result']}")
    if row.get("car_out_result"):
        lines.append(f"出廠結果：{row['car_out_result']}")
    return "\n".join(lines)

def generate_cmwo_text(row: dict) -> str:
    lines = [
        f"維修工單：{row['wonum']}",
        f"車號：{row['assetnum']}",
        f"故障說明：{row.get('description', '')}",
    ]
    if row.get("long_description"):
        lines.append(f"詳細說明：{row['long_description']}")
    lines += [
        f"維修類型：{row.get('work_type', '未知')}",
        f"狀態：{row.get('status', '未知')}",
        f"通報日期：{row.get('report_date', '未知')}",
    ]
    if row.get("repair_proc"):
        lines.append(f"修復程序：{row['repair_proc']}")
    if row.get("ticket_id"):
        lines.append(f"關聯故障通報：{row['ticket_id']}")
    return "\n".join(lines)

def generate_fault_text(row: dict) -> str:
    lines = [
        f"故障通報：{row['ticketid']}",
        f"車號：{row.get('assetnum', '未知')}",
        f"故障概況：{row.get('description', '')}",
    ]
    if row.get("fault_symptom"):
        lines.append(f"故障現象：{row['fault_symptom']}")
    if row.get("handling_desc"):
        lines.append(f"處理情形：{row['handling_desc']}")
    lines.append(f"狀態：{row.get('status_desc', row.get('status', '未知'))}")
    if row.get("tcms_code"):
        lines.append(f"TCMS故障碼：{row['tcms_code']}")
    if row.get("fault_location"):
        lines.append(f"故障位置：{row['fault_location']}")
    if row.get("grade"):
        lines.append(f"等級：{row['grade']}")
    lines.append(f"通報日期：{row.get('report_date', '未知')}")
    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync",
        choices=["assets", "pmwo", "cmwo", "fnm", "domains", "attributes", "meta", "all"],
        default="all",
        help=(
            "meta = domains + attributes only (no data sync); "
            "all = everything"
        ))
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    try:
        if args.sync in ("assets", "all"):
            sync_assets(conn)
        if args.sync in ("pmwo", "all"):
            sync_pmwo(conn)
        if args.sync in ("cmwo", "all"):
            sync_cmwo(conn)
        if args.sync in ("fnm", "all"):
            sync_fnm(conn)
        if args.sync in ("domains", "meta", "all"):
            sync_domains(conn)
        if args.sync in ("attributes", "meta", "all"):
            sync_attributes(conn)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
