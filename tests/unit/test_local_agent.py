from __future__ import annotations

import threading
import unittest
from typing import Any, Literal

from application.domain import ContextManager, ExecutionGuard, LoopDetectedError
from application.infrastructure import TraceRecorder
from application.repositories import ConcurrentUpdateError, SessionStore
from application.repositories.knowledge import (
    DEFAULT_DOCUMENTS,
    KnowledgeDocument,
    VersionedKnowledgeBase,
)
from application.services.evaluation import (
    DEFAULT_EVALUATION_CASES,
    EvaluationSuite,
    PairwiseJudgeProtocol,
    compare_versions,
)
from application.services.local_agent import AgentService


class AgentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        """为每个业务用例创建隔离的本地 Agent 服务。"""
        self.service = AgentService()

    def test_general_request_completes_without_domain_specific_fields(self) -> None:
        """验证通用问题不会因历史业务字段缺失而被限制。"""
        state = self.service.handle(
            user="alice",
            role="standard",
            request="请分析如何制定一个可验收的项目计划",
            session_id="clarify-session",
        )
        self.assertEqual({"analysis"}, set(state["intents"]))
        self.assertEqual("completed", state["status"])
        self.assertEqual([], state["tool_results"])

    def test_custom_role_has_same_general_knowledge_access(self) -> None:
        """验证自定义角色不会被历史业务角色白名单拒绝。"""
        request = "请检索项目规划模板"
        first = self.service.handle(
            user="alice",
            role="product-manager",
            request=request,
            session_id="idempotent-session",
            request_id="first-request",
        )
        second = self.service.handle(
            user="alice",
            role="researcher",
            request=request,
            session_id="separate-session",
            request_id="second-request",
        )
        self.assertEqual("completed", first["status"])
        self.assertEqual("completed", second["status"])

    def test_indirect_prompt_injection_is_flagged(self) -> None:
        """验证知识内容中的间接提示词注入会被标记和隔离。"""
        state = self.service.handle(
            user="alice",
            role="standard",
            request="请检索外部备注示例",
            session_id="security-session",
        )
        flags = set(state["audit"]["security_flags"])
        self.assertIn("ignore_instructions", flags)
        self.assertNotIn("API key", state["answer"])

    def test_trace_does_not_store_raw_user_identity(self) -> None:
        """验证 Trace 不保存用户原始身份信息。"""
        state = self.service.handle(
            user="alice@example.com",
            role="standard",
            request="请核验结论和引用来源",
            session_id="privacy-session",
        )
        serialized = str(state["trace"])
        self.assertNotIn("alice@example.com", serialized)
        self.assertIn("user_hash", serialized)

    def test_knowledge_version_prevents_stale_cache_hit(self) -> None:
        """验证知识版本更新后不会继续命中过期答案缓存。"""
        request = "请核验结论和引用来源"
        first = self.service.handle(
            user="alice",
            role="standard",
            request=request,
            session_id="cache-session-1",
        )
        cached = self.service.handle(
            user="alice",
            role="standard",
            request=request,
            session_id="cache-session-2",
        )
        self.assertEqual("cache_hit", cached["termination_reason"])

        documents = list(DEFAULT_DOCUMENTS) + [
            KnowledgeDocument(
                id="company-update",
                source_type="research",
                domain="通用资料",
                title="结论核验补充",
                content="新增公告版本必须记录发布日期与生效日期。",
                source="guides/conclusion-update.md",
                authority=1.0,
            )
        ]
        new_version = self.service.knowledge_base.replace_documents(documents)
        after_update = self.service.handle(
            user="alice",
            role="standard",
            request=request,
            session_id="cache-session-3",
        )
        self.assertEqual(first["knowledge_version"] + 1, new_version)
        self.assertEqual(new_version, after_update["knowledge_version"])
        self.assertNotEqual("cache_hit", after_update["termination_reason"])


