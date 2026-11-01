"""모의 훈련 v2 API(plan-ai 5-4절). app.py가 기기 인증(current_device)을 넘겨 라우터를 만든다.

임대 GPU 주소(SIM_TTS_URL·SIM_STT_URL)가 없거나 실패하면 501·502와 {"fallback": "browser"}로 알리고,
화면은 브라우저 음성(speechSynthesis)·브라우저 인식(webkitSpeechRecognition)·선택지로 넘어간다.
"""
import base64
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from . import config, db
from .sim import backup_use, engine
from .sim import score as sim_score
from .sim.schema import DEFAULT_PRESET, PRESETS, TONE_GUIDE, SimProfile, Tone, preset_profile

log = logging.getLogger("guard.sim")

# 나이대별 수법 사전 가중치(plan-ai 5-3절). 기관 사칭은 늘 첫 칸에 고정한다(D-1031-8).
AGE_PRIOR = {
    "60s": {"가족지인사칭": 0.4, "기관사칭": 0.35, "대출빙자": 0.25},
    "70s": {"기관사칭": 0.4, "가족지인사칭": 0.4, "기타": 0.2},
    "80plus": {"기관사칭": 0.4, "가족지인사칭": 0.4, "기타": 0.2},
}
PINNED = "agency_call"
BADGE = "먼저 해 보세요"
KST = timezone(timedelta(hours=9))
TTS_CACHE = config.ROOT / "data" / "tts_cache"
MAX_AUDIO = 5 * 1024 * 1024


class SessionIn(BaseModel):
    scenario_id: str = Field(default=PINNED, max_length=60)
    mode: Literal["chat", "call"] = "chat"


class TurnIn(BaseModel):
    choice_id: str | None = Field(default=None, max_length=20)
    text: str | None = Field(default=None, max_length=300)
    input_type: Literal["choice", "text", "voice", "hangup"] = "choice"  # hangup: 전화 화면의 끊기 버튼
    stt_ms: int | None = Field(default=None, ge=0, le=120000)


class ClosingIn(BaseModel):
    option_ids: list[str] = Field(default_factory=list, max_length=10)


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    tone: Tone | None = None  # 장면 말투(감정). 임대 GPU TTS에 emotion·instruct로 넘긴다


# ---------- 프로필 ----------
def load_profile(conn, device: str) -> SimProfile | None:
    row = conn.execute("SELECT sim_profile FROM devices WHERE id = ?", (device,)).fetchone()
    if row and row["sim_profile"]:
        try:
            return SimProfile(**json.loads(row["sim_profile"]))
        except (ValueError, TypeError):
            return None
    return None


def merge_profile(current: SimProfile | None, preset: str | None, fields: dict) -> SimProfile:
    """저장된 프로필 위에 프리셋, 그 위에 직접 고친 칸을 얹는다."""
    data = current.model_dump() if current else {}
    if preset:
        data.update(PRESETS[preset]["profile"])
    data.update({k: v for k, v in fields.items() if v is not None})
    return SimProfile(**data)


# ---------- 세션 ----------
def _load(conn, sid: str, device: str) -> dict:
    row = conn.execute("SELECT state_json FROM sim_sessions WHERE id = ? AND device_id = ?", (sid, device)).fetchone()
    if not row:
        raise HTTPException(404, "훈련을 찾을 수 없습니다")
    return json.loads(row["state_json"])


def _graph(state: dict):
    try:
        return engine.get_graph(state["scenario_id"])
    except KeyError:
        raise HTTPException(410, "대본이 바뀌어 이어 할 수 없습니다")


def _weakness(conn, device: str) -> dict[str, float]:
    return {r["scam_type"]: r["value"] for r in conn.execute("SELECT scam_type, value FROM weakness WHERE device_id = ?", (device,))}


def _plays(conn, device: str) -> dict[str, int]:
    rows = conn.execute("SELECT scenario_id, COUNT(*) n FROM sim_sessions WHERE device_id = ? AND finished_at IS NOT NULL GROUP BY scenario_id", (device,))
    return {r["scenario_id"]: r["n"] for r in rows}


