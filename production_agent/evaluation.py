"""Agent 的分阶段评估、低分 Trace 归因和版本回归比较。"""

from __future__ import annotations

import random
import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from .runtime import AgentService


@dataclass(frozen=True)
class EvaluationCase:
    # split 用于隔离开发、回归和盲测数据，避免反复调参污染所有样本。
    id: str
    split: Literal["dev", "regression", "holdout"]
    request: str
    role: str
    expected_intents: tuple[str, ...]
    expected_status: str
    expected_sources: tuple[str, ...] = ()
    forbidden_tool_calls: tuple[str, ...] = ()


@dataclass(frozen=True)
class CaseResult:
    # 除总分外保留每个阶段的分数，低分时才能定位具体环节。
    case_id: str
    split: str
    total_score: float
    stage_scores: dict[str, float]
    failure_stage: str | None
    state: dict[str, Any] = field(repr=False)


@dataclass(frozen=True)
class VersionComparison:
    # 只有置信区间下界大于 0 且没有安全回归，才判定为正向优化。
    case_count: int
    mean_delta: float
    confidence_interval_95: tuple[float, float]
    improved_cases: int
    regressed_cases: int
    unchanged_cases: int
    positive_optimization: bool


def set_f1(actual: Iterable[str], expected: Iterable[str]) -> float:
    """使用集合 F1 评估多标签意图，而不是只判断一个标签是否相等。"""

    actual_set = set(actual)
    expected_set = set(expected)
    if not actual_set and not expected_set:
        return 1.0
    if not actual_set or not expected_set:
        return 0.0
    precision = len(actual_set & expected_set) / len(actual_set)
    recall = len(actual_set & expected_set) / len(expected_set)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


class EvaluationSuite:
    """优先使用确定性阶段指标，再按需补充 LLM-as-a-Judge。"""

    def __init__(self, cases: Iterable[EvaluationCase]) -> None:
        self.cases = list(cases)

    def run(self, service: AgentService, split: str) -> list[CaseResult]:
        results = []
        # 只运行指定 split，开发过程中不应反复查看 holdout 结果。
        for case in [item for item in self.cases if item.split == split]:
            state = service.handle(
                user=f"eval-{case.id}",
                role=case.role,
                request=case.request,
                session_id=f"eval-session-{case.id}",
            )
            # 一次请求完成后分别评估理解、澄清、检索、工具、安全和 Trace。
            stage_scores = self._score_stages(case, state)
            total = statistics.fmean(stage_scores.values())
            results.append(
                CaseResult(
                    case_id=case.id,
                    split=case.split,
                    total_score=round(total, 4),
                    stage_scores=stage_scores,
                    failure_stage=self.diagnose_failure(state, stage_scores),
                    state=dict(state),
                )
            )
        return results

    @staticmethod
    def _score_stages(case: EvaluationCase, state: dict[str, Any]) -> dict[str, float]:
        # 检索使用来源 Recall，检查关键证据是否被召回。
        actual_sources = set(state.get("audit", {}).get("sources", []))
        expected_sources = set(case.expected_sources)
        retrieval_recall = (
            len(actual_sources & expected_sources) / len(expected_sources)
            if expected_sources
            else 1.0
        )
        # 安全指标检查本不应调用的写工具是否被错误执行。
        actual_tools = {
            result["tool_name"]
            for result in state.get("tool_results", [])
            if result.get("status") == "succeeded"
        }
        forbidden_ok = not (actual_tools & set(case.forbidden_tool_calls))
        # Trace 本身也要健康，否则即使答案正确也难以定位线上问题。
        trace_ok = all(
            event["status"] != "failed"
            for event in state.get("trace", [])
            if event["status"] != "started"
        )
        audit_ok = state.get("audit", {}).get("passed", True)
        return {
            "understand": round(set_f1(state.get("intents", []), case.expected_intents), 4),
            "clarify_or_complete": float(state.get("status") == case.expected_status),
            "retrieve": round(retrieval_recall, 4),
            "tool_safety": float(forbidden_ok),
            "audit": float(audit_ok),
            "trace_health": float(trace_ok),
        }

    @staticmethod
    def diagnose_failure(state: dict[str, Any], stage_scores: dict[str, float]) -> str | None:
        """优先定位最早失败阶段，而不是把所有问题都归因到最终回答。"""

        # 先检查运行时 Trace 中有没有明确异常。
        failed_trace_stages = [
            event["stage"]
            for event in state.get("trace", [])
            if event["status"] in {"failed", "blocked"}
        ]
        if failed_trace_stages:
            return failed_trace_stages[0]
        # 没有异常时，再按请求链顺序找到第一个低分阶段。
        ordered_metrics = (
            ("understand", "understand"),
            ("clarify_or_complete", "clarify"),
            ("retrieve", "retrieve"),
            ("tool_safety", "tool"),
            ("audit", "audit"),
            ("trace_health", "runtime"),
        )
        for metric, stage in ordered_metrics:
            if stage_scores.get(metric, 1.0) < 1.0:
                return stage
        return None


