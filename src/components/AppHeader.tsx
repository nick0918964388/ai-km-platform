"use client";

import {
  Header,
  HeaderContainer,
  HeaderName,
  HeaderNavigation,
  HeaderMenuItem,
  HeaderGlobalBar,
  HeaderGlobalAction,
  SkipToContent,
} from "@carbon/react";
import {
  Search,
  Notification,
  UserAvatar,
  Settings,
} from "@carbon/icons-react";
import { useRouter } from "next/navigation";

export default function AppHeader() {
  const router = useRouter();

  return (
    <HeaderContainer
      render={() => (
        <Header aria-label="AI KM 知識管理平台">
          <SkipToContent />
          <HeaderName href="/" prefix="IBM">
            AI KM 平台
          </HeaderName>
          <HeaderNavigation aria-label="AI KM Platform">
            <HeaderMenuItem href="/">對話</HeaderMenuItem>
            <HeaderMenuItem href="/users">帳號管理</HeaderMenuItem>
            <HeaderMenuItem href="/permissions">權限管理</HeaderMenuItem>
            <HeaderMenuItem href="/settings">設定</HeaderMenuItem>
          </HeaderNavigation>
          <HeaderGlobalBar>
            <HeaderGlobalAction aria-label="搜尋" tooltipAlignment="center">
              <Search size={20} />
            </HeaderGlobalAction>
            <HeaderGlobalAction aria-label="通知" tooltipAlignment="center">
              <Notification size={20} />
            </HeaderGlobalAction>
            <HeaderGlobalAction
              aria-label="設定"
              tooltipAlignment="center"
              onClick={() => router.push("/settings")}
            >
              <Settings size={20} />
            </HeaderGlobalAction>
            <HeaderGlobalAction
              aria-label="使用者"
              tooltipAlignment="end"
              onClick={() => router.push("/login")}
            >
              <UserAvatar size={20} />
            </HeaderGlobalAction>
          </HeaderGlobalBar>
        </Header>
      )}
    />
  );
}
