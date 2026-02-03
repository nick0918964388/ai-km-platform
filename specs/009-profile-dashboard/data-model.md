# Data Model: Profile Settings & Dashboard

**Feature**: 009-profile-dashboard
**Date**: 2026-02-03
**Status**: Complete

## Overview

This document defines all data entities, their fields, relationships, validation rules, and state transitions for the Profile Settings & Dashboard feature.

---

## Entities

### 1. User Profile (Extended)

**Description**: Extends existing `users` table with profile-specific fields for display name, avatar, and account metadata.

**Storage**: SQLite `users` table

**Fields**:

| Field Name | Type | Required | Default | Constraints | Description |
|------------|------|----------|---------|-------------|-------------|
| `id` | UUID | Yes | Auto-generated | Primary Key, Unique | User unique identifier |
| `email` | VARCHAR(255) | Yes | - | Unique, Email format | User email address (existing field) |
| `display_name` | VARCHAR(50) | Yes | Empty string | Length: 2-50 chars | User's display name |
| `avatar_url` | VARCHAR(255) | No | NULL | Valid file path | Relative path to avatar image |
| `account_level` | VARCHAR(20) | Yes | 'free' | Enum: free/pro/enterprise | User's subscription tier |
| `created_at` | TIMESTAMP | Yes | CURRENT_TIMESTAMP | - | Account creation timestamp |
| `updated_at` | TIMESTAMP | Yes | CURRENT_TIMESTAMP | Auto-update on change | Last profile update timestamp |

**Validation Rules**:
- `display_name`: Must be 2-50 characters, can include letters, numbers, spaces, and basic punctuation
- `avatar_url`: Must be NULL or valid relative path matching pattern `avatars/{user_id}_{timestamp}.{ext}`
- `account_level`: Must be one of: 'free', 'pro', 'enterprise'
- `email`: Must be valid email format (enforced at auth layer, read-only in profile)

**Indexes**:
```sql
CREATE INDEX idx_users_id ON users(id);
CREATE INDEX idx_users_email ON users(email);
```

**State Transitions**:
- **Initial State**: New user with default values (display_name='', avatar_url=NULL, account_level='free')
- **Profile Update**: display_name or avatar_url modified, updated_at timestamp refreshed
- **Avatar Upload**: avatar_url changes from NULL to file path, updated_at refreshed
- **Avatar Removal**: avatar_url changes from file path to NULL, updated_at refreshed

---

### 2. Avatar File

**Description**: Physical image file uploaded by user, stored on local filesystem with metadata tracked in User Profile.

**Storage**: Local filesystem at `./storage/avatars/`

**File Naming Convention**: `{user_id}_{timestamp}.jpg`
- Example: `a3f2c9d4-5e6f-4a5b-8c9d-0e1f2a3b4c5d_1704326400.jpg`

**Metadata** (tracked in User Profile `avatar_url` field):

| Metadata | Type | Description |
|----------|------|-------------|
| User ID | UUID | Owner of the avatar |
| Upload Timestamp | Unix timestamp | When file was uploaded |
| File Extension | String | Image format (jpg, png, gif) |

**Processing Rules**:
- **File Size Limit**: 5MB maximum before processing
- **Accepted Formats**: JPG, PNG, GIF (validated via magic numbers, not extension)
- **Output Format**: Always converted to JPG
- **Output Dimensions**: 200x200px (square crop/resize)
- **Output Quality**: 85% JPEG quality for optimal size/quality balance

**Lifecycle**:
1. **Upload**: User selects image file → Client sends to API → Server validates size/format
2. **Processing**: Server uses Pillow to resize to 200x200, convert to JPG, optimize
3. **Storage**: Save to `./storage/avatars/{user_id}_{timestamp}.jpg`
4. **Database Update**: Update user.avatar_url with relative path
5. **Cleanup**: Delete old avatar file when user uploads new one
6. **Removal**: Delete file and set user.avatar_url to NULL when user removes avatar

---

### 3. Activity Log Entry

**Description**: Records individual user actions (document uploads, queries, profile updates) for dashboard activity timeline.

**Storage**: Qdrant collection `activity_logs` (existing, no new collection needed)

**Payload** (metadata in Qdrant):

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| `user_id` | UUID | Yes | User who performed action |
| `action_type` | String | Yes | Type of action: 'document_upload', 'query', 'profile_update' |
| `action_timestamp` | ISO 8601 DateTime | Yes | When action occurred |
| `action_metadata` | JSON Object | No | Additional context (e.g., document name, query text) |

**Example Entry**:
```json
{
  "user_id": "a3f2c9d4-5e6f-4a5b-8c9d-0e1f2a3b4c5d",
  "action_type": "document_upload",
  "action_timestamp": "2026-02-03T10:30:00Z",
  "action_metadata": {
    "document_name": "Q1_Report.pdf",
    "document_size": 2048576
  }
}
```

**Query Pattern**:
```python
# Fetch last 20 activities for dashboard
qdrant.scroll(
    collection_name="activity_logs",
    scroll_filter=Filter(
        must=[
            FieldCondition(key="user_id", match=MatchValue(value=user_id))
        ]
    ),
    limit=20,
    order_by="action_timestamp"
)
```

---

### 4. Query History Entry

**Description**: Stores user's search queries for dashboard top topics analytics.

**Storage**: SQLite `queries` table (existing)

**Fields**:

| Field Name | Type | Required | Description |
|------------|------|----------|-------------|
| `id` | UUID | Yes | Query unique identifier |
| `user_id` | UUID | Yes | User who made query |
| `query_text` | TEXT | Yes | Search query string |
| `timestamp` | TIMESTAMP | Yes | When query was made |
| `results_count` | INTEGER | No | Number of results returned |