def _ranked(conn, device: str, profile: SimProfile | None) -> list[dict]:
    """취약도 × 사전 가중치 × 새로움 순서. 기관 사칭은 늘 첫 칸."""
    prior = AGE_PRIOR[(profile.age_band if profile else "70s")]
    weak, plays = _weakness(conn, device), _plays(conn, device)
    items = []
    for g in engine.graphs().values():
        rank = prior.get(g.scam_type, 0.15) * (1 + weak.get(g.scam_type, 0.0)) / (1 + plays.get(g.id, 0))
        items.append({
            "id": g.id, "title": g.title, "summary": g.summary, "scam_type": g.scam_type, "channel": g.channel,
            "difficulty": g.difficulty, "synthetic": g.synthetic, "aliases": g.aliases,
            "badge": BADGE if g.id == PINNED else None, "plays": plays.get(g.id, 0), "rank": round(rank, 4),
        })
    items.sort(key=lambda i: (i["id"] != PINNED, -i["rank"], i["id"]))
    return items


def recommend(conn, device: str, current: str) -> dict | None:
    others = [i for i in _ranked(conn, device, load_profile(conn, device)) if i["id"] != current]
    if not others:
        return None
    pick = max(others, key=lambda i: i["rank"])
    return {"id": pick["id"], "title": pick["title"], "scam_type": pick["scam_type"], "channel": pick["channel"]}


def _update_weakness(conn, device: str, scam_type: str, total: int) -> None:
    row = conn.execute("SELECT value FROM weakness WHERE device_id = ? AND scam_type = ?", (device, scam_type)).fetchone()
    old = row["value"] if row else 0.5  # 처음은 모름(0.5)에서 시작
    value = 0.7 * old + 0.3 * (1 - total / 100)
    conn.execute(
        "INSERT INTO weakness (device_id, scam_type, value, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(device_id, scam_type) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (device, scam_type, round(value, 4), db.now()),
    )


def _streak(days: set) -> int:
    today = datetime.now(KST).date()
    streak = 0
    while today - timedelta(days=streak) in days:
        streak += 1
    return streak


# ---------- 임대 GPU 음성 ----------
def _host(url: str) -> str:
    from urllib.parse import urlsplit

    try:
        return (urlsplit(url.strip()).hostname or "").lower()
    except ValueError:
        return ""


