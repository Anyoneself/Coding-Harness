"""Coding-Harness 的 HTTP 与 SSE 接入层。"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from fastapi.responses import StreamingResponse

from ..domain.execution import (
    InvalidTurnTransitionError,
    ThreadNotFoundError,
    TurnNotFoundError,
    WorkspaceNotFoundError,
)
from ..repositories.execution import ActiveTurnExistsError, TurnLeaseConflictError
from ..schemas.http import (
    ApiKeyConfigurationRequest,
    ApiKeyConfigurationResponse,
    ThreadCreateRequest,
    ThreadResponse,
    TurnCreateRequest,
    TurnEventResponse,
    TurnResponse,
    WorkspaceCreateRequest,
    WorkspaceResponse,
)
from ..services.configuration import ApiKeyAlreadyConfiguredError, ApiKeyConfigurationService
from ..services.execution import HarnessRuntime


def encode_sse(event_type: str, payload: dict[str, object]) -> str:
    """把结构化 Agent 事件编码为标准 SSE 文本。"""
    event = {"type": event_type, **payload}
    return f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def create_api_router(
    harness_runtime: HarnessRuntime,
    configuration_service: ApiKeyConfigurationService,
) -> APIRouter:
    """创建仅负责协议转换的 API 路由集合。"""
    router = APIRouter(prefix="/api")

    @router.get("/config")
    def get_config() -> dict[str, object]:
        """返回前端可以读取的 Harness 配置。"""
        return configuration_service.get_public_config()

    @router.post("/config/api-key", response_model=ApiKeyConfigurationResponse)
    def configure_api_key(
        payload: ApiKeyConfigurationRequest,
        request: Request,
    ) -> ApiKeyConfigurationResponse:
        """提交首次 API Key 配置并映射重复配置冲突。"""
        if not _is_local_request(request):
            raise HTTPException(status_code=403, detail="仅允许在本机完成 API Key 配置")
        try:
            ready = configuration_service.configure_api_key(
                payload.api_key.get_secret_value(),
            )
        except ApiKeyAlreadyConfiguredError as exc:
            raise HTTPException(status_code=409, detail="API Key 已完成配置") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="API Key 格式无效") from exc
        return ApiKeyConfigurationResponse(ok=True, ready=ready)

    @router.get("/health")
    def health() -> dict[str, bool]:
        """返回进程健康状态和模型配置状态。"""
        return {"ok": True, "model_ready": harness_runtime.model_ready}

    _register_execution_routes(router, harness_runtime)

    return router


def _is_local_request(request: Request) -> bool:
    """仅允许回环地址和测试客户端调用本机敏感配置入口。"""
    host = request.client.host if request.client is not None else ""
    if host == "testclient":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def _register_execution_routes(router: APIRouter, runtime: HarnessRuntime) -> None:
    """注册只负责 Schema、状态码和错误映射的 Harness 资源路由。"""

    @router.post(
        "/workspaces",
        response_model=WorkspaceResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_workspace(payload: WorkspaceCreateRequest) -> WorkspaceResponse:
        """创建工作区资源并返回规范化后的边界。"""
        workspace = runtime.thread_service.create_workspace(
            payload.root_path,
            payload.permission_profile,
        )
        return WorkspaceResponse.model_validate(workspace)

    @router.post(
        "/workspaces/{workspace_id}/threads",
        response_model=ThreadResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_thread(
        workspace_id: Annotated[str, Path(min_length=1, max_length=128)],
        payload: ThreadCreateRequest,
    ) -> ThreadResponse:
        """在指定 Workspace 下创建任务线程。"""
        try:
            thread = runtime.thread_service.create_thread(workspace_id, payload.title)
        except WorkspaceNotFoundError as exc:
            raise HTTPException(status_code=404, detail="workspace not found") from exc
        return ThreadResponse.model_validate(thread)

    @router.post(
        "/threads/{thread_id}/turns",
        response_model=TurnResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_turn(
        thread_id: Annotated[str, Path(min_length=1, max_length=128)],
        payload: TurnCreateRequest,
    ) -> TurnResponse:
        """持久化 Turn 后立即返回，由 Scheduler 在后台执行。"""
        try:
            budget = payload.budget.to_domain() if payload.budget is not None else None
            turn = runtime.command_service.create_turn(thread_id, payload.prompt, budget=budget)
        except ThreadNotFoundError as exc:
            raise HTTPException(status_code=404, detail="thread not found") from exc
        except ActiveTurnExistsError as exc:
            raise HTTPException(status_code=409, detail="thread already has an active turn") from exc
        return TurnResponse.model_validate(turn)

    @router.get("/turns/{turn_id}", response_model=TurnResponse)
    def get_turn(
        turn_id: Annotated[str, Path(min_length=1, max_length=128)],
    ) -> TurnResponse:
        """返回 Turn 当前持久化状态。"""
        try:
            turn = runtime.query_service.get_turn(turn_id)
        except TurnNotFoundError as exc:
            raise HTTPException(status_code=404, detail="turn not found") from exc
        return TurnResponse.model_validate(turn)

    @router.get("/turns/{turn_id}/events", response_model=list[TurnEventResponse])
    def list_turn_events(
        turn_id: Annotated[str, Path(min_length=1, max_length=128)],
        after_sequence: Annotated[int, Query(ge=0)] = 0,
    ) -> list[TurnEventResponse]:
        """按数据库序号重放游标之后的公开 Turn 事件。"""
        try:
            runtime.query_service.get_turn(turn_id)
            events = runtime.query_service.list_events(
                turn_id,
                after_sequence=after_sequence,
            )
        except TurnNotFoundError as exc:
            raise HTTPException(status_code=404, detail="turn not found") from exc
        return [TurnEventResponse.model_validate(event) for event in events]

    @router.get("/turns/{turn_id}/events/stream")
    def stream_turn_events(
        turn_id: Annotated[str, Path(min_length=1, max_length=128)],
        after_sequence: Annotated[int, Query(ge=0)] = 0,
    ) -> StreamingResponse:
        """先重放数据库事件，再使用本地通知降低后续查询延迟。"""
        try:
            runtime.query_service.get_turn(turn_id)
        except TurnNotFoundError as exc:
            raise HTTPException(status_code=404, detail="turn not found") from exc

        def generate_events() -> Iterator[str]:
            """持续以数据库为事实源发送事件，终态后结束连接。"""
            cursor = after_sequence
            while True:
                events = runtime.query_service.list_events(turn_id, after_sequence=cursor)
                for event in events:
                    cursor = event.sequence
                    payload = TurnEventResponse.model_validate(event).model_dump(mode="json")
                    yield f"id: {event.sequence}\n{encode_sse(event.event_type, payload)}"
                turn = runtime.query_service.get_turn(turn_id)
                if turn.status.value in {"completed", "failed", "interrupted", "cancelled"}:
                    return
                runtime.notifier.wait_for_event(turn_id, cursor, timeout=1.0)

        return StreamingResponse(
            generate_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/turns/{turn_id}/interrupt", response_model=TurnResponse)
    def interrupt_turn(
        turn_id: Annotated[str, Path(min_length=1, max_length=128)],
    ) -> TurnResponse:
        """记录显式中断请求，不依赖 SSE 连接状态。"""
        try:
            turn = runtime.command_service.interrupt_turn(turn_id)
        except TurnNotFoundError as exc:
            raise HTTPException(status_code=404, detail="turn not found") from exc
        return TurnResponse.model_validate(turn)

    @router.post("/turns/{turn_id}/resume", response_model=TurnResponse)
    def resume_turn(
        turn_id: Annotated[str, Path(min_length=1, max_length=128)],
    ) -> TurnResponse:
        """由用户主动把 interrupted Turn 重新排队。"""
        try:
            turn = runtime.command_service.resume_turn(turn_id)
        except TurnNotFoundError as exc:
            raise HTTPException(status_code=404, detail="turn not found") from exc
        except (InvalidTurnTransitionError, TurnLeaseConflictError) as exc:
            raise HTTPException(status_code=409, detail="turn cannot be resumed") from exc
        return TurnResponse.model_validate(turn)
