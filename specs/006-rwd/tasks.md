---
description: "Task list for Responsive Web Design Support implementation"
---

# Tasks: Responsive Web Design Support

**Input**: Design documents from `/specs/006-rwd/`
**Prerequisites**: plan.md, spec.md, research.md, quickstart.md

**Tests**: Not requested in feature specification - manual testing strategy defined in quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `frontend/src/` for all source files
- All tasks target frontend components and styles
- No backend changes required for this feature

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify existing mobile infrastructure and prepare for responsive implementation

- [x] T001 Verify Tailwind CSS v4 configuration in frontend/package.json
- [x] T002 [P] Review existing mobile CSS in frontend/src/app/globals.css (lines 1068-1194)
- [x] T003 [P] Verify MobileHeader component exists in frontend/src/components/layout/MobileHeader.tsx
- [x] T004 [P] Check useStore has sidebarOpen and toggleSidebar state in frontend/src/store/useStore.ts
- [x] T005 Create responsive design testing checklist based on quickstart.md Phase 5

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core responsive infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Update globals.css to add mobile-first CSS variables and utility classes in frontend/src/app/globals.css
- [x] T007 [P] Add CSS breakpoint definitions (mobile <768px, tablet 768-1024px, desktop >1024px) in frontend/src/app/globals.css
- [x] T008 [P] Fix touch target sizes for .btn-icon and .input-btn to 44x44px minimum in frontend/src/app/globals.css
- [x] T009 Update useStore to ensure sidebarOpen state is properly initialized in frontend/src/store/useStore.ts
- [x] T010 Add sidebar overlay backdrop styles in frontend/src/app/globals.css

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Mobile Browser Access (Priority: P1) 🎯 MVP

**Goal**: Enable basic mobile browser access with proper layout rendering and no horizontal scrolling

**Independent Test**: Access system from mobile browser (iOS Safari/Android Chrome), verify layout renders properly, text readable without horizontal scrolling, device rotation works correctly

### Implementation for User Story 1

- [x] T011 [P] [US1] Add mobile viewport meta tag to root layout in frontend/src/app/layout.tsx
- [x] T012 [P] [US1] Update .app-container mobile styles for proper viewport height in frontend/src/app/globals.css
- [x] T013 [P] [US1] Add mobile-specific padding and margin adjustments in frontend/src/app/globals.css
- [x] T014 [P] [US1] Update base font sizes for mobile readability in frontend/src/app/globals.css
- [ ] T015 [US1] Test layout on multiple mobile viewports (390x844, 375x667, 360x800) using Chrome DevTools
- [ ] T016 [US1] Verify no horizontal scroll on any page at <768px width
- [ ] T017 [US1] Test orientation change (portrait to landscape) maintains layout integrity

**Checkpoint**: Mobile browser access working - system accessible on mobile without layout breakage

---

## Phase 4: User Story 2 - Mobile Navigation (Priority: P1)

**Goal**: Implement hamburger menu navigation that replaces desktop sidebar on mobile

**Independent Test**: Open system on mobile, tap hamburger menu, verify menu appears with all navigation options, select item to navigate, confirm menu closes, tap outside menu to close without navigating

### Implementation for User Story 2

- [x] T018 [P] [US2] Update Sidebar component to use sidebarOpen state for mobile overlay in frontend/src/components/layout/Sidebar.tsx
- [x] T019 [P] [US2] Add conditional className for .sidebar.open state in frontend/src/components/layout/Sidebar.tsx
- [x] T020 [US2] Update handleNavClick to close sidebar on mobile navigation in frontend/src/components/layout/Sidebar.tsx
- [x] T021 [US2] Add sidebar overlay backdrop component to main layout in frontend/src/app/(main)/layout.tsx
- [x] T022 [US2] Implement overlay click handler to close sidebar in frontend/src/app/(main)/layout.tsx
- [x] T023 [US2] Verify MobileHeader hamburger menu toggles sidebar state in frontend/src/components/layout/MobileHeader.tsx
- [x] T024 [US2] Add smooth slide animation for sidebar (300ms transition) in frontend/src/app/globals.css
- [ ] T025 [US2] Test hamburger menu animation is smooth (<300ms) on mid-range mobile device
- [ ] T026 [US2] Test menu closes when navigation item is tapped
- [ ] T027 [US2] Test menu closes when tapping outside (overlay) without navigating

