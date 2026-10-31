"""안심 대응 점수(plan-ai 5-4절). 훈련 안에서만 쓰는 점수이며 실제 피해 위험을 재지 않는다.

알아차림 30 = round(30·(N−k+1)/N): N은 거친 장면 수, k는 처음으로 끊기·거절·공식번호확인·가족확인·신고를 한 장면.
정보지킴 30 = max(0, 30 − 15·새어 나간 정보 종류 수). 송금·앱 설치로 끝나면 0.
확인행동 25 = 마무리 질문에서 고른 행동의 점수 합(공식번호확인 10, 가족확인 10, 신고 5, 잘못된 행동은 감점), 0–25.
대응속도 15 = 첫 위험 신호가 나온 차례부터 내가 끊은 차례까지 t차례: t≤1 15, 2 10, 3 5, 그 밖 0. 피해로 끝나거나 상대가 먼저 끊으면 0.
"""
from .schema import SAFE_INTENTS, Graph

WEIGHTS = {"알아차림": 30, "정보지킴": 30, "확인행동": 25, "대응속도": 15}


def band(total: int) -> str:
    if total >= 90:
        return "튼튼"
    if total >= 70:
        return "보통"
    if total >= 50:
        return "주의"
    return "위험"


def compute(graph: Graph, state: dict) -> dict:
    visited = state["visited"]
    turns = state["turns"]
    n = len(visited)
    order = {node_id: i + 1 for i, node_id in enumerate(visited)}
    k = next((order[t["node"]] for t in turns if t["intent"] in SAFE_INTENTS), None)
    notice = round(30 * (n - k + 1) / n) if k and n else 0

    term = graph.terminals[state["terminal"]] if state.get("terminal") else None
    if term is not None and term.type == "loss" and term.loss in ("송금", "앱설치"):
        protect = 0
    else:
        protect = max(0, 30 - 15 * len(set(state["leaks"])))

    chosen = set(state.get("closing") or [])
    points = sum(o.points for o in graph.closing.options if o.id in chosen)
    verify = max(0, min(25, points))

    speed = 0
    if term is not None and term.type == "safe" and term.by == "user" and turns:
        first_flag = next((t["seq"] for t in turns if graph.nodes[t["node"]].red_flags), None)
        exit_turn = turns[-1]["seq"]
        if first_flag is not None:
            t = exit_turn - first_flag + 1
            speed = {1: 15, 2: 10, 3: 5}.get(t, 0)

    breakdown = {"알아차림": notice, "정보지킴": protect, "확인행동": verify, "대응속도": speed}
    total = sum(breakdown.values())
    return {
        "total": total,
        "band": band(total),
        "breakdown": breakdown,
        "max": WEIGHTS,
        "scenes_visited": n,
        "first_safe_scene": k,
        "leaks": list(dict.fromkeys(state["leaks"])),
    }
