"use client";

import { useState } from "react";
import AppHeader from "@/components/AppHeader";
import {
  Tabs,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
  Select,
  SelectItem,
  Toggle,
  Button,
  Slider,
  RadioButtonGroup,
  RadioButton,
  InlineNotification,
  Stack,
  Tile,
} from "@carbon/react";
import {
  Settings,
  Security,
  Notification,
  ColorPalette,
  Save,
} from "@carbon/icons-react";

export default function SettingsPage() {
  const [saved, setSaved] = useState(false);
  const [settings, setSettings] = useState({
    // General
    language: "zh-TW",
    timezone: "Asia/Taipei",
    dateFormat: "YYYY-MM-DD",

    // AI Settings
    modelTemperature: 0.7,
    maxTokens: 2048,
    streamResponse: true,

    // Appearance
    theme: "light",
    fontSize: "medium",
    compactMode: false,

    // Notifications
    emailNotifications: true,
    pushNotifications: true,
    soundEnabled: false,

    // Privacy
    saveHistory: true,
    analyticsEnabled: true,
  });

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="min-h-screen bg-carbon-gray-10">
      <AppHeader />
      <div className="pt-12">
        <div className="max-w-5xl mx-auto p-6">
          <div className="flex items-center gap-3 mb-6">
            <Settings size={32} className="text-carbon-blue-60" />
            <div>
              <h1 className="text-2xl font-semibold text-carbon-gray-100">
                系統設定
              </h1>
              <p className="text-carbon-gray-60">
                管理您的偏好設定與系統配置
              </p>
            </div>
          </div>

          {saved && (
            <InlineNotification
              kind="success"
              title="設定已儲存"
              subtitle="您的變更已成功套用"
              lowContrast
              className="mb-4"
            />
          )}

          <div className="bg-white rounded-lg border border-carbon-gray-20">
            <Tabs>
              <TabList aria-label="設定選項" contained>
                <Tab renderIcon={Settings}>一般設定</Tab>
                <Tab renderIcon={ColorPalette}>外觀</Tab>
                <Tab renderIcon={Notification}>通知</Tab>
                <Tab renderIcon={Security}>隱私</Tab>
              </TabList>
              <TabPanels>
                {/* General Settings */}
                <TabPanel className="p-6">
                  <Stack gap={6}>
                    <h3 className="text-lg font-medium">一般設定</h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <Select
                        id="language"
                        labelText="語言"
                        value={settings.language}
                        onChange={(e) =>
                          setSettings({ ...settings, language: e.target.value })
                        }
                      >
                        <SelectItem value="zh-TW" text="繁體中文" />
                        <SelectItem value="zh-CN" text="简体中文" />
                        <SelectItem value="en" text="English" />
                        <SelectItem value="ja" text="日本語" />
                      </Select>

                      <Select
                        id="timezone"
                        labelText="時區"
                        value={settings.timezone}
                        onChange={(e) =>
                          setSettings({ ...settings, timezone: e.target.value })
                        }
                      >
                        <SelectItem value="Asia/Taipei" text="(UTC+8) 台北" />
                        <SelectItem value="Asia/Tokyo" text="(UTC+9) 東京" />
                        <SelectItem value="America/New_York" text="(UTC-5) 紐約" />
                      </Select>
                    </div>

                    <hr className="border-carbon-gray-20" />

                    <h3 className="text-lg font-medium">AI 模型設定</h3>

                    <Slider
                      labelText="回應創意度 (Temperature)"
                      value={settings.modelTemperature}
                      min={0}
                      max={1}
                      step={0.1}
                      onChange={({ value }) =>
                        setSettings({ ...settings, modelTemperature: value })
                      }
                    />

                    <Select
                      id="maxTokens"
                      labelText="最大回應長度"
                      value={settings.maxTokens.toString()}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          maxTokens: parseInt(e.target.value),
                        })
                      }
                    >
                      <SelectItem value="1024" text="1024 tokens (簡短)" />
                      <SelectItem value="2048" text="2048 tokens (標準)" />
                      <SelectItem value="4096" text="4096 tokens (詳細)" />
                    </Select>

                    <Toggle
                      id="streamResponse"
                      labelText="串流回應"
                      labelA="關閉"
                      labelB="開啟"
                      toggled={settings.streamResponse}
                      onToggle={(checked) =>
                        setSettings({ ...settings, streamResponse: checked })
                      }
                    />
                  </Stack>
                </TabPanel>

                {/* Appearance */}
                <TabPanel className="p-6">
                  <Stack gap={6}>
                    <h3 className="text-lg font-medium">外觀設定</h3>

                    <RadioButtonGroup
                      legendText="主題"
                      name="theme"
                      valueSelected={settings.theme}
                      onChange={(value) =>
                        setSettings({ ...settings, theme: value as string })
                      }
                    >
                      <RadioButton labelText="淺色" value="light" />
                      <RadioButton labelText="深色" value="dark" />
                      <RadioButton labelText="跟隨系統" value="system" />
                    </RadioButtonGroup>

                    <RadioButtonGroup
                      legendText="字型大小"
                      name="fontSize"
                      valueSelected={settings.fontSize}
                      onChange={(value) =>
                        setSettings({ ...settings, fontSize: value as string })
                      }
                    >
                      <RadioButton labelText="小" value="small" />
                      <RadioButton labelText="中" value="medium" />
                      <RadioButton labelText="大" value="large" />
                    </RadioButtonGroup>

                    <Toggle
                      id="compactMode"
                      labelText="緊湊模式"
                      labelA="關閉"
                      labelB="開啟"
                      toggled={settings.compactMode}
                      onToggle={(checked) =>
                        setSettings({ ...settings, compactMode: checked })
                      }
                    />
                  </Stack>
                </TabPanel>

                {/* Notifications */}
                <TabPanel className="p-6">
                  <Stack gap={6}>
                    <h3 className="text-lg font-medium">通知設定</h3>

                    <Toggle
                      id="emailNotifications"
                      labelText="電子郵件通知"
                      labelA="關閉"
                      labelB="開啟"
                      toggled={settings.emailNotifications}
                      onToggle={(checked) =>
                        setSettings({ ...settings, emailNotifications: checked })
                      }
                    />

                    <Toggle
                      id="pushNotifications"
                      labelText="推播通知"
                      labelA="關閉"
                      labelB="開啟"
                      toggled={settings.pushNotifications}
                      onToggle={(checked) =>
                        setSettings({ ...settings, pushNotifications: checked })
                      }
                    />

                    <Toggle
                      id="soundEnabled"
                      labelText="音效"
                      labelA="關閉"
                      labelB="開啟"
                      toggled={settings.soundEnabled}
                      onToggle={(checked) =>
                        setSettings({ ...settings, soundEnabled: checked })
                      }
                    />
                  </Stack>
                </TabPanel>

                {/* Privacy */}
                <TabPanel className="p-6">
                  <Stack gap={6}>
                    <h3 className="text-lg font-medium">隱私設定</h3>

                    <Toggle
                      id="saveHistory"
                      labelText="保存對話紀錄"
                      labelA="關閉"
                      labelB="開啟"
                      toggled={settings.saveHistory}
                      onToggle={(checked) =>
                        setSettings({ ...settings, saveHistory: checked })
                      }
                    />

                    <Toggle
                      id="analyticsEnabled"
                      labelText="允許匿名使用統計"
                      labelA="關閉"
                      labelB="開啟"
                      toggled={settings.analyticsEnabled}
                      onToggle={(checked) =>
                        setSettings({ ...settings, analyticsEnabled: checked })
                      }
                    />

                    <Tile className="bg-carbon-gray-10">
                      <p className="text-sm text-carbon-gray-70">
                        我們重視您的隱私。所有對話資料都以加密方式儲存，
                        且不會分享給第三方。您可以隨時刪除您的對話紀錄。
                      </p>
                    </Tile>

                    <Button kind="danger--tertiary" size="md">
                      刪除所有對話紀錄
                    </Button>
                  </Stack>
                </TabPanel>
              </TabPanels>
            </Tabs>
          </div>

          <div className="flex justify-end mt-6 gap-4">
            <Button kind="secondary" size="lg">
              取消
            </Button>
            <Button
              kind="primary"
              size="lg"
              renderIcon={Save}
              onClick={handleSave}
            >
              儲存變更
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