**Checkpoint**: Mobile navigation fully functional - users can access all sections via hamburger menu

---

## Phase 5: User Story 3 - Full-Screen Chat Interface (Priority: P1)

**Goal**: Provide full-screen chat experience on mobile that maximizes viewport space

**Independent Test**: Open chat on mobile, verify full viewport usage (minus header), scroll through messages, tap input to show keyboard, verify input stays above keyboard, send message successfully

### Implementation for User Story 3

- [x] T028 [P] [US3] Update .chat-container to use 100dvh viewport height on mobile in frontend/src/app/globals.css
- [x] T029 [P] [US3] Adjust .chat-messages padding from 5rem to 1rem on mobile in frontend/src/app/globals.css
- [x] T030 [P] [US3] Update .message-content max-width from 70% to 85% on mobile in frontend/src/app/globals.css
- [x] T031 [P] [US3] Reduce .chat-input-container padding from 5rem to 1rem on mobile in frontend/src/app/globals.css
- [x] T032 [US3] Update ChatWindow component to handle mobile keyboard appearance in frontend/src/components/chat/ChatWindow.tsx
- [ ] T033 [US3] Test chat occupies full viewport (minus 56px mobile header) on mobile
- [ ] T034 [US3] Test keyboard appears and input remains accessible above keyboard on iOS
- [ ] T035 [US3] Test keyboard appears and input remains accessible above keyboard on Android
- [ ] T036 [US3] Verify chat scrolls to new message after sending on mobile

**Checkpoint**: Full-screen chat working - mobile users have optimal chat experience

---

## Phase 6: User Story 4 - Responsive Data Display (Priority: P2)

**Goal**: Enable horizontal scrolling for tables and proper stacking of data visualizations on mobile

**Independent Test**: Navigate to pages with tables/data displays, verify horizontal scrolling works smoothly with visible indicators, dashboard cards stack vertically, all data accessible

### Implementation for User Story 4

- [x] T037 [P] [US4] Add horizontal scroll styles to .table-container with touch support in frontend/src/app/globals.css
- [x] T038 [P] [US4] Set min-width for .data-table (600px) to prevent collapse on mobile in frontend/src/app/globals.css
- [x] T039 [P] [US4] Add visible scroll indicators for horizontal scrollable content in frontend/src/app/globals.css
- [x] T040 [US4] Wrap data tables in .table-container div in frontend/src/app/(main)/admin/knowledge-base/page.tsx
- [x] T041 [US4] Wrap data browser tables in .table-container div in frontend/src/components/structured/DataBrowserPanel.tsx
- [x] T042 [US4] Add responsive grid classes to dashboard stat cards in frontend/src/app/(main)/admin/dashboard/page.tsx
- [x] T043 [US4] Stack dashboard cards vertically on mobile (grid-cols-1) in frontend/src/app/(main)/admin/dashboard/page.tsx
- [x] T044 [US4] Update FilterPanel to be collapsible/stackable on mobile in frontend/src/components/structured/FilterPanel.tsx
- [ ] T045 [US4] Test wide tables scroll horizontally with smooth touch scrolling on iOS
- [ ] T046 [US4] Test wide tables scroll horizontally with smooth touch scrolling on Android
- [ ] T047 [US4] Verify dashboard visualizations stack vertically on mobile viewport
- [ ] T048 [US4] Test filter controls are accessible and usable with touch input

**Checkpoint**: Responsive data display working - tables scroll, dashboards stack properly on mobile

