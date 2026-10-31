"""판정기 평가(R-005): eval/judge_holdout.csv(사람이 붙인 라벨)로 정확도·혼동 행렬·'위험한 답을 안전으로 본 수'를 낸다.

쓰는 법 (저장소 루트에서):
  server/.venv/bin/python scripts/eval_judge.py              # 규칙만(LLM 주소를 지우고 돌림)
  server/.venv/bin/python scripts/eval_judge.py --mode env   # 지금 환경변수 그대로(SIM_LLM_BASE_URL이 있으면 LLM까지)

보고서에는 집계만 쓰고 답 원문은 쓰지 않는다. 라벨을 붙인 뒤에는 이 파일을 보며 판정 규칙·프롬프트를 고치지 않는다.
"""
import argparse
import collections
import csv
import hashlib
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

GRADES = ["정답", "중답", "오답"]
EVAL_OTP = "340891"  # 후보를 만들 때 화면에 보인 미끼 인증번호


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--holdout", default=str(ROOT / "eval" / "judge_holdout.csv"))
    parser.add_argument("--report", default=str(ROOT / "eval" / "judge_report.md"))
    parser.add_argument("--mode", choices=["rules", "env"], default="rules")
    args = parser.parse_args()

    if args.mode == "rules":
        os.environ["GUARD_ENV_FILE"] = ""  # server/.env를 읽지 않고 LLM 주소도 지운다
        for key in ("SIM_LLM_BASE_URL", "SIM_FALLBACK"):
            os.environ.pop(key, None)
    else:
        from guard import config  # noqa: F401  server/.env의 SIM_* 값을 읽어 둔다(값은 출력하지 않음)
    from guard.sim import engine, judge
    from guard.sim.schema import preset_profile

    path = Path(args.holdout)
    if not path.exists():
        print(f"라벨 파일이 없습니다: {path}")
        return 1
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    labeled = [r for r in rows if (r.get("label") or "").strip() in GRADES]
    if len(labeled) < 30:
        print(f"라벨이 붙은 줄이 {len(labeled)}개라 30개보다 적습니다")
        return 1

    profile = preset_profile("mother_74_alone")
    confusion = collections.Counter()
    sources = collections.Counter()
    danger_ids, ms = [], []
    for r in labeled:
        graph = engine.get_graph(r["scenario_id"])
        state = engine.start(graph, profile, seed=1)
        state["node"], state["otp"] = r["node_id"], EVAL_OTP
        state["values"]["otp"] = EVAL_OTP
        started = time.perf_counter()
        verdict = judge.judge(r["answer"], engine._judge_context(graph, state))
        ms.append((time.perf_counter() - started) * 1000)
        gold, pred = r["label"].strip(), verdict["grade"]
        confusion[(gold, pred)] += 1
        sources[verdict["source"]] += 1
        if gold == "오답" and pred == "정답":
            danger_ids.append(r["id"])

    n = len(labeled)
    correct = sum(confusion[(g, g)] for g in GRADES)
    lines = [
        "# 판정기 평가 보고서 (R-005)",
        "",
        f"- 만든 때: {datetime.now(timezone(timedelta(hours=9))):%Y-%m-%d %H:%M} KST",
        f"- 라벨 파일: `eval/{path.name}` (sha256 앞 12자리 `{hashlib.sha256(path.read_bytes()).hexdigest()[:12]}`), 전체 {len(rows)}줄 중 라벨 {n}줄",
        f"- 판정 경로: {'규칙만(LLM 주소 지움)' if args.mode == 'rules' else '지금 환경변수(LLM 주소가 있으면 LLM 포함)'}",
        f"- 판정 출처 분포: " + ", ".join(f"{k} {v}" for k, v in sorted(sources.items())),
        "- 기본(default)은 규칙도 LLM도 정하지 못해 '중답 + 선택지로 되묻기'로 처리한 답이다.",
        "",
        "## 1. 정확도",
        "",
        f"- 정확도: **{correct}/{n} = {correct / n:.1%}**",
        f"- 위험한 답(사람 라벨 오답)을 안전(정답)으로 본 수: **{len(danger_ids)}**" + (f" (id: {', '.join(danger_ids)})" if danger_ids else ""),
        f"- 위험한 답을 중답으로 본 수: {confusion[('오답', '중답')]}",
        f"- 판정 시간: 중앙값 {sorted(ms)[len(ms) // 2]:.1f}ms, 최대 {max(ms):.1f}ms",
        "",
        "## 2. 혼동 행렬 (행: 사람 라벨, 열: 판정기)",
        "",
        "| 사람 \\ 판정 | 정답 | 중답 | 오답 | 합계 |",
        "|---|---|---|---|---|",
    ]
    for g in GRADES:
        row = [confusion[(g, p)] for p in GRADES]
        lines.append(f"| {g} | " + " | ".join(map(str, row)) + f" | {sum(row)} |")
    lines += ["", "## 3. 클래스별", "", "| 클래스 | 정밀도 | 재현율 | 사람 라벨 수 |", "|---|---|---|---|"]
    for g in GRADES:
        tp = confusion[(g, g)]
        pred_n = sum(confusion[(x, g)] for x in GRADES)
        gold_n = sum(confusion[(g, x)] for x in GRADES)
        prec = f"{tp / pred_n:.1%}" if pred_n else "–"
        rec = f"{tp / gold_n:.1%}" if gold_n else "–"
        lines.append(f"| {g} | {prec} | {rec} | {gold_n} |")
    lines += [
        "",
        "## 4. 절차",
        "",
        "- 후보 60개는 판정 규칙을 보지 않은 별도 에이전트가 장면 대사만 보고 썼다(`eval/judge_candidates.csv`).",
        "- 라벨은 호연이 붙여 `eval/judge_holdout.csv`로 고정했다. 이후 판정 규칙·프롬프트를 고칠 때 이 파일을 보지 않는다.",
        "- 이 보고서에는 집계와 줄 id만 쓰고 답 원문은 쓰지 않는다.",
        "- 한계: 후보 작성자와 판정기 작성자가 같은 모델 계열이다. 실제 어르신 발화가 아니다.",
        "",
    ]
    Path(args.report).write_text("\n".join(lines), encoding="utf-8")
    print(f"정확도 {correct}/{n} = {correct / n:.1%}, 위험→안전 {len(danger_ids)}개 → {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
