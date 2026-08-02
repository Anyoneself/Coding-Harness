#!/usr/bin/env python3
"""Example LangGraph workflow for a role-aware investment research agent."""

from __future__ import annotations

import argparse
import json
from typing import Any, TypedDict

try:
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:
    raise SystemExit(
        "缺少 LangGraph 依赖，请先执行：python3 -m pip install -r requirements.txt"
    ) from exc


class ResearchState(TypedDict, total=False):
    # LangGraph 在各节点之间传递的共享状态。
    # 每个节点只返回自己新增或修改的字段，框架会自动合并状态。
    user: str
    role: str
    request: str
    allowed_domains: list[str]
    route: str
    retrieved: list[dict[str, Any]]
    specialist_result: dict[str, Any]
    audit: dict[str, Any]
    answer: str
    trace: list[str]


ROLE_PROFILES: dict[str, dict[str, Any]] = {
    # 不同角色拥有不同的知识域访问权限。
    # 真实项目中这里还可以继续配置提示词、工具白名单和文件目录权限。
    "investment": {"label": "投研", "allowed_domains": ["行业研究", "公司研究", "交易执行"]},
    "ir": {"label": "IR", "allowed_domains": ["公司研究", "公司运营"]},
    "operations": {"label": "中后台", "allowed_domains": ["公司运营"]},
}

# 这里用本地列表模拟 Qdrant 返回的知识片段。
# 接入真实系统时，可以替换为 Embedding + Qdrant + 思源原文回读流程。
KNOWLEDGE_BASE = [
    {
        "id": "industry-001",
        "domain": "行业研究",
        "title": "东南亚高层建筑行业观察",
        "content": "印尼核心城市的高层建筑供给主要集中在雅加达、泗水、万丹等区域，适合结合官方建筑库和公开建筑数据进行交叉核验。",
        "keywords": ["印尼", "城市", "高层", "建筑", "行业", "调研"],
        "source": "research/indonesia-building.md",
    },
    {
        "id": "company-001",
        "domain": "公司研究",
        "title": "公司公告核验规范",
        "content": "公司研究结论应区分公告事实、第三方数据和分析判断；涉及核心指标时至少保留一个可回溯来源。",
        "keywords": ["公司", "公告", "来源", "核验", "指标"],
        "source": "research/company-verification.md",
    },
    {
        "id": "trade-001",
        "domain": "交易执行",
        "title": "交易执行前检查清单",
        "content": "交易执行前需检查标的、市场、数量、价格、时间窗口和审批状态，Agent 只允许生成检查结果，不直接提交订单。",
        "keywords": ["交易", "执行", "标的", "审批", "订单"],
        "source": "trading/pre-trade-checklist.md",
    },
    {
        "id": "ops-001",
        "domain": "公司运营",
        "title": "财务文件处理规范",
        "content": "财务角色可以读取授权目录内的 PDF，并输出结构化摘要；未经授权的路径和写入类操作必须拒绝。",
        "keywords": ["财务", "PDF", "文件", "权限", "摘要"],
        "source": "operations/finance-file-policy.md",
    },
]


def add_trace(state: ResearchState, message: str) -> list[str]:
    # 保存可观察的执行轨迹，方便调试和解释 Agent 的执行过程。
    return [*state.get("trace", []), message]


def auth_node(state: ResearchState) -> dict[str, Any]:
    # 节点一：根据请求中的角色加载角色 Profile，并建立知识权限边界。
    profile = ROLE_PROFILES.get(state["role"])
    if profile is None:
        raise PermissionError(f"未知角色：{state['role']}")
    return {
        "allowed_domains": profile["allowed_domains"],
        "trace": add_trace(
            state,
            f"鉴权通过：{state['user']} -> {profile['label']}，知识权限={profile['allowed_domains']}",
        ),
    }


def route_node(state: ResearchState) -> dict[str, Any]:
    # 节点二：用简单规则模拟主 Agent 的任务分类。
    # 真实场景可以替换为 LLM Router 或更复杂的意图识别器。
    text = state["request"]
    if any(word in text for word in ("建筑", "行业", "市场", "城市", "调研")):
        route = "industry"
    elif any(word in text for word in ("交易", "订单", "下单", "审批")):
        route = "trade"
    elif any(word in text for word in ("PDF", "财务", "文件", "运营")):
        route = "operations"
    else:
        route = "company"
    return {"route": route, "trace": add_trace(state, f"任务路由：{route}_specialist")}


def retrieve_node(state: ResearchState) -> dict[str, Any]:
    # 节点三：先执行 ACL 过滤，再做关键词匹配。
    # 关键点是权限过滤发生在检索阶段，避免召回用户无权访问的内容。
    query = state["request"].lower()
    allowed = set(state["allowed_domains"])
    candidates = []
    for item in KNOWLEDGE_BASE:
        if item["domain"] not in allowed:
            continue
        score = sum(keyword.lower() in query for keyword in item["keywords"])
        if score:
            candidates.append((score, item))

    hits = [
        {
            "id": item["id"],
            "domain": item["domain"],
            "title": item["title"],
            "content": item["content"],
            "source": item["source"],
            "score": score,
        }
        for score, item in sorted(candidates, key=lambda pair: pair[0], reverse=True)[:3]
    ]
    return {
        "retrieved": hits,
        "trace": add_trace(state, f"检索完成：命中 {len(hits)} 条，已应用角色 ACL"),
    }


def industry_specialist(state: ResearchState) -> dict[str, Any]:
    # 专业节点：行业研究 Agent。
    # 当前返回固定结果，用于展示编排；后续可接入真实 LLM。
    return {
        "specialist_result": {
            "agent": "industry_specialist",
            "summary": "建议对印尼目标城市的建筑数据进行多源交叉核验，再输出城市级覆盖和重点标的清单。",
            "next_step": "补充官方建筑库、Google Open Buildings 和 CTBUH 数据后生成地图与报告。",
        },
        "trace": add_trace(state, "行业研究 Agent 完成结构化分析"),
    }


