---

description: "Task list for Profile Settings & Dashboard feature implementation"
---

# Tasks: Profile Settings & Dashboard

**Input**: Design documents from `/specs/009-profile-dashboard/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Tests are OPTIONAL - not included in this task list as feature spec does not require them.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `backend/app/`, `frontend/src/`
- Paths are absolute from repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create storage directory for avatars at `storage/avatars/` with .gitkeep file
- [X] T002 [P] Add Pillow==10.2.0 to `backend/requirements.txt` and install
- [X] T003 [P] Create database migration script at `backend/migrations/add_profile_fields.sql` per data-model.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 Run database migration to add profile fields (display_name, avatar_url, account_level, created_at, updated_at) to users table
- [X] T005 [P] Create Pydantic models for profile in `backend/app/models/profile.py` (UserProfile, ProfileUpdateRequest)
- [X] T006 [P] Create TypeScript type definitions in `frontend/src/types/profile.ts` (UserProfile interface)
- [X] T007 [P] Create TypeScript type definitions in `frontend/src/types/dashboard.ts` (DashboardMetrics, ActivityEntry, TopicEntry interfaces)
- [X] T008 Update Zustand store in `frontend/src/store/useStore.ts` to include profile state (user profile, loading, error)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Profile Viewing & Basic Info Update (Priority: P1) 🎯 MVP

**Goal**: Enable users to view and update their basic profile information (display name)

**Independent Test**: User can log in, navigate to `/profile`, view current display name/email/account level, update display name, save successfully, and see changes reflected throughout app immediately

### Implementation for User Story 1

- [X] T009 [P] [US1] Create profile service module in `backend/app/services/profile.py` with get_user_profile() function
- [X] T010 [P] [US1] Implement update_profile() function in `backend/app/services/profile.py` with display name validation (2-50 chars)
- [X] T011 [US1] Create profile router in `backend/app/routers/profile.py` with GET /api/profile endpoint
- [X] T012 [US1] Add PATCH /api/profile endpoint to `backend/app/routers/profile.py` for display name updates
- [X] T013 [US1] Register profile router in `backend/app/main.py` with app.include_router(profile.router)
- [X] T014 [P] [US1] Create profile service in `frontend/src/services/profileService.ts` with getProfile() and updateProfile() functions
- [X] T015 [P] [US1] Create useProfile hook in `frontend/src/hooks/useProfile.ts` for fetching and managing profile state
- [X] T016 [US1] Create ProfileForm component in `frontend/src/components/profile/ProfileForm.tsx` with TextInput for display name, read-only email field, and Save button
- [X] T017 [US1] Create profile settings page at `frontend/src/app/profile/page.tsx` that renders ProfileForm with loading/error states
- [X] T018 [US1] Add form validation to ProfileForm (display name 2-50 chars, show inline errors)
- [X] T019 [US1] Implement optimistic UI updates in ProfileForm (update store immediately, rollback on error)
- [X] T020 [US1] Add success/error notifications to ProfileForm using Carbon InlineNotification

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently

---

## Phase 4: User Story 2 - Avatar Management (Priority: P2)

**Goal**: Enable users to upload/remove custom avatars with account initials fallback

**Independent Test**: User can navigate to `/profile`, see initials fallback (if no avatar), upload JPG/PNG file (<5MB), see preview, save avatar, see it throughout app, remove avatar to revert to initials

### Implementation for User Story 2

- [X] T021 [P] [US2] Create avatar service module in `backend/app/services/avatar.py` with process_avatar() function (Pillow resize to 200x200, convert to JPG)
- [X] T022 [P] [US2] Implement delete_avatar() function in `backend/app/services/avatar.py` to clean up old avatar files
- [X] T023 [P] [US2] Add update_avatar_url() function to `backend/app/services/profile.py`
- [X] T024 [US2] Add POST /api/profile/avatar endpoint to `backend/app/routers/profile.py` for avatar upload (multipart/form-data)
- [X] T025 [US2] Add DELETE /api/profile/avatar endpoint to `backend/app/routers/profile.py` for avatar removal
- [X] T026 [US2] Add GET /api/avatars/{filename} static file endpoint to `backend/app/routers/profile.py` to serve avatar images
- [X] T027 [US2] Implement avatar file validation in `backend/app/services/avatar.py` (magic number check, 5MB limit, JPG/PNG/GIF formats)
- [X] T028 [P] [US2] Create generateInitials() utility function in `frontend/src/lib/utils.ts` (first letter of each word, max 2 letters)
- [X] T029 [P] [US2] Create AccountInitials component in `frontend/src/components/profile/AccountInitials.tsx` to display initials in circular badge
- [X] T030 [P] [US2] Add uploadAvatar() and deleteAvatar() functions to `frontend/src/services/profileService.ts`
- [X] T031 [P] [US2] Create useAvatarUpload hook in `frontend/src/hooks/useAvatarUpload.ts` for upload state management (file, preview, loading, error)
- [X] T032 [US2] Create AvatarUploader component in `frontend/src/components/profile/AvatarUploader.tsx` with Carbon FileUploader, preview, and AccountInitials fallback
- [X] T033 [US2] Integrate AvatarUploader into ProfileForm component in `frontend/src/components/profile/ProfileForm.tsx`
- [X] T034 [US2] Add avatar validation in AvatarUploader (file size, format, show errors)
- [X] T035 [US2] Implement remove avatar button in AvatarUploader with confirmation dialog
- [X] T036 [US2] Update Zustand store to propagate avatar changes to all components using profile data

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Real-Time Dashboard Metrics (Priority: P3)

**Goal**: Display real-time user activity metrics from backend databases

**Independent Test**: User can navigate to `/dashboard`, see document count, query count, account level, recent activity timeline (last 10-20 actions), top 5 topics with counts, empty states work correctly

### Implementation for User Story 3

- [X] T037 [P] [US3] Create dashboard service module in `backend/app/services/dashboard.py` with get_metrics() function
- [X] T038 [P] [US3] Implement get_document_count() helper in `backend/app/services/dashboard.py` (SQL COUNT on documents table filtered by user_id)
- [X] T039 [P] [US3] Implement get_query_count() helper in `backend/app/services/dashboard.py` (SQL COUNT on queries table filtered by user_id)
- [X] T040 [P] [US3] Implement get_recent_activity() helper in `backend/app/services/dashboard.py` (Qdrant scroll on activity_logs collection, limit 20)
- [X] T041 [P] [US3] Implement get_top_topics() helper in `backend/app/services/dashboard.py` (SQL GROUP BY on queries table, ORDER BY count DESC, LIMIT 5)
- [X] T042 [US3] Add Redis caching to get_metrics() in `backend/app/services/dashboard.py` (key: dashboard:{user_id}, TTL: 60s)
- [X] T043 [US3] Create GET /api/dashboard/metrics endpoint in `backend/app/routers/profile.py` with optional refresh parameter
- [X] T044 [US3] Add GET /api/dashboard/activity endpoint to `backend/app/routers/profile.py` with pagination (limit, offset params)
- [X] T045 [US3] Add GET /api/dashboard/topics endpoint to `backend/app/routers/profile.py` with limit parameter (default 5)
- [X] T046 [P] [US3] Create dashboard service in `frontend/src/services/dashboardService.ts` with getDashboardMetrics(), getRecentActivity(), getTopTopics() functions
- [X] T047 [P] [US3] Create useDashboard hook in `frontend/src/hooks/useDashboard.ts` for fetching dashboard data with refresh capability
- [X] T048 [P] [US3] Create MetricsCard component in `frontend/src/components/dashboard/MetricsCard.tsx` using Carbon Tile with icon, title, and value
- [X] T049 [P] [US3] Create ActivityTimeline component in `frontend/src/components/dashboard/ActivityTimeline.tsx` with chronological list of ActivityEntry items
- [X] T050 [P] [US3] Create TopTopics component in `frontend/src/components/dashboard/TopTopics.tsx` showing list of TopicEntry items with counts
- [X] T051 [US3] Create dashboard page at `frontend/src/app/dashboard/page.tsx` using Tailwind grid layout (4 metrics cards + 2 tiles)
- [X] T052 [US3] Add loading skeleton states to dashboard page using Carbon SkeletonText
- [X] T053 [US3] Implement empty state UI in ActivityTimeline for new users with no activity
- [X] T054 [US3] Implement empty state UI in TopTopics for users with no query history
- [X] T055 [US3] Add manual refresh button to dashboard page to bypass cache

**Checkpoint**: All user stories should now be independently functional

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T056 [P] Add navigation links to profile and dashboard pages in `frontend/src/components/layout/Sidebar.tsx` (if sidebar exists)
- [X] T057 [P] Update avatar display in existing UI components (header, sidebar, chat window) to use profile avatar_url or AccountInitials
- [X] T058 [P] Add responsive design breakpoints to ProfileForm (mobile layout stacking)
- [X] T059 [P] Add responsive design breakpoints to dashboard page (mobile: single column, tablet: 2 cols, desktop: 4 cols)
- [X] T060 Code cleanup and remove console.logs from profile and dashboard components
- [X] T061 Verify quickstart.md instructions by following manual testing checklist
- [X] T062 [P] Add Carbon icons to MetricsCard components (DocumentIcon, SearchIcon, StarIcon, CalendarIcon from @carbon/icons-react)
- [X] T063 Test avatar upload with various file types/sizes (JPG, PNG, GIF, >5MB, corrupted files)
- [X] T064 Test profile update with edge cases (empty string, 51 chars, special characters, emoji in display name)
- [X] T065 Test dashboard with edge cases (new user, user with 1000+ documents/queries)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Integrates with US1 ProfileForm but independently testable
- **User Story 3 (P3)**: Can start after Foundational (Phase 2) - No dependencies on US1/US2

### Within Each User Story

- Backend models/services before routers
- Frontend types/services before hooks
- Hooks before components
- Basic components before page integration
- Core implementation before polish/validation

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, all user stories can start in parallel (if team capacity allows)
- Within each user story, tasks marked [P] can run in parallel
- All Polish tasks marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch backend tasks together:
Task: "T009 [P] [US1] Create profile service module in backend/app/services/profile.py"
Task: "T010 [P] [US1] Implement update_profile() function in backend/app/services/profile.py"

# Launch frontend tasks together (after types):
Task: "T014 [P] [US1] Create profile service in frontend/src/services/profileService.ts"
Task: "T015 [P] [US1] Create useProfile hook in frontend/src/hooks/useProfile.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Profile Viewing & Basic Info Update)
4. **STOP and VALIDATE**: Test User Story 1 independently per acceptance scenarios
5. Deploy/demo if ready

**MVP Scope**: After completing User Story 1, users can:
- ✅ View profile information (display name, email, account level, creation date)
- ✅ Update display name with validation
- ✅ See updates reflected throughout application
- ✅ Get validation errors for invalid input

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo (Avatar management)
4. Add User Story 3 → Test independently → Deploy/Demo (Dashboard metrics)
5. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (T009-T020)
   - Developer B: User Story 2 (T021-T036)
   - Developer C: User Story 3 (T037-T055)
3. Stories complete and integrate independently

---

## Task Summary

| Phase | Task Count | Story | Can Start After |
|-------|-----------|-------|-----------------|
| Phase 1: Setup | 3 | N/A | Immediately |
| Phase 2: Foundational | 5 | N/A | Phase 1 |
| Phase 3: User Story 1 (P1) | 12 | Profile Viewing & Update | Phase 2 |
| Phase 4: User Story 2 (P2) | 16 | Avatar Management | Phase 2 |
| Phase 5: User Story 3 (P3) | 19 | Dashboard Metrics | Phase 2 |
| Phase 6: Polish | 10 | N/A | All stories |
| **Total** | **65 tasks** | 3 stories | - |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Tests are OPTIONAL per feature spec - focus on manual testing using acceptance scenarios
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- File paths are absolute from repository root
- Follow quickstart.md for detailed implementation guidance and setup instructions