class InfrastructureTests(unittest.TestCase):
    def test_optimistic_lock_rejects_stale_write(self) -> None:
        """验证会话仓储拒绝使用旧版本覆盖最新状态。"""
        store = SessionStore()
        self.assertEqual(1, store.save("same-session", 0, {"value": 1}))
        with self.assertRaises(ConcurrentUpdateError):
            store.save("same-session", 0, {"value": 2})

    def test_session_reset_keeps_audit_events(self) -> None:
        """验证清理对话上下文时保留已经记录的审计事件。"""
        store = SessionStore()
        store.save("audit-session", 0, {"messages": [{"role": "user", "content": "hi"}]})
        store.append_event(
            session_id="audit-session",
            request_id="request-1",
            sequence=1,
            event={"type": "started", "request_id": "request-1"},
        )

        store.clear_session_context("audit-session")

        self.assertEqual((0, {}), store.load("audit-session"))
        events = store.list_events("audit-session")
        self.assertEqual(1, len(events))
        self.assertEqual("started", events[0].event_type)

    def test_session_delete_removes_context_and_audit_events(self) -> None:
        """验证永久删除会话时同时清理上下文和全部审计事件。"""
        store = SessionStore()
        store.save("deleted-session", 0, {"messages": [{"role": "user", "content": "hi"}]})
        store.append_event(
            session_id="deleted-session",
            request_id="request-delete",
            sequence=1,
            event={"type": "started", "request_id": "request-delete"},
        )

        store.delete_session("deleted-session")

        self.assertEqual((0, {}), store.load("deleted-session"))
        self.assertEqual([], store.list_events("deleted-session"))

    def test_concurrent_requests_preserve_state_versions(self) -> None:
        """验证并发请求通过重试保留连续的会话版本。"""
        service = AgentService()
        barrier = threading.Barrier(2)
        original_load = service.sessions.load
        load_count = 0
        load_lock = threading.Lock()

        def synchronized_load(session_id: str) -> tuple[int, dict[str, Any]]:
            """同步前两次读取，使测试稳定触发乐观锁冲突。"""
            nonlocal load_count
            result = original_load(session_id)
            with load_lock:
                load_count += 1
                should_wait = load_count <= 2
            if should_wait:
                barrier.wait()
            return result

        service.sessions.load = synchronized_load  # type: ignore[method-assign]
        errors: list[Exception] = []
        states: list[dict[str, Any]] = []

        def invoke(index: int) -> None:
            """在线程中执行一次带冲突重试的请求。"""
            try:
                states.append(
                    service.handle(
                        user="alice",
                        role="standard",
                        request="请检索项目规划模板",
                        session_id="concurrent-session",
                        request_id=f"request-{index}",
                        conflict_retries=1,
                    )
                )
            except Exception as exc:  # pragma: no cover - assertion reports it
                errors.append(exc)

        threads = [threading.Thread(target=invoke, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        service.sessions.load = original_load  # type: ignore[method-assign]
        self.assertFalse(errors)
        self.assertEqual([1, 2], sorted(state["persisted_session_version"] for state in states))

    def test_loop_guard_stops_repeated_actions(self) -> None:
        """验证循环保护器阻止超过阈值的重复动作。"""
        guard = ExecutionGuard(max_steps=10, max_repeats=2)
        guard.record("same-tool")
        guard.record("same-tool")
        with self.assertRaises(LoopDetectedError):
            guard.record("same-tool")

    def test_context_compaction_keeps_pinned_and_recent_messages(self) -> None:
        """验证上下文压缩保留固定消息和最近消息。"""
        manager = ContextManager(recent_messages=2)
        messages = [
            {"role": "system", "content": "安全规则", "pinned": True},
            {"role": "user", "content": "第一轮"},
            {"role": "assistant", "content": "第一轮回答"},
            {"role": "user", "content": "第二轮"},
            {"role": "assistant", "content": "第二轮回答"},
        ]
        compacted, summary = manager.compact(messages)
        self.assertEqual("安全规则", compacted[0]["content"])
        self.assertEqual(3, len(compacted))
        self.assertIn("第一轮", summary)

    def test_candidate_set_is_bounded_by_inverted_index(self) -> None:
        """验证无关文档增长不会扩大倒排索引候选集合。"""
        base = VersionedKnowledgeBase(DEFAULT_DOCUMENTS)
        _, before = base.search("项目规划模板", None)
        extra = [
            KnowledgeDocument(
                id=f"unrelated-{index}",
                source_type="research",
                domain="通用资料",
                title=f"无关资料 {index}",
                content="无关主题的背景信息",
                source=f"research/{index}.md",
            )
            for index in range(200)
        ]
        base.replace_documents([*DEFAULT_DOCUMENTS, *extra])
        _, after = base.search("项目规划模板", None)
        self.assertGreater(after.total_documents, before.total_documents)
        self.assertEqual(before.candidate_documents, after.candidate_documents)

    def test_trace_recorder_redacts_sensitive_values(self) -> None:
        """验证 Trace 记录器递归清理密钥和邮箱。"""
        recorder = TraceRecorder("request", "session")
        with recorder.span("test", {"api_key": "secret", "email": "alice@example.com"}):
            pass
        serialized = str(recorder.to_dicts())
        self.assertNotIn("secret", serialized)
        self.assertNotIn("alice@example.com", serialized)


class EvaluationTests(unittest.TestCase):
    def test_regression_suite_scores_all_cases(self) -> None:
        """验证回归集全部案例均能得到满分阶段结果。"""
        results = EvaluationSuite(DEFAULT_EVALUATION_CASES).run(AgentService(), "regression")
        self.assertEqual(2, len(results))
        self.assertTrue(all(result.total_score == 1.0 for result in results))
        self.assertTrue(all(result.failure_stage is None for result in results))

    def test_pairwise_judge_detects_position_bias(self) -> None:
        """验证双向评审可以识别固定选择首位的位置偏差。"""

        def biased_judge(
            answer_a: str,
            answer_b: str,
            rubric: dict[str, str],
        ) -> Literal["A", "B", "tie"]:
            """模拟始终选择第一个候选答案的偏置评审器。"""
            del answer_a, answer_b, rubric
            return "A"

        result = PairwiseJudgeProtocol(biased_judge).compare("A answer", "B answer", {})
        self.assertFalse(result["consistent"])
        self.assertEqual("inconclusive", result["winner"])

    def test_version_comparison_requires_positive_confidence_bound(self) -> None:
        """验证版本提升需满足 Bootstrap 置信区间下界为正。"""
        comparison = compare_versions(
            [0.5, 0.6, 0.4, 0.7],
            [0.7, 0.8, 0.6, 0.9],
            bootstrap_samples=500,
        )
        self.assertTrue(comparison.positive_optimization)
        self.assertGreater(comparison.confidence_interval_95[0], 0)


if __name__ == "__main__":
    unittest.main()
