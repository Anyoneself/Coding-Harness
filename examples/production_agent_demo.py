#!/usr/bin/env python3
"""Example CLI for the local production-oriented Agent mechanisms."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor

from application.services.evaluation import DEFAULT_EVALUATION_CASES, EvaluationSuite
from application.services.local_agent import AgentService


def run_request(service: AgentService, args: argparse.Namespace) -> None:
    """演示一个请求从进入服务到返回答案的完整链路。"""

    # 调用统一服务入口，内部会执行鉴权、理解、澄清、检索、审计和持久化。
    state = service.handle(
        user=args.user,
        role=args.role,
        request=args.request,
        session_id=args.session,
    )
    # 输出最终答案，模拟真实 API 返回给用户的内容。
    print("=== 最终回答 ===")
    print(state["answer"])
    # 输出关键 State，便于面试时解释为什么不能只保存 messages。
    print("\n=== 结构化状态摘要 ===")
    summary = {
        "request_id": state["request_id"],
        "session_version": state["persisted_session_version"],
        "intents": state["intents"],
        "entities": state["entities"],
        "status": state["status"],
        "termination_reason": state["termination_reason"],
        "knowledge_version": state.get("knowledge_version"),
        "step_count": state["step_count"],
        "sources": state.get("audit", {}).get("sources", []),
        "security_flags": state.get("audit", {}).get("security_flags", []),
        "tool_results": state.get("tool_results", []),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # 输出每个阶段的状态和耗时，用于可观测性和低分归因。
    print("\n=== Trace ===")
    for event in state["trace"]:
        if event["status"] != "started":
            print(f"{event['stage']:<28} {event['status']:<10} {event.get('duration_ms', 0):>8} ms")


def run_concurrency_demo(service: AgentService) -> None:
    """演示同一会话的并发请求如何通过乐观锁保持一致。"""

    request = "请检索项目规划模板"

    def invoke(index: int):
        # 两个线程模拟上游把同一个请求重复投递到 Agent 服务。
        return service.handle(
            user="concurrent-user",
            role="standard",
            request=request,
            session_id="same-session",
            request_id="duplicate-delivery-request",
            conflict_retries=2,
        )

    # 两个请求并发执行，SessionStore 会阻止旧版本覆盖新版本。
    with ThreadPoolExecutor(max_workers=2) as executor:
        states = list(executor.map(invoke, range(2)))

    # 预期：会话版本分别为 1、2，且不会发生旧版本覆盖新版本。
    print("=== 并发会话结果 ===")
    print(
        json.dumps(
            [
                {
                    "delivery": index,
                    "request_id": state["request_id"],
                    "session_version": state["persisted_session_version"],
                    "status": state["status"],
                }
                for index, state in enumerate(states)
            ],
            ensure_ascii=False,
            indent=2,
        )
    )


def run_evaluation(service: AgentService, split: str) -> None:
    """运行指定数据集，并展示每个阶段的评分和故障位置。"""

    suite = EvaluationSuite(DEFAULT_EVALUATION_CASES)
    results = suite.run(service, split)
    print(f"=== Evaluation: {split} ===")
    for result in results:
        print(
            json.dumps(
                {
                    "case_id": result.case_id,
                    "total_score": result.total_score,
                    "stage_scores": result.stage_scores,
                    "failure_stage": result.failure_stage,
                },
                ensure_ascii=False,
            )
        )


def main() -> None:
    # CLI 提供单次请求、并发场景和评估三种可独立演示的入口。
    parser = argparse.ArgumentParser(description="生产化 Agent 机制 Demo")
    subparsers = parser.add_subparsers(dest="command")

    request_parser = subparsers.add_parser("run", help="执行一次完整 Agent 请求")
    request_parser.add_argument("--user", default="alice")
    request_parser.add_argument(
        "--role",
        default="standard",
    )
    request_parser.add_argument("--session", default="demo-session")
    request_parser.add_argument(
        "--request",
        default="请分析这份资料并给出可验证的结论",
    )

    subparsers.add_parser("concurrency", help="演示会话乐观锁和工具幂等")
    eval_parser = subparsers.add_parser("eval", help="运行分阶段评估")
    eval_parser.add_argument(
        "--split",
        choices=("dev", "regression", "holdout"),
        default="regression",
    )

    args = parser.parse_args()
    service = AgentService()
    if args.command == "concurrency":
        run_concurrency_demo(service)
    elif args.command == "eval":
        run_evaluation(service, args.split)
    else:
        if args.command is None:
            args.user = "alice"
            args.role = "standard"
            args.session = "demo-session"
            args.request = "请分析这份资料并给出可验证的结论"
        run_request(service, args)


if __name__ == "__main__":
    main()
