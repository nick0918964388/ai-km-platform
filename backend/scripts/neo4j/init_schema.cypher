// ============================================
// Phase 3 Knowledge Graph — Schema Init
// ============================================
// 節點類型：WorkOrder / Asset / ClassStructure / ServiceRequest / SOP / Part
// 關係類型：PERFORMED_ON / CLASSIFIED_AS / PARENT_OF / REPORTED_ON / TRIGGERED_WO / USED_PART / FOLLOWED_SOP
// 此腳本僅建立 schema（constraint + index），不寫入任何資料節點
// 所有 DDL 使用 IF NOT EXISTS 保證 idempotent

// --- Unique Constraints（自動建 btree index）---
CREATE CONSTRAINT wo_wonum_unique IF NOT EXISTS
  FOR (w:WorkOrder) REQUIRE w.wonum IS UNIQUE;

CREATE CONSTRAINT asset_assetnum_unique IF NOT EXISTS
  FOR (a:Asset) REQUIRE a.assetnum IS UNIQUE;

CREATE CONSTRAINT cs_classid_unique IF NOT EXISTS
  FOR (c:ClassStructure) REQUIRE c.classstructureid IS UNIQUE;

CREATE CONSTRAINT sr_ticketid_unique IF NOT EXISTS
  FOR (s:ServiceRequest) REQUIRE s.ticketid IS UNIQUE;

CREATE CONSTRAINT sop_id_unique IF NOT EXISTS
  FOR (s:SOP) REQUIRE s.sop_id IS UNIQUE;

CREATE CONSTRAINT part_id_unique IF NOT EXISTS
  FOR (p:Part) REQUIRE p.part_id IS UNIQUE;

// --- 查詢常用欄位建 btree index ---
CREATE INDEX wo_reportdate IF NOT EXISTS FOR (w:WorkOrder) ON (w.reportdate);
CREATE INDEX wo_status IF NOT EXISTS FOR (w:WorkOrder) ON (w.status);
CREATE INDEX wo_worktype IF NOT EXISTS FOR (w:WorkOrder) ON (w.worktype);
CREATE INDEX wo_assetnum IF NOT EXISTS FOR (w:WorkOrder) ON (w.assetnum);

CREATE INDEX asset_assettype IF NOT EXISTS FOR (a:Asset) ON (a.assettype);
CREATE INDEX asset_status IF NOT EXISTS FOR (a:Asset) ON (a.status);
CREATE INDEX asset_location IF NOT EXISTS FOR (a:Asset) ON (a.location);

CREATE INDEX sr_reportdate IF NOT EXISTS FOR (s:ServiceRequest) ON (s.reportdate);
CREATE INDEX sr_assetnum IF NOT EXISTS FOR (s:ServiceRequest) ON (s.assetnum);
CREATE INDEX sr_zz_currwonum IF NOT EXISTS FOR (s:ServiceRequest) ON (s.zz_currwonum);

// --- 全文索引（供故障描述語意模糊查）---
CREATE FULLTEXT INDEX sr_description_fts IF NOT EXISTS
  FOR (s:ServiceRequest) ON EACH [s.description];

CREATE FULLTEXT INDEX asset_description_fts IF NOT EXISTS
  FOR (a:Asset) ON EACH [a.description];

CREATE FULLTEXT INDEX cs_description_fts IF NOT EXISTS
  FOR (c:ClassStructure) ON EACH [c.description];