def _gpu_headers(kind: str = "tts") -> dict:
    """TTS·STT 요청 머리. 저마다의 키(SIM_TTS_API_KEY·SIM_STT_API_KEY)를 쓰고, 없을 때는 주소의 호스트가
    LLM 주소와 같을 때만 SIM_LLM_API_KEY를 빌린다(다른 제공자에게 LLM 토큰이 가지 않게, GAF 검토 11-01)."""
    url = os.getenv("SIM_TTS_URL" if kind == "tts" else "SIM_STT_URL", "")
    key = os.getenv("SIM_TTS_API_KEY" if kind == "tts" else "SIM_STT_API_KEY", "")
    if not key:
        llm_host = _host(os.getenv("SIM_LLM_BASE_URL", ""))
        if llm_host and _host(url) == llm_host:
            key = os.getenv("SIM_LLM_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


def _timeout(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _tts_path(text: str, tone: str | None = None):
    # 서버 주소·모델·목소리가 바뀌면 다른 캐시를 쓴다(옛 목소리가 다시 나오지 않게).
    url = os.getenv("SIM_TTS_URL", "").strip()
    model = os.getenv("SIM_TTS_MODEL", "tts")
    voice = os.getenv("SIM_TTS_VOICE", "default")
    return TTS_CACHE / (hashlib.sha256(f"{url}|{model}|{voice}|{tone or ''}|{text}".encode()).hexdigest()[:32] + ".audio")


def call_tts(text: str, tone: str | None = None) -> tuple[bytes, str]:
    import httpx

    url = os.getenv("SIM_TTS_URL", "").strip()
    payload = {"model": os.getenv("SIM_TTS_MODEL", "tts"), "input": text, "text": text,
               "voice": os.getenv("SIM_TTS_VOICE", "default"), "response_format": "wav", "language": "ko"}
    if tone:
        payload.update(emotion=tone, instruct=TONE_GUIDE.get(tone, ""))  # 감정을 모르는 서버는 이 두 칸을 무시하면 된다
    r = httpx.post(url, json=payload, headers=_gpu_headers("tts"), timeout=_timeout("SIM_TTS_TIMEOUT", 10))
    r.raise_for_status()
    kind = r.headers.get("content-type", "")
    if kind.startswith("audio/"):
        return r.content, kind.split(";")[0]
    data = r.json()  # {"audio": base64} 꼴도 받는다
    return base64.b64decode(data["audio"]), data.get("content_type", "audio/wav")


_tts_locks: dict[str, threading.Lock] = {}
_tts_locks_guard = threading.Lock()


def _read_cached(path) -> tuple[bytes, str]:
    kind_path = path.with_suffix(".type")
    return path.read_bytes(), (kind_path.read_text() if kind_path.exists() else "audio/wav")


class TtsUnavailable(Exception):
    """임대 GPU 주소도 없고 예비 음성에도 없는 대사. 화면은 이 대사만 브라우저 음성으로 읽는다."""


def cached_tts(text: str, tone: str | None = None) -> tuple[bytes, str]:
    """대사 음성. SIM_BACKUP_FIRST=1이면 예비 음성(mp3) → 임대 GPU, 아니면 임대 GPU(캐시) → 실패·주소 없음이면 예비 음성."""
    backup_first = backup_use.first()
    if backup_first and (hit := backup_use.tts(text, tone)):
        return hit
    if not os.getenv("SIM_TTS_URL", "").strip():
        if not backup_first and (hit := backup_use.tts(text, tone)):
            return hit
        raise TtsUnavailable(text[:20])
    try:
        return _gpu_tts(text, tone)
    except Exception:
        if not backup_first and (hit := backup_use.tts(text, tone)):
            log.info("sim TTS: 임대 GPU 실패, 예비 음성 사용")
            return hit
        raise


def _gpu_tts(text: str, tone: str | None = None) -> tuple[bytes, str]:
    """같은 대사는 한 번만 합성한다. 미리 만들기와 화면 요청이 겹치면 뒤의 것은 앞의 합성을 기다렸다가 캐시를 읽는다
    (임대 GPU 실측 11-01 08:53: 대사 하나 합성에 7–16초라, 겹쳐 두 번 만들면 GPU가 더 밀린다)."""
    path = _tts_path(text, tone)
    if path.exists():
        return _read_cached(path)
    with _tts_locks_guard:
        lock = _tts_locks.setdefault(path.name, threading.Lock())
    with lock:
        if path.exists():
            return _read_cached(path)
        audio, kind = call_tts(text, tone)
        TTS_CACHE.mkdir(parents=True, exist_ok=True)
        path.with_suffix(".type").write_text(kind)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(audio)
        os.replace(tmp, path)  # .audio가 보이면 내용이 다 쓰인 것이다
    return audio, kind


WARM_EVERY = 300  # 초. 임대 GPU는 한동안 안 쓰면 잠들어 첫 호출이 6–15초 걸린다(CSIT).
_warm = {"at": 0.0}
_warm_lock = threading.Lock()


def warm_gpu() -> None:
    """훈련 목록을 열 때 임대 GPU를 미리 깨운다. 5분에 한 번만, 주소가 없으면 아무것도 하지 않고, 실패는 무시한다."""
    import httpx

    base = os.getenv("SIM_LLM_BASE_URL", "").strip().rstrip("/")
    tts = os.getenv("SIM_TTS_URL", "").strip()
    if (not base and not tts) or backup_use.first():  # 예비 자료를 먼저 쓰는 시연에서는 GPU를 깨우지 않는다(크레딧)
        return
    with _warm_lock:
        if time.time() - _warm["at"] < WARM_EVERY:
            return
        _warm["at"] = time.time()
    started = time.perf_counter()
    if base:
        try:
            key = os.getenv("SIM_LLM_API_KEY", "")
            httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"} if key else {}, timeout=20)
        except Exception as exc:
            log.info("sim GPU 깨우기(LLM) 실패: %s", type(exc).__name__)
    if tts:
        try:
            cached_tts("여보세요.", "official")
        except Exception as exc:
            log.info("sim GPU 깨우기(TTS) 실패: %s", type(exc).__name__)
    log.info("sim GPU 깨우기 %dms", int((time.perf_counter() - started) * 1000))


_prerendering: set[str] = set()
_prerender_lock = threading.Lock()


def prerender(profile: dict) -> None:
    """전화 훈련 대사를 미리 합성해 둔다(프로필을 저장할 때, 훈련 목록을 열 때). 모든 대본이 '전화로 연습하기'를 열 수 있어
    셋 다 만들되 고정 대본(기관 사칭)부터 한다. 이미 만든 대사는 건너뛰고, 같은 프로필을 이미 만드는 중이면 하지 않는다.
    TTS 주소가 없으면 아무것도 하지 않는다."""
    if not os.getenv("SIM_TTS_URL", "").strip() or backup_use.first():
        return
    prof = SimProfile(**profile)
    key = prof.model_dump_json()
    with _prerender_lock:
        if key in _prerendering:
            return
        _prerendering.add(key)
    started, made = time.perf_counter(), 0
    try:
        for graph in sorted(engine.graphs().values(), key=lambda g: (g.id != PINNED, g.channel != "call", g.id)):
            values = engine.start(graph, prof, seed=0)["values"]
            for node in graph.nodes.values():
                for line, tone in [(x, node.tone) for x in node.lines] + [(x, node.pressure_tone) for x in node.pressure]:
                    text = engine.render(line, values)
                    if _tts_path(text, tone).exists():
                        continue
                    try:
                        _gpu_tts(text, tone)
                        made += 1
                    except Exception as exc:
                        log.warning("sim 음성 미리 만들기 실패: %s", type(exc).__name__)
                        return
    finally:
        with _prerender_lock:
            _prerendering.discard(key)
        if made:
            log.info("sim 음성 미리 만들기 %d개 %dms", made, int((time.perf_counter() - started) * 1000))


def call_stt(audio: bytes, content_type: str) -> str:
    import httpx

    url = os.getenv("SIM_STT_URL", "").strip()
    ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/mp4": "m4a", "audio/mpeg": "mp3"}.get(content_type.split(";")[0], "webm")
    r = httpx.post(url, files={"file": (f"speech.{ext}", audio, content_type)},
                   data={"model": os.getenv("SIM_STT_MODEL", "whisper-1"), "language": "ko"},
                   headers=_gpu_headers("stt"), timeout=_timeout("SIM_STT_TIMEOUT", 15))
    r.raise_for_status()
    return str(r.json().get("text", "")).strip()


def caps() -> dict:
    """화면이 고를 경로. 예비 음성이 있으면 GPU 주소가 없어도 tts=True(화면은 /v1/sim/tts를 부르고, 없는 대사만 브라우저 음성)."""
    ready = backup_use.ready()
    return {
        "llm": "gpu" if os.getenv("SIM_LLM_BASE_URL", "").strip() else "rule",
        "tts": bool(os.getenv("SIM_TTS_URL", "").strip()) or ready["tts"],
        "stt": bool(os.getenv("SIM_STT_URL", "").strip()),
        "backup": {"first": backup_use.first(), **ready},
    }


def session_seed() -> int | None:
    """예비 음성은 seed 0으로 만든 대사라, 예비 자료를 먼저 쓰거나 GPU 음성이 없으면 seed 0으로 시작한다(인증번호 숫자가 음성과 같게)."""
    return 0 if backup_use.first() or not os.getenv("SIM_TTS_URL", "").strip() else None


def fallback(code: int, reason: str) -> JSONResponse:
    return JSONResponse({"fallback": "browser", "reason": reason}, status_code=code)


def make_router(current_device) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/sim/scenarios")
    def scenarios(tasks: BackgroundTasks, device: str = Depends(current_device)):
        tasks.add_task(warm_gpu)  # 훈련을 시작하기 전에 임대 GPU를 깨워 둔다
        with db.connect() as conn:
            profile = load_profile(conn, device)
            items = _ranked(conn, device, profile)
        # 프로필을 저장하지 않은 기기도 기본 프리셋 대사로 훈련하므로, 목록을 열 때 그 대사를 미리 만든다.
        tasks.add_task(prerender, (profile or preset_profile(DEFAULT_PRESET)).model_dump())
        return {
            "items": items,
            "default": PINNED,
            "profile": profile.model_dump() if profile else None,
            "presets": [{"id": k, "label": v["label"], "profile": v["profile"]} for k, v in PRESETS.items()],
            **caps(),
        }

    @router.get("/v1/sim/caps")
    def sim_caps():
        return caps()

    @router.get("/v1/sim/video/{name}")
    def sim_video(name: str):
        # <video src>는 인증 머리를 못 보내므로 기기 인증 없이 연다. 합성 얼굴 영상(예비 자료)만, 이름은 영문 소문자·숫자·_ 만.
        path = backup_use.video(name)
        if path is None:
            raise HTTPException(404, "영상이 없습니다")
        return FileResponse(path, media_type="video/mp4")

    @router.post("/v1/sim/sessions")
    def create_session(body: SessionIn, device: str = Depends(current_device)):
        graph = engine.get_graph(engine.resolve_type(body.scenario_id))
        with db.connect() as conn:
            stored = load_profile(conn, device)
            profile = stored or preset_profile(DEFAULT_PRESET)
            state = engine.start(graph, profile, body.mode, seed=session_seed())
            sid = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO sim_sessions (id, device_id, scenario_id, scam_type, mode, started_at, state_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sid, device, graph.id, graph.scam_type, body.mode, db.now(), json.dumps(state, ensure_ascii=False)),
            )
        values = state["values"]
        return {
            "session_id": sid,
            "mode": body.mode,
            "profile_source": "device" if stored else "preset",
            "scenario": {"id": graph.id, "title": graph.title, "scam_type": graph.scam_type, "channel": graph.channel},
            "persona": {"role": engine.render(graph.persona.role, values), "name": engine.render(graph.persona.name, values)},
            "scene": engine.scene(graph, state),
        }

    @router.post("/v1/sim/sessions/{sid}/turn")
    def take_turn(sid: str, body: TurnIn, device: str = Depends(current_device)):
        if not body.choice_id and not (body.text or "").strip():
            raise HTTPException(422, "choice_id나 text가 필요합니다")
        with db.connect() as conn:
            state = _load(conn, sid, device)
        if state["status"] != "active":
            raise HTTPException(409, "이미 끝난 훈련입니다")
        graph = _graph(state)
        try:
            # 판정기가 LLM을 부를 수 있으므로 DB 연결을 잡지 않은 채 판정한다.
            response = engine.turn(graph, state, choice_id=body.choice_id, text=body.text,
                                   input_type=body.input_type, stt_ms=body.stt_ms)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        last = state["turns"][-1]
        with db.connect() as conn:
            conn.execute(
                "INSERT INTO sim_turns (session_id, seq, node_id, input_type, input_text, grade, intent, source,"
                " latency_ms, stt_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, last["seq"], last["node"], last["input_type"], last["text"], last["grade"], last["intent"],
                 last["source"], last["judge_ms"], last["stt_ms"], db.now()),
            )
            conn.execute("UPDATE sim_sessions SET state_json = ? WHERE id = ?", (json.dumps(state, ensure_ascii=False), sid))
        log.info("sim 차례 source=%s judge_ms=%s stt_ms=%s", last["source"], last["judge_ms"], last["stt_ms"])
        return response

    @router.post("/v1/sim/sessions/{sid}/closing")
    def closing(sid: str, body: ClosingIn, device: str = Depends(current_device)):
        with db.connect() as conn:
            state = _load(conn, sid, device)
            if state["status"] != "closing":
                raise HTTPException(409, "마무리 질문 차례가 아닙니다")
            graph = _graph(state)
            result = engine.close(graph, state, body.option_ids)
            total = result["score"]["total"]
            conn.execute(
                "UPDATE sim_sessions SET finished_at = ?, total = ?, breakdown_json = ?, state_json = ? WHERE id = ?",
                (db.now(), total, json.dumps(result["score"]["breakdown"], ensure_ascii=False),
                 json.dumps(state, ensure_ascii=False), sid),
            )
            _update_weakness(conn, device, graph.scam_type, total)
            result["next"] = recommend(conn, device, graph.id)
        result["session_id"] = sid
        return result

    @router.get("/v1/sim/sessions/{sid}/result")
    def session_result(sid: str, device: str = Depends(current_device)):
        with db.connect() as conn:
            state = _load(conn, sid, device)
            graph = _graph(state)
            values = state["values"]
            body = {"session_id": sid, "status": state["status"], "current_node": state["node"], "mode": state["mode"],
                    "title": graph.title, "persona": {"role": engine.render(graph.persona.role, values),
                                                      "name": engine.render(graph.persona.name, values)}}
            if state["status"] == "done":
                body.update(engine.result(graph, state))
                body["next"] = recommend(conn, device, graph.id)
            elif state["status"] == "closing":
                body.update(terminal=engine.terminal_view(graph, state), closing=engine.closing_view(graph, state))
            else:
                body["scene"] = engine.scene(graph, state)
        return body

    @router.get("/v1/me/score")
    def my_score(device: str = Depends(current_device)):
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT id, scenario_id, scam_type, total, breakdown_json, finished_at FROM sim_sessions"
                " WHERE device_id = ? AND finished_at IS NOT NULL ORDER BY finished_at", (device,)).fetchall()
            weak = conn.execute(
                "SELECT scam_type, value FROM weakness WHERE device_id = ? ORDER BY value DESC LIMIT 3", (device,)).fetchall()
        history = [{
            "session_id": r["id"], "scenario_id": r["scenario_id"], "scam_type": r["scam_type"], "total": r["total"],
            "band": sim_score.band(r["total"]), "breakdown": json.loads(r["breakdown_json"] or "{}"),
            "finished_at": r["finished_at"],
        } for r in rows]
        days = {datetime.fromtimestamp(r["finished_at"], KST).date() for r in rows}
        return {
            "name": "안심 대응 점수",
            "label": "훈련 안 점수예요. 실제 피해 위험을 재는 점수가 아니에요.",
            "latest": history[-1] if history else None,
            "history": history[-20:],
            "delta_first_last": history[-1]["total"] - history[0]["total"] if len(history) >= 2 else 0,
            "weakness_top3": [{"scam_type": w["scam_type"], "value": w["value"]} for w in weak],
            "streak_days": _streak(days),
        }

    @router.post("/v1/sim/tts")
    def tts(body: TtsIn, _: str = Depends(current_device)):
        if not caps()["tts"]:
            return fallback(501, "tts_not_configured")
        started = time.perf_counter()
        try:
            audio, kind = cached_tts(body.text, body.tone)
        except TtsUnavailable:
            return fallback(404, "tts_line_not_in_backup")  # 이 대사만 브라우저 음성(화면은 GPU 음성을 끄지 않음)
        except Exception as exc:
            log.warning("sim TTS 실패: %s", type(exc).__name__)
            return fallback(502, "tts_failed")
        # 화면이 '미리 만든 GPU 음성'과 '임대 GPU 음성'을 구분해 표시하게(예비 음성은 mp3, 임대 GPU는 wav).
        voice = "backup" if kind == "audio/mpeg" else "gpu"
        return Response(audio, media_type=kind, headers={"X-Sim-Ms": str(int((time.perf_counter() - started) * 1000)), "X-Sim-Voice": voice})

    @router.post("/v1/sim/stt")
    async def stt(request: Request, _: str = Depends(current_device)):
        if not os.getenv("SIM_STT_URL", "").strip():
            return fallback(501, "stt_not_configured")
        audio = await request.body()
        if not audio:
            raise HTTPException(422, "녹음이 비어 있습니다")
        if len(audio) > MAX_AUDIO:
            raise HTTPException(413, "녹음이 너무 깁니다")
        started = time.perf_counter()
        try:
            text = await run_in_threadpool(call_stt, audio, request.headers.get("content-type", "audio/webm"))
        except Exception as exc:
            log.warning("sim STT 실패: %s", type(exc).__name__)
            return fallback(502, "stt_failed")
        return {"text": text, "ms": int((time.perf_counter() - started) * 1000)}

    return router
