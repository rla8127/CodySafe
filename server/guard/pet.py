"""가족 마스코트 코디와 저녁 식탁 퀴즈. 점수는 사기 피해가 아니라 예방 행동에만 줍니다."""
import random
import sqlite3
import time

from . import db, passphrase
from .quiz_cards import BY_ID, CARDS

NAME = "코디"
STAGES = [
    (0, "알", "가족을 연결하면 깨어나요"),
    (100, "아기 코디", "세상이 궁금한 아기 카멜레온"),
    (300, "꼬마 탐정", "수상한 문구를 찾아내기 시작했어요"),
    (700, "안심 지킴이", "위장한 사기꾼도 알아봐요"),
    (1500, "가족 수호자", "우리 가족을 든든히 지켜요"),
]
XP_TRAINING = 20  # 하루 한 번
XP_NEW_SCENARIO = 10  # 시나리오마다 처음 한 번
XP_QUIZ_DONE = 10
XP_QUIZ_CORRECT = 5
XP_QUIZ_FAMILY = 30
XP_ALERT_CHECK = 30  # 하루 한 번
RED_HOURS = 24
YELLOW_DAYS = 7
QUIZ_SIZE = 3
REVEAL_WEEKDAY, REVEAL_HOUR = 6, 21  # 일요일 밤 9시면 전원이 풀지 않아도 공개합니다.
DEMO_SCORES = {"demo-dad": 1, "demo-mom": 3, "demo-brother": 2, "demo-uncle": 2}

def _kst(at: float | None = None) -> time.struct_time:
    return time.gmtime((at if at is not None else time.time()) + 9 * 3600)


def today() -> str:
    return time.strftime("%Y-%m-%d", _kst())


def week_key() -> str:
    return time.strftime("%G-W%V", _kst())