**Indexes**:
```sql
CREATE INDEX idx_queries_user_id ON queries(user_id);
CREATE INDEX idx_queries_timestamp ON queries(timestamp);
```

**Aggregation Query for Top Topics**:
```sql
SELECT query_text, COUNT(*) as count
FROM queries
WHERE user_id = ?
GROUP BY query_text
ORDER BY count DESC
LIMIT 5;
```

---

### 5. Dashboard Metrics (Computed/Aggregated)

**Description**: Aggregated statistics computed from User Profile, Activity Logs, and Query History. Not stored directly, but cached in Redis.

**Storage**: Redis cache (key: `dashboard:{user_id}`, TTL: 60 seconds)

**Structure**:

```typescript
interface DashboardMetrics {
  userId: string;
  documentCount: number;           // COUNT from documents table
  queryCount: number;              // COUNT from queries table
  accountLevel: string;            // From user profile
  createdAt: string;               // From user profile
  recentActivity: ActivityEntry[]; // Last 20 from Qdrant
  topTopics: TopicEntry[];         // Top 5 from queries aggregation
}

interface ActivityEntry {
  actionType: 'document_upload' | 'query' | 'profile_update';
  timestamp: string;  // ISO 8601
  metadata: Record<string, any>;
}

interface TopicEntry {
  queryText: string;
  count: number;
}
```

**Cache Strategy**:
- **Cache Key**: `dashboard:{user_id}`
- **TTL**: 60 seconds
- **Invalidation**: Clear cache on profile update, document upload, or query
- **Cache Miss**: Compute from databases, store in cache, return result

---

## Relationships

```
User Profile (SQLite)
    │
    ├─── 1:1 ──> Avatar File (Filesystem)
    │               - Referenced by avatar_url
    │
    ├─── 1:N ──> Activity Log Entries (Qdrant)
    │               - Filtered by user_id
    │
    ├─── 1:N ──> Query History Entries (SQLite)
    │               - Joined on user_id
    │
    └─── 1:1 ──> Dashboard Metrics (Redis Cache)
                    - Computed/aggregated data
```

---

## Validation Summary

### User Profile Validations
- ✅ Display name: 2-50 characters
- ✅ Email: Valid email format (enforced at auth layer)
- ✅ Account level: Must be 'free', 'pro', or 'enterprise'
- ✅ Avatar URL: NULL or valid file path

### Avatar File Validations
- ✅ File size: ≤ 5MB before processing
- ✅ File format: JPG, PNG, or GIF (magic number validation)
- ✅ Output dimensions: Exactly 200x200px
- ✅ Output format: Always JPG

### Activity Log Validations
- ✅ User ID: Must be valid UUID
- ✅ Action type: Must be 'document_upload', 'query', or 'profile_update'
- ✅ Timestamp: Must be valid ISO 8601 datetime

---

## Database Migration

```sql
-- Migration: Add profile fields to existing users table
-- Run this migration before deploying feature

ALTER TABLE users ADD COLUMN display_name VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN avatar_url VARCHAR(255) NULL;
ALTER TABLE users ADD COLUMN account_level VARCHAR(20) NOT NULL DEFAULT 'free';
ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- Add indexes for performance
CREATE INDEX idx_users_id ON users(id);

-- Create storage directory
-- mkdir -p ./storage/avatars
```

---

## State Machine: Avatar Upload Flow

```
[No Avatar]
    |
    | User uploads image
    v
[Validating]
    |
    ├─ Invalid size/format ──> [Error: Show validation message]
    |
    | Valid file
    v
[Processing]
    |
    | Pillow resize/optimize
    v
[Saving]
    |
    | Write to filesystem
    | Update database
    v
[Avatar Set]
    |
    | User uploads new avatar ──> [Processing] (cleanup old file)
    | User removes avatar ──> [Removing] ──> [No Avatar] (cleanup file)
```

---

## Performance Considerations

### Query Optimization
- **Profile Fetch**: Single SELECT by user ID (indexed) → < 5ms
- **Dashboard Metrics**:
  - Document count: `SELECT COUNT(*)` with user_id index → < 10ms
  - Query count: `SELECT COUNT(*)` with user_id index → < 10ms
  - Recent activity: Qdrant scroll with filter → < 50ms
  - Top topics: SQL GROUP BY with index → < 20ms
  - **Total uncached**: ~90ms
  - **Total cached**: ~5ms (Redis fetch)

### Cache Strategy
- **Hit Rate Target**: > 80% (assuming users view dashboard multiple times within 60s)
- **Cache Size**: ~2KB per user dashboard → 2MB for 1000 users
- **TTL Justification**: 60s balances freshness (<5s spec) with cache effectiveness

---

## Security Considerations

### Avatar Upload Security
- ✅ File type validation using magic numbers (prevents extension spoofing)
- ✅ File size limit enforced before reading full file (prevents DoS)
- ✅ Unique filenames prevent path traversal attacks
- ✅ Files stored outside web root (served via controlled API endpoint)

### Profile Update Security
- ✅ User can only update their own profile (authenticated user_id check)
- ✅ Email not updateable via profile API (prevent account takeover)
- ✅ Account level not updateable via profile API (prevent privilege escalation)
- ✅ Input validation via Pydantic models (prevents injection)

---

## Next Steps

✅ Data model complete

Ready to proceed to:
1. Generate API contracts (profile-api.yaml, dashboard-api.yaml)
2. Create quickstart.md
3. Update agent context