---

## Phase 7: User Story 5 - Touch-Optimized Controls (Priority: P2)

**Goal**: Ensure all interactive elements have adequate touch targets (44x44px minimum) and spacing

**Independent Test**: Attempt to interact with all buttons, links, inputs, dropdowns on mobile, verify accurate tapping without hitting adjacent elements, confirm adequate spacing

### Implementation for User Story 5

- [x] T049 [P] [US5] Audit all button components for 44x44px minimum touch target in frontend/src/app/globals.css
- [x] T050 [P] [US5] Add min-width and min-height constraints to all button classes in frontend/src/app/globals.css
- [x] T051 [P] [US5] Update form input touch targets with adequate padding in frontend/src/app/globals.css
- [x] T052 [P] [US5] Add spacing between adjacent buttons (minimum 8px gap) in frontend/src/app/globals.css
- [x] T053 [US5] Update .button-group to stack vertically on mobile in frontend/src/app/globals.css
- [x] T054 [US5] Increase .form-group spacing to prevent mis-taps in frontend/src/app/globals.css
- [x] T055 [US5] Update ExportButton to meet touch target requirements in frontend/src/components/structured/ExportButton.tsx
- [ ] T056 [US5] Test all navigation items meet 44x44px minimum on mobile
- [ ] T057 [US5] Test form inputs have adequate spacing (no adjacent field mis-taps)
- [ ] T058 [US5] Test action buttons have adequate spacing between them
- [ ] T059 [US5] Run automated accessibility audit to verify touch target sizes

**Checkpoint**: Touch-optimized controls complete - all interactive elements meet mobile touch standards

---

## Phase 8: User Story 6 - Complete Mobile Feature Parity (Priority: P3)

**Goal**: Ensure all features accessible on mobile without functionality loss

**Independent Test**: Systematically access each feature area (admin dashboard, KB management, permissions, settings) on mobile, verify all functions can be performed, compare to desktop functionality

### Implementation for User Story 6

- [ ] T060 [P] [US6] Update UserModal for mobile bottom sheet behavior in frontend/src/components/ui/UserModal.tsx
- [ ] T061 [P] [US6] Add mobile-responsive styles to UserModal with slide-up animation in frontend/src/app/globals.css
- [ ] T062 [P] [US6] Update SourcePreview to mobile-friendly drawer/modal in frontend/src/components/chat/SourcePreview.tsx
- [ ] T063 [US6] Test admin dashboard functions on mobile (all tasks accessible)
- [ ] T064 [US6] Test knowledge base management on mobile (upload documents, edit entries)
- [ ] T065 [US6] Test permission management on mobile (modify user permissions)
- [ ] T066 [US6] Test user settings/profile on mobile (all settings editable)
- [ ] T067 [US6] Verify login page fully responsive on mobile in frontend/src/app/(auth)/login/page.tsx
- [ ] T068 [US6] Document any mobile-specific UI differences in feature documentation
- [ ] T069 [US6] Verify no critical functionality missing on mobile vs desktop

**Checkpoint**: Complete feature parity achieved - all desktop features work on mobile

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final refinements affecting multiple user stories

