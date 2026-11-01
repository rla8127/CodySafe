"""모의 훈련 대본 그래프와 훈련 프로필의 형식(plan-ai 5-3·5-4절).

그래프는 장면(node)과 종료(terminal)로 이루어진다. 장면마다 정답·중답·오답 선택지가 하나씩 있고,
엔진은 판정 결과의 등급으로 다음 장면을 고른다. 대사 안의 {user_title} 같은 칸은 프로필로 채운다.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Grade = Literal["정답", "중답", "오답"]
GRADES: tuple[str, ...] = ("정답", "중답", "오답")

# 판정 의도. 정답 쪽 5개는 점수의 '알아차림' 기준(plan-ai 5-4절 k)이기도 하다.
SAFE_INTENTS = ("끊기", "거절", "공식번호확인", "가족확인", "신고")
MID_INTENTS = ("되묻기", "망설임")
BAD_INTENTS = ("따르기", "정보제공", "송금동의", "앱설치동의")
INTENTS: tuple[str, ...] = SAFE_INTENTS + MID_INTENTS + BAD_INTENTS
GRADE_OF_INTENT = {**{i: "정답" for i in SAFE_INTENTS}, **{i: "중답" for i in MID_INTENTS}, **{i: "오답" for i in BAD_INTENTS}}

Intent = Literal["끊기", "거절", "공식번호확인", "가족확인", "신고", "되묻기", "망설임", "따르기", "정보제공", "송금동의", "앱설치동의"]
Leak = Literal["인증번호", "계좌", "비밀번호", "신분증"]
LossKind = Literal["송금", "앱설치", "정보유출"]
ScamType = Literal["기관사칭", "대출빙자", "가족지인사칭", "스미싱", "투자사기", "로맨스스캠", "중고거래사기", "기타"]
Channel = Literal["call", "chat", "sms", "video"]
Stage = Literal["접근", "신뢰", "공포·긴급", "요구", "압박", "마무리"]
Tactic = Literal["권위", "공포", "긴급", "비밀유지", "보상", "동정", "고립"]
ClosingKind = Literal["공식번호확인", "가족확인", "신고", "기타"]
Tone = Literal["calm", "official", "urgent", "threat", "tremble", "sob", "friendly"]
# 음성 합성에 넘기는 말투 지시. 임대 GPU TTS가 감정 표현을 지원하면 이 글을 따르고, 브라우저 음성은 빠르기·높낮이만 바꾼다.
TONE_GUIDE = {
    "calm": "차분하고 또박또박하게",
    "official": "공무원처럼 딱딱하고 사무적인 말투로, 조금 낮은 목소리로",
    "urgent": "다급하고 빠르게, 재촉하듯이",
    "threat": "위압적으로 다그치듯, 단호하고 낮게",
    "tremble": "불안해서 떨리는 목소리로, 숨이 가쁘게",
    "sob": "울먹이며 흐느끼듯, 말끝이 떨리게",
    "friendly": "다정하고 밝게",
}

MAX_STAY = 2  # 한 장면에서 받을 수 있는 최대 답 수
MAX_TURNS = 8  # 한 대본에서 받을 수 있는 최대 답 수
CLOSING_POINTS = {"공식번호확인": 10, "가족확인": 10, "신고": 5}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceRef(_Strict):
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    published_at: str = ""
    publisher: str = ""
    note: str = ""


class Persona(_Strict):
    role: str
    name: str
    tone: str = ""


class Choice(_Strict):
    id: str = Field(min_length=1)
    grade: Grade
    intent: Intent
    text: str = Field(min_length=1)
    next: str = Field(min_length=1)
    act: Literal["say", "do"] = "say"  # say: 말로 답함, do: 행동(끊기·신고 등)
    leaks: list[Leak] = []


class Media(_Strict):
    kind: Literal["sms", "link", "file"]
    text: str


class Video(_Strict):
    # 예비 자료의 합성 얼굴 영상 이름(server/backup/video/<이름>.mp4, O-2). 자녀 호칭에 '딸'이 있으면 daughter를 쓴다.
    son: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    daughter: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    caption: str = Field(min_length=1)


class Node(_Strict):
    stage: Stage
    tactics: list[Tactic]
    goal: str
    lines: list[str] = Field(min_length=1)
    red_flags: list[str] = Field(min_length=1)
    choices: list[Choice]
    pressure: list[str] = Field(min_length=1)  # 중답 뒤 한 번 더 미는 말
    tone: Tone = "calm"  # 이 장면 대사의 말투
    pressure_tone: Tone = "threat"  # 한 번 더 미는 말의 말투
    debrief: str
    media: Media | None = None
    video: Video | None = None  # 대사·문자와 함께 보이는 영상 메시지(대사 음성 열쇠와는 무관)


class Terminal(_Strict):
    type: Literal["safe", "loss"]
    loss: LossKind | None = None
    message: str
    by: Literal["user", "scammer"] = "user"  # scammer: 사기범이 먼저 끊음(사용자가 끊은 것이 아님)


class Bait(_Strict):
    otp: str = Field(pattern=r"^\d{6}$")


class ClosingOption(_Strict):
    id: str
    text: str
    points: int
    kind: ClosingKind
    why: str = ""


class Closing(_Strict):
    question: str
    options: list[ClosingOption] = Field(min_length=3)


class Graph(_Strict):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    title: str
    scam_type: ScamType
    channel: Channel
    impersonated: str
    difficulty: Literal["쉬움", "보통", "어려움"]
    synthetic: bool
    source_refs: list[SourceRef] = Field(min_length=1)
    persona: Persona
    slots: list[str]
    start: str
    nodes: dict[str, Node]
    terminals: dict[str, Terminal]
    bait: Bait
    closing: Closing
    aliases: list[str] = []  # 탐지 결과의 수법 id(scam_kb) 같은 다른 이름
    summary: str = ""


# ---------- 훈련 프로필(MVP 4칸 + 입력자). 실명·전화번호·종교 칸은 두지 않는다 ----------
AgeBand = Literal["60s", "70s", "80plus"]


class SimProfile(_Strict):
    age_band: AgeBand = "70s"
    family_terms: list[str] = Field(default_factory=lambda: ["아들"], min_length=1, max_length=4)
    main_bank: str = Field(default="농협", min_length=1, max_length=12)
    region: str = Field(default="서울", min_length=1, max_length=12)
    entered_by: Literal["self", "guardian"] = "self"  # 자기 신고. 본인 확인은 하지 않는다


PRESETS: dict[str, dict] = {
    "mother_74_alone": {
        "label": "혼자 사시는 70대 어머니",
        "profile": {"age_band": "70s", "family_terms": ["큰아들", "작은아들"], "main_bank": "농협", "region": "대구"},
    },
    "father_68_retired": {
        "label": "은퇴하신 60대 아버지",
        "profile": {"age_band": "60s", "family_terms": ["딸"], "main_bank": "국민은행", "region": "서울"},
    },
    "grandma_82": {
        "label": "80대 할머니",
        "profile": {"age_band": "80plus", "family_terms": ["손주", "며느리"], "main_bank": "우체국", "region": "전남"},
    },
}
DEFAULT_PRESET = "mother_74_alone"


def preset_profile(preset_id: str) -> SimProfile:
    return SimProfile(**PRESETS[preset_id]["profile"])
