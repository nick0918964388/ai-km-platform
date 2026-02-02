# AIKM Design System

## Style: Minimalist Design (簡約風格)

**Last Updated**: 2026-02-02

### Design Principles
- **Clean & Simple**: 乾淨、簡單的視覺設計，去除所有不必要的裝飾
- **High Contrast**: 清晰的文字與背景對比，確保可讀性
- **Generous Whitespace**: 充足的留白空間，讓內容呼吸
- **Flat Design**: 扁平化設計元素，無立體感或擬真效果
- **Subtle Shadows**: 極輕微的陰影或完全無陰影
- **Solid Backgrounds**: 純色背景，無漸層或模糊效果
- **No Glassmorphism**: 完全移除 backdrop-filter: blur 和半透明背景

### Color Palette
| Role | Hex | Name | Usage |
|------|-----|------|-------|
| Primary | #2563EB | 主要藍色 | Logo、按鈕、強調元素 |
| Primary Light | #EFF6FF | 淺藍背景 | 選中狀態、Hover 狀態 |
| Background | #FFFFFF | 純白背景 | 主要內容區域、卡片 |
| Background Alt | #F8FAFC | 淺灰背景 | 頁面背景、次要區域 |
| Background Light | #FAFAFA | 極淺灰背景 | 替代背景色 |
| Text Primary | #18181B | 深灰文字 | 主標題、重要文字 |
| Text Primary Alt | #1A1A1A | 深灰文字替代 | 一般文字內容 |
| Text Secondary | #71717A | 次要文字 | 描述文字、輔助資訊 |
| Text Muted | #666666 | 淡化文字 | 說明文字、不重要資訊 |
| Border | #E4E4E7 | 主要邊框 | 卡片邊框、分隔線 |
| Border Light | #E5E5E5 | 淺邊框 | 輕微分隔 |
| Success | #10B981 | 成功綠 | 成功訊息、確認操作 |
| Warning | #F59E0B | 警告黃 | 警告訊息、注意事項 |
| Error | #EF4444 | 錯誤紅 | 錯誤訊息、刪除操作 |

### Effects & Visual Details
- **No backdrop blur**: 完全不使用玻璃模糊效果
- **Border**: 1px or 1.5px solid #E4E4E7
- **Box shadow**: 無陰影或極輕微陰影
- **Border radius**:
  - Small: 8px (導航項目)
  - Medium: 10px (Logo)
  - Large: 12px (輸入框、按鈕)
  - XLarge: 16px (卡片)
- **Transitions**: 150ms ease (快速過渡)
- **No gradients**: 避免使用漸層，除了圖片疊加層外

### Spacing
- **Padding**: 8px, 12px, 16px, 24px, 32px, 40px, 48px
- **Gap**: 8px, 12px, 16px, 24px
- **Section spacing**: 24px - 32px

### Typography
- **Font Family**: Inter (主要字體)
- **Font weights**:
  - 400 (normal) - 一般文字
  - 500 (medium) - 小標籤文字
  - 600 (semibold) - 次要標題
  - 700 (bold) - 主標題
- **Font sizes**:
  - 11px - 導航標籤 (letterSpacing: 1px)
  - 14px - 一般文字
  - 16px - 描述文字
  - 18px - 品牌名稱
  - 24px - 頁面標題
  - 32px - 大標題
- **Line height**: 1.5 - 1.6

### Layout Measurements
- **Sidebar Width**: 260px
- **Header Height**: 64px - 72px
- **Input Height**: 40px - 56px
- **Button Height**: 40px - 52px
- **Nav Item Height**: 44px

### Component Guidelines

#### Layout Components
1. **Sidebar**
   - Width: 260px
   - Background: #FFFFFF
   - Border: 右側 1px solid #E4E4E7
   - Padding: 24px 16px
   - Gap: 8px (垂直間距)

2. **Main Content Area**
   - Background: #FFFFFF
   - Padding: 32px

3. **Header**
   - Background: #FFFFFF
   - Height: 64px - 72px
   - Border: 底部 1px solid #E4E4E7
   - Padding: 0 32px

#### UI Components

4. **Cards**
   - Background: #FFFFFF
   - Border: 1.5px solid #E4E4E7
   - Border Radius: 16px
   - Padding: 24px
   - Gap: 16px - 24px

5. **Buttons**
   - Primary:
     - Background: #2563EB
     - Color: #FFFFFF
     - Border Radius: 12px
     - Height: 40px - 52px
     - Padding: 0 16px - 20px
   - Secondary:
     - Background: transparent
     - Border: 1.5px solid #E4E4E7
     - Color: #18181B

6. **Input Fields**
   - Background: #FFFFFF
   - Border: 1.5px solid #E4E4E7
   - Border Radius: 12px
   - Height: 40px - 56px
   - Padding: 0 16px
   - Focus: Border color #2563EB

7. **Modal/Dialog**
   - Background: #FFFFFF
   - Border: 1.5px solid #E4E4E7
   - Border Radius: 16px
   - Padding: 40px

#### Navigation

8. **Nav Items**
   - Height: 44px
   - Border Radius: 8px
   - Padding: 0 12px
   - Gap: 12px (icon + text)
   - Default: transparent background
   - Active/Selected: #EFF6FF background
   - Icon size: 20px - 24px

9. **Nav Section Headers**
   - Font size: 11px
   - Font weight: 500 (medium)
   - Color: #71717A
   - Letter spacing: 1px
   - Text transform: uppercase (建議)

10. **Logo**
    - Icon size: 40px × 40px
    - Icon background: #2563EB
    - Icon border radius: 10px
    - Brand text: 18px, weight 600

### Icon System
- **Icon Library**: Lucide Icons
- **Icon Sizes**:
  - Small: 16px
  - Medium: 20px
  - Large: 24px
- **Icon Colors**: 匹配文字顏色或 #2563EB (強調)

### Interaction States

1. **Hover**
   - Nav items: 輕微背景色變化
   - Buttons: 不透明度 90%
   - Links: 文字顏色加深

2. **Active/Selected**
   - Background: #EFF6FF
   - Icon/Text color: #2563EB

3. **Focus**
   - Input: Border color #2563EB
   - Outline: 2px solid #2563EB (offset 2px)

4. **Disabled**
   - Opacity: 0.5
   - Cursor: not-allowed

### Accessibility
- **最小對比度**: 4.5:1 (WCAG AA)
- **Focus indicators**: 清晰可見的 focus 狀態
- **Touch targets**: 最小 44px × 44px
- **Alt text**: 所有圖片和 icon 都有語意說明

### Favicon
- Logo inspired design
- Primary color: #2563EB
- Size: 32×32, 64×64, 128×128, 192×192
