# Research Summary: Profile Settings & Dashboard

**Quick Reference Guide** | **Date**: 2026-02-03

This is a condensed summary of the technical research findings. For full details, see [technical-research.md](./technical-research.md).

---

## 🎯 Key Decisions

### 1. Database: PostgreSQL (NOT SQLite)

**Critical Finding**: The platform **already uses PostgreSQL** with async SQLAlchemy, not SQLite.

- **Connection**: `postgresql+asyncpg://aikm:aikm@localhost:5432/aikm`
- **Pattern**: `/backend/app/models/document.py` shows existing SQLAlchemy async models
- **Action**: Create `User` model extending existing PostgreSQL setup

**Why not SQLite?**
- Would introduce dual-database complexity
- Platform standardized on PostgreSQL for all structured data
- Existing patterns already use async SQLAlchemy with asyncpg

### 2. Avatar Processing: Pillow (Already Installed)

**Status**: ✅ Pillow 12.1.0 already in requirements.txt and installed

**Implementation**:
- Resize to 200x200px using `ImageOps.fit()`
- Convert to JPEG (quality=85, progressive=True, optimize=True)
- Store at `./storage/avatars/{user_id}_{timestamp}_{hash}.jpg`
- Serve via FastAPI `FileResponse` with 1-hour cache headers

**Security**:
- Validate file type using Pillow (not just extension)
- 5MB size limit enforced before processing
- Path traversal prevention with `Path.is_relative_to()`
- Unique filenames using timestamp + MD5 hash

### 3. Dashboard Metrics: Hybrid SQL + Qdrant + Redis

**Strategy**:
- **PostgreSQL**: Document counts, user counts (fast COUNT queries)
- **Qdrant**: Activity logs, query history (new lightweight `user_activity` collection)
- **Redis**: Cache aggregated results (60-second TTL)

**Performance Target**: < 3s dashboard load time
- Cache hit: ~2-5ms (instant)
- Cache miss: ~200-300ms (well under target)

**Activity Collection Schema**:
```python
ACTIVITY_COLLECTION = "user_activity"
Payload: {
  "user_id": str,
  "activity_type": "query" | "upload" | "delete" | "login",
  "timestamp": ISO 8601,
  "query_text": str (optional),
  ...metadata
}
Vector: [0.0] (dummy 1-D, we don't search by vector)
```

### 4. Frontend State: Extend Zustand Store

**Pattern**: Add profile slice to existing `/frontend/src/store/useStore.ts`

**New State**:
```typescript
{
  profile: UserProfile | null,
  dashboardMetrics: DashboardMetrics | null,
  avatarUploading: boolean,
  avatarUploadProgress: number (0-100),
}
```

**Storage**: LocalStorage for profile persistence (survive page refresh)

### 5. Account Initials: Client-Side Generation

**Algorithm** (in `/frontend/src/lib/utils.ts`):
```typescript
generateInitials(displayName: string): string {
  words = split by whitespace
  if empty → "??"
  if single word → first character
  if multiple words → first char of first + last word
}
```

**Examples**:
- "John Doe" → "JD"
- "Alice" → "A"
- "張三 李四" → "張李"
- "" → "??"

---

## 📦 Zero New Dependencies

**All required libraries already installed**:
- ✅ Pillow 12.1.0 (image processing)
- ✅ PostgreSQL + asyncpg (database)
- ✅ Qdrant client (activity logs)
- ✅ Redis (caching)
- ✅ Zustand (state management)
- ✅ Carbon Design (UI components)
- ✅ Tailwind CSS v4 (styling)

---

## 🏗️ New Files to Create

### Backend (9 files)
```
backend/app/
├── models/user.py              # User SQLAlchemy model
├── services/avatar_service.py  # Avatar upload/processing
├── services/activity_tracker.py # Qdrant activity logging
├── services/dashboard_service.py # Dashboard aggregation
└── routers/profile.py          # Profile API endpoints

backend/alembic/versions/
└── xxx_add_user_profile.py     # Database migration

backend/tests/
├── test_avatar.py              # Avatar processing tests
├── test_dashboard.py           # Dashboard service tests
└── test_profile.py             # Profile API tests
```