def trade_specialist(state: ResearchState) -> dict[str, Any]:
    # 专业节点：交易执行 Agent。
    # Demo 明确不直接下单，只生成交易前检查结果。
    return {
        "specialist_result": {
            "agent": "trade_specialist",
            "summary": "已生成交易前检查项，当前流程不会直接提交订单。",
            "next_step": "补齐标的、数量、价格、时间窗口和审批状态后交由人工确认。",
        },
        "trace": add_trace(state, "交易执行 Agent 完成安全检查"),
    }


def operations_specialist(state: ResearchState) -> dict[str, Any]:
    # 专业节点：运营和文件处理 Agent。
    return {
        "specialist_result": {
            "agent": "operations_specialist",
            "summary": "可以对授权目录内的财务 PDF 做结构化摘要。",
            "next_step": "请提供授权文件路径；系统会拒绝越权路径和写入类动作。",
        },
        "trace": add_trace(state, "运营 Agent 完成文件处理建议"),
    }


def company_specialist(state: ResearchState) -> dict[str, Any]:
    # 专业节点：公司研究 Agent。
    return {
        "specialist_result": {
            "agent": "company_specialist",
            "summary": "公司研究结论将区分公告事实、第三方数据和分析判断。",
            "next_step": "补充公司名称或公告主题后继续检索和来源核验。",
        },
        "trace": add_trace(state, "公司研究 Agent 完成来源规范检查"),
    }


def audit_node(state: ResearchState) -> dict[str, Any]:
    # 节点四：对检索结果做二次权限审计，并记录引用来源。
    # 生产环境还可以在这里校验工具调用、敏感信息和事实依据。
    used_domains = {item["domain"] for item in state.get("retrieved", [])}
    passed = used_domains.issubset(set(state["allowed_domains"]))
    audit = {
        "passed": passed,
        "grounded_sources": [item["source"] for item in state.get("retrieved", [])],
        "permission_check": "passed" if passed else "blocked",
    }
    return {
        "audit": audit,
        "trace": add_trace(
            state,
            f"审计完成：权限={'通过' if passed else '拦截'}，引用来源={len(audit['grounded_sources'])}",
        ),
    }


def summarize_node(state: ResearchState) -> dict[str, Any]:
    # 节点五：主 Agent 汇总专业 Agent 结果和审计结果，生成最终回复。
    result = state["specialist_result"]
    sources = state["audit"]["grounded_sources"]
    answer = (
        f"【{result['agent']}】\n"
        f"结论：{result['summary']}\n"
        f"下一步：{result['next_step']}\n"
        f"引用来源：{', '.join(sources) if sources else '暂无命中'}\n"
        f"权限审计：{'通过' if state['audit']['passed'] else '拦截'}"
    )
    return {"answer": answer, "trace": add_trace(state, "主 Agent 汇总结果并返回")}


def choose_specialist(state: ResearchState) -> str:
    # 条件路由函数：返回下一个节点名称。
    return f"{state['route']}_specialist"


def build_graph():
    # 创建 LangGraph 状态图。
    graph = StateGraph(ResearchState)
    for name, node in {
        "auth": auth_node,
        "route": route_node,
        "retrieve": retrieve_node,
        "industry_specialist": industry_specialist,
        "trade_specialist": trade_specialist,
        "operations_specialist": operations_specialist,
        "company_specialist": company_specialist,
        "audit": audit_node,
        "summarize": summarize_node,
    }.items():
        graph.add_node(name, node)

    graph.add_edge(START, "auth")
    graph.add_edge("auth", "route")
    graph.add_edge("route", "retrieve")
    # 根据 route 动态选择一个专业 Agent。
    graph.add_conditional_edges(
        "retrieve",
        choose_specialist,
        {
            "industry_specialist": "industry_specialist",
            "trade_specialist": "trade_specialist",
            "operations_specialist": "operations_specialist",
            "company_specialist": "company_specialist",
        },
    )
    for specialist in (
        "industry_specialist",
        "trade_specialist",
        "operations_specialist",
        "company_specialist",
    ):
        graph.add_edge(specialist, "audit")
    graph.add_edge("audit", "summarize")
    graph.add_edge("summarize", END)

    # MemorySaver 用于保存线程状态，支持后续扩展中断恢复和多轮任务。
    # 生产环境可以替换为数据库或 LangGraph 的持久化 Checkpointer。
    return graph.compile(checkpointer=MemorySaver())


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph 投研多角色 Agent 本地 Demo")
    parser.add_argument("--role", choices=ROLE_PROFILES, default="investment")
    parser.add_argument("--user", default="alice")
    parser.add_argument("--request", default="请调研印尼12城高层建筑行业，并说明下一步如何核验数据")
    args = parser.parse_args()

    # thread_id 用来标识一条独立任务线程，也是 Checkpointer 的索引。
    result = build_graph().invoke(
        {"user": args.user, "role": args.role, "request": args.request, "trace": []},
        config={"configurable": {"thread_id": f"demo-{args.user}"}},
    )

    print("\n=== LangGraph 投研 Agent Demo ===")
    print(f"用户：{args.user} | 角色：{args.role}")
    print(f"请求：{args.request}\n")
    print("执行轨迹：")
    for index, step in enumerate(result["trace"], 1):
        print(f"{index}. {step}")
    print("\n最终结果：")
    print(result["answer"])
    print("\n最终状态（便于观察 LangGraph State）：")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
