# Implementation Plan: Profile Settings & Dashboard

**Branch**: `009-profile-dashboard` | **Date**: 2026-02-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/009-profile-dashboard/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Implement user profile management (avatar upload with initials fallback, display name editing, account level display, basic profile updates) and real-time dashboard with backend-driven metrics (document count, query history, activity timeline, top topics). This feature enables users to personalize their accounts and track their knowledge management platform usage through data-backed insights.

## Technical Context

**Language/Version**: Python 3.10+ (Backend), TypeScript 5.x strict mode (Frontend)
**Primary Dependencies**: FastAPI 0.109+, Pydantic 2.x, Pillow 10.x (Backend) / React 19, Next.js 16.1, IBM Carbon v1.100, Tailwind CSS v4 (Frontend)
**Storage**: SQLite (user profiles), Qdrant (activity logs, query history), Local filesystem (avatar images at `./storage/avatars/`)
**Testing**: Pytest (Backend), Jest + React Testing Library (Frontend), Playwright (E2E - optional)
**Target Platform**: Web application (Linux server backend + browser frontend)
**Project Type**: Web (backend + frontend)
**Performance Goals**: Avatar upload < 10s, dashboard load < 3s, profile update < 30s from login (per success criteria)
**Constraints**: Avatar file size < 5MB, image formats JPG/PNG/GIF only, responsive design required (mobile + desktop)
**Scale/Scope**: 10k+ users expected, single feature (2 pages: profile settings + dashboard), 8-10 new API endpoints

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. TypeScript Strict Mode ✅
- **Status**: PASS
- **Validation**: All frontend code will use TypeScript strict mode (`strict: true` in tsconfig.json)
- **Application**: Profile settings and dashboard components will have fully typed props, state, and API responses

### II. React Best Practices ✅
- **Status**: PASS
- **Validation**: Functional components with hooks, custom hooks for avatar upload logic, proper dependency arrays
- **Application**: Profile settings form will use controlled components with React Hook Form, dashboard metrics will use custom hooks for data fetching

### III. FastAPI Standard Architecture ✅
- **Status**: PASS
- **Validation**: New router for profile endpoints (`app/routers/profile.py`), Pydantic models for validation, service layer for business logic
- **Application**: Profile update logic in service layer, avatar processing in dedicated service, dependency injection for database/storage

### IV. Qdrant Integration Standards ✅
- **Status**: PASS
- **Validation**: Activity logs and query history stored in Qdrant for dashboard metrics
- **Application**: Use Qdrant Python client for querying activity timeline and top topics, proper error handling for connection failures

### V. Component Library Consistency ✅
- **Status**: PASS
- **Validation**: IBM Carbon Design components (Forms, FileUploader, Tile, ProgressIndicator), Tailwind CSS v4 for custom layouts
- **Application**: Profile form uses Carbon Form components, dashboard uses Carbon Tiles for metric cards, fully responsive design

### VI. API Contract Consistency ✅
- **Status**: PASS
- **Validation**: RESTful endpoints with OpenAPI documentation, Pydantic request/response validation, consistent error responses
- **Application**:
  - `POST /api/profile/avatar` - Avatar upload
  - `PUT /api/profile` - Update profile
  - `GET /api/profile` - Get profile
  - `GET /api/dashboard/metrics` - Dashboard metrics
  - `GET /api/dashboard/activity` - Activity timeline

### Testing Requirements ✅
- **Status**: PASS
- **Validation**: Unit tests for services (avatar processing, profile validation), integration tests for API endpoints, optional E2E tests for critical flows
- **Application**: Pytest for backend services, Jest + RTL for React components, minimum 70% coverage for profile/dashboard business logic

### Performance Standards ✅
- **Status**: PASS
- **Validation**: Avatar upload < 10s, dashboard load < 3s, API response < 200ms for profile endpoints
- **Application**: Image optimization during upload, caching dashboard metrics in Redis (optional), efficient Qdrant queries

### Security Standards ✅
- **Status**: PASS
- **Validation**: Input validation via Pydantic, file upload security (type/size validation), JWT auth for protected endpoints
- **Application**: Avatar upload validates file type/size, sanitize display name input, secure file storage paths

**GATE STATUS**: ✅ **PASSED** - All constitution principles satisfied, no deviations required

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/
│   │   ├── profile.py          # NEW: Profile settings endpoints
│   │   └── dashboard.py         # EXISTING (to be enhanced with real metrics)
│   ├── services/
│   │   ├── profile.py           # NEW: Profile business logic
│   │   ├── avatar.py            # NEW: Avatar upload/processing
│   │   └── dashboard_metrics.py # NEW: Dashboard data aggregation
│   ├── models/
│   │   ├── profile.py           # NEW: Profile Pydantic models
│   │   └── schemas.py           # EXISTING (to be enhanced)
│   └── db/
│       └── sqlite.py            # NEW: SQLite connection for user profiles
└── tests/
    ├── test_profile.py          # NEW: Profile service tests
    ├── test_avatar.py           # NEW: Avatar processing tests
    └── test_dashboard.py        # NEW: Dashboard metrics tests

