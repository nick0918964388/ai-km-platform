"use client";

import { useState } from "react";
import AppHeader from "@/components/AppHeader";
import ConversationSidebar from "@/components/ConversationSidebar";
import ChatInterface from "@/components/ChatInterface";

export default function HomePage() {
  const [selectedConversation, setSelectedConversation] = useState<string>("1");

  return (
    <div className="min-h-screen">
      <AppHeader />
      <div className="flex" style={{ marginTop: "48px", height: "calc(100vh - 48px)" }}>
        {/* Sidebar */}
        <div className="w-72 flex-shrink-0">
          <ConversationSidebar
            selectedId={selectedConversation}
            onSelectConversation={setSelectedConversation}
          />
        </div>

        {/* Main Chat Area */}
        <div className="flex-1">
          <ChatInterface />
        </div>
      </div>
    </div>
  );
}
