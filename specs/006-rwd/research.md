# Phase 0: Research - RWD Implementation

**Feature**: Responsive Web Design Support (006-rwd)
**Date**: 2026-02-02

## Technical Decisions

### 1. Responsive Breakpoint Strategy

**Decision**: Use three-tier breakpoint system with mobile-first approach

**Rationale**:
- Mobile (<768px): Covers smartphones in portrait and landscape
- Tablet (768px-1024px): Covers tablets and small laptops
- Desktop (>1024px): Covers standard desktop monitors

This aligns with industry standards and the existing CSS implementation in `globals.css` which already has `@media (max-width: 768px)` defined.

**Alternatives Considered**:
- Four-tier system (xs, sm, md, lg, xl): Rejected as overly complex for this application's needs
- Two-tier system (mobile/desktop): Rejected as tablets need specific handling for optimal UX

**Implementation**:
```css
/* Mobile-first approach */
/* Base styles = mobile (<768px) */

@media (min-width: 768px) {
  /* Tablet styles */
}

@media (min-width: 1024px) {
  /* Desktop styles */
}
```

---

### 2. Hamburger Menu Implementation

**Decision**: Use CSS transforms with React state management for sidebar toggle

**Rationale**:
- Existing infrastructure already in place (`sidebarOpen` state in useStore.ts)
- MobileHeader.tsx already implements toggle button
- CSS transforms provide smooth 60fps animations
- Native CSS transitions are more performant than JavaScript animations

**Alternatives Considered**:
- Third-party menu libraries (react-burger-menu): Rejected due to unnecessary dependency bloat
- Pure CSS solution (checkbox hack): Rejected as state needs to be accessible to other components

**Implementation Details**:
- Sidebar positioned fixed on mobile with negative left offset when closed
- Overlay backdrop (rgba(0,0,0,0.3)) blocks interaction with main content
- Touch outside or navigation closes menu automatically
- Transform animation uses CSS transition for smooth 300ms animation

---

### 3. Touch Target Sizing Standards

**Decision**: Minimum 44x44px touch targets for all interactive elements

**Rationale**:
- iOS Human Interface Guidelines specify minimum 44pt (44px) touch targets
- Android Material Design specifies minimum 48dp (48px) touch targets
- 44x44px is the more conservative choice that satisfies both platforms
- Existing CSS already implements this for buttons (`.nav-item { height: 44px }`)

**Alternatives Considered**:
- 48x48px minimum: More generous but requires more layout changes
- 40x40px minimum: Below platform guidelines, would fail accessibility

**Audit Required**:
- Verify all buttons meet 44x44px minimum
- Check spacing between adjacent interactive elements (minimum 8px gap)
- Validate form inputs have adequate touch area

---

### 4. Table Horizontal Scroll Strategy

**Decision**: Native horizontal scroll with overflow-x-auto on table containers

**Rationale**:
- Simple, performant solution using native browser scrolling
- Works consistently across mobile browsers
- No JavaScript required
- Users are familiar with horizontal scroll pattern on mobile

**Alternatives Considered**:
- Column hiding/stacking: Rejected as users need access to all data
- Responsive tables (card view): Rejected as complex to implement and loses tabular structure
- Horizontal scroll with sticky first column: Considered for future enhancement

**Implementation**:
```css
.table-container {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch; /* Smooth scrolling on iOS */
}

.table-container::-webkit-scrollbar {
  height: 6px;
}
```

---

### 5. Full-Screen Chat on Mobile

**Decision**: Use viewport height units (vh) with mobile browser UI compensation

**Rationale**:
- Chat is primary feature, deserves maximum screen real estate
- Modern browsers support dvh (dynamic viewport height) for accurate mobile height
- Fallback to vh for older browsers
- Input field stays above keyboard using position: fixed bottom

**Alternatives Considered**:
- Fixed height containers: Rejected due to inconsistent mobile browser chrome
- JavaScript height calculation: Rejected as unnecessary with modern CSS units

**Implementation**:
```css
.chat-container {
  height: 100dvh; /* Dynamic viewport height */
  height: 100vh; /* Fallback for older browsers */
}

@media (max-width: 768px) {
  .chat-container {
    height: calc(100dvh - 56px); /* Subtract mobile header */
  }
}
```

---

### 6. Orientation Change Handling

**Decision**: CSS-only responsive layout with automatic reflow

**Rationale**:
- Modern CSS Grid and Flexbox automatically adapt to dimension changes
- No JavaScript listeners needed for orientation changes
- Browser handles reflow efficiently
- Existing layout already uses flexbox extensively

**Alternatives Considered**:
- JavaScript orientation event listeners: Rejected as unnecessary complexity
- Orientation-specific breakpoints: Rejected as width-based breakpoints suffice

**Best Practices**:
- Use relative units (%, vw, vh) instead of fixed pixels
- Avoid fixed positioning that breaks on orientation change
- Test in both portrait and landscape on real devices

---

### 7. Modal and Dialog Adaptation

**Decision**: Transform desktop modals to mobile-friendly bottom sheets

**Rationale**:
- Bottom sheets are mobile-native pattern (Material Design, iOS)
- Easier to interact with (thumb-friendly)
- No need to reach top of screen
- Maintains context with partial background visibility

**Alternatives Considered**:
- Full-screen modals: Rejected as too jarring for simple actions
- Same desktop modal on mobile: Rejected due to poor mobile UX

**Implementation Strategy**:
```css
@media (max-width: 768px) {
  .modal {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    border-radius: 16px 16px 0 0;
    max-height: 90vh;
    transform: translateY(100%);
    transition: transform 300ms;
  }

  .modal.open {
    transform: translateY(0);
  }
}
```

