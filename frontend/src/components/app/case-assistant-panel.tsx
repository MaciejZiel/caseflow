"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
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
        title: `Thread · ${formatEnumLabel(promptMode)}`,
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
    <section className="surface-card p-6 md:p-7">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="eyebrow">Case assistant</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-slate-950">
              Grounded threads with citations
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
              Ask for summaries, review guidance or next actions. Answers stay inside the case and
              point back to the underlying evidence.
            </p>
          </div>
          <Button onClick={() => void handleCreateThread()} variant="secondary">
            New thread
          </Button>
        </div>

        <div className="surface-panel-dark p-5 text-slate-50">
          <div className="flex flex-wrap gap-2">
            {assistantModes.map((mode) => (
              <button
                key={mode}
                className={`rounded-[1rem] border px-3 py-2 text-sm font-semibold transition-all ${
                  promptMode === mode
                    ? "border-orange-300/60 bg-gradient-to-r from-orange-500 to-orange-600 text-white shadow-[0_18px_36px_-24px_rgba(255,122,69,0.85)]"
                    : "border-white/10 bg-white/6 text-slate-200 hover:border-white/18 hover:bg-white/8"
                }`}
                onClick={() => setPromptMode(mode)}
                type="button"
              >
                {formatEnumLabel(mode)}
              </button>
            ))}
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            {conversations.length === 0 ? (
              <div className="rounded-[1rem] border border-dashed border-white/14 bg-white/4 px-4 py-3 text-sm text-slate-400">
                No assistant threads yet.
              </div>
            ) : (
              conversations.map((conversation) => (
                <button
                  key={conversation.id}
                  className={`rounded-[1rem] border px-4 py-3 text-left text-sm font-medium transition-all ${
                    conversation.id === selectedConversationId
                      ? "border-orange-300/60 bg-white text-slate-950"
                      : "border-white/10 bg-white/6 text-slate-200 hover:border-white/18 hover:bg-white/8"
                  }`}
                  onClick={() => setSelectedConversationId(conversation.id)}
                  type="button"
                >
                  <span className="block max-w-[20rem] truncate">{conversation.title}</span>
                </button>
              ))
            )}
          </div>
        </div>

        {selectedConversation ? (
          <div className="surface-panel px-4 py-4">
            <p className="eyebrow">Active thread</p>
            <p className="mt-2 text-base font-semibold text-slate-950">
              {selectedConversation.title}
            </p>
            <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-500">
              Updated {formatDateTime(selectedConversation.last_message_at)}
            </p>
          </div>
        ) : null}

        {errorMessage ? <p className="field-error">{errorMessage}</p> : null}

        <div className="space-y-4">
          {isLoading ? (
            <div className="rounded-[1.6rem] border border-dashed border-slate-300 bg-white/55 px-5 py-8 text-sm text-slate-500">
              Loading assistant threads…
            </div>
          ) : messages.length === 0 ? (
            <div className="rounded-[1.6rem] border border-dashed border-slate-300 bg-white/55 px-5 py-8 text-sm leading-7 text-slate-500">
              Start a thread to generate a grounded case summary, review guidance or suggested next
              actions.
            </div>
          ) : (
            messages.map((message) => (
              <article
                key={message.id}
                className={`rounded-[1.7rem] border p-5 ${
                  message.role === "assistant"
                    ? "border-slate-200 bg-white/80"
                    : "border-orange-200 bg-orange-50/85"
                }`}
              >
                <div className="flex flex-wrap items-center gap-3">
                  <Badge
                    value={message.role}
                    tone={message.role === "assistant" ? "success" : "warning"}
                  />
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500">
                    {formatEnumLabel(message.prompt_mode)}
                  </span>
                  <span className="text-xs uppercase tracking-[0.18em] text-slate-500">
                    {formatDateTime(message.created_at)}
                  </span>
                </div>
                <div className="mt-4 whitespace-pre-line text-sm leading-7 text-slate-800">
                  {message.content}
                </div>
                {message.role === "assistant" && message.citations_json.length > 0 ? (
                  <div className="mt-5 rounded-[1.4rem] bg-slate-950 p-4 text-slate-50">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                      Evidence used
                    </p>
                    <div className="mt-4 space-y-3">
                      {message.citations_json.map((citation) => (
                        <div
                          key={`${message.id}-${citation.document_id}-${citation.document_version_id ?? "latest"}`}
                          className="rounded-[1.2rem] border border-white/10 bg-white/6 px-4 py-4"
                        >
                          <div className="flex flex-wrap items-center gap-3">
                            <p className="text-sm font-semibold text-white">
                              {citation.document_title}
                            </p>
                            <Badge
                              value={citation.document_status}
                              tone={
                                citation.document_status === "approved" ||
                                citation.document_status === "ready"
                                  ? "success"
                                  : citation.document_status === "failed" ||
                                      citation.document_status === "rejected"
                                    ? "danger"
                                    : "warning"
                              }
                            />
                          </div>
                          <p className="mt-3 text-sm leading-7 text-slate-300">
                            {citation.excerpt}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </article>
            ))
          )}
        </div>

        <form className="surface-panel p-4" onSubmit={handleAsk}>
          <div className="field-shell">
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
          </div>
          <div className="mt-4">
            <Button disabled={isSending} fullWidth type="submit">
              {isSending ? "Generating grounded answer…" : "Ask Caseflow AI"}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}
