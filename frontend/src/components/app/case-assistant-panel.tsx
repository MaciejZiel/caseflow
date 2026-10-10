"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/auth-context";
import {
  ApiError,
  askAssistant,
  createAssistantConversation,
  listAssistantConversations,
  listAssistantMessages,
} from "@/lib/api";
import { formatDateTime, formatEnumLabel } from "@/lib/format";
import type { AssistantConversation, AssistantMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

const assistantModes = [
  "general",
  "case_summary",
  "review_assistant",
  "next_actions",
];

type CaseAssistantPanelProps = {
  caseId: string;
};

export function CaseAssistantPanel({ caseId }: CaseAssistantPanelProps) {
  const { accessToken } = useAuth();
  const [conversations, setConversations] = useState<AssistantConversation[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [promptMode, setPromptMode] = useState("review_assistant");
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (accessToken == null) {
      return;
    }
    const token = accessToken;

    let isCancelled = false;
    async function loadConversations() {
      try {
        setIsLoading(true);
        const nextConversations = await listAssistantConversations(token, caseId);
        if (isCancelled) {
          return;
        }
        setConversations(nextConversations);
        const nextSelectedId = nextConversations[0]?.id ?? null;
        setSelectedConversationId((currentValue) => currentValue ?? nextSelectedId);
        setErrorMessage(null);
      } catch (error) {
        if (isCancelled) {
          return;
        }
        setErrorMessage(
          error instanceof ApiError ? error.message : "Failed to load assistant threads.",
        );
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadConversations();
    return () => {
      isCancelled = true;
    };
  }, [accessToken, caseId]);

  useEffect(() => {
    if (accessToken == null || !selectedConversationId) {
      setMessages([]);
      return;
    }
    const token = accessToken;
    const conversationId = selectedConversationId;

    let isCancelled = false;
    async function loadMessages() {
      try {
        const nextMessages = await listAssistantMessages(token, caseId, conversationId);
        if (!isCancelled) {
          setMessages(nextMessages);
        }
      } catch (error) {
        if (!isCancelled) {
          setErrorMessage(
            error instanceof ApiError ? error.message : "Failed to load conversation messages.",
          );
        }
      }
    }

    void loadMessages();
    return () => {
      isCancelled = true;
    };
  }, [accessToken, caseId, selectedConversationId]);

  const selectedConversation = useMemo(
    () =>
      conversations.find((conversation) => conversation.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  );

  async function handleCreateThread() {
    if (!accessToken) {
      return;
    }
    try {
      const createdConversation = await createAssistantConversation(accessToken, caseId, {
        prompt_mode: promptMode,
        title: formatEnumLabel(promptMode),
      });
      setConversations((currentValue) => [createdConversation, ...currentValue]);
      setSelectedConversationId(createdConversation.id);
      setMessages([]);
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : "Failed to create thread.");
    }
  }

  async function handleAsk(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || !question.trim()) {
      return;
    }

    try {
      setIsSending(true);
      let conversationId = selectedConversationId;
      if (!conversationId) {
        const createdConversation = await createAssistantConversation(accessToken, caseId, {
          prompt_mode: promptMode,
          title: question.trim().slice(0, 80),
        });
        conversationId = createdConversation.id;
        setConversations((currentValue) => [createdConversation, ...currentValue]);
        setSelectedConversationId(conversationId);
      }

      const exchange = await askAssistant(accessToken, caseId, conversationId, {
        question: question.trim(),
        prompt_mode: promptMode,
      });
      setQuestion("");
      setMessages((currentValue) => [
        ...currentValue,
        exchange.user_message,
        exchange.assistant_message,
      ]);
      setConversations((currentValue) => {
        const updated = currentValue.filter(
          (conversation) => conversation.id !== exchange.conversation.id,
        );
        return [exchange.conversation, ...updated];
      });
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(error instanceof ApiError ? error.message : "Assistant request failed.");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <section className="panel min-w-0" aria-labelledby="assistant-heading">
      <div className="panel-head">
        <h2 className="panel-title" id="assistant-heading">
          Assistant
        </h2>
        <Button onClick={() => void handleCreateThread()} variant="secondary">
          New thread
        </Button>
      </div>

      <div className="space-y-3 border-b border-line px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted">Mode</span>
          <div className="inline-flex flex-wrap overflow-hidden rounded border border-line">
            {assistantModes.map((mode) => (
              <button
                key={mode}
                aria-pressed={promptMode === mode}
                className={cn(
                  "border-r border-line px-2.5 py-1 text-[13px] last:border-r-0",
                  promptMode === mode
                    ? "bg-accent text-white"
                    : "bg-surface text-ink hover:bg-paper",
                )}
                onClick={() => setPromptMode(mode)}
                type="button"
              >
                {formatEnumLabel(mode)}
              </button>
            ))}
          </div>
        </div>

        {conversations.length > 0 ? (
          <div className="flex items-center gap-2">
            <label className="text-xs text-muted" htmlFor="assistant-thread">
              Thread
            </label>
            <select
              id="assistant-thread"
              className="min-w-0 flex-1"
              value={selectedConversationId ?? ""}
              onChange={(event) => setSelectedConversationId(event.target.value)}
            >
              {conversations.map((conversation) => (
                <option key={conversation.id} value={conversation.id}>
                  {conversation.title} ({formatDateTime(conversation.last_message_at)})
                </option>
              ))}
            </select>
          </div>
        ) : null}
      </div>

      {errorMessage ? <p className="field-error px-4 pt-3">{errorMessage}</p> : null}

      <div className="max-h-[38rem] overflow-y-auto">
        {isLoading ? (
          <p className="empty">Loading threads…</p>
        ) : messages.length === 0 ? (
          <p className="empty">
            {selectedConversation
              ? "No messages in this thread yet."
              : "Ask a question about this case. Answers cite the documents they use."}
          </p>
        ) : (
          messages.map((message) => (
            <article
              key={message.id}
              className={cn(
                "border-b border-line px-4 py-3",
                message.role === "user" && "bg-paper/60",
              )}
            >
              <p className="text-xs text-muted">
                <span className="font-medium text-ink">
                  {message.role === "assistant" ? "Assistant" : "You"}
                </span>{" "}
                · {formatEnumLabel(message.prompt_mode)} · {formatDateTime(message.created_at)}
              </p>
              <div className="mt-1.5 whitespace-pre-line">{message.content}</div>
              {message.role === "assistant" && message.citations_json.length > 0 ? (
                <div className="mt-3 border-l-2 border-accent pl-3">
                  <p className="text-xs font-medium text-muted">Sources</p>
                  <ul className="mt-1.5 space-y-2">
                    {message.citations_json.map((citation) => (
                      <li
                        key={`${message.id}-${citation.document_id}-${citation.document_version_id ?? "latest"}`}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{citation.document_title}</span>
                          <Badge
                            value={citation.document_status}
                            tone={statusTone[citation.document_status] ?? "neutral"}
                          />
                        </div>
                        <p className="mt-0.5 text-[13px] text-muted">{citation.excerpt}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </article>
          ))
        )}
      </div>

      <form className="space-y-2 p-4" onSubmit={handleAsk}>
        <label className="field-label" htmlFor="assistant-question">
          Ask the assistant
        </label>
        <textarea
          id="assistant-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="What is missing before this case can move forward?"
          required
        />
        <Button disabled={isSending} type="submit">
          {isSending ? "Answering…" : "Ask"}
        </Button>
      </form>
    </section>
  );
}
