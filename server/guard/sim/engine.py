"""대본 그래프 진행 엔진(plan-ai 5-4절).

세션 상태는 JSON으로 저장할 수 있는 dict다. 흐름:
start() → scene 하나 → turn()을 받을 때마다 판정 → 정답·오답은 그 선택지의 다음으로,
중답은 같은 장면에서 한 번 더 압박한 뒤 다음 장면으로 → 종료에 닿으면 마무리 질문 → close()로 점수.
"""
import json
import random
import re
import time
from functools import lru_cache
from pathlib import Path

from . import judge as judge_mod
from . import score as score_mod
from .schema import MAX_STAY, MAX_TURNS, Graph, SimProfile
from .validate import assert_valid

GRAPH_DIR = Path(__file__).parent / "graphs"
GENERATED_DIR = GRAPH_DIR / "generated"
_SLOT = re.compile(r"\{(\w+)\}")

# 지역 → 사칭에 자주 쓰이는 관할 검찰청 이름(공공기관 이름이며 번호·주소는 쓰지 않는다)
REGION_OFFICE = {
    "서울": "서울중앙지검", "부산": "부산지검", "대구": "대구지검", "인천": "인천지검", "광주": "광주지검",
    "대전": "대전지검", "울산": "울산지검", "세종": "대전지검", "경기": "수원지검", "강원": "춘천지검",
    "충북": "청주지검", "충남": "대전지검", "전북": "전주지검", "전남": "광주지검", "경북": "대구지검",
    "경남": "창원지검", "제주": "제주지검",
}

# 탐지 결과의 수법 id(scam_kb)와 분류 이름을 기본 그래프로 잇는다(O-4의 '같은 수법 훈련하기' 링크).
TYPE_TO_GRAPH = {
    "prosecutor_impersonation": "agency_call", "bank_security": "agency_call", "government_benefit": "agency_call",
    "기관사칭": "agency_call", "agency": "agency_call",
    "family_impersonation": "family_messenger", "가족지인사칭": "family_messenger", "family": "family_messenger",
    "smishing": "delivery_sms", "스미싱": "delivery_sms", "delivery": "delivery_sms", "card_delivery": "delivery_sms",
}
DEFAULT_GRAPH = "agency_call"


@lru_cache(maxsize=1)
def _load_all() -> dict[str, Graph]:
    graphs: dict[str, Graph] = {}
    for folder in (GRAPH_DIR, GENERATED_DIR):
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.json")):
            graph = assert_valid(json.loads(path.read_text(encoding="utf-8")))
            graphs[graph.id] = graph
    return graphs


def graphs() -> dict[str, Graph]:
    return _load_all()


def reload() -> None:
    _load_all.cache_clear()


def get_graph(scenario_id: str) -> Graph:
    all_graphs = graphs()
    if scenario_id in all_graphs:
        return all_graphs[scenario_id]
    mapped = TYPE_TO_GRAPH.get(scenario_id)
    if mapped and mapped in all_graphs:
        return all_graphs[mapped]
    raise KeyError(scenario_id)


def resolve_type(kind: str | None) -> str:
    """'같은 수법 훈련하기' 링크의 type 값을 그래프 ID로 바꾼다. 모르면 기관 사칭(기본 선택)."""
    if not kind:
        return DEFAULT_GRAPH
    if kind in graphs():
        return kind
    for graph in graphs().values():
        if kind in graph.aliases:
            return graph.id
    return TYPE_TO_GRAPH.get(kind, DEFAULT_GRAPH)


def slot_values(profile: SimProfile, otp: str) -> dict[str, str]:
    terms = profile.family_terms
    return {
        "user_title": "선생님" if profile.age_band == "60s" else "어르신",
        "child_title": terms[0],
        "family_other": terms[1] if len(terms) > 1 else "다른 가족",
        "bank": profile.main_bank,
        "region_office": REGION_OFFICE.get(profile.region, "서울중앙지검"),
        "pension_org": "국민연금공단",
        "otp": otp,
    }


def render(text: str, values: dict[str, str]) -> str:
    return _SLOT.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def _new_otp(rng: random.Random) -> str:
    # 공식 번호(112·1301·1332·118)와 겹치는 숫자는 판정을 헷갈리게 하므로 피한다.
    while True:
        otp = f"{rng.randint(200000, 999999)}"
        if not any(n in otp for n in ("112", "1301", "1332", "118", "182")):
            return otp


