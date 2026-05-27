import pytest
from context import ContextEngine, ContextManager, SharedMemory, MemoryEntry


class TestSharedMemory:
    def test_set_and_get(self):
        memory = SharedMemory()

        memory.set("key1", "value1")
        assert memory.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        memory = SharedMemory()

        result = memory.get("nonexistent")
        assert result is None

    def test_delete(self):
        memory = SharedMemory()

        memory.set("key1", "value1")
        assert memory.get("key1") == "value1"

        result = memory.delete("key1")
        assert result is True
        assert memory.get("key1") is None

    def test_delete_nonexistent(self):
        memory = SharedMemory()

        result = memory.delete("nonexistent")
        assert result is False

    def test_get_all(self):
        memory = SharedMemory()

        memory.set("key1", "value1")
        memory.set("key2", "value2")

        all_data = memory.get_all()
        assert all_data == {"key1": "value1", "key2": "value2"}

    def test_search_by_tag(self):
        memory = SharedMemory()

        memory.set("key1", "value1", tags=["tag1", "tag2"])
        memory.set("key2", "value2", tags=["tag2", "tag3"])
        memory.set("key3", "value3", tags=["tag4"])

        results = memory.search("tag2")
        assert len(results) == 2
        assert "value1" in results
        assert "value2" in results


class TestMemoryEntry:
    def test_memory_entry_creation(self):
        entry = MemoryEntry(key="test_key", value="test_value")

        assert entry.key == "test_key"
        assert entry.value == "test_value"
        assert entry.timestamp is not None
        assert entry.tags == []

    def test_memory_entry_with_tags(self):
        entry = MemoryEntry(key="test_key", value="test_value", tags=["tag1", "tag2"])

        assert entry.tags == ["tag1", "tag2"]


class TestContextEngine:
    def test_task_context_operations(self):
        context = ContextEngine(session_id="test-session")

        context.set_task_context("task_key", "task_value")
        assert context.get_task_context("task_key") == "task_value"

    def test_code_context_operations(self):
        context = ContextEngine(session_id="test-session")

        context.set_code_context("code_key", "code_value")
        assert context.get_code_context("code_key") == "code_value"

    def test_project_context_operations(self):
        context = ContextEngine(session_id="test-session")

        context.set_project_context("project_key", "project_value")
        assert context.get_project_context("project_key") == "project_value"

    def test_conversation_operations(self):
        context = ContextEngine(session_id="test-session")

        context.add_conversation("user", "Hello world")
        context.add_conversation("assistant", "Hi there!")

        history = context.get_conversation_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello world"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Hi there!"

    def test_conversation_with_limit(self):
        context = ContextEngine(session_id="test-session")

        for i in range(10):
            context.add_conversation("user", f"Message {i}")

        history = context.get_conversation_history(limit=5)
        assert len(history) == 5

    def test_clear(self):
        context = ContextEngine(session_id="test-session")

        context.set_task_context("key", "value")
        context.set_code_context("key", "value")
        context.set_project_context("key", "value")
        context.add_conversation("user", "Hello")

        context.clear()

        assert context.get_task_context("key") is None
        assert context.get_code_context("key") is None
        assert context.get_project_context("key") is None
        assert context.get_conversation_history() == []


class TestContextManager:
    def test_get_context(self):
        session_id = "test-session-get"

        context1 = ContextManager.get_context(session_id)
        context2 = ContextManager.get_context(session_id)

        assert context1 is context2

    def test_delete_context(self):
        session_id = "test-session-delete"

        context = ContextManager.get_context(session_id)
        assert ContextManager.get_context(session_id) is context

        ContextManager.delete_context(session_id)

    def test_list_sessions(self):
        session1 = "test-session-list-1"
        session2 = "test-session-list-2"

        ContextManager.get_context(session1)
        ContextManager.get_context(session2)

        sessions = ContextManager.list_sessions()
        assert session1 in sessions
        assert session2 in sessions

        ContextManager.delete_context(session1)
        ContextManager.delete_context(session2)