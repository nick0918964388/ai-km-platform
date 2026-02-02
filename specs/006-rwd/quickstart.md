# Quickstart Guide - RWD Implementation

**Feature**: Responsive Web Design Support (006-rwd)
**Date**: 2026-02-02
**Status**: Ready for Implementation

## Overview

This guide provides step-by-step instructions for implementing responsive web design support in the AIKM system. Follow the implementation order to ensure dependencies are satisfied.

---

## Prerequisites

Before starting implementation:

1. **Development Environment**:
   - Node.js 20+
   - Next.js 16.1.6
   - Tailwind CSS v4 (already installed)

2. **Testing Tools**:
   - Chrome DevTools (Responsive Mode)
   - Real iOS device with Safari (iPhone 12 or newer)
   - Real Android device with Chrome (mid-range or better)

3. **Reference Materials**:
   - [research.md](./research.md) - Technical decisions and rationale
   - [spec.md](./spec.md) - Feature requirements

---

## Implementation Phases

### Phase 1: Core Mobile Infrastructure (Priority: P1)

**Goal**: Establish mobile header, hamburger menu, and responsive layout foundation.

**Estimated Time**: 2-3 hours

#### Step 1.1: Verify Mobile Header Implementation

**File**: `frontend/src/components/layout/MobileHeader.tsx`

**Actions**:
1. Open the file and verify the component exists
2. Check that it imports and uses `useStore` for `sidebarOpen` state
3. Ensure hamburger menu icon toggles between `Menu` and `Close` icons
4. Verify "New Chat" button exists and functions

**Validation**:
```bash
cd frontend
npm run dev
# Open http://localhost:3000 in mobile viewport (390x844)
# Verify mobile header appears
# Click hamburger menu - sidebar should toggle
```

**Expected Result**: Mobile header visible below 768px breakpoint, hamburger menu toggles sidebar state.

---

#### Step 1.2: Update Sidebar for Mobile Overlay

**File**: `frontend/src/components/layout/Sidebar.tsx`

**Actions**:
1. Add `sidebarOpen` state from `useStore`
2. Add conditional className for mobile open state
3. Update `handleNavClick` to close sidebar on mobile navigation

**Changes Required**:
```tsx
// Add to component
const { sidebarOpen } = useStore();

// Update wrapper with mobile overlay class
<div className={`sidebar ${sidebarOpen ? 'open' : ''} ${sidebarCollapsed ? 'collapsed' : ''}`}>
```

**CSS Already Exists** in `globals.css` (lines 1152-1163):
- `.sidebar` with `position: fixed` and `left: -260px` on mobile
- `.sidebar.open` with `left: 0` transition

**Validation**:
- Mobile viewport: Sidebar hidden by default
- Click hamburger: Sidebar slides in from left
- Click nav item: Sidebar closes automatically

---

#### Step 1.3: Add Sidebar Overlay Backdrop

**File**: `frontend/src/app/(main)/layout.tsx`

**Actions**:
1. Import `useStore` hook
2. Add overlay element that appears when sidebar is open on mobile
3. Add click handler to close sidebar when clicking overlay

**Implementation**:
```tsx
'use client';

import MobileHeader from '@/components/layout/MobileHeader';
import Sidebar from '@/components/layout/Sidebar';
import { useStore } from '@/store/useStore';

export default function MainLayout({ children }: { children: React.ReactNode }) {
  const { sidebarOpen, toggleSidebar } = useStore();

  return (
    <div className="app-container">
      <MobileHeader />

      {/* Sidebar overlay for mobile */}
      {sidebarOpen && (
        <div
          className="sidebar-overlay"
          onClick={toggleSidebar}
          aria-hidden="true"
        />
      )}

      <Sidebar />

      <main className="main-content">
        {children}
      </main>
    </div>
  );
}
```

**CSS Already Exists** in `globals.css` (lines 1117-1124):
- `.sidebar-overlay` styles defined

**Validation**:
- Mobile: Tap outside sidebar to close it
- Overlay should have semi-transparent black background

---

#### Step 1.4: Touch Target Size Audit

**Files to Check**:
- All button components
- Navigation items
- Form inputs
- Action buttons

**Minimum Requirements**:
- All interactive elements: 44x44px minimum
- Spacing between elements: 8px minimum

**Audit Checklist**:
```bash
# Use browser DevTools to inspect element dimensions
# Check these components:
- .nav-item (currently 44px ✓)
- .btn (check padding results in 44px height)
- .mobile-menu-btn (44x44px ✓)
- .input-btn (40x40px - needs fix to 44x44px)
- Form inputs (touch area adequate)
```

**Fix Required** in `globals.css`:
```css
/* Update from 40x40px to 44x44px */
.btn-icon,
.input-btn {
  width: 44px;
  height: 44px;
  min-width: 44px;
  min-height: 44px;
}
```

