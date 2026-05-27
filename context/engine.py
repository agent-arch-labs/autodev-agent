from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import threading
import json
import logging

logger = logging.getLogger("autodev.context")


class MemoryEntry(BaseModel):
    key: str
    value: Any
    timestamp: datetime = Field(default_factory=datetime.now)
    tags: List[str] = Field(default_factory=list)


class SharedMemory:
    def __init__(self):
        self._memory: Dict[str, MemoryEntry] = {}

    def set(self, key: str, value: Any, tags: Optional[List[str]] = None) -> None:
        self._memory[key] = MemoryEntry(key=key, value=value, tags=tags or [])

    def get(self, key: str) -> Optional[Any]:
        entry = self._memory.get(key)
        return entry.value if entry else None

    def get_all(self) -> Dict[str, Any]:
        return {k: v.value for k, v in self._memory.items()}

    def delete(self, key: str) -> bool:
        return self._memory.pop(key, None) is not None

    def search(self, tag: str) -> List[Any]:
        return [v.value for v in self._memory.values() if tag in v.tags]


class ContextEngine:
    def __init__(self, session_id: str, user_id: Optional[str] = None):
        self.session_id = session_id
        self.user_id = user_id
        self.shared_memory = SharedMemory()
        self.task_context: Dict[str, Any] = {}
        self.code_context: Dict[str, Any] = {}
        self.project_context: Dict[str, Any] = {}
        self.conversation_history: List[Dict[str, Any]] = []

    def set_task_context(self, key: str, value: Any) -> None:
        self.task_context[key] = value
        self.shared_memory.set(f"task.{key}", value, tags=["task"])

    def get_task_context(self, key: str) -> Optional[Any]:
        return self.task_context.get(key)

    def set_code_context(self, key: str, value: Any) -> None:
        self.code_context[key] = value
        self.shared_memory.set(f"code.{key}", value, tags=["code"])

    def get_code_context(self, key: str) -> Optional[Any]:
        return self.code_context.get(key)

    def set_project_context(self, key: str, value: Any) -> None:
        self.project_context[key] = value
        self.shared_memory.set(f"project.{key}", value, tags=["project"])

    def get_project_context(self, key: str) -> Optional[Any]:
        return self.project_context.get(key)

    def add_conversation(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self.conversation_history.append(entry)

    def get_conversation_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if limit:
            return self.conversation_history[-limit:]
        return self.conversation_history

    def clear(self) -> None:
        self.shared_memory = SharedMemory()
        self.task_context = {}
        self.code_context = {}
        self.project_context = {}
        self.conversation_history = []


class ContextManager:
    _instances: Dict[str, ContextEngine] = {}
    _session_user_map: Dict[str, str] = {}
    _lock = threading.Lock()

    @classmethod
    def get_context(cls, session_id: str, user_id: Optional[str] = None) -> ContextEngine:
        with cls._lock:
            if session_id not in cls._instances:
                resolved_user_id = user_id or session_id
                cls._instances[session_id] = ContextEngine(session_id, resolved_user_id)
                cls._session_user_map[session_id] = resolved_user_id
                logger.info(f"创建会话 {session_id}，归属用户 {resolved_user_id}")
            return cls._instances[session_id]

    @classmethod
    def delete_context(cls, session_id: str) -> None:
        with cls._lock:
            if session_id in cls._instances:
                del cls._instances[session_id]
                logger.info(f"删除会话 {session_id}")
            if session_id in cls._session_user_map:
                del cls._session_user_map[session_id]

    @classmethod
    def list_sessions(cls) -> List[str]:
        with cls._lock:
            return list(cls._instances.keys())

    @classmethod
    def get_user_id_for_session(cls, session_id: str) -> Optional[str]:
        with cls._lock:
            return cls._session_user_map.get(session_id)

    @classmethod
    def get_sessions_for_user(cls, user_id: str) -> List[str]:
        with cls._lock:
            return [sid for sid, uid in cls._session_user_map.items() if uid == user_id]