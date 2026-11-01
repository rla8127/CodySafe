"""합성 통화 60건으로 판정을 평가합니다. 운영 DB에 쓰지 않고 Langfuse로도 보내지 않습니다.

실행: cd server && .venv/bin/python -m eval.run   # .env의 ANTHROPIC_API_KEY, GUARD_RAG_URL 필요
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# config가 .env를 읽을 때 setdefault를 쓰므로 먼저 비워 두면 트레이스가 꺼집니다.
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["LANGFUSE_PUBLIC_KEY"] = ""

from guard import config, llm  # noqa: E402

from .calls import calls  # noqa: E402

SCAM_LABELS = {llm.VOICE_PHISHING, llm.OTHER_SCAM}
RAG_URL = config.RAG_URL


def judge(call: dict) -> dict:
    for attempt in range(3):
        try:
            result = llm.analyze(call["transcript"])
            return {**call, "pred": result["label"], "confidence": result["confidence"]}
        except Exception as exc:
            error = type(exc).__name__
    return {**call, "pred": "error", "confidence": 0.0, "error": error}


def summarize(rows: list[dict]) -> dict:
    scam = [r for r in rows if r["label"] == "scam"]
    normal = [r for r in rows if r["label"] == "normal"]
    alert = lambda r: r["pred"] == llm.VOICE_PHISHING and r["confidence"] >= config.ALERT_THRESHOLD
    lock = lambda r: r["pred"] == llm.VOICE_PHISHING and r["confidence"] >= config.LOCK_THRESHOLD
    return {
        "scam": len(scam),
        "normal": len(normal),
        "detected": sum(r["pred"] in SCAM_LABELS for r in scam),
        "false_positive": sum(r["pred"] in SCAM_LABELS for r in normal),
        "uncertain_scam": sum(r["pred"] == "uncertain" for r in scam),
        "uncertain_normal": sum(r["pred"] == "uncertain" for r in normal),
        "alert_scam": sum(alert(r) for r in scam),
        "lock_scam": sum(lock(r) for r in scam),
        "alert_normal": sum(alert(r) for r in normal),
        "lock_normal": sum(lock(r) for r in normal),
        "errors": sum(r["pred"] == "error" for r in rows),
        "missed": [r["id"] for r in scam if r["pred"] not in SCAM_LABELS],
        "false_alarms": [r["id"] for r in normal if r["pred"] in SCAM_LABELS],
    }


def run(rag_url: str) -> list[dict]:
    config.RAG_URL = rag_url
    with ThreadPoolExecutor(6) as pool:
        return list(pool.map(judge, calls()))


def main() -> None:
    if config.LLM == "rule":
        sys.exit("GUARD_LLM을 anthropic으로 설정하세요")
    out = {}
    for name, url in (("llm_only", ""), ("with_rag", RAG_URL)):
        rows = run(url)
        out[name] = {"summary": summarize(rows), "rows": [{k: v for k, v in r.items() if k != "transcript"} for r in rows]}
        print(name, json.dumps(out[name]["summary"], ensure_ascii=False), flush=True)
    Path(__file__).with_name("results.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