frontend/
├── src/
│   ├── app/
│   │   ├── profile/
│   │   │   └── page.tsx         # NEW: Profile settings page
│   │   └── dashboard/
│   │       └── page.tsx         # NEW: Dashboard page
│   ├── components/
│   │   ├── profile/
│   │   │   ├── ProfileForm.tsx  # NEW: Profile edit form
│   │   │   ├── AvatarUpload.tsx # NEW: Avatar upload component
│   │   │   └── Avatar.tsx       # NEW: Avatar display (with initials fallback)
│   │   └── dashboard/
│   │       ├── MetricCard.tsx   # NEW: Dashboard metric tile
│   │       ├── ActivityTimeline.tsx # NEW: Recent activity list
│   │       └── TopTopics.tsx    # NEW: Top searched topics widget
│   ├── hooks/
│   │   ├── useProfile.ts        # NEW: Profile data fetching hook
│   │   ├── useAvatarUpload.ts   # NEW: Avatar upload logic hook
│   │   └── useDashboard.ts      # NEW: Dashboard metrics hook
│   ├── services/
│   │   ├── profileApi.ts        # NEW: Profile API client
│   │   └── dashboardApi.ts      # NEW: Dashboard API client
│   ├── store/
│   │   └── useStore.ts          # EXISTING (to be enhanced with profile state)
│   └── types/
│       └── index.ts             # EXISTING (to be enhanced with profile types)
└── tests/
    ├── components/
    │   ├── ProfileForm.test.tsx # NEW: Profile form tests
    │   └── AvatarUpload.test.tsx # NEW: Avatar upload tests
    └── hooks/
        └── useProfile.test.ts   # NEW: Profile hook tests

storage/
└── avatars/                     # NEW: Avatar image storage directory
    └── .gitkeep

