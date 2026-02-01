"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Button,
  TextInput,
  PasswordInput,
  Checkbox,
  Form,
  Stack,
  InlineNotification,
  Link,
} from "@carbon/react";
import { Login, ArrowRight } from "@carbon/icons-react";

export default function LoginPage() {
  const router = useRouter();
  const [formData, setFormData] = useState({
    username: "",
    password: "",
    rememberMe: false,
  });
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    // Simulate login
    setTimeout(() => {
      if (formData.username === "admin" && formData.password === "admin") {
        router.push("/");
      } else {
        setError("使用者名稱或密碼錯誤");
      }
      setIsLoading(false);
    }, 1000);
  };

  return (
    <div className="min-h-screen bg-carbon-gray-10 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo & Title */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-carbon-blue-60 rounded-lg mb-4">
            <Login size={32} className="text-white" />
          </div>
          <h1 className="text-2xl font-semibold text-carbon-gray-100">
            AI KM 知識管理平台
          </h1>
          <p className="text-carbon-gray-60 mt-2">
            登入以存取您的知識庫
          </p>
        </div>

        {/* Login Form */}
        <div className="bg-white p-8 rounded-lg shadow-sm border border-carbon-gray-20">
          <Form onSubmit={handleSubmit}>
            <Stack gap={6}>
              {error && (
                <InlineNotification
                  kind="error"
                  title="登入失敗"
                  subtitle={error}
                  lowContrast
                  hideCloseButton
                />
              )}

              <TextInput
                id="username"
                labelText="使用者名稱"
                placeholder="請輸入使用者名稱"
                value={formData.username}
                onChange={(e) =>
                  setFormData({ ...formData, username: e.target.value })
                }
                required
              />

              <PasswordInput
                id="password"
                labelText="密碼"
                placeholder="請輸入密碼"
                value={formData.password}
                onChange={(e) =>
                  setFormData({ ...formData, password: e.target.value })
                }
                required
              />

              <div className="flex items-center justify-between">
                <Checkbox
                  id="rememberMe"
                  labelText="記住我"
                  checked={formData.rememberMe}
                  onChange={(_, { checked }) =>
                    setFormData({ ...formData, rememberMe: checked })
                  }
                />
                <Link href="#" className="text-sm">
                  忘記密碼？
                </Link>
              </div>

              <Button
                type="submit"
                kind="primary"
                size="lg"
                className="w-full"
                renderIcon={ArrowRight}
                disabled={isLoading}
              >
                {isLoading ? "登入中..." : "登入"}
              </Button>
            </Stack>
          </Form>

          <div className="mt-6 pt-6 border-t border-carbon-gray-20 text-center">
            <p className="text-sm text-carbon-gray-60">
              還沒有帳號？{" "}
              <Link href="#" className="text-carbon-blue-60">
                聯絡管理員
              </Link>
            </p>
          </div>
        </div>

        {/* Demo credentials */}
        <div className="mt-4 p-4 bg-carbon-blue-10 rounded-lg border border-carbon-blue-20">
          <p className="text-sm text-carbon-gray-70">
            <strong>測試帳號：</strong> admin / admin
          </p>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-carbon-gray-50 mt-8">
          &copy; 2024 AI KM Platform. All rights reserved.
        </p>
      </div>
    </div>
  );
}