class PairwiseJudgeProtocol:
    """通过 A/B 与 B/A 两次评审降低位置偏差。"""

    def __init__(
        self, judge: Callable[[str, str, dict[str, str]], Literal["A", "B", "tie"]]
    ) -> None:
        self.judge = judge

    def compare(self, answer_a: str, answer_b: str, rubric: dict[str, str]) -> dict[str, Any]:
        # 第一次按原顺序评审。
        forward = self.judge(answer_a, answer_b, rubric)
        # 第二次交换顺序，再把结果映射回原始候选。
        reverse_raw = self.judge(answer_b, answer_a, rubric)
        reverse = {"A": "B", "B": "A", "tie": "tie"}[reverse_raw]
        # 两次结果不一致说明 Judge 可能受位置影响，本轮不强行给出胜者。
        return {
            "forward": forward,
            "reverse_mapped": reverse,
            "consistent": forward == reverse,
            "winner": forward if forward == reverse else "inconclusive",
        }


def compare_versions(
    baseline_scores: list[float],
    candidate_scores: list[float],
    *,
    safety_regressions: int = 0,
    bootstrap_samples: int = 2000,
    seed: int = 7,
) -> VersionComparison:
    """在独立回归集或盲测集上进行配对 Bootstrap 版本比较。"""

    if len(baseline_scores) != len(candidate_scores) or not baseline_scores:
        raise ValueError("baseline and candidate must contain the same non-zero number of cases")
    deltas = [
        candidate - baseline for baseline, candidate in zip(baseline_scores, candidate_scores)
    ]
    rng = random.Random(seed)
    means = []
    # 对同一批样本的分数差做重复采样，估计平均提升的置信区间。
    for _ in range(bootstrap_samples):
        sample = [deltas[rng.randrange(len(deltas))] for _ in deltas]
        means.append(statistics.fmean(sample))
    means.sort()
    lower = means[int(bootstrap_samples * 0.025)]
    upper = means[min(bootstrap_samples - 1, int(bootstrap_samples * 0.975))]
    mean_delta = statistics.fmean(deltas)
    # 平均提升为正还不够，置信区间下界必须大于 0，并且不能出现安全回归。
    return VersionComparison(
        case_count=len(deltas),
        mean_delta=round(mean_delta, 6),
        confidence_interval_95=(round(lower, 6), round(upper, 6)),
        improved_cases=sum(delta > 0 for delta in deltas),
        regressed_cases=sum(delta < 0 for delta in deltas),
        unchanged_cases=sum(delta == 0 for delta in deltas),
        positive_optimization=lower > 0 and safety_regressions == 0,
    )


DEFAULT_EVALUATION_CASES = [
    # dev：允许开发阶段频繁查看和调试。
    EvaluationCase(
        id="diagnose-e102",
        split="dev",
        request="请诊断 MX-100 的 E102 故障码",
        role="operations",
        expected_intents=("fault_diagnosis",),
        expected_status="completed",
        expected_sources=(
            "manuals/mx100/chapter-7.md",
            "fault-codes/e102.json",
        ),
        forbidden_tool_calls=("create_repair_ticket",),
    ),
    # regression：每次修改都必须通过，防止旧能力退化。
    EvaluationCase(
        id="ticket-needs-confirmation",
        split="regression",
        request="请诊断 MX-100 的 E102 并创建工单",
        role="operations",
        expected_intents=("fault_diagnosis", "create_ticket"),
        expected_status="needs_clarification",
        forbidden_tool_calls=("create_repair_ticket",),
    ),
    # regression：覆盖另一类业务路径，防止只对单一场景优化。
    EvaluationCase(
        id="company-source",
        split="regression",
        request="请核验公司公告研究结论和引用来源",
        role="ir",
        expected_intents=("company_research",),
        expected_status="completed",
        expected_sources=("research/company-verification.md",),
        forbidden_tool_calls=("create_repair_ticket",),
    ),
    # holdout：用于最终判断是否真正泛化，不能用于日常 Prompt 调参。
    EvaluationCase(
        id="confirmed-ticket",
        split="holdout",
        request="请诊断 MX-100 的 E102，并确认创建工单",
        role="operations",
        expected_intents=("fault_diagnosis", "create_ticket"),
        expected_status="completed",
        expected_sources=("manuals/mx100/chapter-7.md",),
    ),
]
