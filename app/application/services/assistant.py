"""Case-scoped grounded assistant services."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.assistant import (
    AssistantConversationCreateRequest,
    AssistantMessageCreateRequest,
)
from app.application.actors import ActorContext
from app.application.services.events import EventPublisher
from app.core.errors import NotFoundError
from app.domain.assistant.models import (
    AssistantConversation,
    AssistantMessage,
    AssistantMessageRole,
    AssistantPromptMode,
)
from app.domain.cases.models import Case, CaseComment
from app.domain.cases.policies import CASE_READ_ROLES
from app.domain.documents.models import Document, DocumentVersion
from app.domain.organizations.policies import ensure_role_allowed

_TOKEN_PATTERN = re.compile(r"[a-z0-9]{4,}")


@dataclass(slots=True)
class GroundedDocumentSnippet:
    document_id: UUID
    document_title: str
    document_type: str
    document_status: str
    document_version_id: UUID | None
    original_filename: str | None
    excerpt: str
    score: int


@dataclass(slots=True)
class AssistantExchange:
    conversation: AssistantConversation
    user_message: AssistantMessage
    assistant_message: AssistantMessage


class AssistantService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.publisher = EventPublisher(session)

    def create_conversation(
        self,
        *,
        actor: ActorContext,
        case_id: UUID,
        payload: AssistantConversationCreateRequest,
    ) -> AssistantConversation:
        case = self._get_case(actor=actor, case_id=case_id)
        title = (
            payload.title.strip()
            if payload.title is not None and payload.title.strip()
            else f"{case.title[:80]} assistant"
        )
        conversation = AssistantConversation(
            id=uuid4(),
            organization_id=actor.organization.id,
            case_id=case.id,
            created_by_user_id=actor.user.id,
            title=title,
            prompt_mode=payload.prompt_mode,
            last_message_at=None,
        )
        self.session.add(conversation)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def list_conversations(
        self,
        *,
        actor: ActorContext,
        case_id: UUID,
    ) -> list[AssistantConversation]:
        self._get_case(actor=actor, case_id=case_id)
        return list(
            self.session.scalars(
                select(AssistantConversation)
                .where(
                    AssistantConversation.organization_id == actor.organization.id,
                    AssistantConversation.case_id == case_id,
                )
                .order_by(
                    AssistantConversation.last_message_at.desc().nullslast(),
                    AssistantConversation.updated_at.desc(),
                )
            )
        )

    def list_messages(
        self,
        *,
        actor: ActorContext,
        case_id: UUID,
        conversation_id: UUID,
    ) -> list[AssistantMessage]:
        self._get_conversation(actor=actor, case_id=case_id, conversation_id=conversation_id)
        return list(
            self.session.scalars(
                select(AssistantMessage)
                .where(
                    AssistantMessage.organization_id == actor.organization.id,
                    AssistantMessage.case_id == case_id,
                    AssistantMessage.conversation_id == conversation_id,
                )
                .order_by(AssistantMessage.created_at.asc())
            )
        )

    def ask(
        self,
        *,
        actor: ActorContext,
        case_id: UUID,
        conversation_id: UUID,
        payload: AssistantMessageCreateRequest,
    ) -> AssistantExchange:
        case = self._get_case(actor=actor, case_id=case_id)
        conversation = self._get_conversation(
            actor=actor,
            case_id=case_id,
            conversation_id=conversation_id,
        )
        prompt_mode = payload.prompt_mode or conversation.prompt_mode
        conversation.prompt_mode = prompt_mode
        if conversation.title.endswith(" assistant"):
            conversation.title = payload.question[:80].strip()

        user_message = AssistantMessage(
            id=uuid4(),
            organization_id=actor.organization.id,
            case_id=case.id,
            conversation_id=conversation.id,
            actor_user_id=actor.user.id,
            role=AssistantMessageRole.USER,
            prompt_mode=prompt_mode,
            content=payload.question.strip(),
            citations_json=[],
            metadata_json={"source": "user"},
        )
        snippets = self._collect_document_snippets(case=case, question=payload.question)
        assistant_content = self._build_grounded_answer(
            case=case,
            question=payload.question,
            prompt_mode=prompt_mode,
            snippets=snippets,
        )
        assistant_message = AssistantMessage(
            id=uuid4(),
            organization_id=actor.organization.id,
            case_id=case.id,
            conversation_id=conversation.id,
            actor_user_id=None,
            role=AssistantMessageRole.ASSISTANT,
            prompt_mode=prompt_mode,
            content=assistant_content,
            citations_json=[_snippet_to_json(snippet) for snippet in snippets],
            metadata_json={
                "source": "grounded_case_assistant",
                "question": payload.question.strip(),
                "citation_count": len(snippets),
            },
        )
        timestamp = datetime.now(UTC)
        conversation.last_message_at = timestamp
        self.session.add(user_message)
        self.session.add(assistant_message)
        self.session.flush()
        self.publisher.record_event(
            organization_id=actor.organization.id,
            actor_user_id=actor.user.id,
            event_type="case.assistant_responded",
            entity_type="case",
            entity_id=case.id,
            metadata={
                "conversation_id": conversation.id,
                "prompt_mode": prompt_mode,
                "user_message_id": user_message.id,
                "assistant_message_id": assistant_message.id,
                "citation_count": len(snippets),
            },
            deliver_webhooks=False,
        )
        self.session.commit()
        self.session.refresh(conversation)
        self.session.refresh(user_message)
        self.session.refresh(assistant_message)
        return AssistantExchange(
            conversation=conversation,
            user_message=user_message,
            assistant_message=assistant_message,
        )

    def _get_case(self, *, actor: ActorContext, case_id: UUID) -> Case:
        ensure_role_allowed(
            actor.membership.role,
            allowed_roles=CASE_READ_ROLES,
            message="Your role cannot access the assistant for this case.",
        )
        case = self.session.scalar(
            select(Case).where(
                Case.id == case_id,
                Case.organization_id == actor.organization.id,
            )
        )
        if case is None:
            raise NotFoundError("case", "Case does not exist.")
        return case

    def _get_conversation(
        self,
        *,
        actor: ActorContext,
        case_id: UUID,
        conversation_id: UUID,
    ) -> AssistantConversation:
        conversation = self.session.scalar(
            select(AssistantConversation).where(
                AssistantConversation.id == conversation_id,
                AssistantConversation.case_id == case_id,
                AssistantConversation.organization_id == actor.organization.id,
            )
        )
        if conversation is None:
            raise NotFoundError("assistant_conversation", "Assistant conversation does not exist.")
        return conversation

    def _collect_document_snippets(
        self,
        *,
        case: Case,
        question: str,
    ) -> list[GroundedDocumentSnippet]:
        documents = list(
            self.session.scalars(
                select(Document)
                .where(
                    Document.case_id == case.id,
                    Document.organization_id == case.organization_id,
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.updated_at.desc(), Document.created_at.desc())
            )
        )
        if not documents:
            return []

        version_ids = [
            document.current_version_id
            for document in documents
            if document.current_version_id
        ]
        versions = {
            version.id: version
            for version in self.session.scalars(
                select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
            )
        }
        comment_excerpt = self._recent_comment_excerpt(case=case)
        tokens = _extract_tokens(question)
        snippets: list[GroundedDocumentSnippet] = []
        for document in documents:
            current_version = versions.get(document.current_version_id)
            extracted_payload = current_version.extracted_payload_json if current_version else None
            preview_text = ""
            if isinstance(extracted_payload, dict):
                preview_text = str(extracted_payload.get("preview_text") or "").strip()
            searchable_blob = " ".join(
                part
                for part in (
                    document.title,
                    document.document_type.value,
                    document.status.value,
                    current_version.original_filename if current_version else "",
                    preview_text,
                    comment_excerpt,
                )
                if part
            ).lower()
            score = sum(searchable_blob.count(token) for token in tokens)
            if document.status in {"failed", "rejected"}:
                score += 1
            if not tokens:
                score += 1
            snippets.append(
                GroundedDocumentSnippet(
                    document_id=document.id,
                    document_title=document.title,
                    document_type=document.document_type.value,
                    document_status=document.status.value,
                    document_version_id=current_version.id if current_version else None,
                    original_filename=(
                        current_version.original_filename if current_version else None
                    ),
                    excerpt=(
                        preview_text
                        or "No extracted preview is available yet for this document."
                    ),
                    score=score,
                )
            )

        snippets.sort(
            key=lambda snippet: (
                snippet.score,
                1 if snippet.document_status in {"failed", "rejected"} else 0,
            ),
            reverse=True,
        )
        top_snippets = [snippet for snippet in snippets if snippet.score > 0][:3]
        return top_snippets or snippets[:3]

    def _recent_comment_excerpt(self, *, case: Case) -> str:
        latest_comment = self.session.scalar(
            select(CaseComment.body)
            .where(
                CaseComment.case_id == case.id,
                CaseComment.organization_id == case.organization_id,
            )
            .order_by(CaseComment.created_at.desc())
            .limit(1)
        )
        return latest_comment or ""

    def _build_grounded_answer(
        self,
        *,
        case: Case,
        question: str,
        prompt_mode: AssistantPromptMode,
        snippets: list[GroundedDocumentSnippet],
    ) -> str:
        status_line = (
            f'Case "{case.title}" is currently {case.status.value.replace("_", " ")} '
            f"with {case.priority.value.replace('_', ' ')} priority."
        )
        if case.due_date is not None:
            status_line += f" Due date: {case.due_date.astimezone(UTC).date().isoformat()}."

        if snippets:
            evidence_lines = "\n".join(
                f"- {snippet.document_title} ({snippet.original_filename or 'no filename'})"
                f": {snippet.excerpt[:180]}"
                for snippet in snippets
            )
            evidence_block = f"Grounded evidence reviewed:\n{evidence_lines}"
        else:
            evidence_block = (
                "Grounded evidence reviewed:\n"
                "- No documents are attached to this case yet, so the answer is limited."
            )

        risks = []
        if not snippets:
            risks.append("No documents are attached, so the case cannot be fully assessed.")
        if any(snippet.document_status in {"failed", "rejected"} for snippet in snippets):
            risks.append("At least one cited document is failed or rejected and needs attention.")
        if case.archived_at is not None:
            risks.append("The case is archived, so new action may be restricted.")
        if not risks:
            risks.append("No obvious blocking signal is visible in the cited evidence.")

        recommendations = {
            AssistantPromptMode.GENERAL: [
                "Use the cited documents as the primary operator context.",
                "Verify whether any missing or stale documents should be refreshed.",
            ],
            AssistantPromptMode.CASE_SUMMARY: [
                "Confirm the case summary against the latest document versions before sharing it.",
                "Highlight anything still missing for completion.",
            ],
            AssistantPromptMode.REVIEW_ASSISTANT: [
                "Check whether the cited evidence is enough to approve the case or document.",
                "Flag missing evidence explicitly instead of assuming completion.",
            ],
            AssistantPromptMode.NEXT_ACTIONS: [
                "Prioritize the smallest operator action that reduces uncertainty.",
                "Use the latest evidence and due date to decide the next queue move.",
            ],
        }[prompt_mode]
        recommendation_block = "\n".join(f"- {item}" for item in recommendations)

        return (
            f"Question: {question.strip()}\n\n"
            f"{status_line}\n\n"
            f"{evidence_block}\n\n"
            "Risk signals:\n"
            + "\n".join(f"- {risk}" for risk in risks)
            + "\n\nRecommended next actions:\n"
            + recommendation_block
        )


def _extract_tokens(question: str) -> list[str]:
    unique_tokens: list[str] = []
    for token in _TOKEN_PATTERN.findall(question.lower()):
        if token not in unique_tokens:
            unique_tokens.append(token)
    return unique_tokens[:8]


def _snippet_to_json(snippet: GroundedDocumentSnippet) -> dict[str, object]:
    return {
        "document_id": str(snippet.document_id),
        "document_title": snippet.document_title,
        "document_type": snippet.document_type,
        "document_status": snippet.document_status,
        "document_version_id": (
            str(snippet.document_version_id) if snippet.document_version_id is not None else None
        ),
        "original_filename": snippet.original_filename,
        "excerpt": snippet.excerpt[:500],
        "score": snippet.score,
    }
