"use client";

import { useState, useCallback, useRef, useEffect } from "react";

// ── Types ───────────────────────────────────────────────────────────

export interface ChatMessage {
  id: string;
  type: "user" | "agent" | "system";
  agentRole?: string;
  agentId?: string;
  agentName: string;
  agentEmoji?: string;
  agentColor?: string;
  content: string;
  timestamp: string;
}

interface TypingState {
  [agentId: string]: { name: string; isTyping: boolean };
}

interface UseWebSocketChatReturn {
  messages: ChatMessage[];
  typingAgents: TypingState;
  isConnected: boolean;
  isComplete: boolean;
  sessionId: string | null;
  error: string | null;
  sendDiagnosis: (text: string, maxRounds?: number) => void;
  reset: () => void;
}

// ── Hook ────────────────────────────────────────────────────────────

export function useWebSocketChat(): UseWebSocketChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [typingAgents, setTypingAgents] = useState<TypingState>({});
  const [isConnected, setIsConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const msgIdCounter = useRef(0);

  const nextId = () => `msg_${++msgIdCounter.current}_${Date.now()}`;

  const addMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const sendDiagnosis = useCallback(
    (text: string, maxRounds = 3) => {
      // Reset state
      setMessages([]);
      setTypingAgents({});
      setIsComplete(false);
      setError(null);
      setSessionId(null);
      msgIdCounter.current = 0;

      // Add user message
      const userMsg: ChatMessage = {
        id: nextId(),
        type: "user",
        agentName: "You",
        agentEmoji: "👤",
        content: text,
        timestamp: new Date().toISOString(),
      };
      setMessages([userMsg]);

      // Connect WebSocket
      const wsUrl = `ws://localhost:8000/ws/diagnose`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        // Send patient data
        ws.send(
          JSON.stringify({
            patient_text: text,
            max_rounds: maxRounds,
          })
        );
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          switch (data.type) {
            case "session_start":
              setSessionId(data.session_id);
              break;

            case "chat_message":
              addMessage({
                id: nextId(),
                type: data.agent_role === "system" ? "system" : "agent",
                agentRole: data.agent_role,
                agentId: data.agent_id,
                agentName: data.agent_name,
                agentEmoji: data.agent_emoji,
                agentColor: data.agent_color,
                content: data.content,
                timestamp: data.timestamp,
              });
              break;

            case "typing_indicator":
              setTypingAgents((prev) => ({
                ...prev,
                [data.agent_role]: {
                  name: data.agent_name,
                  isTyping: data.is_typing,
                },
              }));
              break;

            case "error":
              setError(data.error);
              addMessage({
                id: nextId(),
                type: "system",
                agentName: "System",
                agentEmoji: "❌",
                agentColor: "#ef4444",
                content: `Error: ${data.error}`,
                timestamp: new Date().toISOString(),
              });
              break;

            case "complete":
              setIsComplete(true);
              setIsConnected(false);
              break;

            // Silently ignore structured events (they have chat_message companions)
            default:
              break;
          }
        } catch {
          // Ignore unparseable messages
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        setTypingAgents({});
      };

      ws.onerror = () => {
        setError("WebSocket connection failed. Is the backend running?");
        setIsConnected(false);
      };
    },
    [addMessage]
  );

  const reset = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setMessages([]);
    setTypingAgents({});
    setIsConnected(false);
    setIsComplete(false);
    setSessionId(null);
    setError(null);
    msgIdCounter.current = 0;
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return {
    messages,
    typingAgents,
    isConnected,
    isComplete,
    sessionId,
    error,
    sendDiagnosis,
    reset,
  };
}