def start(graph: Graph, profile: SimProfile, mode: str = "chat", seed: int | None = None) -> dict:
    seed = seed if seed is not None else random.SystemRandom().randint(1, 10**9)
    otp = _new_otp(random.Random(seed))
    return {
        "scenario_id": graph.id,
        "mode": mode,
        "seed": seed,
        "otp": otp,
        "profile": profile.model_dump(),
        "values": slot_values(profile, otp),
        "node": graph.start,
        "stay": 0,
        "visited": [graph.start],
        "turns": [],
        "leaks": [],
        "status": "active",
        "terminal": None,
        "closing": None,
        "started_at": time.time(),
    }


def _choices(graph: Graph, state: dict, node_id: str) -> list[dict]:
    node = graph.nodes[node_id]
    items = [{"id": c.id, "text": render(c.text, state["values"]), "act": c.act} for c in node.choices]
    random.Random(f"{state['seed']}:{node_id}").shuffle(items)  # 정답이 늘 같은 자리에 있지 않게
    return items


def scene(graph: Graph, state: dict, pressure: str | None = None) -> dict:
    """화면에 보낼 지금 장면. 등급과 해설은 끝나기 전에는 보내지 않는다."""
    node_id = state["node"]
    node = graph.nodes[node_id]
    values = state["values"]
    return {
        "node_id": node_id,
        "stage": node.stage,
        "lines": [render(line, values) for line in node.lines] if pressure is None else [pressure],
        "pressure": pressure is not None,
        "tone": node.tone if pressure is None else node.pressure_tone,
        "media": {"kind": node.media.kind, "text": render(node.media.text, values)} if node.media and pressure is None else None,
        "choices": _choices(graph, state, node_id),
        "turn": len(state["turns"]) + 1,
        "max_turns": MAX_TURNS,
    }


def _judge_context(graph: Graph, state: dict) -> dict:
    node = graph.nodes[state["node"]]
    values = state["values"]
    return {
        "scenario": graph.title,
        "scam_type": graph.scam_type,
        "stage": node.stage,
        "lines": [render(line, values) for line in node.lines],
        "choices": [{"grade": c.grade, "intent": c.intent, "text": render(c.text, values)} for c in node.choices],
        "otp": state["otp"],
        "family_terms": state["profile"].get("family_terms", []),
    }


def _loss_terminal(graph: Graph, kind: str) -> str | None:
    return next((tid for tid, t in graph.terminals.items() if t.type == "loss" and t.loss == kind), None)


def _quit_terminal(graph: Graph) -> str:
    return next(
        (tid for tid, t in graph.terminals.items() if t.type == "safe" and t.by == "scammer"),
        next(tid for tid, t in graph.terminals.items() if t.type == "safe"),
    )


