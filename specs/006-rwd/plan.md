# Implementation Plan: Responsive Web Design Support

**Branch**: `006-rwd` | **Date**: 2026-02-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-rwd/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Add comprehensive responsive web design (RWD) support to the AIKM system to enable full functionality on mobile browsers. The implementation will leverage Tailwind CSS v4 utility classes and CSS custom properties to adapt the existing layout (sidebar navigation, chat interface, data tables, forms) to mobile viewports (<768px) and tablet viewports (768px-1024px). A hamburger menu will replace the desktop sidebar on mobile, the chat interface will occupy full viewport on small screens, and all interactive elements will meet minimum touch target sizes (44x44px iOS, 48x48px Android).

## Technical Context

**Language/Version**: TypeScript 5.x strict mode, Next.js 16.1.6, React 19.2.3
**Primary Dependencies**: Tailwind CSS v4, @carbon/react v1.100.0, @carbon/icons-react v11.74.0
**Storage**: N/A (frontend-only changes)
**Testing**: Manual testing on real devices (iOS Safari, Android Chrome), browser DevTools responsive mode
**Target Platform**: Modern mobile browsers (iOS Safari 15+, Chrome for Android 100+), tablet browsers, desktop browsers
**Project Type**: Web (frontend-only modifications)
**Performance Goals**: <300ms animation transitions, <200ms layout adaptation on orientation change
**Constraints**: Maintain 100% feature parity with desktop, no layout breakage on any supported viewport size
**Scale/Scope**: ~15-20 component files to modify, 3 responsive breakpoints (mobile <768px, tablet 768-1024px, desktop >1024px)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No constitution file exists for this project. Proceeding without constitutional constraints.

## Project Structure

### Documentation (this feature)

```text
specs/006-rwd/
├── plan.md              # This file
├── research.md          # Phase 0 research output
├── quickstart.md        # Phase 1 implementation guide
└── tasks.md             # Phase 2 task breakdown (created by /speckit.tasks)
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── app/
│   │   ├── globals.css                    # Modify: Add mobile-specific CSS rules
│   │   ├── (main)/layout.tsx              # Modify: Add MobileHeader, responsive layout wrapper
│   │   └── (auth)/login/page.tsx          # Modify: Ensure mobile responsiveness
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx                # Modify: Add mobile overlay behavior
│   │   │   └── MobileHeader.tsx           # Already exists: Verify implementation
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx             # Modify: Full-screen mobile layout
│   │   │   └── SourcePreview.tsx          # Modify: Mobile-friendly modal/drawer
│   │   ├── structured/
│   │   │   ├── DataBrowserPanel.tsx       # Modify: Horizontal scroll tables
│   │   │   ├── FilterPanel.tsx            # Modify: Mobile collapsible filters
│   │   │   └── ExportButton.tsx           # Modify: Touch-friendly button
│   │   └── ui/
│   │       └── UserModal.tsx              # Modify: Mobile-responsive modal
│   ├── hooks/
│   │   ├── useDashboard.ts                # Modify: Add mobile detection
│   │   └── useStructuredQuery.ts          # Verify: Ensure works on mobile
│   └── store/
│       └── useStore.ts                    # Modify: Add sidebarOpen state
├── package.json                            # Already has Tailwind CSS v4
└── next.config.ts                          # No changes needed
```

**Structure Decision**: Web application structure. This is a frontend-only feature modifying the presentation layer. No backend changes required as this is purely a responsive UI adaptation using CSS media queries and React state management for mobile menu toggling.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

N/A - No constitutional violations. This is a straightforward responsive design implementation using industry-standard practices (CSS media queries, mobile-first breakpoints, touch target sizing).
