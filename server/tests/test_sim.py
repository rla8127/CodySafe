"""모의 훈련 v2: 검사기, 대본 진행, 점수 세 경로, 프리셋, LLM 주소가 틀려도 끝까지 도는지, API."""
import copy
import json
import os
import tempfile

_tmp = tempfile.mkdtemp()
for key, value in dict(
    GUARD_DEMO_FAMILY="0", GUARD_DB=f"{_tmp}/sim.db", GUARD_LOCAL_AUDIO_DIR=f"{_tmp}/a", GUARD_STORAGE="local",
    GUARD_STT="text", GUARD_LLM="rule", GUARD_EMBED="hash", GUARD_ADMIN_TOKEN="admin",
).items():
    os.environ.setdefault(key, value)

import pytest
from fastapi.testclient import TestClient

from guard.app import app
from guard.sim import engine, judge, validate
from guard.sim.schema import preset_profile

BROKEN_LLM = "http://127.0.0.1:9/v1"  # 일부러 틀린 주소(아무도 듣지 않는 포트)


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """기본은 LLM 없이 규칙만. 유료 API를 부르지 않는다."""
    for key in ("SIM_LLM_BASE_URL", "SIM_LLM_API_KEY", "SIM_LLM_MODEL", "SIM_FALLBACK", "SIM_TTS_URL", "SIM_STT_URL"):
        monkeypatch.delenv(key, raising=False)


def graph_data(name="agency_call"):
    return json.loads((engine.GRAPH_DIR / f"{name}.json").read_text(encoding="utf-8"))


def play(graph, choices, closing=(), preset="mother_74_alone", texts=None):
    state = engine.start(graph, preset_profile(preset), seed=7)
    for step in choices:
        node = graph.nodes[state["node"]]
        if step in ("정답", "중답", "오답"):
            choice_id = next(c.id for c in node.choices if c.grade == step)
            engine.turn(graph, state, choice_id=choice_id)
        else:
            engine.turn(graph, state, text=step, input_type="text")
        if state["status"] != "active":
            break
    assert state["status"] == "closing"
    return state, engine.close(graph, state, list(closing))


# ---------- 검사기 (R-001) ----------
def test_schema_validate_all_default_graphs_pass():
    for name in ("agency_call", "family_messenger", "delivery_sms"):
        assert validate.validate(graph_data(name)) == [], name
    assert set(engine.graphs()) >= {"agency_call", "family_messenger", "delivery_sms"}


@pytest.mark.parametrize("break_it, expected", [
    (lambda g: g["nodes"]["n1_intro"]["choices"][1].update(next="nowhere"), "다음 장면"),
    (lambda g: g["nodes"]["n1_intro"]["choices"][2].update(grade="정답", intent="끊기"), "하나씩"),
    (lambda g: [c.update(next="t_safe") for c in g["nodes"]["n1_intro"]["choices"]], "닿지 않는 장면"),
    (lambda g: g["nodes"]["n4_transfer"]["choices"][2].update(next="t_safe"), "실패 종료"),
    (lambda g: g["nodes"]["n2_fear"]["choices"][1].update(next="n1_intro"), "순환"),
    (lambda g: g.update(source_refs=[]), "source_refs"),
    (lambda g: g["nodes"]["n1_intro"]["lines"].append("02-3480-2000으로 전화 주세요"), "전화번호"),
    (lambda g: g["nodes"]["n1_intro"]["lines"].append("https://www.example-bank.co.kr/app 을 여세요"), "example 도메인"),
    (lambda g: g["nodes"]["n1_intro"]["lines"].append("계좌 110-234-567890 으로"), "계좌번호"),
    (lambda g: g["nodes"]["n1_intro"]["lines"].append("{real_name} 님"), "모르는 칸"),
])
def test_validate_rejects_broken_graphs(break_it, expected):
    data = graph_data()
    break_it(data)
    errors = validate.validate(data)
    assert any(expected in e for e in errors), errors


def test_validate_rejects_paths_longer_than_eight_turns():
    data = graph_data()
    n5 = copy.deepcopy(data["nodes"]["n4_transfer"])
    for c in n5["choices"]:
        c["next"] = {"정답": "t_safe", "중답": "t_quit", "오답": "t_loss_money"}[c["grade"]]
    data["nodes"]["n5_extra"] = n5
    data["nodes"]["n4_transfer"]["choices"][1]["next"] = "n5_extra"  # 5장면 × 2차례 = 10차례
    assert any("8차례" in e for e in validate.validate(data))


def test_fake_numbers_and_example_domains_are_allowed():
    assert validate.scan_unsafe("010-0000-5821로 연락 https://parcel-kr.example/a7 1301 112") == []


# ---------- 한 대본 끝까지와 점수 세 경로 ----------
def test_one_script_runs_to_the_end_with_closing_question():
    graph = engine.get_graph("agency_call")
    state = engine.start(graph, preset_profile("mother_74_alone"), seed=3)
    first = engine.scene(graph, state)
    assert first["node_id"] == "n1_intro" and len(first["choices"]) == 3
    assert all("grade" not in c for c in first["choices"])  # 등급은 끝나기 전에 보내지 않는다
    response = engine.turn(graph, state, choice_id=next(c.id for c in graph.nodes["n1_intro"].choices if c.grade == "오답"))
    assert response["scene"]["node_id"] == "n2_fear"
    response = engine.turn(graph, state, choice_id=next(c.id for c in graph.nodes["n2_fear"].choices if c.grade == "정답"))
    assert response["status"] == "closing" and response["terminal"]["type"] == "safe"
    assert response["closing"]["question"] and len(response["closing"]["options"]) == 5
    result = engine.close(graph, state, ["k1"])
    assert result["status"] == "done" and [s["node_id"] for s in result["scenes"]] == ["n1_intro", "n2_fear"]
    assert result["scenes"][0]["debrief"] and result["scenes"][0]["best"]
    assert "훈련 안 점수" in result["label"]


def test_score_hang_up_at_once_with_full_closing_is_100():
    graph = engine.get_graph("agency_call")
    _, result = play(graph, ["정답"], closing=["k1", "k2", "k3"])
    assert result["score"]["breakdown"] == {"알아차림": 30, "정보지킴": 30, "확인행동": 25, "대응속도": 15}
    assert result["score"]["total"] == 100 and result["score"]["band"] == "튼튼"


def test_score_hang_up_midway_is_in_the_middle():
    graph = engine.get_graph("agency_call")
    state, result = play(graph, ["중답", "중답", "정답"], closing=["k1"])
    assert [t["node"] for t in state["turns"]] == ["n1_intro", "n1_intro", "n2_fear"]  # 중답 뒤 한 번 더 압박
    assert result["score"]["breakdown"] == {"알아차림": 15, "정보지킴": 30, "확인행동": 10, "대응속도": 5}
    assert 40 < result["score"]["total"] < 90


def test_score_sending_money_is_low():
    graph = engine.get_graph("agency_call")
    state, result = play(graph, ["오답", "오답", "오답", "오답"], closing=["k4"])
    assert state["terminal"] == "t_loss_money" and state["leaks"] == ["인증번호"]
    assert result["score"]["total"] < 30 and result["score"]["band"] == "위험"
    assert result["score"]["breakdown"]["정보지킴"] == 0 and result["score"]["breakdown"]["확인행동"] == 0


def test_mid_answers_stay_once_then_move_on_and_never_exceed_eight_turns():
    graph = engine.get_graph("agency_call")
    state, result = play(graph, ["중답"] * 8)
    assert len(state["turns"]) == 8 and state["terminal"] == "t_quit"
    assert result["score"]["breakdown"]["대응속도"] == 0


def test_every_default_graph_reaches_safe_and_loss_by_choices():
    for gid in ("agency_call", "family_messenger", "delivery_sms"):
        graph = engine.get_graph(gid)
        _, best = play(graph, ["정답"], closing=["k1", "k2", "k3"])
        assert best["score"]["total"] == 100, gid
        _, worst = play(graph, ["오답"] * 4)
        assert worst["terminal"]["type"] == "loss", gid


def test_preset_changes_rendered_lines():
    graph = engine.get_graph("agency_call")
    mother = engine.scene(graph, engine.start(graph, preset_profile("mother_74_alone"), seed=1))["lines"]
    father = engine.scene(graph, engine.start(graph, preset_profile("father_68_retired"), seed=1))["lines"]
    assert mother != father
    assert "대구지검" in mother[0] and "어르신" in mother[0] and "농협" in mother[1]
    assert "서울중앙지검" in father[0] and "선생님" in father[0] and "국민은행" in father[1]
    family = engine.get_graph("family_messenger")
    lines = engine.scene(family, engine.start(family, preset_profile("father_68_retired"), seed=1))["choices"]
    assert any("딸" in c["text"] for c in lines)
    assert not any("{" in c["text"] for c in lines)


def test_type_links_from_detection_pick_the_matching_graph():
    assert engine.resolve_type("prosecutor_impersonation") == "agency_call"
    assert engine.resolve_type("family_impersonation") == "family_messenger"
    assert engine.resolve_type("스미싱") == "delivery_sms"
    assert engine.resolve_type("romance_scam") == "agency_call"  # 모르는 수법은 기본(기관 사칭)
    assert engine.resolve_type(None) == "agency_call"


# ---------- 판정기 규칙 ----------
def ctx_for(node_id="n3_otp", otp="340891"):
    graph = engine.get_graph("agency_call")
    state = engine.start(graph, preset_profile("mother_74_alone"), seed=1)
    state["node"], state["otp"] = node_id, otp
    return engine._judge_context(graph, state)


@pytest.mark.parametrize("text, grade, intent", [
    ("네 340891이요", "오답", "정보제공"),
    ("삼사공팔구일", "오답", "정보제공"),
    ("지금 끊고 1301에 전화해 볼게요", "정답", None),
    ("112에 신고할게요", "정답", "신고"),
    ("아들한테 전화해서 물어볼게요", "정답", "가족확인"),
    ("돈은 절대 안 보낼 거예요", "정답", "거절"),
    ("말씀하신 계좌로 보낼게요", "오답", "송금동의"),
    ("네 앱 설치할게요", "오답", "앱설치동의"),
    ("알겠습니다 아무한테도 말 안 할게요", "오답", "따르기"),
    ("무슨 사건인데요?", "중답", "되묻기"),
])
def test_rule_judge(text, grade, intent):
    verdict = judge.judge(text, ctx_for())
    assert verdict["grade"] == grade and verdict["source"] == "rule"
    if intent:
        assert verdict["intent"] == intent


def test_mixed_answer_is_left_to_llm_then_default_mid_with_reask():
    verdict = judge.judge("아들한테 물어보고 보내 줄게요", ctx_for())
    assert verdict == {**verdict, "grade": "중답", "source": "default", "reask": True}


def test_llm_is_used_only_when_rules_cannot_decide(monkeypatch):
    calls = []
    monkeypatch.setenv("SIM_LLM_BASE_URL", "http://gpu.example/v1")
    monkeypatch.setattr(judge, "_ask_gpu", lambda text, ctx: calls.append(text) or {"grade": "정답", "intent": "끊기", "confidence": 0.9})
    assert judge.judge("음 그게 좀", ctx_for())["source"] == "llm"
    assert judge.judge("112에 신고할게요", ctx_for())["source"] == "rule"
    assert calls == ["음 그게 좀"]
    # LLM이 정답이라 해도 의도가 위험하면 더 나쁜 쪽으로 본다.
    assert judge._parse('{"grade":"정답","intent":"송금동의","confidence":0.9}')["grade"] == "오답"


def test_wrong_llm_address_still_runs_to_the_end(monkeypatch):
    monkeypatch.setenv("SIM_LLM_BASE_URL", BROKEN_LLM)
    monkeypatch.setenv("SIM_LLM_TIMEOUT", "1")
    graph = engine.get_graph("agency_call")
    state, result = play(graph, ["음 그게"] * 8)
    assert {t["source"] for t in state["turns"]} == {"default"}
    assert state["terminal"] == "t_quit" and result["status"] == "done"


def test_free_text_install_goes_to_app_loss_terminal():
    graph = engine.get_graph("agency_call")
    state, _ = play(graph, ["오답", "오답", "오답", "보안 앱 설치할게요"])
    assert state["terminal"] == "t_loss_app"


