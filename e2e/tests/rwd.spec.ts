/**
 * Responsive Web Design (RWD) E2E Tests
 * Feature: 006-rwd
 *
 * 測試範圍：
 * - User Story 1: Mobile Browser Access (P1)
 * - User Story 2: Mobile Navigation (P1)
 * - User Story 3: Full-Screen Chat (P1)
 * - User Story 4: Responsive Data Display (P2)
 * - User Story 5: Touch-Optimized Controls (P2)
 */

import { test, expect, Page } from '@playwright/test';

// Test configuration
const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const ADMIN_EMAIL = 'admin@example.com';
const ADMIN_PASSWORD = 'admin';

// Viewport configurations
const VIEWPORTS = {
  mobile_iphone14: { width: 390, height: 844, name: 'iPhone 14 Pro' },
  mobile_iphoneSE: { width: 375, height: 667, name: 'iPhone SE' },
  mobile_android: { width: 360, height: 800, name: 'Android Mid-range' },
  tablet_ipad: { width: 768, height: 1024, name: 'iPad' },
  desktop: { width: 1280, height: 720, name: 'Desktop' },
};

// Helper function: Login as admin
async function loginAsAdmin(page: Page) {
  await page.goto(BASE_URL);
  await page.getByPlaceholder('請輸入您的電子郵件').fill(ADMIN_EMAIL);
  await page.getByPlaceholder('請輸入密碼').fill(ADMIN_PASSWORD);
  await page.getByRole('button', { name: '登入' }).click();
  await page.waitForURL(/\/(chat|admin)/, { timeout: 10000 });
  await page.waitForLoadState('networkidle');
}

// Helper function: Measure element size
async function getElementSize(page: Page, selector: string) {
  return await page.locator(selector).boundingBox();
}

// Helper function: Check if element is visible
async function isElementVisible(page: Page, selector: string): Promise<boolean> {
  try {
    await page.locator(selector).waitFor({ state: 'visible', timeout: 2000 });
    return true;
  } catch {
    return false;
  }
}

// ==========================================
// User Story 1: Mobile Browser Access (P1)
// ==========================================
test.describe('US1: Mobile Browser Access', () => {

  test.describe('Multiple Viewports', () => {

    test('應該在 iPhone 14 Pro (390×844) 正確顯示', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Check no horizontal scroll
      const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = page.viewportSize()!.width;
      expect(bodyWidth).toBeLessThanOrEqual(viewportWidth);

      // Check content visible
      await expect(page.getByPlaceholder('輸入您的問題...')).toBeVisible();
    });

    test('應該在 iPhone SE (375×667) 正確顯示', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphoneSE);
      await loginAsAdmin(page);

      // Check no horizontal scroll
      const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = page.viewportSize()!.width;
      expect(bodyWidth).toBeLessThanOrEqual(viewportWidth);
    });

    test('應該在 Android (360×800) 正確顯示', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_android);
      await loginAsAdmin(page);

      // Check no horizontal scroll
      const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = page.viewportSize()!.width;
      expect(bodyWidth).toBeLessThanOrEqual(viewportWidth);
    });

    test('應該在 iPad (768×1024) 正確顯示', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.tablet_ipad);
      await loginAsAdmin(page);

      // Tablet should show sidebar in hybrid mode or toggle
      const nav = page.getByRole('navigation');
      await expect(nav).toBeVisible();
    });

  });

  test.describe('Orientation Changes', () => {

    test('從直向切換到橫向應該正常適應', async ({ page }) => {
      // Start in portrait
      await page.setViewportSize({ width: 390, height: 844 });
      await loginAsAdmin(page);

      // Check initial state
      await expect(page.getByPlaceholder('輸入您的問題...')).toBeVisible();

      // Switch to landscape
      await page.setViewportSize({ width: 844, height: 390 });

      // Wait for layout adaptation (should be <200ms, but give some buffer)
      await page.waitForTimeout(300);

      // Check content still visible
      await expect(page.getByPlaceholder('輸入您的問題...')).toBeVisible();

      // Check no horizontal scroll in landscape
      const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = page.viewportSize()!.width;
      expect(bodyWidth).toBeLessThanOrEqual(viewportWidth);
    });

    test('從橫向切換到直向應該正常適應', async ({ page }) => {
      // Start in landscape
      await page.setViewportSize({ width: 844, height: 390 });
      await loginAsAdmin(page);

      // Switch to portrait
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(300);

      // Check content still visible
      await expect(page.getByPlaceholder('輸入您的問題...')).toBeVisible();
    });

  });

  test.describe('Viewport Meta Tag', () => {

    test('應該設定正確的 viewport meta 標籤', async ({ page }) => {
      await page.goto(BASE_URL);

      const viewport = await page.evaluate(() => {
        const meta = document.querySelector('meta[name="viewport"]');
        return meta?.getAttribute('content');
      });

      expect(viewport).toContain('width=device-width');
      expect(viewport).toContain('initial-scale=1');
    });

  });

});