---

### Phase 2: Component Adaptation (Priority: P1-P2)

**Goal**: Adapt major components for mobile use.

**Estimated Time**: 4-5 hours

#### Step 2.1: Chat Interface Full-Screen Mobile

**File**: `frontend/src/components/chat/ChatWindow.tsx`

**Actions**:
1. Update chat container to use full viewport height on mobile
2. Adjust message padding for smaller screens
3. Update input container padding

**CSS Updates** in `globals.css`:

```css
/* Update existing .chat-messages */
@media (max-width: 768px) {
  .chat-messages {
    padding: 1rem; /* Reduce from 5rem */
  }

  .message-content {
    max-width: 85%; /* Increase from 70% */
  }
}

/* Update existing .chat-input-container */
@media (max-width: 768px) {
  .chat-input-container {
    padding: 1rem; /* Reduce from 5rem */
  }
}

/* Full viewport height on mobile */
.chat-container {
  height: 100vh;
  height: 100dvh; /* Dynamic viewport height for mobile */
}

@media (max-width: 768px) {
  .chat-container {
    height: calc(100vh - 56px); /* Subtract mobile header */
    height: calc(100dvh - 56px);
  }
}
```

**Validation**:
- Mobile chat fills entire screen below header
- Messages readable without horizontal scroll
- Input stays above keyboard when focused

---

#### Step 2.2: Login Page Mobile Responsiveness

**File**: `frontend/src/app/(auth)/login/page.tsx`

**CSS Already Exists** in `globals.css` (lines 1165-1181):
- Login container responsive layout
- Image panel collapses to small height on mobile
- Login form adapts to full width

**Actions**:
1. Verify existing responsive styles work correctly
2. Test on real mobile device
3. Check image panel minimum height (200px)

**Validation**:
- Portrait mobile: Login form full width, image panel 200px high
- Form inputs easy to tap and fill
- "Sign In" button full width and easily tappable

---

#### Step 2.3: Dashboard Cards Mobile Stacking

**File**: `frontend/src/app/(main)/admin/dashboard/page.tsx`

**Actions**:
1. Add responsive grid classes using Tailwind CSS
2. Stack stat cards vertically on mobile
3. Ensure charts/graphs adapt to narrow width

**Implementation Strategy**:
```tsx
{/* Stat cards grid - responsive */}
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
  <StatCard {...} />
  <StatCard {...} />
  <StatCard {...} />
  <StatCard {...} />
</div>

{/* Charts section - stacked on mobile */}
<div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
  <div className="card">
    {/* Chart 1 */}
  </div>
  <div className="card">
    {/* Chart 2 */}
  </div>
</div>
```

**Validation**:
- Mobile (<768px): Single column layout
- Tablet (768-1024px): 2 columns for stats
- Desktop (>1024px): 4 columns for stats

---

#### Step 2.4: Table Horizontal Scroll

**Files**:
- `frontend/src/app/(main)/admin/knowledge-base/page.tsx`
- `frontend/src/components/structured/DataBrowserPanel.tsx`

**Actions**:
1. Wrap data tables in `.table-container` div
2. Enable horizontal scroll with touch support
3. Add visible scroll indicators

**Implementation**:
```tsx
<div className="table-container">
  <table className="data-table">
    {/* Table content */}
  </table>
</div>
```

**CSS Already Exists** in `globals.css` (lines 495-500):
- `.table-container` with border and overflow

**Additional CSS Required**:
```css
@media (max-width: 768px) {
  .table-container {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }

  .data-table {
    min-width: 600px; /* Prevent table from collapsing too narrow */
  }
}
```

**Validation**:
- Wide tables scroll horizontally on mobile
- Scroll indicator visible
- Smooth touch scrolling on iOS/Android

---

### Phase 3: Form and Input Optimization (Priority: P2)

**Goal**: Ensure all forms and inputs work well on mobile.

**Estimated Time**: 2-3 hours

#### Step 3.1: Form Input Touch Targets

**Files to Update**:
- All forms across the application

**Actions**:
1. Audit all input fields for adequate touch area
2. Increase spacing between form fields
3. Ensure labels are tappable and associated with inputs

**CSS Verification**:
```css
/* Verify existing styles meet requirements */
.form-input {
  padding: 0.75rem 1rem; /* 12px + font height = adequate */
  min-height: 44px;
}

.form-group {
  margin-bottom: 1.25rem; /* 20px spacing between fields */
}
```

**Validation**:
- All inputs tappable without precision aiming
- Adequate spacing prevents mis-taps
- Labels associated with inputs (click label focuses input)

---

#### Step 3.2: Mobile Keyboard Handling

**Component**: Chat input, search boxes, form fields

