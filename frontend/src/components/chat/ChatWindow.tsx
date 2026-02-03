'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send,
  Add,
  Bot,
  Chat,
} from '@carbon/icons-react';
import ReactMarkdown from 'react-markdown';
import { useStore } from '@/store/useStore';
import { Message, SearchResult } from '@/types';
import SourcePreview from './SourcePreview';
import { getApiHeaders, API_URL, TIMEOUTS, fetchWithTimeout, TimeoutError, getErrorMessage } from '@/lib/api';
import { VoiceInputButton } from '@/components/VoiceInput';

interface MessageSources {
  [messageId: string]: SearchResult[];
}

interface MessageMetadata {
  model: string;
  duration_ms: number;
  tokens?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  } | null;
}

interface MessageMetadataMap {
  [messageId: string]: MessageMetadata;
}

interface StreamingStatus {
  [messageId: string]: boolean;
}

interface ExpandedInfoMap {
  [messageId: string]: boolean;
}

interface MessageFollowUps {
  [messageId: string]: string[];
}

// Helper: get score color based on similarity value
function getScoreColor(score: number): string {
  if (score > 0.8) return '#24a148'; // Green - high
  if (score >= 0.5) return '#f1c21b'; // Yellow - medium
  return '#da1e28'; // Red - low
}

// Helper: get score label
function getScoreLabel(score: number): string {
  if (score > 0.8) return '高';
  if (score >= 0.5) return '中';
  return '低';
}

// Helper: highlight keywords in text
function highlightText(text: string, query: string): React.ReactNode {
  if (!query || !text) return text;
  
  // Extract keywords (split by spaces, filter short words)
  const keywords = query
    .split(/\s+/)
    .filter(k => k.length >= 2)
    .map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')); // Escape regex chars
  
  if (keywords.length === 0) return text;
  
  const pattern = new RegExp(`(${keywords.join('|')})`, 'gi');
  const parts = text.split(pattern);
  
  return parts.map((part, i) => {
    if (keywords.some(k => part.toLowerCase() === k.toLowerCase())) {
      return (
        <mark key={i} style={{
          background: 'rgba(37, 99, 235, 0.2)',
          color: 'var(--primary)',
          padding: '0 2px',
          borderRadius: 2,
          fontWeight: 500,
        }}>
          {part}
        </mark>
      );
    }
    return part;
  });
}

