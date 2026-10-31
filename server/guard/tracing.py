"""Langfuse 트레이싱. 키가 없거나 전송에 실패해도 분석은 그대로 진행합니다.

통화 내용을 외부 관측 서비스에 쌓지 않도록 입력과 출력은 보내지 않고,
소요 시간, 모델, 토큰 수, 판정 라벨 같은 메타데이터만 기록합니다.
"""
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar

from opentelemetry import context as otel_context

log = logging.getLogger("guard.tracing")
_langfuse = None
_ready = False
# FastAPI가 자체로 만드는 스팬은 내보내지 않으므로, 그 스팬을 부모로 삼으면 트리가 끊어집니다.
# 그래서 부모 관계를 직접 들고 다닙니다. 스레드풀과 백그라운드 작업에도 함께 복사됩니다.
_current: ContextVar[tuple[str, str] | None] = ContextVar("guard_trace_parent", default=None)


class _NoOp:
    def update(self, **_):
        pass


def _client():
    global _langfuse, _ready
    if _ready:
        return _langfuse
    _ready = True
    public, secret = os.getenv("LANGFUSE_PUBLIC_KEY"), os.getenv("LANGFUSE_SECRET_KEY")
    if public and secret:
        try:
            from langfuse import Langfuse

            # 다른 라이브러리의 자동 계측이 통화 내용을 담아 보내지 않도록 우리가 만든 기록만 내보냅니다.
            _langfuse = Langfuse(
                public_key=public,
                secret_key=secret,
                base_url=os.getenv("LANGFUSE_BASE_URL") or None,
                should_export_span=lambda span: span.instrumentation_scope.name == "langfuse-sdk",
            )
        except Exception as exc:
            log.warning("Langfuse 시작 실패: %s", type(exc).__name__)
    return _langfuse


def update(observation, **fields) -> None:
    try:
        observation.update(**fields)
    except Exception as exc:
        log.warning("Langfuse 기록 실패: %s", type(exc).__name__)


@contextmanager
def observe(name: str, as_type: str = "span", **fields):
    client = _client()
    context = None
    token = None
    detached = None
    if client:
        try:
            parent = _current.get()
            if parent:
                fields["trace_context"] = {"trace_id": parent[0], "parent_span_id": parent[1]}
            else:
                # 새 트레이스의 맨 위가 되도록 FastAPI 스팬에서 떼어 냅니다.
                detached = otel_context.attach(otel_context.Context())
            context = client.start_as_current_observation(name=name, as_type=as_type, **fields)
            observation = context.__enter__()
            token = _current.set((observation.trace_id, observation.id))
        except Exception as exc:
            log.warning("Langfuse 기록 실패: %s", type(exc).__name__)
            context = None
    if context is None:
        if detached is not None:
            otel_context.detach(detached)
        yield _NoOp()
        return
    try:
        yield observation
    except Exception as exc:
        # 오류 메시지에 통화 내용이 섞일 수 있어 종류만 남깁니다.
        update(observation, level="ERROR", status_message=type(exc).__name__)
        raise
    finally:
        if token is not None:
            _current.reset(token)
        try:
            context.__exit__(None, None, None)
        except Exception as exc:
            log.warning("Langfuse 기록 실패: %s", type(exc).__name__)
        if detached is not None:
            otel_context.detach(detached)


@contextmanager
def trace(name: str, **fields):
    """한 작업의 하위 기록을 Langfuse에서 이름 있는 트레이스 하나로 묶습니다."""
    with observe(name, **fields) as root:
        attributes = None
        if _client():
            try:
                from langfuse import propagate_attributes

                attributes = propagate_attributes(trace_name=name)
                attributes.__enter__()
            except Exception as exc:
                attributes = None
                log.warning("Langfuse 기록 실패: %s", type(exc).__name__)
        try:
            yield root
        finally:
            if attributes:
                try:
                    attributes.__exit__(None, None, None)
                except Exception as exc:
                    log.warning("Langfuse 기록 실패: %s", type(exc).__name__)


def shutdown() -> None:
    if _langfuse:
        try:
            _langfuse.shutdown()
        except Exception as exc:
            log.warning("Langfuse 종료 실패: %s", type(exc).__name__)
