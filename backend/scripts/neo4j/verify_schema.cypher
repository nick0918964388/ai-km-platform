// ============================================
// Phase 3 Knowledge Graph — Schema Verify
// ============================================
// 驗證 schema 建立狀況：constraints、indexes、labels、relationship types

SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties;

SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state;

CALL db.labels() YIELD label RETURN label ORDER BY label;

CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType;