**Actions**:
1. Ensure input fields scroll into view when keyboard appears
2. Test fixed-position input bars stay above keyboard
3. Verify keyboard dismiss on submit/outside tap

**Implementation Notes**:
- Use `position: fixed; bottom: 0` for chat input
- Viewport height units (dvh) automatically account for keyboard
- Test on real devices (simulator keyboard behavior differs)

**Validation**:
- iOS: Keyboard appears, input visible above it
- Android: Same behavior across different keyboards (Gboard, SwiftKey)
- Landscape: Input still accessible when keyboard shows

---

#### Step 3.3: Button Spacing and Sizing

**Actions**:
1. Audit all button groups for adequate spacing
2. Ensure buttons meet 44x44px minimum
3. Add spacing between adjacent buttons

**CSS Updates**:
```css
/* Add gap to button groups */
.button-group {
  display: flex;
  gap: 0.75rem; /* 12px minimum spacing */
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .button-group {
    flex-direction: column; /* Stack vertically on mobile */
  }

  .button-group .btn {
    width: 100%; /* Full width buttons on mobile */
  }
}
```

**Validation**:
- No buttons smaller than 44x44px
- Minimum 8px spacing between buttons
- Mobile: Buttons stack vertically for easy tapping

---

### Phase 4: Modals and Overlays (Priority: P2)

**Goal**: Adapt modals to mobile-friendly bottom sheets.

**Estimated Time**: 2-3 hours

#### Step 4.1: User Modal Mobile Adaptation

**File**: `frontend/src/components/ui/UserModal.tsx`

**Actions**:
1. Add mobile-specific styles for bottom sheet behavior
2. Transform modal to slide up from bottom on mobile
3. Add swipe-down-to-close gesture (optional future enhancement)

**CSS Implementation**:
```css
@media (max-width: 768px) {
  .modal-overlay {
    align-items: flex-end; /* Align modal to bottom */
  }

  .modal-content {
    width: 100%;
    max-width: 100%;
    border-radius: 16px 16px 0 0;
    max-height: 90vh;
    margin: 0;
  }

  /* Add drag handle at top of bottom sheet */
  .modal-content::before {
    content: '';
    display: block;
    width: 40px;
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    margin: 12px auto 16px;
  }
}
```

**Validation**:
- Desktop: Modal centers on screen
- Mobile: Modal slides up from bottom
- Easy to close with tap outside or close button

---

### Phase 5: Testing and Validation (Priority: P3)

**Goal**: Comprehensive testing across devices and viewports.

**Estimated Time**: 3-4 hours

#### Step 5.1: Real Device Testing

**Test Matrix**:

| Device | OS | Browser | Viewport | Test Status |
|--------|----|---------|---------:|------------:|
| iPhone 14 Pro | iOS 17 | Safari | 393×852 | [ ] |
| iPhone SE | iOS 16 | Safari | 375×667 | [ ] |
| Samsung Galaxy S21 | Android 13 | Chrome | 360×800 | [ ] |
| iPad Air | iOS 17 | Safari | 820×1180 | [ ] |
| Desktop | - | Chrome DevTools | Various | [ ] |

**Test Scenarios**:
1. **Navigation Flow**:
   - [ ] Open hamburger menu
   - [ ] Navigate to each section
   - [ ] Verify menu closes after navigation
   - [ ] Test back button behavior

2. **Chat Interface**:
   - [ ] Send messages
   - [ ] View message history
   - [ ] Scroll through long conversations
   - [ ] Test input with mobile keyboard

3. **Data Tables**:
   - [ ] Scroll wide tables horizontally
   - [ ] Sort and filter data
   - [ ] Export functionality works
   - [ ] Pagination controls accessible

4. **Forms**:
   - [ ] Fill out all form fields
   - [ ] Submit forms successfully
   - [ ] Error validation displays correctly
   - [ ] Dropdown/select controls work

5. **Orientation Changes**:
   - [ ] Portrait to landscape transition smooth
   - [ ] No layout breakage
   - [ ] Content reflows correctly
   - [ ] Active states preserved

---

#### Step 5.2: Performance Profiling

**Tools**:
- Chrome DevTools Performance tab
- Lighthouse Mobile audit
- WebPageTest on 4G connection

**Metrics to Measure**:
- [ ] Menu animation: 60fps (16.6ms frame time)
- [ ] Sidebar slide transition: <300ms
- [ ] Orientation change reflow: <200ms
- [ ] Touch target response: <100ms

**Performance Budget**:
```
Sidebar animation: 300ms @ 60fps
Modal slide up: 300ms @ 60fps
Layout reflow on orientation: <200ms
First Contentful Paint (mobile): <2s on 4G
Lighthouse Mobile score: >90
```

---

#### Step 5.3: Accessibility Audit

