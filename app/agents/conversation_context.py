"""
Conversation Context Manager

Preserves conversation state across multiple turns,
allowing follow-up queries to reference previous results and context.
"""

import logging
import threading
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ConversationMessage:
    """Represents a single message in conversation history."""

    def __init__(
        self,
        role: str,  # "user" or "assistant"
        content: str,
        query_result: Optional[Dict[str, Any]] = None,
    ):
        self.id = str(uuid.uuid4())
        self.role = role
        self.content = content
        self.query_result = query_result
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "query_result": self.query_result,
            "timestamp": self.timestamp.isoformat(),
        }


class ConversationContext:
    """Manages conversation state and history."""

    def __init__(
        self,
        conversation_id: Optional[str] = None,
        max_history: int = 50,
        max_age_minutes: int = 60,
    ):
        """Initialize conversation context.

        Args:
            conversation_id: Unique ID for conversation (auto-generated if None)
            max_history: Maximum messages to keep in memory
            max_age_minutes: Maximum age of conversation in minutes
        """
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.messages: List[ConversationMessage] = []
        self.max_history = max_history
        self.max_age_minutes = max_age_minutes
        self.created_at = datetime.utcnow()
        self.last_accessed = datetime.utcnow()

        # Context variables for reference in follow-up queries
        self.context = {
            "last_domain": None,
            "last_views": [],
            "last_result_count": 0,
            "session_variables": {},
        }

        logger.debug(f"Created conversation context: {self.conversation_id}")

    def add_message(
        self,
        role: str,
        content: str,
        query_result: Optional[Dict[str, Any]] = None,
    ) -> ConversationMessage:
        """Add message to conversation.

        Args:
            role: "user" or "assistant"
            content: Message content
            query_result: Optional query result metadata

        Returns:
            Added message
        """
        message = ConversationMessage(role, content, query_result)
        self.messages.append(message)
        self.last_accessed = datetime.utcnow()

        # Trim history if needed
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]

        logger.debug(
            f"Added {role} message to conversation {self.conversation_id}"
        )
        return message

    def add_user_message(self, content: str) -> ConversationMessage:
        """Add user message."""
        return self.add_message("user", content)

    def add_assistant_message(
        self,
        content: str,
        query_result: Optional[Dict[str, Any]] = None,
    ) -> ConversationMessage:
        """Add assistant message with optional query result."""
        return self.add_message("assistant", content, query_result)

    def get_message_history(
        self,
        limit: Optional[int] = None,
        include_results: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get conversation message history.

        Args:
            limit: Maximum number of recent messages to return
            include_results: Whether to include query results

        Returns:
            List of message dictionaries
        """
        messages = self.messages
        if limit:
            messages = messages[-limit:]

        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                **({"query_result": m.query_result} if include_results else {}),
                "timestamp": m.timestamp.isoformat(),
            }
            for m in messages
        ]

    def get_context_summary(self) -> str:
        """Get natural language summary of conversation context for LLM prompts.

        Includes the actual text of recent user queries so the LLM can resolve
        pronoun references like "the same", "that region", or "just the West".

        Returns:
            Pipe-separated context string, or "No previous context." if empty.
        """
        if not self.messages:
            return "No previous context."

        summary_parts = []

        # Structured metadata
        if self.context["last_domain"]:
            summary_parts.append(f"Domain: {self.context['last_domain']}")
        if self.context["last_views"]:
            summary_parts.append(f"Views: {', '.join(self.context['last_views'])}")
        if self.context["last_result_count"]:
            summary_parts.append(f"Last result: {self.context['last_result_count']} rows")

        # Last two user messages with actual content so the LLM can resolve references
        recent_user = [m for m in self.messages if m.role == "user"][-2:]
        for m in recent_user:
            # Truncate to avoid prompt bloat
            text = m.content[:200]
            summary_parts.append(f'User asked: "{text}"')

        return " | ".join(summary_parts) if summary_parts else "No context available."

    def update_context(
        self,
        domain: Optional[str] = None,
        views: Optional[List[str]] = None,
        result_count: Optional[int] = None,
    ) -> None:
        """Update conversation context from query results.

        Args:
            domain: Domain that was queried
            views: Views that were accessed
            result_count: Number of rows returned
        """
        if domain:
            self.context["last_domain"] = domain
        if views:
            self.context["last_views"] = views
        if result_count is not None:
            self.context["last_result_count"] = result_count

        logger.debug(
            f"Updated context for conversation {self.conversation_id}"
        )

    def set_session_variable(self, key: str, value: Any) -> None:
        """Set a session variable for reference in future queries.

        Args:
            key: Variable name
            value: Variable value
        """
        self.context["session_variables"][key] = value
        logger.debug(f"Set session variable: {key}")

    def get_session_variable(self, key: str) -> Optional[Any]:
        """Get a session variable.

        Args:
            key: Variable name

        Returns:
            Variable value or None
        """
        return self.context["session_variables"].get(key)

    def is_expired(self) -> bool:
        """Check if conversation has expired.

        Returns:
            True if conversation is older than max_age_minutes
        """
        age = datetime.utcnow() - self.created_at
        return age > timedelta(minutes=self.max_age_minutes)

    def to_dict(self) -> Dict[str, Any]:
        """Convert conversation to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "conversation_id": self.conversation_id,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "message_count": len(self.messages),
            "messages": self.get_message_history(),
            "context": {
                "last_domain": self.context["last_domain"],
                "last_views": self.context["last_views"],
                "last_result_count": self.context["last_result_count"],
            }
        }


class ConversationManager:
    """Manages multiple conversation contexts.

    Thread-safe: all mutations of ``self.conversations`` are protected by
    a reentrant lock so concurrent FastAPI requests cannot corrupt state.
    """

    def __init__(self):
        self.conversations: Dict[str, ConversationContext] = {}
        self._lock = threading.Lock()

    def create_conversation(self) -> ConversationContext:
        """Create new conversation and register it."""
        conversation = ConversationContext()
        with self._lock:
            self.conversations[conversation.conversation_id] = conversation
        logger.info(f"Created conversation: {conversation.conversation_id}")
        return conversation

    def get_conversation(
        self,
        conversation_id: str,
    ) -> Optional[ConversationContext]:
        """Return an existing, non-expired conversation or None."""
        with self._lock:
            conversation = self.conversations.get(conversation_id)
            if conversation and conversation.is_expired():
                logger.warning(f"Conversation expired: {conversation_id}")
                del self.conversations[conversation_id]
                return None

        if conversation:
            conversation.last_accessed = datetime.utcnow()

        return conversation

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete conversation. Returns True if it existed."""
        with self._lock:
            if conversation_id in self.conversations:
                del self.conversations[conversation_id]
                logger.info(f"Deleted conversation: {conversation_id}")
                return True
        return False

    def cleanup_expired(self) -> int:
        """Remove expired conversations. Returns count removed."""
        with self._lock:
            expired_ids = [
                cid for cid, conv in self.conversations.items()
                if conv.is_expired()
            ]
            for cid in expired_ids:
                del self.conversations[cid]

        if expired_ids:
            logger.info(f"Cleaned up {len(expired_ids)} expired conversations")

        return len(expired_ids)

    def get_stats(self) -> Dict[str, Any]:
        """Return conversation manager statistics."""
        with self._lock:
            n = len(self.conversations)
            total_messages = sum(len(c.messages) for c in self.conversations.values())

        return {
            "active_conversations": n,
            "total_messages": total_messages,
            "avg_messages_per_conversation": total_messages // n if n else 0,
        }


# Global singleton instance
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """Get global conversation manager."""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager
