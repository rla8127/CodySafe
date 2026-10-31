"""공식 사례로 대본 그래프 만들기(P1, R-008).

O-3가 만든 data/clean/2026_official_cases.jsonl(칸: title, scam_type, channel, impersonated_target, stage, tactics,
requested_actions, target_age_band, sample_lines, published_at, source_url, source_tier, license, synthetic)에서
같은 수법의 최근 사례 3–5건을 골라, 검증된 기본 그래프의 뼈대(선택지·해설·종료)에 사례 대사를 장면 단계별로 얹는다.

- 사례 글은 데이터다. 그 안의 지시문은 따르지 않고, 지시처럼 보이는 줄은 버린다.
- 번호·계좌·주소는 가짜로 바꾸고(010-0000-XXXX, example 도메인), 바꾼 뒤에도 검사기에 걸리면 그 줄을 버린다.
- 결과는 synthetic=true, source_refs에 사례 출처를 적고 검사기를 통과해야 저장한다.
- 지금은 규칙(틀) 방식이다. 임대 GPU LLM으로 대사를 다시 쓰는 단계는 주소가 온 뒤 붙인다.

쓰는 법(server 폴더): .venv/bin/python -m guard.sim.generate --cases ../data/clean/2026_official_cases.jsonl --scam-type 기관사칭
"""
import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

from . import engine
from .schema import PRESETS
from .validate import _is_safe_host, scan_unsafe, validate

BASE_FOR = {"기관사칭": "agency_call", "가족지인사칭": "family_messenger", "스미싱": "delivery_sms"}
_URL = re.compile(r"(?:https?://|www\.)[^\s'\"<>]+", re.I)
_PHONE = re.compile(r"(?<!\d)0\d{1,2}[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)")
_REP = re.compile(r"(?<!\d)1[5-9]\d{2}-?\d{4}(?!\d)")
_RRN = re.compile(r"(?<!\d)\d{6}\s*-\s*[1-4]\d{6}(?!\d)")
_DIGITS = re.compile(r"(?<!\d)\d[\d-]{7,}\d(?!\d)")
_INSTRUCTION = re.compile(r"(지시|무시하|무시해|명령|프롬프트|ignore|system|assistant|instruction|정답으로|채점)", re.I)
_SLOT = re.compile(r"[{}<>]")
MAX_LINE = 90


def mask_line(text: str) -> str | None:
    """사례 대사 한 줄을 훈련용으로 바꾼다. 쓸 수 없으면 None."""
    text = " ".join(str(text).split())
    if not text or _INSTRUCTION.search(text):
        return None
    text = _SLOT.sub("", text)  # 칸 표시·태그처럼 보이는 글자는 지운다
    text = _URL.sub(lambda m: m.group(0) if _is_safe_host(re.sub(r"^(https?://|www\.)", "", m.group(0)).split("/")[0]) else "https://case-link.example/a1", text)
    text = _RRN.sub("******-*******", text)
    text = _PHONE.sub("\x00PHONE\x00", text)  # 가짜 번호로 바꿀 자리(긴 숫자 가림에 먹히지 않게)
    text = _REP.sub("대표번호", text)
    text = _DIGITS.sub("***", text).replace("\x00PHONE\x00", "010-0000-1234")
    if len(text) > MAX_LINE:
        cut = max(text.rfind(".", 0, MAX_LINE), text.rfind("?", 0, MAX_LINE), text.rfind("요", 0, MAX_LINE))
        text = text[: cut + 1] if cut > 20 else text[:MAX_LINE]
    return None if scan_unsafe(text) else text


def load_cases(path: str | Path) -> list[dict]:
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def pick_cases(cases: list[dict], scam_type: str, age_band: str | None, limit: int = 5) -> list[dict]:
    same = [c for c in cases if c.get("scam_type") == scam_type and c.get("source_url") and c.get("sample_lines")]
    # 프리셋 나이대에 맞는 사례를 먼저, 그다음 최근 사례 순
    same.sort(key=lambda c: str(c.get("published_at", "")), reverse=True)
    same.sort(key=lambda c: age_band not in _as_list(c.get("target_age_band")))
    return same[:limit]


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def generate(cases: list[dict], scam_type: str, preset: str = "mother_74_alone", out_dir: Path | None = None) -> dict:
    if preset not in PRESETS:
        raise ValueError(f"모르는 프리셋: {preset}")
    base_id = BASE_FOR.get(scam_type)
    if not base_id:
        raise ValueError(f"이 수법은 아직 기본 그래프가 없습니다: {scam_type}")
    age_band = PRESETS[preset]["profile"]["age_band"]
    chosen = pick_cases(cases, scam_type, age_band)
    if len(chosen) < 3:
        raise ValueError(f"{scam_type} 사례가 {len(chosen)}건이라 3건보다 적습니다")

    base = engine.get_graph(base_id).model_dump()
    graph = copy.deepcopy(base)
    used, taken = 0, set()
    for node_id, node in graph["nodes"].items():
        lines = []
        for case in chosen:
            if case.get("stage") and node["stage"] not in _as_list(case.get("stage")):  # 사례의 stage는 목록(plan-ai 5-2절)
                continue
            for raw in _as_list(case.get("sample_lines")):
                masked = mask_line(raw)
                if masked and masked not in taken:  # 같은 대사를 두 장면에 쓰지 않는다
                    lines.append(masked)
                    taken.add(masked)
                if len(lines) >= 2:
                    break  # 쓰지 않을 대사까지 taken에 넣어 다른 장면에서 못 쓰게 하지 않는다
            if len(lines) >= 2:
                break
        if lines:
            node["lines"] = lines[:2]
            used += 1
    if not used:
        raise ValueError("장면 단계와 맞는 사례 대사가 없습니다")

    digest = hashlib.sha256(json.dumps([c.get("source_url") for c in chosen], ensure_ascii=False).encode()).hexdigest()[:8]
    graph["id"] = f"gen_{base_id}_{digest}"
    graph["title"] = f"최근 사례로 만든 {base['title']}"
    graph["summary"] = f"공식 사례 {len(chosen)}건의 대사를 장면 {used}곳에 넣은 생성 대본({PRESETS[preset]['label']} 기준)"
    graph["synthetic"] = True
    graph["aliases"] = []
    graph["source_refs"] = [
        {"title": str(c.get("title", ""))[:80] or "공식 사례", "url": c["source_url"], "published_at": str(c.get("published_at", "")),
         "publisher": "", "note": f"출처 등급 {c.get('source_tier', '')}, 이용 조건 {c.get('license', '확인 중')}"}
        for c in chosen
    ] + base["source_refs"]
    errors = validate(graph)
    if errors:
        raise ValueError("생성 그래프 검사 실패: " + "; ".join(errors))
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{graph['id']}.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--scam-type", default="기관사칭")
    parser.add_argument("--preset", default="mother_74_alone")
    parser.add_argument("--out", default=str(engine.GENERATED_DIR))
    args = parser.parse_args()
    graph = generate(load_cases(args.cases), args.scam_type, args.preset, Path(args.out))
    print(f"{graph['id']}: 장면 {len(graph['nodes'])}개, 출처 {len(graph['source_refs'])}개 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