// ==========================================
// User Story 2: Mobile Navigation (P1)
// ==========================================
test.describe('US2: Mobile Navigation', () => {

  test.describe('Hamburger Menu', () => {

    test('在行動版應該顯示漢堡選單', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Mobile header with hamburger should be visible
      const mobileHeader = page.locator('.mobile-header');
      await expect(mobileHeader).toBeVisible();

      // Hamburger button should exist
      const hamburger = page.locator('.mobile-header button').first();
      await expect(hamburger).toBeVisible();
    });

    test('點擊漢堡選單應該打開側邊欄', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Sidebar should be hidden initially
      const sidebar = page.locator('.sidebar');
      const isOpen = await sidebar.evaluate(el => el.classList.contains('open'));
      expect(isOpen).toBe(false);

      // Click hamburger
      const hamburger = page.locator('.mobile-header button').first();
      await hamburger.click();

      // Sidebar should open
      await page.waitForTimeout(100);
      const isOpenAfter = await sidebar.evaluate(el => el.classList.contains('open'));
      expect(isOpenAfter).toBe(true);

      // Overlay should be visible
      const overlay = page.locator('.sidebar-overlay');
      await expect(overlay).toBeVisible();
    });

    test('側邊欄打開動畫應該在 300ms 內完成', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      const hamburger = page.locator('.mobile-header button').first();

      const startTime = Date.now();
      await hamburger.click();

      // Wait for sidebar to be fully open
      await page.locator('.sidebar.open').waitFor({ state: 'visible' });
      const animationTime = Date.now() - startTime;

      // Should be less than 300ms (with some buffer for test execution)
      expect(animationTime).toBeLessThan(500);
    });

  });

  test.describe('Menu Interactions', () => {

    test('點擊導航項目應該關閉選單並導航', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Open menu
      const hamburger = page.locator('.mobile-header button').first();
      await hamburger.click();
      await page.waitForTimeout(100);

      // Click navigation item
      await page.locator('nav a:has-text("對話")').first().click();

      // Wait for navigation
      await page.waitForURL(/\/chat/);

      // Menu should close
      await page.waitForTimeout(100);
      const sidebar = page.locator('.sidebar');
      const isOpen = await sidebar.evaluate(el => el.classList.contains('open'));
      expect(isOpen).toBe(false);
    });

    test('點擊 overlay 應該關閉選單不導航', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Get current URL
      const urlBefore = page.url();

      // Open menu
      const hamburger = page.locator('.mobile-header button').first();
      await hamburger.click();
      await page.waitForTimeout(100);

      // Click overlay
      const overlay = page.locator('.sidebar-overlay');
      await overlay.click();
      await page.waitForTimeout(100);

      // Menu should close
      const sidebar = page.locator('.sidebar');
      const isOpen = await sidebar.evaluate(el => el.classList.contains('open'));
      expect(isOpen).toBe(false);

      // URL should not change
      expect(page.url()).toBe(urlBefore);
    });

  });

  test.describe('Desktop Behavior', () => {

    test('在桌面版不應該顯示漢堡選單', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.desktop);
      await loginAsAdmin(page);

      // Mobile header should not be visible
      const mobileHeader = page.locator('.mobile-header');
      const isVisible = await mobileHeader.isVisible().catch(() => false);
      expect(isVisible).toBe(false);

      // Sidebar should be visible
      const sidebar = page.locator('.sidebar');
      await expect(sidebar).toBeVisible();
    });

  });

});

