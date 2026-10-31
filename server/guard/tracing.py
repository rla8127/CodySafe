"""Langfuse 트레이싱. 키가 없거나 전송에 실패해도 분석은 그대로 진행합니다.

통화 내용을 외부 관측 서비스에 쌓지 않도록 입력과 출력은 보내지 않고,
소요 시간, 모델, 토큰 수, 판정 라벨 같은 메타데이터만 기록합니다.
"""
import logging
import os
from contextlib import contextmanager

log = logging.getLogger("guard.tracing")
_langfuse = None
_ready = False


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
    if client:
        try:
            context = client.start_as_current_observation(name=name, as_type=as_type, **fields)
            observation = context.__enter__()
        except Exception as exc:
            log.warning("Langfuse 기록 실패: %s", type(exc).__name__)
            context = None
    if context is None:
        yield _NoOp()
        return
    try:
        yield observation
    except Exception as exc:
        # 오류 메시지에 통화 내용이 섞일 수 있어 종류만 남깁니다.
        update(observation, level="ERROR", status_message=type(exc).__name__)
        raise
    finally:
        try:
            context.__exit__(None, None, None)
        except Exception as exc:
            log.warning("Langfuse 기록 실패: %s", type(exc).__name__)


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
