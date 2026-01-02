/**
 * Chat Layout with History Sidebar
 * 
 * Implements Task 6.1: History Sidebar & Navigation Integration
 * 
 * Features:
 * - Side-by-side layout with history sidebar and chat interface
 * - Load historical sessions into chat
 * - Toggle sidebar visibility
 * - Responsive design
 * 
 * Usage:
 *   <ChatLayout />
 */

'use client';

import React, { useState, useCallback } from 'react';
import { HistorySidebar } from './HistorySidebar';
import { ChatInterface } from './ChatInterface';
import { SessionMessage, ChatSession } from '@/hooks/useChatSessions';
import { ChatMessage } from '@/hooks/useChatStream';
import { Button } from '@/components/ui/button';
import { MenuIcon, XIcon } from 'lucide-react';

export interface ChatLayoutProps {
  className?: string;
  showSidebar?: boolean;
  sidebarWidth?: string;
}

export const ChatLayout: React.FC<ChatLayoutProps> = ({
  className = '',
  showSidebar: initialShowSidebar = true,
  sidebarWidth = '320px',
}) => {
  const [showSidebar, setShowSidebar] = useState(initialShowSidebar);
  const [loadedMessages, setLoadedMessages] = useState<ChatMessage[]>([]);
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null);

  /**
   * Handle session load from sidebar
   * Convert SessionMessage to ChatMessage format
   */
  const handleSessionLoad = useCallback(
    (messages: SessionMessage[], session: ChatSession) => {
      console.log('Loading session:', session.id, 'with', messages.length, 'messages');

      // Convert SessionMessage to ChatMessage format
      const chatMessages: ChatMessage[] = messages.map((msg) => ({
        id: msg.id,
        role: msg.role,
        content: msg.content,
        timestamp: new Date(msg.created_at),
        status: 'complete' as const,
        report: msg.report,
      }));

      setLoadedMessages(chatMessages);
      setCurrentSession(session);

      // Close sidebar on mobile
      if (window.innerWidth < 768) {
        setShowSidebar(false);
      }
    },
    []
  );

  /**
   * Handle new chat
   */
  const handleNewChat = useCallback(() => {
    setLoadedMessages([]);
    setCurrentSession(null);
  }, []);

  /**
   * Toggle sidebar
   */
  const toggleSidebar = () => {
    setShowSidebar((prev) => !prev);
  };

  return (
    <div className={`chat-layout flex h-full ${className}`}>
      {/* Sidebar */}
      {showSidebar && (
        <div
          className="sidebar-container border-r bg-white"
          style={{ width: sidebarWidth }}
        >
          <HistorySidebar
            onSessionLoad={handleSessionLoad}
            onNewChat={handleNewChat}
            className="h-full"
          />
        </div>
      )}

      {/* Main Chat Area */}
      <div className="chat-container flex flex-col flex-1 relative">
        {/* Mobile Sidebar Toggle */}
        <Button
          variant="ghost"
          size="icon"
          className="absolute top-4 left-4 z-10 md:hidden"
          onClick={toggleSidebar}
        >
          {showSidebar ? (
            <XIcon className="w-5 h-5" />
          ) : (
            <MenuIcon className="w-5 h-5" />
          )}
        </Button>

        {/* Current Session Header */}
        {currentSession && (
          <div className="px-4 py-2 bg-blue-50 border-b flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-blue-900">
                {currentSession.title}
              </p>
              <p className="text-xs text-blue-700">
                {currentSession.message_count} message
                {currentSession.message_count !== 1 ? 's' : ''}
              </p>
            </div>
            <Button variant="ghost" size="sm" onClick={handleNewChat}>
              New Chat
            </Button>
          </div>
        )}

        {/* Chat Interface */}
        <ChatInterface
          endpoint="/api/v1/chat/stream"
          className="flex-1"
        />
      </div>
    </div>
  );
};

/**
 * Example Usage Component
 * 
 * Shows how to integrate ChatLayout with proper providers
 */
export const ChatLayoutExample: React.FC = () => {
  return (
    <div className="w-full h-screen bg-gray-100">
      <ChatLayout />
    </div>
  );
};

export default ChatLayout;

