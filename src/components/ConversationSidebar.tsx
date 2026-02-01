"use client";

import { useState } from "react";
import { Button, Search } from "@carbon/react";
import { Add, Chat } from "@carbon/icons-react";

interface Conversation {
  id: string;
  title: string;
  lastMessage: string;
  timestamp: string;
}

const mockConversations: Conversation[] = [
  {
    id: "1",
    title: "專案規劃討論",
    lastMessage: "讓我幫你分析這個專案的需求...",
    timestamp: "今天 14:30",
  },
  {
    id: "2",
    title: "技術文件查詢",
    lastMessage: "根據知識庫的資料顯示...",
    timestamp: "今天 11:20",
  },
  {
    id: "3",
    title: "API 整合問題",
    lastMessage: "這個 API 的使用方式是...",
    timestamp: "昨天",
  },
  {
    id: "4",
    title: "資料庫設計諮詢",
    lastMessage: "建議使用以下的資料結構...",
    timestamp: "2天前",
  },
  {
    id: "5",
    title: "效能優化建議",
    lastMessage: "可以從以下幾個方面著手...",
    timestamp: "3天前",
  },
];

interface ConversationSidebarProps {
  onSelectConversation?: (id: string) => void;
  selectedId?: string;
}

export default function ConversationSidebar({
  onSelectConversation,
  selectedId,
}: ConversationSidebarProps) {
  const [conversations] = useState<Conversation[]>(mockConversations);
  const [searchTerm, setSearchTerm] = useState("");

  const filteredConversations = conversations.filter(
    (conv) =>
      conv.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      conv.lastMessage.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full bg-white border-r border-carbon-gray-20">
      {/* Header */}
      <div className="p-4 border-b border-carbon-gray-20">
        <Button
          kind="primary"
          size="md"
          renderIcon={Add}
          className="w-full mb-4"
          onClick={() => onSelectConversation?.("new")}
        >
          新對話
        </Button>
        <Search
          size="md"
          placeholder="搜尋對話..."
          labelText="搜尋"
          closeButtonLabelText="清除搜尋"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto">
        {filteredConversations.map((conversation) => (
          <div
            key={conversation.id}
            className={`conversation-item ${
              selectedId === conversation.id ? "active" : ""
            }`}
            onClick={() => onSelectConversation?.(conversation.id)}
          >
            <div className="flex items-start gap-3">
              <Chat size={20} className="text-carbon-gray-60 mt-0.5 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex justify-between items-center mb-1">
                  <h4 className="font-medium text-sm text-carbon-gray-100 truncate">
                    {conversation.title}
                  </h4>
                  <span className="text-xs text-carbon-gray-50 flex-shrink-0 ml-2">
                    {conversation.timestamp}
                  </span>
                </div>
                <p className="text-xs text-carbon-gray-60 truncate">
                  {conversation.lastMessage}
                </p>
              </div>
            </div>
          </div>
        ))}

        {filteredConversations.length === 0 && (
          <div className="p-4 text-center text-carbon-gray-50 text-sm">
            沒有找到符合的對話
          </div>
        )}
      </div>
    </div>
  );
}