### Frontend (11 files)
```
frontend/src/
├── app/profile/page.tsx        # Profile settings page
├── app/dashboard/page.tsx      # Dashboard page
├── components/profile/
│   ├── Avatar.tsx              # Avatar display component
│   ├── AvatarUpload.tsx        # Avatar upload form
│   └── ProfileForm.tsx         # Profile edit form
├── components/dashboard/
│   ├── MetricCard.tsx          # Dashboard metric tile
│   ├── ActivityTimeline.tsx    # Recent activity list
│   └── TopTopics.tsx           # Top topics widget
├── hooks/useAvatarUpload.ts    # Avatar upload logic
└── services/
    ├── profileApi.ts           # Profile API client
    └── dashboardApi.ts         # Dashboard API client
```

---

## 🚨 Critical Implementation Notes

### 1. Database Schema (PostgreSQL)
```sql
-- Use existing PostgreSQL, NOT SQLite
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    display_name VARCHAR(50) NOT NULL DEFAULT '',
    avatar_url VARCHAR(255),
    account_level VARCHAR(20) NOT NULL DEFAULT 'free',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
```

### 2. Qdrant Activity Collection
```python
# Create lightweight collection for activity tracking
# Call in app startup (main.py lifespan handler)
ensure_activity_collection()  # Creates "user_activity" collection
```

### 3. Cache Invalidation Points
```python
# Invalidate dashboard cache when:
- User uploads document → invalidate_dashboard_cache(user_id)
- User performs query → invalidate_dashboard_cache(user_id)
- User updates profile → invalidate_dashboard_cache(user_id)
```

### 4. Existing Patterns to Follow
- **Database Models**: `/backend/app/models/document.py` (async SQLAlchemy pattern)
- **File Upload**: `/backend/app/routers/kb.py` (UploadFile handling)
- **File Serving**: `/backend/app/routers/kb.py:145` (FileResponse pattern)
- **Qdrant Client**: `/backend/app/services/vector_store.py` (singleton pattern)
- **Redis Cache**: `/backend/app/services/cache.py` (get/set with TTL)
- **Zustand Store**: `/frontend/src/store/useStore.ts` (state management)

---

## ⚠️ Key Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **Concurrent profile updates** | Use optimistic locking with `updated_at` timestamp |
| **Large activity logs (10k+ records)** | Pagination (show 20, load more), cache aggregations |
| **Avatar storage growth** | Cleanup job for deleted users, disk monitoring |
| **Cache invalidation bugs** | Comprehensive testing + manual refresh button |

---

## 🎯 Performance Targets

| Metric | Target | Strategy |
|--------|--------|----------|
| Avatar upload | < 10s | Pillow optimization, async I/O |
| Dashboard load | < 3s | Redis cache (60s TTL), efficient queries |
| Profile update | < 30s from login | Optimistic UI updates |
| Image size | < 50KB | JPEG quality=85, 200x200px |
| Cache hit rate | > 70% | 60s TTL, invalidate on user actions |

---

## 📋 Implementation Checklist

### Phase 0: Research ✅
- [x] Database choice (PostgreSQL, not SQLite)
- [x] Avatar processing (Pillow patterns)
- [x] Qdrant collections strategy
- [x] Dashboard metrics aggregation
- [x] Frontend state management

### Phase 1: Design (Next)
- [ ] Create data-model.md
- [ ] Generate API contracts (profile-api.yaml, dashboard-api.yaml)
- [ ] Create quickstart.md
- [ ] Update CLAUDE.md with profile context

### Phase 2: Implementation
- [ ] User model + migration
- [ ] Avatar service (upload, processing, serving)
- [ ] Activity tracker (Qdrant logging)
- [ ] Dashboard service (metrics aggregation)
- [ ] Profile API endpoints
- [ ] Frontend components (Avatar, ProfileForm, Dashboard)
- [ ] Zustand store extensions
- [ ] API client hooks

### Phase 3: Testing
- [ ] Unit tests (avatar processing, initials generation)
- [ ] Integration tests (API endpoints)
- [ ] E2E tests (upload flow, dashboard load)
- [ ] Performance tests (dashboard under load)

---

## 📚 Reference Documents

- **Full Research**: [technical-research.md](./technical-research.md) (detailed findings)
- **Original Research**: [research.md](./research.md) (initial draft)
- **Implementation Plan**: [plan.md](./plan.md) (constitution check, structure)
- **Feature Spec**: [spec.md](./spec.md) (requirements, success criteria)

---

**Status**: Research Complete ✅
**Ready for**: Phase 1 (Design & Contracts)
**Next Action**: Create data-model.md and API contracts
**Date**: 2026-02-03