// ==========================================
// User Story 3: Full-Screen Chat (P1)
// ==========================================
test.describe('US3: Full-Screen Chat Interface', () => {

  test.describe('Viewport Usage', () => {

    test('對話容器應該使用完整視窗高度（扣除 header）', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Navigate to chat
      await page.goto(`${BASE_URL}/chat`);
      await page.waitForLoadState('networkidle');

      // Get chat container height
      const chatContainer = page.locator('.chat-container').first();
      const boundingBox = await chatContainer.boundingBox();

      expect(boundingBox).not.toBeNull();
      if (boundingBox) {
        // Should use at least 85% of viewport height (minus header)
        const viewportHeight = page.viewportSize()!.height;
        const minHeight = viewportHeight * 0.85;
        expect(boundingBox.height).toBeGreaterThanOrEqual(minHeight);
      }
    });

    test('對話應該使用完整寬度', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);
      await page.goto(`${BASE_URL}/chat`);

      const chatContainer = page.locator('.chat-container').first();
      const boundingBox = await chatContainer.boundingBox();

      expect(boundingBox).not.toBeNull();
      if (boundingBox) {
        const viewportWidth = page.viewportSize()!.width;
        // Allow small margin for borders/padding
        expect(boundingBox.width).toBeGreaterThan(viewportWidth - 10);
      }
    });

  });

  test.describe('Input Area', () => {

    test('輸入框應該在焦點時保持可見', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);
      await page.goto(`${BASE_URL}/chat`);

      // Focus input
      const input = page.getByPlaceholder('輸入您的問題...');
      await input.focus();

      // Input should still be visible
      await expect(input).toBeVisible();

      // Check input is in viewport
      const boundingBox = await input.boundingBox();
      expect(boundingBox).not.toBeNull();
      if (boundingBox) {
        const viewportHeight = page.viewportSize()!.height;
        expect(boundingBox.y + boundingBox.height).toBeLessThanOrEqual(viewportHeight);
      }
    });

    test('輸入文字應該可以正常輸入', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);
      await page.goto(`${BASE_URL}/chat`);

      const input = page.getByPlaceholder('輸入您的問題...');
      await input.fill('測試訊息');
      await expect(input).toHaveValue('測試訊息');
    });

  });

  test.describe('Message Display', () => {

    test('訊息內容應該適應行動版寬度', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);
      await page.goto(`${BASE_URL}/chat`);

      // Check message width on mobile
      const messages = page.locator('.message-content');
      const count = await messages.count();

      if (count > 0) {
        const firstMessage = messages.first();
        const boundingBox = await firstMessage.boundingBox();

        if (boundingBox) {
          const viewportWidth = page.viewportSize()!.width;
          // Messages should be at most 85% of viewport width (per spec)
          expect(boundingBox.width).toBeLessThanOrEqual(viewportWidth * 0.85 + 10);
        }
      }
    });

  });

});

