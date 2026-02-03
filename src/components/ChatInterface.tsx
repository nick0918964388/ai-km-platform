"use client";

import { useState, useRef, useEffect } from "react";
import {
  Button,
  TextArea,
  IconButton,
  Loading,
} from "@carbon/react";
import {
  Send,
  Image as ImageIcon,
  Attachment,
  Copy,
  ThumbsUp,
  ThumbsDown,
} from "@carbon/icons-react";
import { VoiceInputButton } from "./VoiceInput";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  attachments?: { type: "image" | "file"; name: string }[];
}

const initialMessages: Message[] = [
  {
    id: "1",
    role: "assistant",
    content:
      "您好！我是 AI KM 知識管理助手。我可以幫助您查詢知識庫、回答問題、分析文件等。請問有什麼我可以幫助您的嗎？",
    timestamp: new Date(),
  },
];

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);

    // Simulate AI response
    setTimeout(() => {
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `感謝您的提問。根據知識庫的資料，我找到了以下相關資訊：

這是一個模擬的 AI 回應。在實際應用中，這裡會連接到後端 API，並從知識庫中檢索相關資訊來回答您的問題。

主要功能包括：
1. 自然語言理解與問答
2. 文件分析與摘要
3. 知識檢索與推薦
4. 多模態輸入支援（文字、語音、圖片）

如果您有任何其他問題，請隨時提出！`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, aiMessage]);
      setIsLoading(false);
    }, 1500);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleVoiceTranscription = (text: string) => {
    // Append transcribed text to input value
    setInputValue((prev) => {
      const separator = prev.trim() ? " " : "";
      return prev + separator + text;
    });
  };

  const handleImageUpload = () => {
    imageInputRef.current?.click();
  };

  const handleFileUpload = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className="chat-container bg-carbon-gray-10">
      {/* Messages Area */}
      <div className="chat-messages">
        <div className="max-w-4xl mx-auto">
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${
                message.role === "user" ? "justify-end" : "justify-start"
              } mb-4`}
            >
              <div
                className={`message-bubble ${
                  message.role === "user" ? "message-user" : "message-ai"
                }`}
              >
                <div className="whitespace-pre-wrap">{message.content}</div>
                {message.role === "assistant" && (
                  <div className="flex gap-2 mt-3 pt-2 border-t border-carbon-gray-30">
                    <IconButton
                      kind="ghost"
                      size="sm"
                      label="複製"
                      onClick={() => navigator.clipboard.writeText(message.content)}
                    >
                      <Copy size={16} />
                    </IconButton>
                    <IconButton kind="ghost" size="sm" label="有幫助">
                      <ThumbsUp size={16} />
                    </IconButton>
                    <IconButton kind="ghost" size="sm" label="沒有幫助">
                      <ThumbsDown size={16} />
                    </IconButton>
                  </div>
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex justify-start mb-4">
              <div className="message-bubble message-ai">
                <div className="flex items-center gap-2">
                  <Loading small withOverlay={false} />
                  <span>AI 正在思考中...</span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="chat-input-container">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-end gap-2 bg-white rounded-lg border border-carbon-gray-30 p-2">
            {/* Attachment buttons */}
            <div className="flex gap-1">
              <IconButton
                kind="ghost"
                size="md"
                label="上傳圖片"
                onClick={handleImageUpload}
              >
                <ImageIcon size={20} />
              </IconButton>
              <IconButton
                kind="ghost"
                size="md"
                label="上傳檔案"
                onClick={handleFileUpload}
              >
                <Attachment size={20} />
              </IconButton>
              <VoiceInputButton
                onTranscriptionReceived={handleVoiceTranscription}
              />
            </div>

            {/* Text input */}
            <div className="flex-1">
              <TextArea
                id="chat-input"
                labelText=""
                placeholder="輸入您的問題..."
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={1}
                className="border-0 resize-none"
                style={{ minHeight: "40px", maxHeight: "120px" }}
              />
            </div>

            {/* Send button */}
            <Button
              kind="primary"
              size="md"
              renderIcon={Send}
              iconDescription="發送"
              hasIconOnly
              onClick={handleSend}
              disabled={!inputValue.trim() || isLoading}
            />
          </div>

          <p className="text-xs text-carbon-gray-50 mt-2 text-center">
            AI 助手可能會產生不準確的資訊，重要決策請以官方文件為準
          </p>
        </div>
      </div>

      {/* Hidden file inputs */}
      <input
        type="file"
        ref={imageInputRef}
        className="hidden"
        accept="image/*"
        onChange={(e) => console.log("Image selected:", e.target.files)}
      />
      <input
        type="file"
        ref={fileInputRef}
        className="hidden"
        onChange={(e) => console.log("File selected:", e.target.files)}
      />
    </div>
  );
}