def turn(graph: Graph, state: dict, *, choice_id: str | None = None, text: str | None = None,
         input_type: str = "choice", stt_ms: int | None = None, judge_fn=None) -> dict:
    """답 하나를 받아 상태를 고치고 화면에 보낼 응답을 돌려준다."""
    if state["status"] != "active":
        raise ValueError("이미 끝난 훈련입니다")
    node = graph.nodes[state["node"]]
    by_grade = {c.grade: c for c in node.choices}
    started = time.perf_counter()
    if choice_id:
        choice = next((c for c in node.choices if c.id == choice_id), None)
        if choice is None:
            raise ValueError("이 장면에 없는 선택지입니다")
        verdict = {"grade": choice.grade, "intent": choice.intent, "confidence": 1.0, "source": "choice",
                   "leaks": list(choice.leaks), "reask": False}
        text = render(choice.text, state["values"])
        input_type = "choice" if input_type not in ("voice", "choice") else input_type
    else:
        text = (text or "").strip()[:300]
        if not text:
            raise ValueError("답이 비어 있습니다")
        verdict = (judge_fn or judge_mod.judge)(text, _judge_context(graph, state))
    judge_ms = int((time.perf_counter() - started) * 1000)

    state["turns"].append({
        "seq": len(state["turns"]) + 1, "node": state["node"], "input_type": input_type, "text": text,
        "grade": verdict["grade"], "intent": verdict["intent"], "source": verdict["source"],
        "leaks": verdict.get("leaks", []), "judge_ms": judge_ms, "stt_ms": stt_ms,
    })
    for leak in verdict.get("leaks", []):
        if leak not in state["leaks"]:
            state["leaks"].append(leak)

    # 다음 자리 고르기
    target = None
    if verdict["intent"] == "송금동의":
        target = _loss_terminal(graph, "송금")
    elif verdict["intent"] == "앱설치동의":
        target = _loss_terminal(graph, "앱설치")
    pressure = None
    if target is None:
        if verdict["grade"] == "중답" and state["stay"] < MAX_STAY - 1:
            state["stay"] += 1
            line = node.pressure[(state["stay"] - 1) % len(node.pressure)]
            pressure = render(line, state["values"])
        else:
            target = by_grade[verdict["grade"]].next
    if len(state["turns"]) >= MAX_TURNS and (target is None or target in graph.nodes):
        target, pressure = _quit_terminal(graph), None  # 안전망: 8차례를 채우면 상대가 끊은 것으로 끝낸다

    response = {"judge": {k: verdict[k] for k in ("grade", "intent", "source", "reask")}, "status": "active"}
    if target is not None:
        # 다음 장면·종료로 넘어갔으면 '못 알아들었어요' 배너를 새 장면에 띄우지 않는다(되묻기는 같은 장면에 머물 때만).
        response["judge"]["reask"] = False
    if target is None:
        response["scene"] = scene(graph, state, pressure=pressure)
    elif target in graph.terminals:
        state["status"] = "closing"
        state["terminal"] = target
        response["status"] = "closing"
        response["terminal"] = terminal_view(graph, state)
        response["closing"] = closing_view(graph, state)
    else:
        state["node"] = target
        state["stay"] = 0
        if target not in state["visited"]:
            state["visited"].append(target)
        response["scene"] = scene(graph, state)
    return response


def terminal_view(graph: Graph, state: dict) -> dict:
    term = graph.terminals[state["terminal"]]
    return {"id": state["terminal"], "type": term.type, "loss": term.loss, "by": term.by,
            "message": render(term.message, state["values"])}


def closing_view(graph: Graph, state: dict) -> dict:
    options = [{"id": o.id, "text": render(o.text, state["values"])} for o in graph.closing.options]
    random.Random(f"{state['seed']}:closing").shuffle(options)
    return {"question": render(graph.closing.question, state["values"]), "options": options, "multi": True}


def close(graph: Graph, state: dict, option_ids: list[str]) -> dict:
    if state["status"] != "closing":
        raise ValueError("마무리 질문 차례가 아닙니다")
    known = {o.id for o in graph.closing.options}
    state["closing"] = [o for o in dict.fromkeys(option_ids) if o in known]
    state["status"] = "done"
    state["finished_at"] = time.time()
    return result(graph, state)


def result(graph: Graph, state: dict) -> dict:
    """점수와 장면별 해설. 사용자 글은 그대로 돌려주며 화면은 textContent로만 넣는다."""
    values = state["values"]
    scored = score_mod.compute(graph, state)
    scenes = []
    for node_id in state["visited"]:
        node = graph.nodes[node_id]
        mine = [t for t in state["turns"] if t["node"] == node_id]
        best = next(c for c in node.choices if c.grade == "정답")
        scenes.append({
            "node_id": node_id,
            "stage": node.stage,
            "line": render(node.lines[0], values),
            "answers": [{"text": t["text"], "grade": t["grade"], "intent": t["intent"], "source": t["source"]} for t in mine],
            "best": render(best.text, values),
            "red_flags": [render(f, values) for f in node.red_flags],
            "debrief": render(node.debrief, values),
        })
    chosen = set(state.get("closing") or [])
    closing = [{"id": o.id, "text": render(o.text, values), "kind": o.kind, "points": o.points,
                "chosen": o.id in chosen, "why": render(o.why, values)} for o in graph.closing.options]
    return {
        "scenario_id": graph.id,
        "title": graph.title,
        "scam_type": graph.scam_type,
        "status": state["status"],
        "terminal": terminal_view(graph, state) if state.get("terminal") else None,
        "score": scored,
        "scenes": scenes,
        "closing": closing,
        "label": "훈련 안 점수예요. 실제 피해 위험을 재는 점수가 아니에요.",
        "sources": [r.model_dump() for r in graph.source_refs],
    }