- [ ] T070 [P] Add CSS animations for smooth transitions (fade-in, slide-up) in frontend/src/app/globals.css
- [ ] T071 [P] Optimize scrollbar styles for mobile browsers in frontend/src/app/globals.css
- [ ] T072 [P] Add hover state alternatives for touch interactions in frontend/src/app/globals.css
- [ ] T073 Perform comprehensive mobile browser testing per quickstart.md Phase 5.1 test matrix
- [ ] T074 Run Lighthouse Mobile audit and achieve score >90
- [ ] T075 Profile animation performance (<300ms, 60fps) on mid-range Android device
- [ ] T076 Test orientation changes across all pages maintain layout integrity
- [ ] T077 Verify all success criteria from spec.md are met
- [ ] T078 Update DESIGN_SYSTEM.md with responsive design patterns and breakpoints
- [ ] T079 [P] Document mobile debugging tips in developer documentation
- [ ] T080 Run full quickstart.md validation checklist

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-8)**: All depend on Foundational phase completion
  - User stories can proceed in parallel (if staffed) or sequentially in priority order
  - US1 (Mobile Browser Access) - Independent, can start first
  - US2 (Mobile Navigation) - Independent, can start in parallel with US1
  - US3 (Full-Screen Chat) - Independent, can start in parallel with US1/US2
  - US4 (Responsive Data Display) - Depends on US1 completing, can run with US5
  - US5 (Touch-Optimized Controls) - Independent, can run in parallel with US4
  - US6 (Complete Feature Parity) - Depends on US1-US5, should be last
- **Polish (Phase 9)**: Depends on desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Foundation for mobile access - Independent, no dependencies on other stories
- **User Story 2 (P1)**: Mobile navigation - Independent, can run parallel with US1
- **User Story 3 (P1)**: Full-screen chat - Independent, can run parallel with US1/US2
- **User Story 4 (P2)**: Data display - Requires US1 (mobile browser access) as foundation
- **User Story 5 (P2)**: Touch controls - Independent, can run parallel with US4
- **User Story 6 (P3)**: Feature parity - Integrates with US1-US5, should complete last

### Within Each User Story

- CSS foundation updates before component modifications
- Component updates before testing tasks
- Parallel tasks marked [P] can run simultaneously (different files)
- Testing tasks should complete before marking story done
- Story complete before moving to next priority

### Parallel Opportunities

**Setup Phase** (T001-T005): All tasks [P] can run in parallel

**Foundational Phase** (T006-T010): Tasks T007, T008 [P] can run in parallel

**User Story 1** (T011-T017): T011, T012, T013, T014 [P] can run simultaneously

**User Story 2** (T018-T027): T018, T019 [P] can run simultaneously

**User Story 3** (T028-T036): T028, T029, T030, T031 [P] can run simultaneously

**User Story 4** (T037-T048): T037, T038, T039 [P] can run simultaneously

**User Story 5** (T049-T059): T049, T050, T051, T052 [P] can run simultaneously

**User Story 6** (T060-T069): T060, T061, T062 [P] can run simultaneously

**Polish Phase** (T070-T080): T070, T071, T072, T079 [P] can run simultaneously

---

## Parallel Example: User Story 1 (Mobile Browser Access)

```bash
# Launch all CSS updates for US1 in parallel:
Task: "Add mobile viewport meta tag to root layout in frontend/src/app/layout.tsx"
Task: "Update .app-container mobile styles for proper viewport height in frontend/src/app/globals.css"
Task: "Add mobile-specific padding and margin adjustments in frontend/src/app/globals.css"
Task: "Update base font sizes for mobile readability in frontend/src/app/globals.css"

# Then sequentially:
Task: "Test layout on multiple mobile viewports"
Task: "Verify no horizontal scroll on any page"
Task: "Test orientation change maintains layout integrity"
```

---

## Parallel Example: User Story 2 (Mobile Navigation)

```bash
# Launch component updates in parallel:
Task: "Update Sidebar component to use sidebarOpen state for mobile overlay"
Task: "Add conditional className for .sidebar.open state"

# Then:
Task: "Update handleNavClick to close sidebar on mobile navigation"

# Then layout integration:
Task: "Add sidebar overlay backdrop component to main layout"
Task: "Implement overlay click handler to close sidebar"

# Finally testing:
Task: "Test hamburger menu animation is smooth (<300ms)"
Task: "Test menu closes when navigation item is tapped"
Task: "Test menu closes when tapping outside (overlay)"
```

---

## Implementation Strategy