export default function ChatWindow() {
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [messageSources, setMessageSources] = useState<MessageSources>({});
  const [messageMetadata, setMessageMetadata] = useState<MessageMetadataMap>({});
  const [messageStreamingStatus, setMessageStreamingStatus] = useState<StreamingStatus>({});
  const [expandedInfo, setExpandedInfo] = useState<ExpandedInfoMap>({});
  const [messageFollowUps, setMessageFollowUps] = useState<MessageFollowUps>({});
  const [messageQueries, setMessageQueries] = useState<{ [msgId: string]: string }>({});
  const [expandedSources, setExpandedSources] = useState<{ [key: string]: boolean }>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const {
    conversations,
    activeConversationId,
    setActiveConversation,
    addMessage,
    addConversation,
    updateConversationTitle
  } = useStore();

  const activeConversation = conversations.find(c => c.id === activeConversationId);
  const messages = activeConversation?.messages || [];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [input]);

  // Load sources from messages when conversation changes or messages update
  useEffect(() => {
    if (messages.length > 0) {
      const newSources: MessageSources = {};
      const newQueries: { [msgId: string]: string } = {};
      messages.forEach((msg) => {
        if (msg.sources && msg.sources.length > 0) {
          newSources[msg.id] = msg.sources;
        }
        if (msg.query) {
          newQueries[msg.id] = msg.query;
        }
      });
      setMessageSources(newSources);
      setMessageQueries(newQueries);
    } else {
      // Reset when no messages
      setMessageSources({});
      setMessageQueries({});
    }
  }, [activeConversationId, messages]);

  const handleNewChat = () => {
    const newConv = {
      id: Date.now().toString(),
      title: '新對話',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    addConversation(newConv);
  };

  const handleSend = useCallback(async (overrideQuery?: string) => {
    const queryToSend = overrideQuery || input;
    if (!queryToSend.trim() || isLoading) return;
    
    // Clear input if using the input field value
    if (!overrideQuery) {
      setInput('');
    }

    let convId = activeConversationId;

    if (!convId) {
      const newConv = {
        id: Date.now().toString(),
        title: queryToSend.slice(0, 30) + (queryToSend.length > 30 ? '...' : ''),
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date(),
      };
      addConversation(newConv);
      convId = newConv.id;
    }

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: queryToSend,
      timestamp: new Date(),
    };

    addMessage(convId, userMessage);
    
    // Auto-update conversation title with first user message
    const currentConv = conversations.find(c => c.id === convId);
    if (currentConv && (currentConv.title === '新對話' || currentConv.messages.length === 0)) {
      const newTitle = queryToSend.slice(0, 30) + (queryToSend.length > 30 ? '...' : '');
      updateConversationTitle(convId, newTitle);
    }
    
    const userQuery = queryToSend;
    setIsLoading(true);

    const messageId = (Date.now() + 1).toString();
    
    // Store query for highlighting in sources
    setMessageQueries(prev => ({ ...prev, [messageId]: userQuery }));

    try {
      const response = await fetchWithTimeout(`${API_URL}/api/chat/stream`, {
        method: 'POST',
        headers: getApiHeaders(),
        body: JSON.stringify({
          query: userQuery,
          top_k: 5,
        }),
        timeout: TIMEOUTS.STREAMING,
      });

      if (!response.ok) {
        throw new Error('Streaming API request failed');
      }

      const assistantMessage: Message = {
        id: messageId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      };
      addMessage(convId!, assistantMessage);
      setIsStreaming(true);
      setMessageStreamingStatus(prev => ({ ...prev, [messageId]: true }));

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let streamedContent = '';
      let buffer = '';
      let receivedSources: any[] = [];

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          buffer += chunk;

          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));

                if (data.type === 'sources' && data.data?.length > 0) {
                  receivedSources = data.data;
                  setMessageSources(prev => ({
                    ...prev,
                    [messageId]: data.data,
                  }));
                } else if (data.type === 'content') {
                  streamedContent += data.data;
                  useStore.getState().updateMessage(convId!, messageId, streamedContent);
                } else if (data.type === 'metadata' && data.data) {
                  setMessageMetadata(prev => ({
                    ...prev,
                    [messageId]: data.data,
                  }));
                } else if (data.type === 'follow_up' && data.data?.length > 0) {
                  setMessageFollowUps(prev => ({
                    ...prev,
                    [messageId]: data.data,
                  }));
                } else if (data.type === 'done') {
                  setMessageStreamingStatus(prev => ({ ...prev, [messageId]: false }));
                  // Save sources to message for persistence
                  if (receivedSources.length > 0) {
                    useStore.getState().updateMessage(convId!, messageId, streamedContent, { sources: receivedSources, query: userQuery });
                  }
                } else if (data.type === 'error') {
                  useStore.getState().updateMessage(convId!, messageId, getSimulatedResponse(userQuery));
                  setMessageStreamingStatus(prev => ({ ...prev, [messageId]: false }));
                }
              } catch (e) {
                console.warn('Failed to parse SSE line:', line, e);
              }
            }
          }
        }

        if (buffer.startsWith('data: ')) {
          try {
            const data = JSON.parse(buffer.slice(6));
            if (data.type === 'sources' && data.data?.length > 0) {
              receivedSources = data.data;
              setMessageSources(prev => ({
                ...prev,
                [messageId]: data.data,
              }));
            } else if (data.type === 'content') {
              streamedContent += data.data;
              useStore.getState().updateMessage(convId!, messageId, streamedContent);
            } else if (data.type === 'metadata' && data.data) {
              setMessageMetadata(prev => ({
                ...prev,
                [messageId]: data.data,
              }));
            } else if (data.type === 'follow_up' && data.data?.length > 0) {
              setMessageFollowUps(prev => ({
                ...prev,
                [messageId]: data.data,
              }));
            } else if (data.type === 'done') {
              setMessageStreamingStatus(prev => ({ ...prev, [messageId]: false }));
            }
          } catch (e) {
            // Final buffer wasn't valid JSON
          }
        }
      }

      // Mark streaming as complete for this message
      setMessageStreamingStatus(prev => ({ ...prev, [messageId]: false }));

      if (!streamedContent) {
        useStore.getState().updateMessage(convId!, messageId, getSimulatedResponse(userQuery));
      }

    } catch (error) {
      console.error('Streaming API error:', error);

      try {
        const response = await fetchWithTimeout(`${API_URL}/api/chat`, {
          method: 'POST',
          headers: getApiHeaders(),
          body: JSON.stringify({
            query: userQuery,
            top_k: 5,
          }),
          timeout: TIMEOUTS.DEFAULT,
        });

        if (!response.ok) {
          throw new Error('API request failed');
        }

        const data = await response.json();

        const assistantMessage: Message = {
          id: messageId,
          role: 'assistant',
          content: data.answer || getSimulatedResponse(userQuery),
          timestamp: new Date(),
        };

        if (data.sources && data.sources.length > 0) {
          setMessageSources(prev => ({
            ...prev,
            [messageId]: data.sources,
          }));
        }

        // Non-streaming mode: immediately mark as complete
        setMessageStreamingStatus(prev => ({ ...prev, [messageId]: false }));

        addMessage(convId!, assistantMessage);
      } catch (fallbackError) {
        console.error('Fallback API error:', fallbackError);
        const assistantMessage: Message = {
          id: messageId,
          role: 'assistant',
          content: getSimulatedResponse(userQuery),
          timestamp: new Date(),
        };
        setMessageStreamingStatus(prev => ({ ...prev, [messageId]: false }));
        addMessage(convId!, assistantMessage);
      }
    } finally {
      setIsLoading(false);
      setIsStreaming(false);
    }
  }, [activeConversationId, input, isLoading, addConversation, addMessage]);

  // Handle follow-up question click - directly send the question
  const handleFollowUpClick = useCallback((question: string) => {
    if (!isLoading) {
      handleSend(question);
    }
  }, [handleSend, isLoading]);

  const getSimulatedResponse = (question: string): string => {
    const responses: Record<string, string> = {
      'EMU900': '關於 EMU900 轉向架維修，主要需要注意以下幾點：\n\n- **轉向架結構**：一組 SOJAT/C 空氣彈簧 4 個組\n- **定期檢查**：每 60,000 公里檢查避震器\n- **空氣彈簧**：每年度需要完整檢測一次\n- **磨耗標準**：車輪踏面 ≥850,090 公里需更換\n\n請問需要更詳細的維修流程說明嗎？',
      '轉向架': '轉向架維修程序包含以下步驟：\n\n1. **拆卸前檢查**：記錄車輪踏面磨耗狀況\n2. **主要零件檢測**：軸承、彈簧、避震器\n3. **清潔與潤滑**：使用指定規格潤滑油\n4. **組裝校準**：依規範扭力值鎖固\n\n相關技術文件已為您準備好。',
      '煞車': '煞車系統維修要點：\n\n- 煞車片磨耗檢查\n- 煞車盤厚度測量\n- 油壓系統測試\n- ABS 功能驗證',
    };

    for (const [keyword, response] of Object.entries(responses)) {
      if (question.includes(keyword)) return response;
    }

    return `您好！針對您的問題「${question}」\n\n我正在查詢車輛維修知識庫中的相關資料。請稍候，我會根據技術文件為您提供專業的維修建議。`;
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{ display: 'flex', flex: 1, height: '100%', overflow: 'hidden' }}>
      {/* Main Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Chat Header */}
        <div style={{
          height: 72,
          padding: '0 2rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--bg-secondary)',
          borderBottom: '1px solid var(--border)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div style={{
              width: 40,
              height: 40,
              background: 'var(--primary-light)',
              borderRadius: 10,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <Bot size={20} style={{ color: 'var(--accent)' }} />
            </div>
            <div>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                AI 維修顧問
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                隨時為您服務
              </div>
            </div>
          </div>
          <button
            onClick={handleNewChat}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.5rem 1rem',
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              fontSize: '0.875rem',
              cursor: 'pointer',
            }}
          >
            <Add size={16} />
            新對話
          </button>
        </div>

        {/* Messages Area */}
        <div style={{
          flex: 1,
          overflow: 'auto',
          padding: '2rem 5rem',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: messages.length === 0 ? 'center' : 'flex-start',
        }}>
          {messages.length === 0 ? (
            <div style={{
              textAlign: 'center',
              color: 'var(--text-secondary)',
            }}>
              <div style={{
                width: 80,
                height: 80,
                background: 'var(--primary-light)',
                borderRadius: 20,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                margin: '0 auto 1.5rem',
              }}>
                <Bot size={36} style={{ color: 'var(--accent)' }} />
              </div>
              <h2 style={{ marginBottom: '0.5rem', color: 'var(--text-primary)', fontWeight: 600, fontSize: '1.25rem' }}>
                開始新對話
              </h2>
              <p style={{ marginBottom: '1.5rem', fontSize: '0.875rem' }}>
                詢問任何車輛維修相關問題
              </p>
              <div style={{
                display: 'flex',
                gap: '0.75rem',
                justifyContent: 'center',
                flexWrap: 'wrap',
              }}>
                {['EMU900 轉向架維修', '煞車系統檢測', '定期保養週期'].map((q) => (
                  <button
                    key={q}
                    onClick={() => setInput(q)}
                    style={{
                      padding: '0.5rem 1rem',
                      background: 'var(--bg-secondary)',
                      border: '1px solid var(--border)',
                      borderRadius: 20,
                      color: 'var(--text-primary)',
                      fontSize: '0.8125rem',
                      cursor: 'pointer',
                    }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              {messages.map((msg) => (
                <div key={msg.id} style={{
                  display: 'flex',
                  gap: '0.75rem',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}>
                  {msg.role === 'assistant' && (
                    <div style={{
                      width: 36,
                      height: 36,
                      borderRadius: '50%',
                      background: 'var(--primary-light)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}>
                      <Bot size={18} style={{ color: 'var(--accent)' }} />
                    </div>
                  )}
                  <div 
                    className={msg.role === 'assistant' && messageStreamingStatus[msg.id] ? 'ai-message-streaming' : ''}
                    style={{
                    maxWidth: '70%',
                    padding: '1rem 1.25rem',
                    borderRadius: 'var(--radius-lg)',
                    background: msg.role === 'user' ? 'var(--primary)' : 'var(--bg-secondary)',
                    border: msg.role === 'assistant' ? '1px solid var(--border)' : 'none',
                    color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
                    lineHeight: 1.6,
                    position: 'relative',
                  }}>
                    {msg.role === 'assistant' ? (
                      <div className="markdown-content">
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => <p style={{ margin: '0.5rem 0' }}>{children}</p>,
                            ul: ({ children }) => <ul style={{ margin: '0.5rem 0', paddingLeft: '1.5rem' }}>{children}</ul>,
                            ol: ({ children }) => <ol style={{ margin: '0.5rem 0', paddingLeft: '1.5rem' }}>{children}</ol>,
                            li: ({ children }) => <li style={{ margin: '0.25rem 0' }}>{children}</li>,
                            strong: ({ children }) => <strong style={{ color: 'var(--accent)' }}>{children}</strong>,
                            code: ({ className, children, ...props }) => {
                              const isInline = !className;
                              if (isInline) {
                                return (
                                  <code style={{
                                    background: 'var(--bg-tertiary)',
                                    padding: '0.125rem 0.375rem',
                                    borderRadius: '4px',
                                    fontSize: '0.875em',
                                    fontFamily: 'monospace'
                                  }} {...props}>
                                    {children}
                                  </code>
                                );
                              }
                              return (
                                <code style={{
                                  display: 'block',
                                  background: 'var(--bg-tertiary)',
                                  padding: '1rem',
                                  borderRadius: '8px',
                                  fontSize: '0.875rem',
                                  fontFamily: 'monospace',
                                  overflowX: 'auto',
                                  margin: '0.5rem 0'
                                }} {...props}>
                                  {children}
                                </code>
                              );
                            },
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      msg.content.split('\n').map((line, i) => (
                        <p key={i} style={{ margin: i === 0 ? 0 : '0.5rem 0 0' }}>
                          {line}
                        </p>
                      ))
                    )}
                    {/* 來源文件 - 只在 streaming 完成後且 AI 回答引用了來源時顯示 */}
                    {msg.role === 'assistant' && 
                     messageSources[msg.id] && 
                     messageSources[msg.id].length > 0 && 
                     !messageStreamingStatus[msg.id] &&
                     /\[來源\s*\d+\]/.test(msg.content) && (
                      <div style={{
                        marginTop: '1rem',
                        paddingTop: '0.75rem',
                        borderTop: '1px solid var(--border)',
                        fontSize: '0.8125rem',
                      }}>
                        <div style={{ color: 'var(--accent)', marginBottom: '0.5rem', fontSize: '0.75rem' }}>
                          來源文件
                        </div>
                        {messageSources[msg.id]
                          .map((source, idx) => {
                          const sourceNumber = idx + 1; // 來源編號從 1 開始
                          const scorePercent = Math.round((source.score || 0) * 100);
                          const scoreColor = getScoreColor(source.score || 0);
                          const query = messageQueries[msg.id] || '';
                          const contentPreview = source.content?.slice(0, 200) || '';
                          const sourceKey = `${msg.id}-${idx}`;
                          const isExpanded = expandedSources[sourceKey];
                          return (
                            <div key={source.id || idx} style={{
                              background: 'var(--bg-primary)',
                              borderRadius: 'var(--radius-sm)',
                              marginBottom: '0.5rem',
                              border: '1px solid var(--border)',
                              overflow: 'hidden',
                            }}>
                              {/* Header: Always visible - Source Number + Document Name + Score + Preview */}
                              <div 
                                onClick={() => setExpandedSources(prev => ({ ...prev, [sourceKey]: !prev[sourceKey] }))}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '0.5rem',
                                  padding: '0.5rem 0.75rem',
                                  cursor: 'pointer',
                                  transition: 'background 0.15s',
                                }}
                                onMouseEnter={(e) => e.currentTarget.style.background = 'var(--bg-secondary)'}
                                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                              >
                                <span style={{ 
                                  color: 'var(--text-muted)', 
                                  fontSize: '0.75rem',
                                  transition: 'transform 0.2s',
                                  transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                                }}>
                                  ▶
                                </span>
                                <span style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  minWidth: '1.25rem',
                                  height: '1.25rem',
                                  background: 'var(--primary)',
                                  color: 'white',
                                  borderRadius: '50%',
                                  fontSize: '0.6875rem',
                                  fontWeight: 600,
                                  flexShrink: 0,
                                }}>
                                  {sourceNumber}
                                </span>
                                <span style={{ 
                                  flex: 1, 
                                  overflow: 'hidden', 
                                  textOverflow: 'ellipsis', 
                                  whiteSpace: 'nowrap',
                                  fontSize: '0.8125rem',
                                }}>
                                  📄 {source.document_name}
                                </span>
                                <span style={{
                                  fontSize: '0.6875rem',
                                  fontWeight: 600,
                                  color: scoreColor,
                                  padding: '0.125rem 0.375rem',
                                  background: `${scoreColor}15`,
                                  borderRadius: 4,
                                }}>
                                  {scorePercent}%
                                </span>
                                <div onClick={(e) => e.stopPropagation()}>
                                  <SourcePreview
                                    documentId={source.document_id}
                                    documentName={source.document_name}
                                  />
                                </div>
                              </div>
                              {/* Expandable Content */}
                              {isExpanded && contentPreview && (
                                <div style={{
                                  padding: '0.75rem',
                                  borderTop: '1px solid var(--border)',
                                  background: 'var(--bg-secondary)',
                                }}>
                                  <div style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    marginBottom: '0.5rem',
                                    fontSize: '0.6875rem',
                                    color: 'var(--text-muted)',
                                  }}>
                                    <span>{source.content?.length || 0} 字</span>
                                    <span>·</span>
                                    <span>SCORE {(source.score || 0).toFixed(2)}</span>
                                  </div>
                                  <div style={{
                                    fontSize: '0.8125rem',
                                    color: 'var(--text-secondary)',
                                    lineHeight: 1.6,
                                  }}>
                                    {highlightText(contentPreview, query)}
                                    {source.content && source.content.length > 200 && '...'}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {/* 模型資訊 - 可收合區塊 */}
                    {msg.role === 'assistant' && 
                     messageMetadata[msg.id] && 
                     !messageStreamingStatus[msg.id] && (
                      <div style={{ marginTop: '0.75rem' }}>
                        <button
                          onClick={() => setExpandedInfo(prev => ({ ...prev, [msg.id]: !prev[msg.id] }))}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.25rem',
                            padding: '0.25rem 0.5rem',
                            background: 'transparent',
                            border: 'none',
                            color: 'var(--text-muted)',
                            fontSize: '0.75rem',
                            cursor: 'pointer',
                          }}
                        >
                          <span>{expandedInfo[msg.id] ? '▼' : '▶'}</span>
                          <span>ℹ️ 詳細資訊</span>
                        </button>
                        {expandedInfo[msg.id] && (
                          <div style={{
                            marginTop: '0.5rem',
                            padding: '0.5rem 0.75rem',
                            background: 'var(--bg-tertiary, #f4f4f4)',
                            borderRadius: 'var(--radius-sm)',
                            fontSize: '0.75rem',
                            color: 'var(--text-secondary)',
                          }}>
                            <div style={{ marginBottom: '0.25rem' }}>
                              <strong>模型：</strong>{messageMetadata[msg.id].model}
                            </div>
                            <div style={{ marginBottom: '0.25rem' }}>
                              <strong>回應時長：</strong>{(messageMetadata[msg.id].duration_ms / 1000).toFixed(2)} 秒
                            </div>
                            {messageMetadata[msg.id].tokens && (
                              <div>
                                <strong>Token 使用量：</strong>
                                {messageMetadata[msg.id].tokens?.total_tokens} 
                                <span style={{ marginLeft: '0.5rem', opacity: 0.7 }}>
                                  (輸入: {messageMetadata[msg.id].tokens?.prompt_tokens}, 
                                  輸出: {messageMetadata[msg.id].tokens?.completion_tokens})
                                </span>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                    {/* Follow-up Questions */}
                    {msg.role === 'assistant' &&
                     messageFollowUps[msg.id] &&
                     messageFollowUps[msg.id].length > 0 &&
                     !messageStreamingStatus[msg.id] && (
                      <div style={{
                        marginTop: '1rem',
                        paddingTop: '0.75rem',
                        borderTop: '1px solid var(--border)',
                      }}>
                        <div style={{ 
                          color: 'var(--text-muted)', 
                          marginBottom: '0.5rem', 
                          fontSize: '0.75rem',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                        }}>
                          💡 相關問題
                        </div>
                        <div style={{
                          display: 'flex',
                          flexWrap: 'wrap',
                          gap: '0.5rem',
                        }}>
                          {messageFollowUps[msg.id].map((question, idx) => (
                            <button
                              key={idx}
                              onClick={() => handleFollowUpClick(question)}
                              style={{
                                padding: '0.375rem 0.75rem',
                                background: 'var(--bg-primary)',
                                border: '1px solid var(--border)',
                                borderRadius: 16,
                                color: 'var(--text-primary)',
                                fontSize: '0.8125rem',
                                cursor: 'pointer',
                                transition: 'all 0.15s ease',
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.background = 'var(--primary-light)';
                                e.currentTarget.style.borderColor = 'var(--accent)';
                                e.currentTarget.style.color = 'var(--accent)';
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.background = 'var(--bg-primary)';
                                e.currentTarget.style.borderColor = 'var(--border)';
                                e.currentTarget.style.color = 'var(--text-primary)';
                              }}
                            >
                              {question}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  {msg.role === 'user' && (
                    <div style={{
                      width: 36,
                      height: 36,
                      borderRadius: '50%',
                      background: 'var(--primary)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: 'white',
                      fontWeight: 500,
                      fontSize: '0.875rem',
                      flexShrink: 0,
                    }}>
                      U
                    </div>
                  )}
                </div>
              ))}
              {isLoading && !isStreaming && (
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <div style={{
                    width: 36,
                    height: 36,
                    borderRadius: '50%',
                    background: 'var(--primary-light)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <Bot size={18} style={{ color: 'var(--accent)' }} />
                  </div>
                  <div style={{
                    padding: '1rem 1.25rem',
                    background: 'var(--bg-secondary)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-lg)',
                  }}>
                    <div className="typing-indicator">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Chat Input */}
        <div style={{
          padding: '1.5rem 5rem',
          background: 'var(--bg-primary)',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '0.5rem 1rem',
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
          }}>
            <Chat size={20} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            <textarea
              ref={textareaRef}
              placeholder="輸入您的問題..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              style={{
                flex: 1,
                border: 'none',
                background: 'transparent',
                padding: '0.5rem 0',
                fontSize: '0.9375rem',
                color: 'var(--text-primary)',
                resize: 'none',
                minHeight: 24,
                maxHeight: 150,
                outline: 'none',
              }}
            />
            <VoiceInputButton
              onTranscriptionReceived={(text) => {
                setInput((prev) => prev ? `${prev} ${text}` : text);
              }}
            />
            <button
              data-send-button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              title="發送"
              style={{
                width: 40,
                height: 40,
                border: 'none',
                background: 'var(--primary)',
                borderRadius: 10,
                cursor: input.trim() && !isLoading ? 'pointer' : 'not-allowed',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'white',
                opacity: input.trim() && !isLoading ? 1 : 0.5,
              }}
            >
              <Send size={20} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
