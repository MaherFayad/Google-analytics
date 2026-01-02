/**
 * Chat Sessions Hook
 * 
 * Implements Task 6.1: History Sidebar & Navigation
 * 
 * Features:
 * - Fetch chat sessions from backend
 * - Load specific session messages
 * - Delete sessions
 * - Create new session
 * 
 * Tech: TanStack Query for data fetching
 * 
 * Usage:
 *   const { sessions, isLoading, loadSession, deleteSession } = useChatSessions();
 */

'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message?: string;
  tenant_id?: string;
  user_id?: string;
}

export interface SessionMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  
  // For assistant messages with structured data
  report?: {
    answer: string;
    charts: any[];
    metrics: any[];
    confidence: number;
  };
}

export interface UseChatSessionsOptions {
  apiBaseUrl?: string;
  enabled?: boolean;
  refetchInterval?: number;
}

export interface UseChatSessionsReturn {
  // Session list
  sessions: ChatSession[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  
  // Current session
  currentSession: ChatSession | null;
  currentMessages: SessionMessage[];
  
  // Actions
  loadSession: (sessionId: string) => Promise<void>;
  createSession: (title?: string) => Promise<ChatSession>;
  deleteSession: (sessionId: string) => Promise<void>;
  renameSession: (sessionId: string, newTitle: string) => Promise<void>;
  refreshSessions: () => Promise<void>;
}

/**
 * Hook for managing chat sessions with history
 * 
 * Implements Task 6.1 requirements:
 * - Fetch GET /api/v1/chat/sessions
 * - Implement "Load Session" logic
 * - Populate main chat window with historical messages
 */
export function useChatSessions(
  options: UseChatSessionsOptions = {}
): UseChatSessionsReturn {
  const {
    apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || '/api',
    enabled = true,
    refetchInterval,
  } = options;

  const queryClient = useQueryClient();
  
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  /**
   * Fetch all chat sessions
   */
  const {
    data: sessionsData,
    isLoading: isLoadingSessions,
    isError: isErrorSessions,
    error: sessionsError,
    refetch: refetchSessions,
  } = useQuery({
    queryKey: ['chatSessions'],
    queryFn: async () => {
      const response = await fetch(`${apiBaseUrl}/v1/chat/sessions`, {
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch sessions: ${response.statusText}`);
      }

      const data = await response.json();
      return data.sessions as ChatSession[];
    },
    enabled,
    refetchInterval,
    staleTime: 30000, // Consider fresh for 30 seconds
  });

  /**
   * Fetch messages for a specific session
   */
  const {
    data: messagesData,
    isLoading: isLoadingMessages,
  } = useQuery({
    queryKey: ['chatMessages', currentSessionId],
    queryFn: async () => {
      if (!currentSessionId) {
        return [];
      }

      const response = await fetch(
        `${apiBaseUrl}/v1/chat/sessions/${currentSessionId}/messages`,
        {
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch messages: ${response.statusText}`);
      }

      const data = await response.json();
      return data.messages as SessionMessage[];
    },
    enabled: !!currentSessionId,
  });

  /**
   * Create a new chat session
   */
  const createSessionMutation = useMutation({
    mutationFn: async (title?: string) => {
      const response = await fetch(`${apiBaseUrl}/v1/chat/sessions`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          title: title || `Chat ${new Date().toLocaleDateString()}`,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to create session: ${response.statusText}`);
      }

      const data = await response.json();
      return data.session as ChatSession;
    },
    onSuccess: () => {
      // Invalidate and refetch sessions list
      queryClient.invalidateQueries({ queryKey: ['chatSessions'] });
    },
  });

  /**
   * Delete a chat session
   */
  const deleteSessionMutation = useMutation({
    mutationFn: async (sessionId: string) => {
      const response = await fetch(
        `${apiBaseUrl}/v1/chat/sessions/${sessionId}`,
        {
          method: 'DELETE',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to delete session: ${response.statusText}`);
      }

      return sessionId;
    },
    onSuccess: (deletedId) => {
      // Invalidate sessions list
      queryClient.invalidateQueries({ queryKey: ['chatSessions'] });
      
      // If deleted session was current, clear it
      if (deletedId === currentSessionId) {
        setCurrentSessionId(null);
      }
    },
  });

  /**
   * Rename a chat session
   */
  const renameSessionMutation = useMutation({
    mutationFn: async ({
      sessionId,
      newTitle,
    }: {
      sessionId: string;
      newTitle: string;
    }) => {
      const response = await fetch(
        `${apiBaseUrl}/v1/chat/sessions/${sessionId}`,
        {
          method: 'PATCH',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ title: newTitle }),
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to rename session: ${response.statusText}`);
      }

      return response.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chatSessions'] });
    },
  });

  /**
   * Load a specific session
   */
  const loadSession = async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    
    // Prefetch messages
    await queryClient.prefetchQuery({
      queryKey: ['chatMessages', sessionId],
      queryFn: async () => {
        const response = await fetch(
          `${apiBaseUrl}/v1/chat/sessions/${sessionId}/messages`,
          {
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
            },
          }
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch messages: ${response.statusText}`);
        }

        const data = await response.json();
        return data.messages as SessionMessage[];
      },
    });
  };

  const currentSession = sessionsData?.find(s => s.id === currentSessionId) || null;

  return {
    // Session list
    sessions: sessionsData || [],
    isLoading: isLoadingSessions || isLoadingMessages,
    isError: isErrorSessions,
    error: sessionsError,
    
    // Current session
    currentSession,
    currentMessages: messagesData || [],
    
    // Actions
    loadSession,
    createSession: async (title?: string) => {
      return createSessionMutation.mutateAsync(title);
    },
    deleteSession: async (sessionId: string) => {
      return deleteSessionMutation.mutateAsync(sessionId);
    },
    renameSession: async (sessionId: string, newTitle: string) => {
      return renameSessionMutation.mutateAsync({ sessionId, newTitle });
    },
    refreshSessions: async () => {
      await refetchSessions();
    },
  };
}

export default useChatSessions;