**Tools**:
- Chrome DevTools Lighthouse Accessibility
- axe DevTools browser extension
- Manual keyboard navigation testing
- Screen reader testing (VoiceOver on iOS)

**Checklist**:
- [ ] All touch targets ≥44x44px
- [ ] Color contrast meets WCAG AA (4.5:1 for text)
- [ ] Focus indicators visible on all interactive elements
- [ ] Hamburger menu has aria-label
- [ ] Modal has proper ARIA attributes
- [ ] Tables have proper headers and captions
- [ ] Form inputs have associated labels

---

## Testing Commands

```bash
# Start development server
cd frontend
npm run dev

# Run in mobile viewport
# Chrome DevTools: Toggle device toolbar (Cmd+Shift+M / Ctrl+Shift+M)
# Select device: iPhone 12 Pro (390x844)

# Build for production testing
npm run build
npm run start

# Run Lighthouse audit
# Chrome DevTools > Lighthouse > Mobile > Analyze
```

---

## Troubleshooting

### Issue: Sidebar doesn't open on mobile

**Diagnosis**:
1. Check `useStore` sidebarOpen state is updating
2. Verify MobileHeader onClick triggers toggleSidebar
3. Check CSS `.sidebar.open` class is applied
4. Verify z-index hierarchy (sidebar z-50, overlay z-40)

**Fix**:
- Add console.log to verify state changes
- Inspect element to see if `.open` class is present
- Check CSS specificity isn't being overridden

---

### Issue: Horizontal scroll appears on mobile

**Diagnosis**:
1. Inspect which element is wider than viewport
2. Check for fixed-width elements or large padding
3. Look for `width` values in pixels rather than percentages

**Fix**:
```css
/* Add to body or root container */
body {
  overflow-x: hidden;
}

/* Fix specific overflowing elements */
.overflowing-element {
  max-width: 100%;
  overflow-x: auto;
}
```

---

### Issue: Touch targets too small

**Diagnosis**:
1. Use Chrome DevTools to measure element dimensions
2. Check computed styles for width/height
3. Verify padding isn't collapsed

**Fix**:
```css
.small-button {
  min-width: 44px;
  min-height: 44px;
  padding: 12px 16px; /* Ensure adequate padding */
}
```

---

### Issue: Keyboard covers input on iOS

**Diagnosis**:
1. Check if input is in fixed-position container
2. Verify viewport height units are used correctly
3. Test if scroll is disabled on body

**Fix**:
```css
/* Use dynamic viewport height */
.chat-container {
  height: 100dvh; /* Accounts for keyboard */
}

/* Ensure input scrolls into view */
input:focus {
  scroll-margin-bottom: 20px;
}
```

---

## Rollback Plan

If critical issues are discovered after deployment:

1. **Immediate Rollback**:
   ```bash
   git revert <commit-hash>
   git push origin main
   ```

2. **CSS-Only Rollback** (faster):
   - Comment out mobile-specific CSS in `globals.css`
   - Keep desktop breakpoint (>1024px) as default
   - Deploy updated CSS

3. **Feature Flag Approach** (if implemented):
   - Toggle `ENABLE_MOBILE_RWD` flag to false
   - Fallback to desktop-only layout

---

## Success Criteria Verification

Before marking feature complete, verify all success criteria from [spec.md](./spec.md):

- [ ] **SC-001**: Mobile browsers (iOS Safari, Android Chrome) work without layout breakage
- [ ] **SC-002**: Mobile task completion time within ±20% of desktop
- [ ] **SC-003**: 100% of interactive elements meet 44x44px minimum
- [ ] **SC-004**: All tables have smooth horizontal scrolling, no content cutoff
- [ ] **SC-005**: Hamburger menu opens/closes in <300ms
- [ ] **SC-006**: 95% of mobile users navigate successfully on first attempt
- [ ] **SC-007**: Chat interface uses ≥85% of viewport height on mobile
- [ ] **SC-008**: Zero features blocked on mobile vs desktop
- [ ] **SC-009**: Orientation change adapts within 200ms
- [ ] **SC-010**: Mobile page load within 120% of desktop time on 4G

---

## Post-Implementation Tasks

After completing implementation:

1. **Documentation**:
   - Update README with mobile testing instructions
   - Document known mobile browser quirks
   - Add mobile debugging tips to dev docs

2. **Monitoring**:
   - Set up analytics for mobile usage metrics
   - Track mobile error rates vs desktop
   - Monitor performance metrics by device type

3. **Future Enhancements** (out of scope):
   - PWA features (offline support, installability)
   - Touch gestures (swipe to close sidebar)
   - Lazy loading images for mobile bandwidth
   - Sticky table headers on scroll

---

**Phase 1 Complete**: Implementation guide ready. Proceed with `/speckit.tasks` to generate detailed task breakdown.
