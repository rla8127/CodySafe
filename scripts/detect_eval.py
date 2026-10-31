"""탐지 오탐·미탐 표본 검사: 글자 파일들을 rag_first 경로로 판정해 구간별 건수를 분모와 함께 냅니다.

입력 파일(녹취 글자)은 저장소에 넣지 않습니다. 실제 통화를 쓸 때는 양쪽 동의, '외부 STT·미국 S3로 전송' 고지,
시험 뒤 삭제를 지킵니다. GUARD_LLM이 rule이 아니면 글자가 그 LLM 공급자로 전송됩니다.

쓰는 법(저장소 루트에서):
  server/.venv/bin/python scripts/detect_eval.py --scam 사기폴더/*.txt --normal 가족통화폴더/*.txt
  server/.venv/bin/python scripts/detect_eval.py --list 목록.tsv      # 줄마다 '경로<TAB>scam|normal'

출력: 구간(기록·주의·위험·매우 위험·판단 어려움)별 건수, 오탐(정상인데 가족 알림·잠금), 미탐(사기인데 가족 알림 없음).
파일 내용과 근거 발화는 출력하지 않습니다(파일 이름만).
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
os.environ.setdefault("GUARD_RAG_FIRST", "1")

from guard import rag_first  # noqa: E402

BANDS = ["log", "caution", "alert", "lock", "unclear"]


def load(args) -> list[tuple[Path, str]]:
    items = [(Path(p), "scam") for p in args.scam] + [(Path(p), "normal") for p in args.normal]
    if args.list:
        for line in Path(args.list).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                path, _, kind = line.partition("\t")
                if kind.strip() not in ("scam", "normal"):
                    sys.exit(f"목록의 두 번째 칸은 scam 또는 normal이어야 합니다: {line}")
                items.append((Path(path.strip()), kind.strip()))
    return items


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d * 100:.0f}%)" if d else f"{n}/0 (-)"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scam", nargs="*", default=[], help="사기 통화 글자 파일")
    ap.add_argument("--normal", nargs="*", default=[], help="정상(가족) 통화 글자 파일")
    ap.add_argument("--list", help="'경로<TAB>scam|normal' 목록 파일")
    ap.add_argument("--show", action="store_true", help="파일마다 구간을 보여 줍니다(이름만)")
    args = ap.parse_args()
    items = load(args)
    if not items:
        ap.error("파일을 하나 이상 주세요")

    counts = {k: Counter() for k in ("scam", "normal")}
    failed = Counter()
    rows = []
    for path, kind in items:
        try:
            result = rag_first.analyze(path.read_text(encoding="utf-8"))
        except Exception as exc:  # 판정 형식 실패도 '판단 어려움'과 같이 자동 조치 없음
            failed[kind] += 1
            counts[kind]["unclear"] += 1
            rows.append((path.name, kind, "unclear", None, f"실패: {type(exc).__name__}"))
            continue
        b = rag_first.result_band(result)
        alert, lock = rag_first.auto_actions(result)
        counts[kind][b] += 1
        counts[kind]["auto_alert"] += int(alert)
        counts[kind]["auto_lock"] += int(lock)
        rows.append((path.name, kind, b, result.get("score"), result["label"]))

    print(f"판정: GUARD_LLM={rag_first.config.LLM}, 사례 검색={'켜짐' if rag_first.config.RAG_URL else '꺼짐(로컬 수법 설명만)'}")
    print("점수는 AI 의심 점수(보정 전, 확률 아님). 구간: 0–39 기록 / 40–69 주의 / 70–89 위험 / 90+ 매우 위험\n")
    print("| 구분 | 분모 | " + " | ".join(rag_first.BANDS[b] for b in BANDS) + " | 판정 실패 |")
    print("|---|---|" + "---|" * (len(BANDS) + 1))
    for kind, name in (("scam", "사기"), ("normal", "정상")):
        n = sum(counts[kind][b] for b in BANDS)
        print(f"| {name} | {n} | " + " | ".join(str(counts[kind][b]) for b in BANDS) + f" | {failed[kind]} |")

    ns = sum(counts["scam"][b] for b in BANDS)
    nn = sum(counts["normal"][b] for b in BANDS)
    print()
    print(f"- 오탐(정상인데 가족 알림): {pct(counts['normal']['auto_alert'], nn)}, 그중 잠금 {counts['normal']['auto_lock']}")
    print(f"- 정상인데 주의 이상(본인 확인 안내): {pct(sum(counts['normal'][b] for b in ('caution', 'alert', 'lock')), nn)}")
    print(f"- 미탐(사기인데 가족 알림 없음): {pct(ns - counts['scam']['auto_alert'], ns)}, 그중 판단 어려움 {counts['scam']['unclear']}")
    print(f"- 사기 중 잠금까지: {pct(counts['scam']['auto_lock'], ns)}")
    if args.show:
        print("\n| 파일 | 정답 | 구간 | 점수 | 판정 |\n|---|---|---|---|---|")
        for name, kind, b, score, label in rows:
            print(f"| {name} | {kind} | {rag_first.BANDS[b]} | {'' if score is None else score} | {label} |")


if __name__ == "__main__":
    main()
