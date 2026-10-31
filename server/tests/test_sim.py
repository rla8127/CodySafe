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
    for key in ("SIM_LLM_BASE_URL", "SIM_LLM_API_KEY", "SIM_LLM_MODEL", "SIM_FALLBACK", "SIM_TTS_URL", "SIM_STT_URL",
                "SIM_TTS_API_KEY", "SIM_STT_API_KEY"):
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


# ---------- GAF 검토(11-01) 필수 수정 회귀 시험 ----------
# 1번: 위험한 답이 안전 낱말 때문에 정답으로 판정되던 예문. 보류셋(judge_holdout.csv)과 따로 둔다.
@pytest.mark.parametrize("text, expected", [
    ("네 가족한테 말하지 않을게요", "오답"),
    ("큰아들한테 전화 안 할게요", "오답"),
    ("아들한테 절대 안 알릴게요", "오답"),
    ("가족한테는 얘기 안 할게요", "오답"),
    ("네 지금 주소 확인할게요", None),
    ("링크에서 확인할게요", None),
    ("문자 왔나 확인할게요", None),
    ("인증번호 문자 온 거 확인해 보고 불러 드릴게요", "오답"),
    ("계좌번호 집에 가서 확인해 보고 말씀드릴게요", "오답"),
    ("암구호는 모르겠고 입금했습니다", "오답"),
    ("이미 보냈어요", "오답"),
    ("앱 설치했어요", "오답"),
    ("112는 안 부를게요", None),
    ("신고 안 해요", None),
    ("신고할 필요 없어요", None),
    ("사기 아니면 돈 보내요", None),
    ("제가 사기에 연루됐다고요? 어떡해요", None),
    ("사기 계좌라니 빨리 옮겨야겠네요", None),
    ("이거 사기 아니에요?", None),
])
def test_dangerous_answers_are_never_judged_safe(text, expected):
    verdict = judge.judge(text, {**ctx_for(), "family_terms": ["큰아들"]})
    assert verdict["grade"] != "정답", verdict
    if expected:
        assert verdict["grade"] == expected and verdict["source"] == "rule", verdict


@pytest.mark.parametrize("text, intent", [
    ("인증번호는 절대 안 알려드릴게요", "거절"),
    ("이거 사기죠 안 보내요", "거절"),
    ("은행에 직접 전화해서 확인할게요", "공식번호확인"),
    ("1332에 확인해 볼게요", "공식번호확인"),
    ("택배앱에서 운송장 확인할게요", "공식번호확인"),
    ("암구호 물어볼게요", "가족확인"),
    ("딸한테 먼저 연락해 볼게요", "가족확인"),
    ("경찰서에 가서 물어볼게요", "신고"),
    ("전화 안 받을래요 끊을게요", "끊기"),
])
def test_clear_safe_answers_stay_safe_after_the_fix(text, intent):
    verdict = judge.judge(text, ctx_for())
    assert verdict["grade"] == "정답" and verdict["intent"] == intent, verdict


def test_done_transfer_ends_in_money_loss_even_with_a_safe_word():
    graph = engine.get_graph("agency_call")
    state = engine.start(graph, preset_profile("mother_74_alone"), seed=7)
    response = engine.turn(graph, state, text="암구호는 모르겠고 입금했습니다", input_type="text")
    assert response["status"] == "closing" and state["terminal"] == "t_loss_money"


# 2번: 확인행동은 설계식 min(25, 10·공식번호확인 + 10·가족확인 + 5·신고)만. '기타'는 감점하지 않는다.
@pytest.mark.parametrize("closing, verify", [
    (["k1", "k2", "k3"], 25), (["k1", "k2", "k3", "k4", "k5"], 25), (["k4", "k5"], 0), ([], 0),
    (["k1", "k1", "k3"], 15), (["k2"], 10),
])
def test_closing_points_follow_the_design_formula(closing, verify):
    graph = engine.get_graph("agency_call")
    _, result = play(graph, ["정답"], closing=closing)
    assert result["score"]["breakdown"]["확인행동"] == verify


# 3번: 예약된 가상 도메인만 허용하고, 화면에 나오는 모든 칸을 검사한다.
@pytest.mark.parametrize("url", ["https://test.com/app", "test.com/app", "https://bank.example.kr", "http://x.invalid.com",
                                 "www.example-bank.co.kr"])
def test_validator_rejects_real_looking_domains(url):
    assert validate.scan_unsafe(f"{url} 을 여세요"), url


@pytest.mark.parametrize("url", ["https://parcel-kr.example/a7", "www.example.com/x", "http://a.b.test", "https://x.example.org/y",
                                 "https://y.invalid"])
def test_validator_allows_reserved_example_domains(url):
    assert validate.scan_unsafe(url) == [], url


@pytest.mark.parametrize("break_it", [
    lambda g: g["persona"].update(name="수사관 02-3480-2000"),
    lambda g: g["persona"].update(role="https://test.com 담당"),
    lambda g: g.update(summary="www.real-bank.com 사칭"),
    lambda g: g["nodes"]["n1_intro"]["red_flags"].append("010-1234-5678 번호"),
    lambda g: g["nodes"]["n1_intro"].update(goal="계좌 110-234-567890 받기"),
    lambda g: g["closing"]["options"][0].update(why="https://test.com 참고"),
])
def test_validator_checks_persona_summary_flags_and_closing(break_it):
    data = graph_data()
    break_it(data)
    assert validate.validate(data), "검사기가 표시 칸의 실제 같은 값을 놓침"


