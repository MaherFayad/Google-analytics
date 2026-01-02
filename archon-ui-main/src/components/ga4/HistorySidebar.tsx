/**
 * History Sidebar Component
 * 
 * Implements Task 6.1: History Sidebar & Navigation
 * 
 * Features:
 * - List of past chat sessions
 * - Search/filter sessions
 * - Load session to populate chat
 * - Delete sessions
 * - Rename sessions
 * - Create new session
 * 
 * Tech: TanStack Query, Shadcn UI
 * 
 * Usage:
 *   <HistorySidebar onSessionLoad={(messages) => setChatMessages(messages)} />
 */

'use client';

import React, { useState } from 'react';
import { useChatSessions, SessionMessage, ChatSession } from '@/hooks/useChatSessions';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  MessageSquareIcon,
  PlusIcon,
  Trash2Icon,
  EditIcon,
  CheckIcon,
  XIcon,
  SearchIcon,
  LoaderIcon,
  ClockIcon,
} from 'lucide-react';

export interface HistorySidebarProps {
  onSessionLoad?: (messages: SessionMessage[], session: ChatSession) => void;
  onNewChat?: () => void;
  className?: string;
}

export const HistorySidebar: React.FC<HistorySidebarProps> = ({
  onSessionLoad,
  onNewChat,
  className = '',
}) => {
  const {
    sessions,
    isLoading,
    isError,
    error,
    currentSession,
    currentMessages,
    loadSession,
    createSession,
    deleteSession,
    renameSession,
  } = useChatSessions();

  const [searchQuery, setSearchQuery] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  /**
   * Filter sessions by search query
   */
  const filteredSessions = sessions.filter((session) =>
    session.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  /**
   * Handle session click - load messages
   */
  const handleSessionClick = async (session: ChatSession) => {
    await loadSession(session.id);
    
    // Wait for messages to load, then call callback
    setTimeout(() => {
      if (onSessionLoad && currentMessages.length > 0) {
        onSessionLoad(currentMessages, session);
      }
    }, 100);
  };

  /**
   * Handle create new session
   */
  const handleCreateSession = async () => {
    const newSession = await createSession();
    onNewChat?.();
  };

  /**
   * Handle delete session
   */
  const handleDeleteSession = async (
    e: React.MouseEvent,
    sessionId: string
  ) => {
    e.stopPropagation();
    
    if (confirm('Are you sure you want to delete this chat session?')) {
      await deleteSession(sessionId);
    }
  };

  /**
   * Start editing session title
   */
  const startEditing = (e: React.MouseEvent, session: ChatSession) => {
    e.stopPropagation();
    setEditingSessionId(session.id);
    setEditingTitle(session.title);
  };

  /**
   * Save edited title
   */
  const saveEdit = async (e: React.MouseEvent) => {
    e.stopPropagation();
    
    if (editingSessionId && editingTitle.trim()) {
      await renameSession(editingSessionId, editingTitle);
      setEditingSessionId(null);
      setEditingTitle('');
    }
  };

  /**
   * Cancel editing
   */
  const cancelEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingSessionId(null);
    setEditingTitle('');
  };

  /**
   * Format date for display
   */
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString();
  };

  return (
    <div className={`history-sidebar flex flex-col h-full bg-gray-50 border-r ${className}`}>
      {/* Header */}
      <div className="p-4 border-b bg-white">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <MessageSquareIcon className="w-5 h-5" />
            Chat History
          </h3>
          <Button
            variant="default"
            size="sm"
            onClick={handleCreateSession}
            className="flex items-center gap-1"
          >
            <PlusIcon className="w-4 h-4" />
            New
          </Button>
        </div>

        {/* Search */}
        <div className="relative">
          <SearchIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <Input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Sessions List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {/* Loading State */}
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <LoaderIcon className="w-6 h-6 animate-spin text-gray-400" />
              <span className="ml-2 text-sm text-gray-600">Loading history...</span>
            </div>
          )}

          {/* Error State */}
          {isError && (
            <Card className="p-4 bg-red-50 border-red-200">
              <p className="text-sm text-red-700">
                Failed to load chat history: {error?.message}
              </p>
            </Card>
          )}

          {/* Empty State */}
          {!isLoading && !isError && filteredSessions.length === 0 && (
            <div className="text-center py-8 px-4">
              <MessageSquareIcon className="w-12 h-12 mx-auto text-gray-300 mb-3" />
              <p className="text-sm text-gray-600">
                {searchQuery ? 'No matching conversations' : 'No chat history yet'}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                Start a new conversation to see it here
              </p>
            </div>
          )}

          {/* Sessions */}
          {!isLoading && filteredSessions.map((session) => (
            <Card
              key={session.id}
              className={`
                p-3 cursor-pointer transition-colors
                hover:bg-gray-100 hover:border-gray-300
                ${currentSession?.id === session.id ? 'bg-blue-50 border-blue-300' : ''}
              `}
              onClick={() => handleSessionClick(session)}
            >
              {/* Editing Mode */}
              {editingSessionId === session.id ? (
                <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                  <Input
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    className="flex-1 h-8 text-sm"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') saveEdit(e as any);
                      if (e.key === 'Escape') cancelEdit(e as any);
                    }}
                  />
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={saveEdit}
                  >
                    <CheckIcon className="w-4 h-4 text-green-600" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={cancelEdit}
                  >
                    <XIcon className="w-4 h-4 text-red-600" />
                  </Button>
                </div>
              ) : (
                <>
                  {/* Title and Actions */}
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <h4 className="text-sm font-medium truncate flex-1">
                      {session.title}
                    </h4>
                    <div className="flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                        onClick={(e) => startEditing(e, session)}
                      >
                        <EditIcon className="w-3 h-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-100"
                        onClick={(e) => handleDeleteSession(e, session.id)}
                      >
                        <Trash2Icon className="w-3 h-3 text-red-600" />
                      </Button>
                    </div>
                  </div>

                  {/* Last Message Preview */}
                  {session.last_message && (
                    <p className="text-xs text-gray-600 truncate mb-2">
                      {session.last_message}
                    </p>
                  )}

                  {/* Metadata */}
                  <div className="flex items-center justify-between text-xs text-gray-500">
                    <span className="flex items-center gap-1">
                      <ClockIcon className="w-3 h-3" />
                      {formatDate(session.updated_at)}
                    </span>
                    {session.message_count > 0 && (
                      <span className="bg-gray-200 px-2 py-0.5 rounded-full">
                        {session.message_count} msgs
                      </span>
                    )}
                  </div>
                </>
              )}
            </Card>
          ))}
        </div>
      </ScrollArea>

      {/* Footer Stats */}
      {!isLoading && sessions.length > 0 && (
        <div className="p-3 border-t bg-white text-xs text-gray-600 text-center">
          {sessions.length} conversation{sessions.length !== 1 ? 's' : ''}
        </div>
      )}
    </div>
  );
};

export default HistorySidebar;