---

### 8. Performance Optimization

**Decision**: CSS-based animations with GPU acceleration via transforms

**Rationale**:
- Transform and opacity are GPU-accelerated properties
- Avoid layout thrashing from width/height animations
- 60fps animations on mid-range mobile devices
- Battery-friendly compared to JavaScript animations

**Best Practices**:
- Use `transform: translateX()` instead of `left` property
- Use `will-change: transform` sparingly for animated elements
- Avoid animating properties that trigger layout recalculation
- Test on mid-range Android devices (not just flagship phones)

**Animation Performance Checklist**:
- Sidebar slide: `transform: translateX()` ✓
- Modal slide up: `transform: translateY()` ✓
- Fade effects: `opacity` ✓
- Menu toggle icon: CSS transform ✓

---

### 9. Testing Strategy

**Decision**: Multi-device testing with real hardware + browser DevTools

**Testing Matrix**:
| Device Type | Browser | Viewport | Priority |
|------------|---------|----------|----------|
| iPhone 12-15 | Safari | 390x844 | P1 |
| Android mid-range | Chrome | 360x800 | P1 |
| iPad | Safari | 768x1024 | P2 |
| Android tablet | Chrome | 800x1280 | P2 |
| Desktop | Chrome DevTools | Various | P1 |

**Testing Checklist**:
- [ ] All features accessible on mobile
- [ ] No horizontal scroll on any viewport
- [ ] Touch targets minimum 44x44px
- [ ] Hamburger menu opens/closes smoothly
- [ ] Tables scroll horizontally on mobile
- [ ] Chat interface full-screen on mobile
- [ ] Orientation change works correctly
- [ ] Forms usable with mobile keyboard
- [ ] No layout breakage at any breakpoint
- [ ] Performance: animations at 60fps

---

### 10. Tailwind CSS v4 Integration

**Decision**: Use Tailwind CSS v4 utility classes + custom CSS variables

**Rationale**:
- Project already uses Tailwind CSS v4 (`@import "tailwindcss"` in globals.css)
- Custom CSS variables in globals.css provide consistent design tokens
- Hybrid approach: Tailwind utilities for rapid development, custom CSS for complex layouts
- Existing components use custom CSS classes, minimize disruption

**Usage Pattern**:
```tsx
// Tailwind utilities for responsive layout
<div className="flex flex-col md:flex-row gap-4 p-4 md:p-8">

// Custom classes for complex components
<div className="sidebar">
```

**Tailwind Responsive Utilities**:
- `hidden md:block` - Hide on mobile, show on desktop
- `w-full md:w-auto` - Full width mobile, auto desktop
- `px-4 md:px-8` - 1rem mobile padding, 2rem desktop
- `text-sm md:text-base` - Smaller text on mobile

---

## Implementation Phases

### Phase 1: Core Mobile Infrastructure (P1)
1. Mobile header and hamburger menu (already exists, verify)
2. Sidebar overlay and animation
3. Global layout responsive wrapper
4. Touch target size audit and fixes

### Phase 2: Component Adaptation (P1-P2)
1. Chat interface full-screen mobile
2. Login page mobile layout
3. Dashboard cards stacking
4. Table horizontal scroll

### Phase 3: Form and Input Optimization (P2)
1. Form input touch targets
2. Mobile keyboard handling
3. Button spacing and sizing
4. Dropdown/select mobile patterns

### Phase 4: Testing and Refinement (P3)
1. Real device testing
2. Orientation change validation
3. Performance profiling
4. Accessibility audit

---

## Known Issues and Limitations

### Current Implementation Gaps
1. Sidebar overlay opacity check: Verify `display: none` to `display: block` transition works
2. MobileHeader integration: Ensure shows only on mobile breakpoint
3. Chat message max-width: Currently 70%, needs adjustment for mobile (85%)
4. Table containers: Need explicit `.table-container` wrapping for scroll

### Future Enhancements (Out of Scope)
1. PWA features (offline support, installability)
2. Touch gestures (swipe to close menu)
3. Sticky table headers on scroll
4. Lazy loading for long lists
5. Image optimization for mobile bandwidth

---

## References

### Standards and Guidelines
- [iOS Human Interface Guidelines - Touch Targets](https://developer.apple.com/design/human-interface-guidelines/inputs)
- [Material Design - Touch Targets](https://m3.material.io/foundations/interaction/states/state-layers)
- [WCAG 2.1 - Target Size (Level AAA)](https://www.w3.org/WAI/WCAG21/Understanding/target-size.html)

### Tailwind CSS v4
- [Tailwind CSS v4 Documentation](https://tailwindcss.com/docs)
- [Responsive Design - Tailwind](https://tailwindcss.com/docs/responsive-design)

### Browser Support
- [Can I Use - CSS Grid](https://caniuse.com/css-grid)
- [Can I Use - Flexbox](https://caniuse.com/flexbox)
- [Can I Use - dvh units](https://caniuse.com/viewport-unit-variants)

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Layout breakage on specific viewports | High | Comprehensive testing at multiple breakpoints |
| Animation performance on low-end devices | Medium | Use GPU-accelerated properties, test on mid-range Android |
| Browser compatibility (older Safari) | Low | Provide fallbacks for modern CSS features (dvh → vh) |
| Existing custom CSS conflicts | Medium | Thorough CSS audit, use specificity carefully |
| Touch target too small | High | Automated accessibility audit tools, manual testing |

---

**Phase 0 Complete**: All technical decisions documented. Ready for Phase 1 (quickstart.md generation).