def test_source_refs_official_urls_are_not_flagged():
    data = graph_data()
    assert any(not r["url"].endswith(".example") for r in data["source_refs"])
    assert validate.validate(data) == []


# 5번: 판정 유보(reask) 뒤 다음 장면·종료로 넘어가면 새 장면에 '못 알아들었어요'를 띄우지 않는다.
def test_reask_is_cleared_when_the_scene_moves_on():
    graph = engine.get_graph("agency_call")
    state = engine.start(graph, preset_profile("mother_74_alone"), seed=7)
    unsure = lambda text, ctx: {"grade": "중답", "intent": "되묻기", "confidence": 0.0, "leaks": [], "source": "default", "reask": True}
    first = engine.turn(graph, state, text="음 그게", input_type="text", judge_fn=unsure)
    assert first["judge"]["reask"] is True and first["scene"]["node_id"] == "n1_intro"  # 같은 장면: 되묻기
    second = engine.turn(graph, state, text="음 그게", input_type="text", judge_fn=unsure)
    assert second["scene"]["node_id"] != "n1_intro" and second["judge"]["reask"] is False
    while state["status"] == "active":
        before = state["node"]
        last = engine.turn(graph, state, text="음 그게", input_type="text", judge_fn=unsure)
        moved = last["status"] != "active" or last["scene"]["node_id"] != before
        assert last["judge"]["reask"] is (not moved)
    assert last["status"] == "closing" and last["judge"]["reask"] is False


# 6번: LLM 토큰은 같은 호스트에만. TTS·STT는 저마다의 키를 쓴다.
def test_llm_token_is_not_sent_to_other_tts_or_stt_hosts(monkeypatch):
    from guard import sim_api

    monkeypatch.setenv("SIM_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SIM_LLM_API_KEY", "llm-token")
    monkeypatch.setenv("SIM_TTS_URL", "https://other-tts.example/v1/audio/speech")
    monkeypatch.setenv("SIM_STT_URL", "https://other-stt.example/v1/audio/transcriptions")
    assert sim_api._gpu_headers("tts") == {} and sim_api._gpu_headers("stt") == {}
    monkeypatch.setenv("SIM_TTS_URL", "https://llm.example/tts")
    monkeypatch.setenv("SIM_STT_URL", "https://llm.example/stt")
    assert sim_api._gpu_headers("tts") == {"Authorization": "Bearer llm-token"}
    assert sim_api._gpu_headers("stt") == {"Authorization": "Bearer llm-token"}
    monkeypatch.setenv("SIM_TTS_API_KEY", "tts-token")
    monkeypatch.setenv("SIM_STT_API_KEY", "stt-token")
    assert sim_api._gpu_headers("tts") == {"Authorization": "Bearer tts-token"}
    assert sim_api._gpu_headers("stt") == {"Authorization": "Bearer stt-token"}


def test_stt_request_uses_stt_key_not_llm_key(monkeypatch):
    import httpx

    from guard import sim_api

    seen = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"text": "끊을게요"}

    monkeypatch.setattr(httpx, "post", lambda url, **kw: seen.append(kw.get("headers")) or FakeResponse())
    monkeypatch.setenv("SIM_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("SIM_LLM_API_KEY", "llm-token")
    monkeypatch.setenv("SIM_STT_URL", "https://stt-provider.example/v1/audio/transcriptions")
    assert sim_api.call_stt(b"x", "audio/webm") == "끊을게요"
    assert seen[-1] == {}


# 4번: 늦게 온 음성 인식 결과는 녹음을 시작한 세션·장면·차례와 같을 때만 답으로 낸다(sim2.js, Node로 함수 단위 확인).
def test_late_stt_result_is_dropped_after_session_or_scene_changes(tmp_path):
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    src = (engine.GRAPH_DIR.parents[2] / "web" / "sim2.js").read_text(encoding="utf-8")
    parts = [re.search(r"function %s\(.*?\n}\n" % name, src, re.S).group(0) for name in ("s2Ticket", "s2Fresh", "s2CancelStt")]
    assert src.count("s2Fresh(ticket)") >= 3  # GPU 녹음 두 곳 + 브라우저 인식 한 곳
    harness = """
const S2 = { session: { session_id: 'old' }, scene: { node_id: 'n1', turn: 1 }, busy: false, sttGen: 0, sttAbort: null };
const $ = () => ({});
""" + "\n".join(parts) + """
const out = [];
let t = s2Ticket(); out.push(s2Fresh(t));
S2.session = { session_id: 'new' }; out.push(s2Fresh(t));
S2.session = { session_id: 'old' }; S2.scene = { node_id: 'n2', turn: 2 }; out.push(s2Fresh(t));
S2.scene = { node_id: 'n1', turn: 1 }; let aborted = false; S2.sttAbort = { abort() { aborted = true; } };
s2CancelStt(); out.push(s2Fresh(t)); out.push(aborted);
t = s2Ticket(); S2.busy = true; out.push(s2Fresh(t));
console.log(JSON.stringify(out));
"""
    script = tmp_path / "h.js"
    script.write_text(harness, encoding="utf-8")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [True, False, False, False, True, False]
