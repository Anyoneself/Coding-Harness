from __future__ import annotations

import threading
import unittest

from production_agent.evaluation import (
    DEFAULT_EVALUATION_CASES,
    EvaluationSuite,
    PairwiseJudgeProtocol,
    compare_versions,
)
from production_agent.retrieval import DEFAULT_DOCUMENTS, KnowledgeDocument, VersionedKnowledgeBase
from production_agent.runtime import (
    AgentService,
    ConcurrentUpdateError,
    ContextManager,
    ExecutionGuard,
    LoopDetectedError,
    SessionStore,
)
from production_agent.security import TraceRecorder


class AgentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentService()

    def test_multi_intent_write_requires_clarification(self) -> None:
        state = self.service.handle(
            user="alice",
            role="operations",
            request="请诊断 MX-100 的 E102 并创建工单",
            session_id="clarify-session",
        )
        self.assertEqual({"fault_diagnosis", "create_ticket"}, set(state["intents"]))
        self.assertEqual("needs_clarification", state["status"])
        self.assertEqual([], state["tool_results"])

    def test_confirmed_write_is_idempotent(self) -> None:
        request = "请诊断 MX-100 的 E102，并确认创建工单"
        first = self.service.handle(
            user="alice",
            role="operations",
            request=request,
            session_id="idempotent-session",
            request_id="same-upstream-request",
        )
        second = self.service.handle(
            user="alice",
            role="operations",
            request=request,
            session_id="idempotent-session",
            request_id="same-upstream-request",
        )
        self.assertEqual(
            first["tool_results"][0]["output"]["ticket_id"],
            second["tool_results"][0]["output"]["ticket_id"],
        )
        self.assertTrue(second["tool_results"][0]["replayed"])
        self.assertEqual(1, self.service.tools.created_ticket_count)

    def test_indirect_prompt_injection_is_flagged(self) -> None:
        state = self.service.handle(
            user="alice",
            role="operations",
            request="请诊断 MX-100 的 E102 故障码",
            session_id="security-session",
        )
        flags = set(state["audit"]["security_flags"])
        self.assertIn("ignore_instructions", flags)
        self.assertNotIn("API key", state["answer"])

    def test_trace_does_not_store_raw_user_identity(self) -> None:
        state = self.service.handle(
            user="alice@example.com",
            role="ir",
            request="请核验公司公告研究结论和引用来源",
            session_id="privacy-session",
        )
        serialized = str(state["trace"])
        self.assertNotIn("alice@example.com", serialized)
        self.assertIn("user_hash", serialized)

    def test_knowledge_version_prevents_stale_cache_hit(self) -> None:
        request = "请核验公司公告研究结论和引用来源"
        first = self.service.handle(
            user="alice",
            role="ir",
            request=request,
            session_id="cache-session-1",
        )
        cached = self.service.handle(
            user="alice",
            role="ir",
            request=request,
            session_id="cache-session-2",
        )
        self.assertEqual("cache_hit", cached["termination_reason"])

        documents = list(DEFAULT_DOCUMENTS) + [
            KnowledgeDocument(
                id="company-update",
                source_type="research",
                domain="公司研究",
                title="公司公告核验补充",
                content="新增公告版本必须记录发布日期与生效日期。",
                source="research/company-update.md",
                authority=1.0,
            )
        ]
        new_version = self.service.knowledge_base.replace_documents(documents)
        after_update = self.service.handle(
            user="alice",
            role="ir",
            request=request,
            session_id="cache-session-3",
        )
        self.assertEqual(first["knowledge_version"] + 1, new_version)
        self.assertEqual(new_version, after_update["knowledge_version"])
        self.assertNotEqual("cache_hit", after_update["termination_reason"])


class InfrastructureTests(unittest.TestCase):
    def test_optimistic_lock_rejects_stale_write(self) -> None:
        store = SessionStore()
        self.assertEqual(1, store.save("same-session", 0, {"value": 1}))
        with self.assertRaises(ConcurrentUpdateError):
            store.save("same-session", 0, {"value": 2})

    def test_concurrent_requests_preserve_state_versions(self) -> None:
        service = AgentService()
        barrier = threading.Barrier(2)
        original_load = service.sessions.load
        load_count = 0
        load_lock = threading.Lock()

        def synchronized_load(session_id: str):
            nonlocal load_count
            result = original_load(session_id)
            with load_lock:
                load_count += 1
                should_wait = load_count <= 2
            if should_wait:
                barrier.wait()
            return result

        service.sessions.load = synchronized_load  # type: ignore[method-assign]
        errors = []
        states = []

        def invoke(index: int) -> None:
            try:
                states.append(
                    service.handle(
                        user="alice",
                        role="operations",
                        request="请诊断 MX-100 的 E102 故障码",
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
        guard = ExecutionGuard(max_steps=10, max_repeats=2)
        guard.record("same-tool")
        guard.record("same-tool")
        with self.assertRaises(LoopDetectedError):
            guard.record("same-tool")

    def test_context_compaction_keeps_pinned_and_recent_messages(self) -> None:
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
        base = VersionedKnowledgeBase(DEFAULT_DOCUMENTS)
        _, before = base.search("MX-100 E102", {"设备维修"}, "MX-100")
        extra = [
            KnowledgeDocument(
                id=f"unrelated-{index}",
                source_type="research",
                domain="行业研究",
                title=f"无关行业资料 {index}",
                content="建筑市场与城市研究",
                source=f"research/{index}.md",
            )
            for index in range(200)
        ]
        base.replace_documents([*DEFAULT_DOCUMENTS, *extra])
        _, after = base.search("MX-100 E102", {"设备维修"}, "MX-100")
        self.assertGreater(after.total_documents, before.total_documents)
        self.assertEqual(before.candidate_documents, after.candidate_documents)

    def test_trace_recorder_redacts_sensitive_values(self) -> None:
        recorder = TraceRecorder("request", "session")
        with recorder.span("test", {"api_key": "secret", "email": "alice@example.com"}):
            pass
        serialized = str(recorder.to_dicts())
        self.assertNotIn("secret", serialized)
        self.assertNotIn("alice@example.com", serialized)


class EvaluationTests(unittest.TestCase):
    def test_regression_suite_scores_all_cases(self) -> None:
        results = EvaluationSuite(DEFAULT_EVALUATION_CASES).run(AgentService(), "regression")
        self.assertEqual(2, len(results))
        self.assertTrue(all(result.total_score == 1.0 for result in results))
        self.assertTrue(all(result.failure_stage is None for result in results))

    def test_pairwise_judge_detects_position_bias(self) -> None:
        def biased_judge(answer_a: str, answer_b: str, rubric: dict[str, str]):
            del answer_a, answer_b, rubric
            return "A"

        result = PairwiseJudgeProtocol(biased_judge).compare("A answer", "B answer", {})
        self.assertFalse(result["consistent"])
        self.assertEqual("inconclusive", result["winner"])

    def test_version_comparison_requires_positive_confidence_bound(self) -> None:
        comparison = compare_versions(
            [0.5, 0.6, 0.4, 0.7],
            [0.7, 0.8, 0.6, 0.9],
            bootstrap_samples=500,
        )
        self.assertTrue(comparison.positive_optimization)
        self.assertGreater(comparison.confidence_interval_95[0], 0)


if __name__ == "__main__":
    unittest.main()