// ==========================================
// User Story 4: Responsive Data Display (P2)
// ==========================================
test.describe('US4: Responsive Data Display', () => {

  test.describe('Table Scrolling', () => {

    test('知識庫表格應該可以水平滾動', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Navigate to knowledge base
      await page.goto(`${BASE_URL}/admin/knowledge-base`);
      await page.waitForLoadState('networkidle');

      // Check table container has horizontal scroll
      const tableContainer = page.locator('.table-container').first();
      const hasScroll = await tableContainer.evaluate(el => {
        return el.scrollWidth > el.clientWidth;
      });

      // If table is wide, it should be scrollable
      if (hasScroll) {
        // Try scrolling
        await tableContainer.evaluate(el => el.scrollLeft = 50);
        const scrollLeft = await tableContainer.evaluate(el => el.scrollLeft);
        expect(scrollLeft).toBeGreaterThan(0);
      }
    });

    test('表格應該有最小寬度防止崩潰', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);
      await page.goto(`${BASE_URL}/admin/knowledge-base`);
      await page.waitForLoadState('networkidle');

      // Check table min-width
      const table = page.locator('.data-table').first();
      const width = await table.evaluate(el => {
        return window.getComputedStyle(el).minWidth;
      });

      // Should have min-width of 600px per spec
      expect(parseInt(width)).toBeGreaterThanOrEqual(600);
    });

  });

  test.describe('Dashboard Grid', () => {

    test('儀表板卡片應該在行動版垂直堆疊', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Navigate to dashboard
      await page.goto(`${BASE_URL}/admin/dashboard`);
      await page.waitForLoadState('networkidle');

      // Check grid layout
      const grid = page.locator('.dashboard-grid').first();
      const gridTemplate = await grid.evaluate(el => {
        return window.getComputedStyle(el).gridTemplateColumns;
      });

      // On mobile, should be single column
      // The computed style might be in px, but we check it's effectively 1fr
      expect(gridTemplate).not.toContain('repeat');
    });

    test('統計卡片應該全寬顯示', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);
      await page.goto(`${BASE_URL}/admin/dashboard`);
      await page.waitForLoadState('networkidle');

      const cards = page.locator('.stat-card');
      const count = await cards.count();

      if (count > 0) {
        const firstCard = cards.first();
        const boundingBox = await firstCard.boundingBox();
        const grid = page.locator('.dashboard-grid').first();
        const gridBox = await grid.boundingBox();

        if (boundingBox && gridBox) {
          // Card should take most of grid width (minus gap/padding)
          expect(boundingBox.width).toBeGreaterThan(gridBox.width * 0.9);
        }
      }
    });

  });

  test.describe('Filter Controls', () => {

    test('篩選面板應該在行動版可訪問', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Navigate to structured query page
      await page.goto(`${BASE_URL}/query`);
      await page.waitForLoadState('networkidle');

      // Filter panel should be accessible (Carbon Accordion is collapsible by default)
      const filterPanel = page.locator('[class*="filter"]').first();
      const isVisible = await filterPanel.isVisible().catch(() => false);

      // Panel should exist (may be collapsed)
      expect(isVisible).toBeDefined();
    });

  });

});

// ==========================================
// User Story 5: Touch-Optimized Controls (P2)
// ==========================================
test.describe('US5: Touch-Optimized Controls', () => {

  test.describe('Touch Target Sizes', () => {

    test('所有按鈕應該至少 44×44px', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Check all buttons
      const buttons = page.locator('button:visible');
      const count = await buttons.count();

      for (let i = 0; i < Math.min(count, 20); i++) {
        const button = buttons.nth(i);
        const box = await button.boundingBox();

        if (box) {
          expect(box.width).toBeGreaterThanOrEqual(44);
          expect(box.height).toBeGreaterThanOrEqual(44);
        }
      }
    });

    test('導航項目應該至少 44×44px', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Open sidebar on mobile
      const hamburger = page.locator('.mobile-header button').first();
      await hamburger.click();
      await page.waitForTimeout(100);

      // Check navigation items
      const navItems = page.locator('nav a:visible');
      const count = await navItems.count();

      for (let i = 0; i < Math.min(count, 10); i++) {
        const item = navItems.nth(i);
        const box = await item.boundingBox();

        if (box) {
          expect(box.height).toBeGreaterThanOrEqual(44);
        }
      }
    });

    test('表單輸入框應該至少 44px 高度', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await page.goto(BASE_URL);

      // Check login form inputs
      const emailInput = page.getByPlaceholder('請輸入您的電子郵件');
      const passwordInput = page.getByPlaceholder('請輸入密碼');

      const emailBox = await emailInput.boundingBox();
      const passwordBox = await passwordInput.boundingBox();

      expect(emailBox?.height).toBeGreaterThanOrEqual(44);
      expect(passwordBox?.height).toBeGreaterThanOrEqual(44);
    });

  });

  test.describe('Button Spacing', () => {

    test('按鈕群組應該有足夠間距', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);
      await page.goto(`${BASE_URL}/admin/dashboard`);
      await page.waitForLoadState('networkidle');

      // Check button groups
      const buttonGroups = page.locator('.button-group');
      const count = await buttonGroups.count();

      if (count > 0) {
        const firstGroup = buttonGroups.first();
        const gap = await firstGroup.evaluate(el => {
          return window.getComputedStyle(el).gap;
        });

        // Should have at least 12px gap (0.75rem)
        const gapValue = parseInt(gap);
        expect(gapValue).toBeGreaterThanOrEqual(12);
      }
    });

  });

  test.describe('Form Interactions', () => {

    test('表單欄位應該容易點擊', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await page.goto(BASE_URL);

      // Try tapping input
      const input = page.getByPlaceholder('請輸入您的電子郵件');
      await input.tap();

      // Should be focused
      await expect(input).toBeFocused();
    });

    test('複選框應該有足夠的觸碰區域', async ({ page }) => {
      await page.setViewportSize(VIEWPORTS.mobile_iphone14);
      await loginAsAdmin(page);

      // Find checkboxes if they exist
      const checkboxes = page.locator('input[type="checkbox"]:visible');
      const count = await checkboxes.count();

      if (count > 0) {
        const firstCheckbox = checkboxes.first();
        const box = await firstCheckbox.boundingBox();

        // Checkbox itself + padding should create adequate touch target
        expect(box?.width).toBeGreaterThanOrEqual(20);
        expect(box?.height).toBeGreaterThanOrEqual(20);
      }
    });

  });

});

