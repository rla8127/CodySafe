"""모의 훈련 v2 API(plan-ai 5-4절). app.py가 기기 인증(current_device)을 넘겨 라우터를 만든다.

임대 GPU 주소(SIM_TTS_URL·SIM_STT_URL)가 없거나 실패하면 501·502와 {"fallback": "browser"}로 알리고,
화면은 브라우저 음성(speechSynthesis)·브라우저 인식(webkitSpeechRecognition)·선택지로 넘어간다.
"""
import base64
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import config, db
from .sim import engine
from .sim import score as sim_score
from .sim.schema import DEFAULT_PRESET, PRESETS, SimProfile, preset_profile

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
def _gpu_headers() -> dict:
    key = os.getenv("SIM_TTS_API_KEY") or os.getenv("SIM_LLM_API_KEY") or ""
    return {"Authorization": f"Bearer {key}"} if key else {}


def _timeout(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _tts_path(text: str):
    voice = os.getenv("SIM_TTS_VOICE", "")
    return TTS_CACHE / (hashlib.sha256(f"{voice}|{text}".encode()).hexdigest()[:32] + ".audio")


def call_tts(text: str) -> tuple[bytes, str]:
    import httpx

    url = os.getenv("SIM_TTS_URL", "").strip()
    payload = {"model": os.getenv("SIM_TTS_MODEL", "tts"), "input": text, "text": text,
               "voice": os.getenv("SIM_TTS_VOICE", "default"), "response_format": "wav", "language": "ko"}
    r = httpx.post(url, json=payload, headers=_gpu_headers(), timeout=_timeout("SIM_TTS_TIMEOUT", 10))
    r.raise_for_status()
    kind = r.headers.get("content-type", "")
    if kind.startswith("audio/"):
        return r.content, kind.split(";")[0]
    data = r.json()  # {"audio": base64} 꼴도 받는다
    return base64.b64decode(data["audio"]), data.get("content_type", "audio/wav")


def cached_tts(text: str) -> tuple[bytes, str]:
    path = _tts_path(text)
    if path.exists():
        kind = (path.with_suffix(".type").read_text() if path.with_suffix(".type").exists() else "audio/wav")
        return path.read_bytes(), kind
    audio, kind = call_tts(text)
    TTS_CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    path.with_suffix(".type").write_text(kind)
    return audio, kind


def prerender(profile: dict) -> None:
    """프로필을 저장할 때 전화 훈련 대사를 미리 합성해 둔다. TTS 주소가 없으면 아무것도 하지 않는다."""
    if not os.getenv("SIM_TTS_URL", "").strip():
        return
    prof = SimProfile(**profile)
    for graph in engine.graphs().values():
        if graph.channel != "call":
            continue
        values = engine.start(graph, prof, seed=0)["values"]
        for node in graph.nodes.values():
            for line in node.lines + node.pressure:
                try:
                    cached_tts(engine.render(line, values))
                except Exception as exc:
                    log.warning("sim 음성 미리 만들기 실패: %s", type(exc).__name__)
                    return


def call_stt(audio: bytes, content_type: str) -> str:
    import httpx

    url = os.getenv("SIM_STT_URL", "").strip()
    ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/mp4": "m4a", "audio/mpeg": "mp3"}.get(content_type.split(";")[0], "webm")
    r = httpx.post(url, files={"file": (f"speech.{ext}", audio, content_type)},
                   data={"model": os.getenv("SIM_STT_MODEL", "whisper-1"), "language": "ko"},
                   headers=_gpu_headers(), timeout=_timeout("SIM_STT_TIMEOUT", 15))
    r.raise_for_status()
    return str(r.json().get("text", "")).strip()


def fallback(code: int, reason: str) -> JSONResponse:
    return JSONResponse({"fallback": "browser", "reason": reason}, status_code=code)


def make_router(current_device) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/sim/scenarios")
    def scenarios(device: str = Depends(current_device)):
        with db.connect() as conn:
            profile = load_profile(conn, device)
            items = _ranked(conn, device, profile)
        return {
            "items": items,
            "default": PINNED,
            "profile": profile.model_dump() if profile else None,
            "presets": [{"id": k, "label": v["label"], "profile": v["profile"]} for k, v in PRESETS.items()],
            "llm": "gpu" if os.getenv("SIM_LLM_BASE_URL", "").strip() else "rule",
            "tts": bool(os.getenv("SIM_TTS_URL", "").strip()),
            "stt": bool(os.getenv("SIM_STT_URL", "").strip()),
        }

    @router.post("/v1/sim/sessions")
    def create_session(body: SessionIn, device: str = Depends(current_device)):
        graph = engine.get_graph(engine.resolve_type(body.scenario_id))
        with db.connect() as conn:
            stored = load_profile(conn, device)
            profile = stored or preset_profile(DEFAULT_PRESET)
            state = engine.start(graph, profile, body.mode)
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
            body = {"session_id": sid, "status": state["status"], "current_node": state["node"]}
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
        if not os.getenv("SIM_TTS_URL", "").strip():
            return fallback(501, "tts_not_configured")
        started = time.perf_counter()
        try:
            audio, kind = cached_tts(body.text)
        except Exception as exc:
            log.warning("sim TTS 실패: %s", type(exc).__name__)
            return fallback(502, "tts_failed")
        return Response(audio, media_type=kind, headers={"X-Sim-Ms": str(int((time.perf_counter() - started) * 1000))})

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