def award(conn: sqlite3.Connection, device: str, kind: str, points: int, key: str) -> int:
    """같은 행동의 점수가 두 번 쌓이지 않게 합니다. 실제로 더해진 점수를 돌려줍니다."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO pet_events (device_id, kind, points, dedupe_key, created_at) VALUES (?, ?, ?, ?, ?)",
        (device, kind, points, key, db.now()),
    )
    return points if cur.rowcount else 0


def _marks(ids: list[str]) -> str:
    return ",".join("?" * len(ids))


def _stage(xp: int, group_size: int) -> int:
    index = max(i for i, s in enumerate(STAGES) if xp >= s[0])
    # 가족을 연결하면 경험치와 상관없이 알에서 깨어납니다.
    return max(index, 1) if group_size > 1 else index


def _mood(conn: sqlite3.Connection, device: str, group: list[str]) -> dict:
    """가족에게는 의심 여부까지만 드러납니다. 노랑은 본인 기록으로만 정해 가족에게 보이지 않습니다."""
    rows = conn.execute(
        f"SELECT recording_id, MAX(acked) AS checked FROM alerts WHERE protected_id IN ({_marks(group)}) AND created_at > ?"
        " GROUP BY recording_id",
        (*group, db.now() - RED_HOURS * 3600),
    ).fetchall()
    if any(not r["checked"] for r in rows):
        return {"key": "red", "text": "확인이 필요한 통화가 있어요. 가족에게 직접 연락해 주세요."}
    if rows:
        return {"key": "blue", "text": "가족이 함께 확인했어요. 잘하셨어요!"}
    pending = conn.execute(
        "SELECT 1 FROM recordings WHERE device_id = ? AND needs_review = 1 AND review_label IS NULL AND created_at > ? LIMIT 1",
        (device, db.now() - YELLOW_DAYS * 86400),
    ).fetchone()
    if pending:
        return {"key": "yellow", "text": "판단이 애매한 통화가 있어요. 한번 살펴봐 주세요."}
    return {"key": "green", "text": "오늘은 평온해요. 눈을 굴리며 살피는 중이에요."}


def status(conn: sqlite3.Connection, device: str) -> dict:
    group = passphrase.members(conn, device)
    xp = conn.execute(f"SELECT COALESCE(SUM(points), 0) AS xp FROM pet_events WHERE device_id IN ({_marks(group)})", group).fetchone()["xp"]
    index = _stage(xp, len(group))
    next_stage = STAGES[index + 1] if index + 1 < len(STAGES) else None
    trained = conn.execute("SELECT 1 FROM pet_events WHERE device_id = ? AND dedupe_key = ?", (device, f"training:{today()}")).fetchone()
    played = [r["scenario"] for r in conn.execute("SELECT DISTINCT scenario FROM training_results WHERE device_id = ?", (device,))]
    answered = _answers(conn, device, week_key())
    wrong = [BY_ID[a["card_id"]]["scenario"] for a in answered.values() if not a["correct"] and BY_ID[a["card_id"]]["is_scam"]]
    return {
        "name": NAME,
        "xp": xp,
        "stage": index,
        "stage_name": STAGES[index][1],
        "stage_text": STAGES[index][2],
        "stage_start": STAGES[index][0],
        "next_xp": next_stage[0] if next_stage else None,
        "next_name": next_stage[1] if next_stage else None,
        "stages": [{"name": s[1], "xp": s[0]} for s in STAGES],
        "mood": _mood(conn, device, group),
        "family_size": len(group),
        "trained_today": bool(trained),
        "played": played,
        "recommend": wrong[0] if wrong else None,
        "quiz_answered": len(answered),
        "quiz_size": QUIZ_SIZE,
        "rewards": {"training": XP_TRAINING, "new_scenario": XP_NEW_SCENARIO},
    }


def record_training(conn: sqlite3.Connection, device: str, scenario: str) -> dict:
    """체험 점수와 상관없이 끝까지 해 본 것을 칭찬합니다. 틀린 체험도 연습입니다."""
    before = status(conn, device)
    gained = award(conn, device, "training", XP_TRAINING, f"training:{today()}")
    gained += award(conn, device, "new_scenario", XP_NEW_SCENARIO, f"scenario:{scenario}")
    after = status(conn, device)
    return {"gained": gained, "xp": after["xp"], "stage_name": after["stage_name"], "grew": after["stage"] > before["stage"]}


def record_alert_check(conn: sqlite3.Connection, device: str) -> None:
    award(conn, device, "alert_check", XP_ALERT_CHECK, f"alert_check:{today()}")


# ---------- 저녁 식탁 퀴즈 ----------
def week_cards(week: str) -> list[dict]:
    """전부 사기면 찍어도 맞으므로 사기와 정상을 반드시 섞습니다."""
    rng = random.Random(week)
    scams = [c for c in CARDS if c["is_scam"]]
    normals = [c for c in CARDS if not c["is_scam"]]
    picked = [rng.choice(scams), rng.choice(normals)]
    picked.append(rng.choice([c for c in CARDS if c not in picked]))
    rng.shuffle(picked)
    return picked


def _answers(conn: sqlite3.Connection, device: str, week: str) -> dict:
    rows = conn.execute("SELECT card_id, answer, correct FROM quiz_answers WHERE device_id = ? AND week = ?", (device, week)).fetchall()
    return {r["card_id"]: dict(r) for r in rows}


def _seed_demo_answers(conn: sqlite3.Connection, viewer: str, group: list[str], week: str) -> None:
    """시연 가족은 다른 구성원이 이미 푼 것처럼 보여 공개 화면까지 볼 수 있게 합니다. 경험치는 주지 않습니다."""
    if "demo-me" not in group:
        return
    cards = week_cards(week)
    for member, score in DEMO_SCORES.items():
        if member == viewer or member not in group or _answers(conn, member, week):
            continue
        for i, card in enumerate(cards):
            correct = i < score
            conn.execute(
                "INSERT INTO quiz_answers (device_id, week, card_id, answer, correct, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (member, week, card["id"], int(card["is_scam"] == correct), int(correct), db.now()),
            )


def _card_view(card: dict, answer: dict | None) -> dict:
    view = {"id": card["id"], "sender": card["sender"], "text": card["text"], "answered": bool(answer)}
    if answer:
        view.update(correct=bool(answer["correct"]), is_scam=card["is_scam"], why=card["why"], clue=card["clue"], scenario=card["scenario"])
    return view


def _past_deadline() -> bool:
    now = _kst()
    return now.tm_wday == REVEAL_WEEKDAY and now.tm_hour >= REVEAL_HOUR


def quiz(conn: sqlite3.Connection, device: str) -> dict:
    week = week_key()
    group = passphrase.members(conn, device)
    _seed_demo_answers(conn, device, group, week)
    cards = week_cards(week)
    mine = _answers(conn, device, week)
    members = []
    for row in conn.execute(f"SELECT id, name FROM devices WHERE id IN ({_marks(group)})", group):
        answers = _answers(conn, row["id"], week)
        members.append({
            "id": row["id"],
            "name": row["name"],
            "me": row["id"] == device,
            "done": len(answers) >= QUIZ_SIZE,
            "score": sum(a["correct"] for a in answers.values()),
        })
    all_done = all(m["done"] for m in members)
    i_am_done = len(mine) >= QUIZ_SIZE
    reveal = i_am_done and (all_done or _past_deadline())
    done = [m for m in members if m["done"]]
    lowest = min((m["score"] for m in done), default=0)
    losers = [m for m in done if m["score"] == lowest]
    # 동점이면 아무도 벌칙을 받지 않습니다. 혼자 풀면 벌칙도 없습니다.
    dishes = losers[0]["name"] if reveal and len(done) > 1 and len(losers) == 1 else None
    return {
        "week": week,
        "cards": [_card_view(c, mine.get(c["id"])) for c in cards],
        "finished": i_am_done,
        "reveal": reveal,
        "dishes": dishes,
        "members": [{"name": m["name"], "me": m["me"], "done": m["done"], "score": m["score"] if reveal or m["me"] else None} for m in members],
    }


def answer(conn: sqlite3.Connection, device: str, card_id: str, is_scam: bool) -> dict | None:
    week = week_key()
    cards = {c["id"]: c for c in week_cards(week)}
    card = cards.get(card_id)
    if not card:
        return None
    correct = card["is_scam"] == is_scam
    cur = conn.execute(
        "INSERT OR IGNORE INTO quiz_answers (device_id, week, card_id, answer, correct, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (device, week, card_id, int(is_scam), int(correct), db.now()),
    )
    gained = 0
    if cur.rowcount and correct:
        gained += award(conn, device, "quiz_correct", XP_QUIZ_CORRECT, f"quiz:{week}:{card_id}")
    mine = _answers(conn, device, week)
    if len(mine) >= QUIZ_SIZE:
        gained += award(conn, device, "quiz_done", XP_QUIZ_DONE, f"quiz_done:{week}")
        group = passphrase.members(conn, device)
        _seed_demo_answers(conn, device, group, week)
        if all(len(_answers(conn, member, week)) >= QUIZ_SIZE for member in group) and len(group) > 1:
            claimed = conn.execute(
                f"SELECT 1 FROM pet_events WHERE dedupe_key = ? AND device_id IN ({_marks(group)})", (f"quiz_family:{week}", *group)
            ).fetchone()
            if not claimed:
                gained += award(conn, device, "quiz_family", XP_QUIZ_FAMILY, f"quiz_family:{week}")
    # 처음 낸 답을 기준으로 채점합니다. 답을 바꿔 다시 맞혀도 점수는 그대로입니다.
    return {**_card_view(card, mine[card_id]), "gained": gained, "finished": len(mine) >= QUIZ_SIZE}