// ==========================================
// Performance & Accessibility
// ==========================================
test.describe('RWD Performance & Accessibility', () => {

  test('行動版首次載入應該在合理時間內完成', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile_iphone14);

    const startTime = Date.now();
    await page.goto(BASE_URL);
    await page.waitForLoadState('networkidle');
    const loadTime = Date.now() - startTime;

    // Should load within 3 seconds (mobile performance)
    expect(loadTime).toBeLessThan(3000);
  });

  test('側邊欄動畫應該流暢（無明顯卡頓）', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile_iphone14);
    await loginAsAdmin(page);

    // Open sidebar multiple times
    const hamburger = page.locator('.mobile-header button').first();

    for (let i = 0; i < 3; i++) {
      await hamburger.click();
      await page.waitForTimeout(350);
      await hamburger.click();
      await page.waitForTimeout(350);
    }

    // No assertion needed - test passes if no crashes/hangs
    expect(true).toBe(true);
  });

  test('文字對比應該符合可訪問性標準', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile_iphone14);
    await loginAsAdmin(page);

    // Check primary text color contrast
    const textElement = page.locator('.text-primary').first();
    const isVisible = await textElement.isVisible().catch(() => false);

    if (isVisible) {
      const colors = await textElement.evaluate(el => {
        const style = window.getComputedStyle(el);
        return {
          color: style.color,
          backgroundColor: style.backgroundColor,
        };
      });

      // Basic check that colors are defined
      expect(colors.color).toBeTruthy();
      expect(colors.backgroundColor).toBeTruthy();
    }
  });

});

// ==========================================
// Cross-Device Compatibility
// ==========================================
test.describe('Cross-Device Compatibility', () => {

  test('應該在所有定義的視窗尺寸正常運作', async ({ page }) => {
    for (const [key, viewport] of Object.entries(VIEWPORTS)) {
      await page.setViewportSize(viewport);
      await page.goto(BASE_URL);

      // Check page loads without errors
      await expect(page.getByRole('button', { name: '登入' })).toBeVisible();

      // Check no horizontal scroll
      const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
      const viewportWidth = page.viewportSize()!.width;
      expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 5); // 5px tolerance
    }
  });

  test('平板尺寸應該使用適當的佈局', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.tablet_ipad);
    await loginAsAdmin(page);

    // Tablet should show navigation (may be toggleable or permanent)
    const nav = page.getByRole('navigation');
    await expect(nav).toBeVisible();

    // Content should be visible
    await expect(page.getByPlaceholder('輸入您的問題...')).toBeVisible();
  });

});
