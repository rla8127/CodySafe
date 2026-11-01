"""Presets for the family-impersonation video-call training clips (all people FICTIONAL, scripts paraphrased/fake).

A preset = age band x gender x story x expression ->
  face_prompt (gpu/face.py), TTS voice + rate + lines (codysafe-voice /tts), EchoMimicV3 prompt (gpu/video.py).

    from deepfake_presets import build, PRESETS
    p = build("20s_late", "male", "accident_settlement")       # any combination
    p = PRESETS["son_accident"]                                 # the two clips made for the demo

CLI:  python gpu/deepfake_presets.py            -> list options and the ready-made presets

Scripts contain no real names, phone numbers, account numbers, bank names or URLs.
TTS voices exist only for a son (late 20s, "family") and a daughter (early 20s, "family_female");
other age bands reuse the voice of the same gender (the face changes, the voice does not).
"""

AGE_BANDS = {
    "20s_early": "in {pos} early 20s",
    "20s_late": "in {pos} late 20s",
    "30s": "in {pos} 30s",
}

GENDERS = {
    "male": {"noun": "man", "pos": "his", "relation": "son", "voice": "family",
             "look": "short black hair, plain dark t-shirt"},
    "female": {"noun": "woman", "pos": "her", "relation": "daughter", "voice": "family_female",
               "look": "shoulder-length black hair, plain light beige t-shirt, no makeup look"},
}

EXPRESSIONS = {
    "worried": {
        "face": "worried and anxious expression, eyebrows drawn together and slightly raised in the middle, "
                "tense forehead, tense lips, mouth closed, eyes glistening with worry",
        "video": "is worried and anxious, eyebrows drawn together, speaking urgently and pleadingly",
    },
    "calm": {
        "face": "neutral calm expression, mouth closed",
        "video": "is calm, speaking naturally",
    },
}

# Lines are addressed to mother ("엄마"); 4 lines -> about 27 s at rate 5.0 syllables/s.
STORIES = {
    "accident_settlement": {
        "title": "접촉사고 합의금",
        "lines": [
            "엄마, 나야. 놀라지 말고 들어. 폰 액정이 깨져서, 지금 친구 폰으로 영상통화 하는 거야.",
            "오늘 운전하다가 접촉 사고가 났어. 상대방이 합의금을 오늘 안에 안 주면 경찰에 신고한대.",
            "아빠한테는 말하지 마. 내 통장이 막혀서 그래. 친구 계좌로 좀 보내 줘. 엄마, 부탁이야.",
            "지금 너무 무서워서 그래. 이 폰은 곧 돌려줘야 하니까, 보내고 나서 문자로만 알려 줘.",
        ],
    },
    "deposit_phone_broken": {
        "title": "휴대폰 액정 깨짐 + 자취방 보증금",
        "lines": [
            "엄마, 나야. 폰을 떨어뜨려서 액정이 다 깨졌어. 지금 친구 폰 빌려서 전화하는 거야.",
            "근데 오늘까지 자취방 보증금 잔금을 못 넣으면, 계약이 취소된대. 폰 수리비도 내야 하고.",
            "내 계좌는 폰 인증이 안 돼서 못 써. 친구 계좌로 보내 주면 바로 처리할게. 엄마, 급해.",
            "집주인 아저씨가 계속 연락해서 그래. 이 폰은 곧 돌려줘야 하니까, 보내고 나서 문자로만 알려 줘.",
        ],
    },
    "hospital_bill": {
        "title": "다쳐서 병원비",
        "lines": [
            "엄마, 나야. 놀라지 마. 계단에서 넘어져서 지금 병원 응급실이야. 폰은 그때 망가졌어.",
            "검사비랑 치료비를 먼저 내야 한대. 지금 간호사 선생님 폰 잠깐 빌려서 하는 거야.",
            "아빠는 걱정하니까 나중에 말할게. 친구 계좌로 보내 주면 친구가 대신 내 준대. 빨리.",
            "지금 검사 들어가야 해서 전화는 못 받아. 보내고 나서 문자로만 알려 줘.",
        ],
    },
}

DEFAULT_RATE = 5.0  # syllables/s: worried but natural (5.6+ sounded rushed in round 1)


def build(age: str, gender: str, story: str, expression: str = "worried", rate: float = DEFAULT_RATE) -> dict:
    g, e, s = GENDERS[gender], EXPRESSIONS[expression], STORIES[story]
    who = f"a fictional Korean {g['noun']} {AGE_BANDS[age].format(pos=g['pos'])}"
    face_prompt = (
        f"Photorealistic head-and-shoulders portrait photo of {who}, {g['look']}, facing the camera straight on, "
        f"eyes looking directly into the camera, {e['face']}, face centered, shoulders up, plain light grey "
        "background, soft even indoor lighting, sharp focus, natural skin texture, no text, no watermark, "
        "no logo, no glasses, no hands"
    )
    video_prompt = (f"A young Korean {g['noun']} {e['video']} to the camera on a phone video call, "
                    "clear mouth movements matching the speech.")
    return {
        "name": f"{g['relation']}_{age}_{story}_{expression}",
        "relation": g["relation"], "age": age, "gender": gender, "story": story, "story_title": s["title"],
        "expression": expression, "face_prompt": face_prompt, "voice": g["voice"], "rate": rate,
        "lines": list(s["lines"]), "video_prompt": video_prompt,
    }


PRESETS = {
    "son_accident": build("20s_late", "male", "accident_settlement"),
    "daughter_deposit": build("20s_early", "female", "deposit_phone_broken"),
}


if __name__ == "__main__":
    print("age:", ", ".join(AGE_BANDS))
    print("gender:", ", ".join(GENDERS))
    print("story:", ", ".join(f"{k} ({v['title']})" for k, v in STORIES.items()))
    print("expression:", ", ".join(EXPRESSIONS))
    for k, p in PRESETS.items():
        print(f"\n[{k}] {p['name']} voice={p['voice']} rate={p['rate']}")
        print("  face:", p["face_prompt"])
        print("  video:", p["video_prompt"])
