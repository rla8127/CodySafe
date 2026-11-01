#!/usr/bin/env python3
"""Field check for cleaned case JSONL (plan 5-2). Usage: python3 scripts/check_cases.py data/clean/2026_official_cases.jsonl [--min 30]"""
import argparse, json, re, sys
from collections import Counter

SCAM_TYPES = {"기관사칭", "대출빙자", "가족지인사칭", "스미싱", "투자사기", "로맨스스캠", "중고거래사기", "기타"}
CHANNELS = {"전화", "문자", "메신저", "SNS", "이메일", "웹사이트", "앱", "기타"}
STAGES = {"접근", "신뢰", "공포·긴급", "요구", "압박", "마무리"}
TACTICS = {"권위", "공포", "긴급", "비밀유지", "보상", "동정", "고립"}
ACTIONS = {"송금", "앱설치", "인증번호", "개인정보", "현금전달", "상품권"}
REQUIRED = ["id", "title", "scam_type", "channel", "impersonated_target", "stage", "tactics", "requested_actions",
            "target_age_band", "sample_lines", "published_at", "source_url", "source_tier", "license", "synthetic"]
URL_IN_LINE = re.compile(r"https?://|www\.|\.(kr|com|guru|gl|me)\b", re.I)
PHONE = re.compile(r"\d{2,4}-\d{3,4}-\d{4}")


def check(o):
    e = []
    for k in REQUIRED:
        if k not in o:
            e.append(f"missing {k}")
    if e:
        return e
    if not isinstance(o["title"], str) or not o["title"].strip():
        e.append("title")
    if o["scam_type"] not in SCAM_TYPES:
        e.append(f"scam_type={o['scam_type']}")
    if o["channel"] not in CHANNELS:
        e.append(f"channel={o['channel']}")
    if o["impersonated_target"] is not None and not isinstance(o["impersonated_target"], str):
        e.append("impersonated_target")
    for k, allowed in (("stage", STAGES), ("tactics", TACTICS), ("requested_actions", ACTIONS)):
        v = o[k]
        if not isinstance(v, list) or not v or any(x not in allowed for x in v):
            e.append(f"{k}={v}")
    if o["target_age_band"] is not None and not isinstance(o["target_age_band"], str):
        e.append("target_age_band")
    sl = o["sample_lines"]
    if not isinstance(sl, list) or not 3 <= len(sl) <= 6 or not all(isinstance(x, str) and x.strip() for x in sl):
        e.append(f"sample_lines n={len(sl) if isinstance(sl, list) else '?'} (need 3-6)")
    else:
        for x in sl:
            if not (x.startswith("[인용]") or x.startswith("[바꿔씀]")):
                e.append("sample_line without [인용]/[바꿔씀] tag")
            if URL_IN_LINE.search(x) and "[링크]" not in x and "대검찰.kr" not in x:
                e.append(f"unmasked url: {x[:40]}")
            if PHONE.search(x):
                e.append(f"phone number: {x[:40]}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(o["published_at"])) or not str(o["published_at"]).startswith(("2025", "2026")):
        e.append(f"published_at={o['published_at']}")
    if not str(o["source_url"]).startswith("https://"):
        e.append("source_url")
    if o["source_tier"] != "official":
        e.append("source_tier")
    if not isinstance(o["license"], str) or not o["license"]:
        e.append("license")
    if o["synthetic"] is not False:
        e.append("synthetic must be false")
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--min", type=int, default=30)
    a = ap.parse_args()
    rows, bad, ids = 0, 0, Counter()
    types, chans = Counter(), Counter()
    for n, line in enumerate(open(a.path, encoding="utf-8"), 1):
        if not line.strip():
            continue
        rows += 1
        try:
            o = json.loads(line)
        except json.JSONDecodeError as x:
            print(f"line {n}: json error {x}")
            bad += 1
            continue
        ids[o.get("id")] += 1
        types[o.get("scam_type")] += 1
        chans[o.get("channel")] += 1
        e = check(o)
        if e:
            bad += 1
            print(f"line {n} ({o.get('id')}): " + "; ".join(e))
    dup = [k for k, v in ids.items() if v > 1]
    if dup:
        print("duplicate id:", dup)
    ok = rows - bad
    print(f"rows={rows} ok={ok} bad={bad} required_fields_ok={ok / rows:.0%}" if rows else "rows=0")
    print("scam_type:", dict(types.most_common()))
    print("channel:", dict(chans.most_common()))
    passed = rows >= a.min and bad == 0 and not dup
    print("PASS" if passed else f"FAIL (need >= {a.min} rows, 0 bad, unique id)")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