e2e/
└── profile-dashboard.spec.ts    # NEW: E2E tests for profile & dashboard
```

**Structure Decision**: This is a web application with backend (FastAPI) and frontend (Next.js). Profile and dashboard features add new routers, services, and components to the existing structure. Avatar images are stored in local filesystem (`./storage/avatars/`), user profiles in SQLite database, and activity logs/query history in existing Qdrant collections.

## Complexity Tracking

> **Not applicable** - All Constitution Check gates passed without violations. No complexity justifications needed.

---

## Phase Completion Summary

### ✅ Phase 0: Outline & Research (COMPLETE)

**Artifacts Created**:
- `research.md` - Comprehensive technical research covering:
  - PostgreSQL schema design (corrected from SQLite assumption)
  - Avatar upload & processing with Pillow
  - Qdrant collections strategy
  - Dashboard metrics aggregation
  - Frontend state management patterns

**Key Decisions**:
- Use existing PostgreSQL infrastructure (not SQLite)
- Pillow 12.1.0 for image processing (already installed)
- Hybrid dashboard metrics: PostgreSQL + Qdrant + Redis caching (60s TTL)
- Extend Zustand store for profile state

**Zero New Dependencies**: All required libraries already installed ✅

---

### ✅ Phase 1: Design & Contracts (COMPLETE)

**Artifacts Created**:
1. **data-model.md** - Complete entity definitions:
   - User Profile (PostgreSQL extended schema)
   - Avatar File (filesystem metadata)
   - Activity Log Entry (Qdrant payload structure)
   - Query History Entry (PostgreSQL aggregation)
   - Dashboard Metrics (computed/cached structure)
   - Validation rules, relationships, state machines

2. **contracts/** - OpenAPI 3.0 specifications:
   - `profile-api.yaml` - 5 endpoints for profile management
   - `dashboard-api.yaml` - 3 endpoints for dashboard metrics
   - Full request/response schemas with examples
   - Error responses (400, 401, 404, 500)
   - JWT authentication scheme

3. **quickstart.md** - Developer implementation guide:
   - Step-by-step setup instructions
   - Database migration scripts
   - Code examples for backend services, routers
   - Frontend components, hooks, pages
   - Testing checklist and verification steps
   - Troubleshooting guide

4. **CLAUDE.md** - Agent context updated:
   - Added technology stack for 009-profile-dashboard
   - Preserves manual additions between markers

---

### Post-Phase 1 Constitution Check: ✅ PASSED (RE-VALIDATED)

**Validation Results**:
- ✅ TypeScript Strict Mode - All frontend code uses strict mode
- ✅ React Best Practices - Functional components, custom hooks, proper patterns
- ✅ FastAPI Architecture - Routers, services, Pydantic models, dependency injection
- ✅ Qdrant Standards - Python client, proper error handling, payload schemas
- ✅ Component Library - IBM Carbon + Tailwind CSS v4
- ✅ API Contracts - OpenAPI docs, RESTful conventions, Pydantic validation
- ✅ Testing Requirements - Pytest + Jest, 70% coverage target
- ✅ Performance Standards - <10s upload, <3s dashboard load, Redis caching
- ✅ Security Standards - Input validation, file type checks, JWT auth

**No Constitution Violations** - All principles satisfied ✅

---

## Implementation Readiness

### Files to Create (Backend)
- [ ] `backend/app/models/user.py` - User SQLAlchemy model
- [ ] `backend/app/models/profile.py` - Profile Pydantic models
- [ ] `backend/app/services/profile.py` - Profile business logic
- [ ] `backend/app/services/avatar.py` - Avatar processing service
- [ ] `backend/app/services/dashboard_metrics.py` - Dashboard aggregation
- [ ] `backend/app/routers/profile.py` - Profile API router
- [ ] `backend/app/db/migrations/009_add_profile_fields.py` - Database migration
- [ ] `backend/tests/test_profile.py` - Profile service tests
- [ ] `backend/tests/test_avatar.py` - Avatar processing tests
- [ ] `backend/tests/test_dashboard.py` - Dashboard metrics tests

### Files to Create (Frontend)
- [ ] `frontend/src/types/profile.ts` - Profile TypeScript types
- [ ] `frontend/src/services/profileApi.ts` - Profile API client
- [ ] `frontend/src/services/dashboardApi.ts` - Dashboard API client
- [ ] `frontend/src/hooks/useProfile.ts` - Profile data hook
- [ ] `frontend/src/hooks/useAvatarUpload.ts` - Avatar upload hook
- [ ] `frontend/src/hooks/useDashboard.ts` - Dashboard metrics hook
- [ ] `frontend/src/components/profile/ProfileForm.tsx` - Profile edit form
- [ ] `frontend/src/components/profile/AvatarUpload.tsx` - Avatar uploader
- [ ] `frontend/src/components/profile/Avatar.tsx` - Avatar display (with initials)
- [ ] `frontend/src/components/dashboard/MetricCard.tsx` - Metric tile
- [ ] `frontend/src/components/dashboard/ActivityTimeline.tsx` - Activity list
- [ ] `frontend/src/components/dashboard/TopTopics.tsx` - Top topics widget
- [ ] `frontend/src/app/profile/page.tsx` - Profile settings page
- [ ] `frontend/src/app/dashboard/page.tsx` - Dashboard page
- [ ] `frontend/tests/components/ProfileForm.test.tsx` - Profile form tests
- [ ] `frontend/tests/components/AvatarUpload.test.tsx` - Avatar upload tests
- [ ] `frontend/tests/hooks/useProfile.test.ts` - Profile hook tests

### Infrastructure Setup
- [ ] Create `storage/avatars/` directory
- [ ] Run database migration (add profile fields to users table)
- [ ] Create Qdrant collection `user_activity` (if not exists)
- [ ] Configure Redis cache for dashboard metrics

---

## Next Steps

**Ready for Phase 2: Task Generation** ✅

Run `/speckit.tasks` to generate actionable, dependency-ordered tasks.md based on:
- Functional requirements from spec.md
- Technical design from plan.md, data-model.md
- API contracts from contracts/
- Implementation guidance from quickstart.md

**Expected Tasks** (estimated):
- ~15-20 backend tasks (models, services, routers, tests)
- ~15-20 frontend tasks (components, hooks, pages, tests)
- ~5 infrastructure tasks (database migration, storage setup)
- **Total: 35-45 tasks** (estimated 3-5 days implementation time)

---

## Performance Targets (from Success Criteria)

| Metric | Target | Strategy |
|--------|--------|----------|
| Avatar upload time | < 10s | Pillow optimization, async I/O |
| Dashboard load time | < 3s | Redis cache (60s TTL), indexed queries |
| Profile update time | < 30s from login | Optimistic UI updates, fast API responses |
| Cache hit rate | > 70% | Smart invalidation on user actions |
| API response (profile) | < 200ms | PostgreSQL indexes, single queries |
| Image file size | < 50KB | JPEG quality=85, 200x200px |

---

## Risk Summary

**Low Risk** ✅
- All dependencies already installed
- Existing patterns well-established
- Clear technical decisions made
- PostgreSQL infrastructure mature
- No architectural changes required

**Mitigation Strategies**:
- Avatar upload security: Magic number validation, size limits, path sanitization
- Performance: Redis caching, indexed database queries
- Data consistency: Use existing auth system, follow established patterns

---

## Documentation Index

- **[spec.md](./spec.md)** - Feature specification (user requirements, success criteria)
- **[plan.md](./plan.md)** - This file (implementation plan, technical context)
- **[research.md](./research.md)** - Technical research findings
- **[data-model.md](./data-model.md)** - Entity definitions, validation rules
- **[quickstart.md](./quickstart.md)** - Developer implementation guide
- **[contracts/profile-api.yaml](./contracts/profile-api.yaml)** - Profile API OpenAPI spec
- **[contracts/dashboard-api.yaml](./contracts/dashboard-api.yaml)** - Dashboard API OpenAPI spec

---

**Plan Status**: ✅ **COMPLETE AND READY FOR IMPLEMENTATION**

**Last Updated**: 2026-02-03
**Phase**: Phase 1 Complete - Ready for `/speckit.tasks`