# ---------- API ----------
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def device(client, name="어머니"):
    token = client.post("/v1/devices", json={"name": name}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_sim_api_requires_device_token(client):
    assert client.get("/v1/sim/scenarios").status_code == 401
    assert client.post("/v1/sim/sessions", json={"scenario_id": "agency_call"}).status_code == 401
    assert client.get("/v1/me/score").status_code == 401


def test_sim_api_lists_agency_first_with_badge(client):
    h = device(client)
    body = client.get("/v1/sim/scenarios", headers=h).json()
    assert body["items"][0]["id"] == "agency_call" and body["items"][0]["badge"]
    assert body["default"] == "agency_call"
    assert {p["id"] for p in body["presets"]} >= {"mother_74_alone", "father_68_retired"}


def test_profile_fields_are_saved_and_old_clients_still_work(client):
    h = device(client)
    assert client.put("/v1/devices/me", headers=h, json={"role": "mom", "memo": "첫째"}).status_code == 200
    assert client.get("/v1/devices/me", headers=h).json() == {"name": "어머니", "role": "mom", "memo": "첫째"}
    profile = {"age_band": "60s", "family_terms": ["딸"], "main_bank": "국민은행", "region": "서울", "entered_by": "guardian"}
    assert client.put("/v1/devices/me", headers=h, json=profile).status_code == 200
    me = client.get("/v1/devices/me", headers=h).json()
    assert me["role"] == "mom" and me["memo"] == "첫째" and me["sim_profile"] == profile
    assert client.put("/v1/devices/me", headers=h, json={"preset": "mother_74_alone"}).status_code == 200
    assert client.get("/v1/devices/me", headers=h).json()["sim_profile"]["family_terms"] == ["큰아들", "작은아들"]
    for bad in ({"age_band": "50s"}, {"entered_by": "police"}, {"preset": "nope"}, {"family_terms": []}, {"phone": "010"}):
        assert client.put("/v1/devices/me", headers=h, json=bad).status_code == 422, bad


def test_sim_api_full_session_keeps_user_text_as_plain_text(client):
    h = device(client)
    client.put("/v1/devices/me", headers=h, json={"preset": "father_68_retired"})
    started = client.post("/v1/sim/sessions", headers=h, json={"scenario_id": "prosecutor_impersonation", "mode": "chat"}).json()
    sid = started["session_id"]
    assert started["scenario"]["id"] == "agency_call" and "선생님" in started["scene"]["lines"][0]
    r = client.post(f"/v1/sim/sessions/{sid}/turn", headers=h, json={"text": "<b>x</b>", "input_type": "text"})
    assert r.status_code == 200 and r.json()["judge"]["reask"] is True
    best = next(c.id for c in engine.get_graph("agency_call").nodes["n1_intro"].choices if c.grade == "정답")
    r = client.post(f"/v1/sim/sessions/{sid}/turn", headers=h, json={"choice_id": best}).json()
    assert r["status"] == "closing"
    other = device(client, "남")
    assert client.post(f"/v1/sim/sessions/{sid}/closing", headers=other, json={"option_ids": ["k1"]}).status_code == 404
    result = client.post(f"/v1/sim/sessions/{sid}/closing", headers=h, json={"option_ids": ["k1", "k2", "k3"]}).json()
    assert result["scenes"][0]["answers"][0]["text"] == "<b>x</b>"
    assert result["score"]["total"] > 0 and result["next"]["id"] != "agency_call"
    assert client.get(f"/v1/sim/sessions/{sid}/result", headers=h).json()["score"] == result["score"]
    assert client.post(f"/v1/sim/sessions/{sid}/turn", headers=h, json={"choice_id": best}).status_code == 409


def test_me_score_shows_history_delta_and_weakness(client):
    h = device(client, "점수")
    for grades, closing in ((["오답"] * 4, []), (["정답"], ["k1", "k2", "k3"])):
        sid = client.post("/v1/sim/sessions", headers=h, json={"scenario_id": "agency_call"}).json()["session_id"]
        for grade in grades:
            node = client.get(f"/v1/sim/sessions/{sid}/result", headers=h).json()["current_node"]
            choice = next(c.id for c in engine.get_graph("agency_call").nodes[node].choices if c.grade == grade)
            r = client.post(f"/v1/sim/sessions/{sid}/turn", headers=h, json={"choice_id": choice}).json()
            if r["status"] != "active":
                break
        client.post(f"/v1/sim/sessions/{sid}/closing", headers=h, json={"option_ids": closing})
    score = client.get("/v1/me/score", headers=h).json()
    assert score["latest"]["total"] == 100 and len(score["history"]) == 2
    assert score["delta_first_last"] == 100 - score["history"][0]["total"]
    assert score["weakness_top3"][0]["scam_type"] == "기관사칭" and 0 < score["weakness_top3"][0]["value"] <= 1
    assert score["streak_days"] == 1


def test_tts_and_stt_report_fallback_when_gpu_is_missing_or_broken(client, monkeypatch):
    h = device(client)
    r = client.post("/v1/sim/tts", headers=h, json={"text": "여보세요"})
    assert r.status_code == 501 and r.json()["fallback"] == "browser"
    r = client.post("/v1/sim/stt", headers={**h, "Content-Type": "audio/webm"}, content=b"\x00" * 10)
    assert r.status_code == 501 and r.json()["fallback"] == "browser"
    monkeypatch.setenv("SIM_TTS_URL", BROKEN_LLM)
    monkeypatch.setenv("SIM_STT_URL", BROKEN_LLM)
    assert client.post("/v1/sim/tts", headers=h, json={"text": "여보세요"}).status_code == 502
    assert client.post("/v1/sim/stt", headers={**h, "Content-Type": "audio/webm"}, content=b"\x00" * 10).status_code == 502


def test_gpu_is_warmed_once_per_five_minutes_and_never_without_address(monkeypatch):
    import httpx

    from guard import sim_api

    calls = []
    monkeypatch.setattr(httpx, "get", lambda url, **kw: calls.append(url))
    monkeypatch.setattr(sim_api, "_warm", {"at": 0.0})
    sim_api.warm_gpu()
    assert calls == []  # 주소가 없으면 부르지 않는다
    monkeypatch.setenv("SIM_LLM_BASE_URL", "http://gpu.example/v1/")
    sim_api.warm_gpu()
    sim_api.warm_gpu()
    assert calls == ["http://gpu.example/v1/models"]


def test_scene_carries_tone_and_tts_sends_emotion(client, monkeypatch, tmp_path):
    import httpx

    from guard import sim_api

    graph = engine.get_graph("agency_call")
    state = engine.start(graph, preset_profile("mother_74_alone"), seed=1)
    assert engine.scene(graph, state)["tone"] == graph.nodes["n1_intro"].tone
    assert engine.scene(graph, state, pressure="더 미는 말")["tone"] == graph.nodes["n1_intro"].pressure_tone

    sent = []

    class FakeResponse:
        headers = {"content-type": "audio/wav"}
        content = b"RIFF0000WAVE"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(httpx, "post", lambda url, json=None, **kw: sent.append(json) or FakeResponse())
    monkeypatch.setattr(sim_api, "TTS_CACHE", tmp_path)
    monkeypatch.setenv("SIM_TTS_URL", "http://gpu.example/tts")
    h = device(client, "말투")
    r = client.post("/v1/sim/tts", headers=h, json={"text": "지금 끊으면 구속됩니다", "tone": "threat"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert sent[-1]["emotion"] == "threat" and sent[-1]["instruct"] and sent[-1]["text"] == "지금 끊으면 구속됩니다"
    client.post("/v1/sim/tts", headers=h, json={"text": "지금 끊으면 구속됩니다", "tone": "threat"})
    assert len(sent) == 1  # 같은 말·같은 말투는 캐시에서
    client.post("/v1/sim/tts", headers=h, json={"text": "지금 끊으면 구속됩니다", "tone": "tremble"})
    assert len(sent) == 2 and sent[-1]["emotion"] == "tremble"  # 말투가 다르면 다시 합성
    assert client.post("/v1/sim/tts", headers=h, json={"text": "x", "tone": "angry"}).status_code == 422