### MVP First (User Stories 1, 2, 3 Only - Core P1)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Mobile Browser Access)
4. Complete Phase 4: User Story 2 (Mobile Navigation)
5. Complete Phase 5: User Story 3 (Full-Screen Chat)
6. **STOP and VALIDATE**: Test core mobile functionality independently
7. Deploy/demo if ready - users can now access and use AIKM on mobile browsers

### Incremental Delivery

1. **Foundation** (Phase 1-2) → Development environment ready, CSS framework in place
2. **MVP** (Phase 3-5: US1-US3) → Test independently → Deploy/Demo (Core mobile functionality!)
3. **Enhanced UX** (Phase 6-7: US4-US5) → Test independently → Deploy/Demo (Better data viewing and touch)
4. **Complete** (Phase 8: US6) → Test independently → Deploy/Demo (Full feature parity)
5. **Polish** (Phase 9) → Final refinements → Deploy/Demo (Production-ready)

Each increment adds value without breaking previous functionality.

### Parallel Team Strategy

With multiple developers:

1. **All together**: Complete Setup + Foundational (Phase 1-2)
2. **Once Foundational done, split work**:
   - Developer A: User Story 1 (Mobile Browser Access)
   - Developer B: User Story 2 (Mobile Navigation)
   - Developer C: User Story 3 (Full-Screen Chat)
3. **Next iteration**:
   - Developer A: User Story 4 (Responsive Data Display)
   - Developer B: User Story 5 (Touch-Optimized Controls)
4. **Final iteration**:
   - All together: User Story 6 (Complete Feature Parity)
   - All together: Polish & Cross-Cutting Concerns

Stories complete and integrate independently without blocking each other.

---

## Task Summary

**Total Tasks**: 80 tasks across 9 phases

**Task Breakdown by Phase**:
- Phase 1 (Setup): 5 tasks
- Phase 2 (Foundational): 5 tasks
- Phase 3 (US1 - Mobile Browser Access): 7 tasks
- Phase 4 (US2 - Mobile Navigation): 10 tasks
- Phase 5 (US3 - Full-Screen Chat): 9 tasks
- Phase 6 (US4 - Responsive Data Display): 12 tasks
- Phase 7 (US5 - Touch-Optimized Controls): 11 tasks
- Phase 8 (US6 - Complete Feature Parity): 10 tasks
- Phase 9 (Polish): 11 tasks

**Task Breakdown by User Story**:
- User Story 1 (P1 - Mobile Browser Access): 7 implementation tasks
- User Story 2 (P1 - Mobile Navigation): 10 implementation tasks
- User Story 3 (P1 - Full-Screen Chat): 9 implementation tasks
- User Story 4 (P2 - Responsive Data Display): 12 implementation tasks
- User Story 5 (P2 - Touch-Optimized Controls): 11 implementation tasks
- User Story 6 (P3 - Complete Feature Parity): 10 implementation tasks
- Setup + Foundational: 10 tasks
- Polish: 11 tasks

**Parallel Opportunities**: 35 tasks marked [P] can run in parallel within their phases

**MVP Scope**: User Stories 1, 2, 3 (26 implementation tasks + 10 setup/foundational = 36 tasks for MVP)

**Independent Test Criteria**:
- US1: Access from mobile browser, no horizontal scroll, orientation change works
- US2: Hamburger menu opens/closes, navigation works, menu closes on selection/outside tap
- US3: Chat full-screen, keyboard handling, message sending works
- US4: Tables scroll horizontally, dashboards stack, filters accessible
- US5: All elements 44x44px minimum, no mis-taps, adequate spacing
- US6: All features accessible, no functionality loss vs desktop

---

## Notes

- [P] tasks = different files, no dependencies within phase
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- No test tasks (manual testing strategy in quickstart.md)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- CSS-first approach: Update styles before component logic
- Mobile-first breakpoints: Base styles for mobile, media queries for larger screens
- Performance budget: <300ms animations, 60fps on mid-range devices
- Accessibility: 44x44px touch targets, adequate spacing, keyboard support
