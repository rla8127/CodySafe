"""대본 그래프 검사기(R-001).

검사: 다음 장면 ID가 있는지, 시작점에서 모든 장면과 성공·실패 종료에 닿는지, 장면마다 정답·중답·오답이
하나씩인지, 한 장면 최대 2차례·전체 8차례를 넘지 않는지(순환 없음), 출처가 있는지, 진짜 같은 번호·계좌·주소가 없는지.
"""
import re
from collections import deque

from pydantic import ValidationError

from .schema import CLOSING_POINTS, GRADE_OF_INTENT, GRADES, MAX_STAY, MAX_TURNS, Graph

KNOWN_SLOTS = {"user_title", "child_title", "family_other", "bank", "region_office", "pension_org", "otp"}
_SLOT = re.compile(r"\{(\w+)\}")
_URL = re.compile(r"(?:https?://|www\.)([^\s/'\"<>]+)", re.I)
_PHONE = re.compile(r"(?<!\d)(0\d{1,2})[-. ]?(\d{3,4})[-. ]?(\d{4})(?!\d)")
_REP_NUMBER = re.compile(r"(?<!\d)1[5-9]\d{2}-?\d{4}(?!\d)")  # 1588-xxxx 같은 대표번호
_RRN = re.compile(r"(?<!\d)\d{6}\s*-\s*[1-4]\d{6}(?!\d)")
_ACCOUNT = re.compile(r"(?<!\d)\d{2,6}-\d{2,6}-\d{2,8}(?!\d)")
_LONG_DIGITS = re.compile(r"\d{9,}")
# 스킴 없이 쓴 도메인(예: test.com/app). 한국어 대사 안에서 흔한 끝 이름만 본다.
_BARE_HOST = re.compile(r"(?<![\w.@/-])((?:[a-z0-9-]+\.)+(?:com|net|org|kr|io|me|app|xyz|top|shop|site|info|biz|ly|cc|co|example|test|invalid))(?![\w-])", re.I)
_RESERVED_TLD = {"example", "test", "invalid"}  # RFC 2606·6761 예약 이름
_RESERVED_SLD = {("example", "com"), ("example", "org"), ("example", "net")}


def _is_safe_host(host: str) -> bool:
    """예약된 가상 도메인(.example·.test·.invalid 끝, example.com/org/net과 그 하위)만 참."""
    h = host.lower().strip().rstrip(".,)]}>").split("@")[-1].split(":")[0].rstrip(".")
    labels = [x for x in h.split(".") if x]
    if not labels:
        return False
    if labels[-1] in _RESERVED_TLD:
        return True
    return len(labels) >= 2 and (labels[-2], labels[-1]) in _RESERVED_SLD


def scan_unsafe(text: str) -> list[str]:
    """진짜처럼 보이는 번호·계좌·주소를 찾는다. 010-0000-XXXX 꼴과 example 도메인만 허용한다."""
    problems = []
    hosts = list(dict.fromkeys(_URL.findall(text) + _BARE_HOST.findall(_URL.sub(" ", text))))
    for host in hosts:
        if not _is_safe_host(host):
            problems.append(f"example 도메인이 아닌 주소: {host}")
    for match in _PHONE.finditer(text):
        if match.group(2) != "0000":
            problems.append(f"진짜 같은 전화번호: {match.group(0)}")
    for pattern, label in ((_REP_NUMBER, "대표번호"), (_RRN, "주민번호"), (_ACCOUNT, "계좌번호"), (_LONG_DIGITS, "긴 숫자")):
        for found in pattern.findall(text):
            if label in ("계좌번호", "긴 숫자") and _PHONE.fullmatch(found if isinstance(found, str) else ""):
                continue
            problems.append(f"진짜 같은 {label}: {found}")
    return problems


def _texts(graph: Graph):
    """화면에 나오는 모든 글(제목·요약·상대 이름과 역할, 대사, 위험 신호, 선택지, 해설, 종료 문구, 마무리 질문)을 위치와 함께 돌려준다.
    출처(source_refs)의 공식 주소는 대본의 유인 주소가 아니므로 검사하지 않는다."""
    yield "title", graph.title
    yield "summary", graph.summary
    yield "impersonated", graph.impersonated
    yield "persona.name", graph.persona.name
    yield "persona.role", graph.persona.role
    yield "persona.tone", graph.persona.tone
    for nid, node in graph.nodes.items():
        yield f"{nid}.goal", node.goal
        for i, flag in enumerate(node.red_flags):
            yield f"{nid}.red_flags[{i}]", flag
        for i, line in enumerate(node.lines):
            yield f"{nid}.lines[{i}]", line
        for i, line in enumerate(node.pressure):
            yield f"{nid}.pressure[{i}]", line
        for c in node.choices:
            yield f"{nid}.{c.id}", c.text
        yield f"{nid}.debrief", node.debrief
        if node.media:
            yield f"{nid}.media", node.media.text
    for tid, term in graph.terminals.items():
        yield f"{tid}.message", term.message
    yield "closing.question", graph.closing.question
    for opt in graph.closing.options:
        yield f"closing.{opt.id}", opt.text + " " + opt.why


def _longest_turns(graph: Graph, errors: list[str]) -> int:
    """시작점에서 종료까지 가장 긴 길의 답 수(장면마다 최대 2차례). 순환이 있으면 오류."""
    memo: dict[str, int] = {}
    state: dict[str, int] = {}

    def walk(nid: str) -> int:
        if nid in graph.terminals or nid not in graph.nodes:
            return 0
        if state.get(nid) == 1:
            errors.append(f"순환이 있음: {nid}")
            return MAX_TURNS + 1
        if nid in memo:
            return memo[nid]
        state[nid] = 1
        best = MAX_STAY + max(walk(c.next) for c in graph.nodes[nid].choices)
        state[nid] = 2
        memo[nid] = best
        return best

    return walk(graph.start)


def validate(data: dict | Graph) -> list[str]:
    """문제 목록을 돌려준다. 빈 목록이면 통과."""
    try:
        graph = data if isinstance(data, Graph) else Graph.model_validate(data)
    except ValidationError as exc:
        return [f"형식: {e['loc']} {e['msg']}" for e in exc.errors()]
    errors: list[str] = []
    targets = set(graph.nodes) | set(graph.terminals)
    if graph.start not in graph.nodes:
        errors.append(f"시작 장면이 없음: {graph.start}")
        return errors
    if set(graph.nodes) & set(graph.terminals):
        errors.append("장면과 종료 ID가 겹침")

    for nid, node in graph.nodes.items():
        grades = sorted(c.grade for c in node.choices)
        if len(node.choices) != 3 or set(grades) != set(GRADES):
            errors.append(f"{nid}: 정답·중답·오답 선택지가 하나씩 있어야 함 (지금 {grades})")
        if len({c.id for c in node.choices}) != len(node.choices):
            errors.append(f"{nid}: 선택지 ID가 겹침")
        for c in node.choices:
            if c.next not in targets:
                errors.append(f"{nid}.{c.id}: 다음 장면 '{c.next}'이 없음")
            if GRADE_OF_INTENT[c.intent] != c.grade:
                errors.append(f"{nid}.{c.id}: 등급 {c.grade}와 의도 {c.intent}가 맞지 않음")
            if c.leaks and c.grade != "오답":
                errors.append(f"{nid}.{c.id}: 정보를 내주는 선택지는 오답이어야 함")

    # 도달 가능성: 선택지로 이어진 길만 센다.
    seen, queue = {graph.start}, deque([graph.start])
    while queue:
        nid = queue.popleft()
        if nid in graph.nodes:
            for c in graph.nodes[nid].choices:
                if c.next in targets and c.next not in seen:
                    seen.add(c.next)
                    queue.append(c.next)
    for nid in graph.nodes:
        if nid not in seen:
            errors.append(f"시작점에서 닿지 않는 장면: {nid}")
    reached = [graph.terminals[t] for t in seen if t in graph.terminals]
    if not any(t.type == "safe" and t.by == "user" for t in reached):
        errors.append("시작점에서 닿는 성공 종료(사용자가 끊음)가 없음")
    if not any(t.type == "loss" for t in reached):
        errors.append("시작점에서 닿는 실패 종료가 없음")
    for tid, term in graph.terminals.items():
        # 송금·앱설치 실패 종료는 자유 입력의 의도로도 갈 수 있으므로 선택지로 닿지 않아도 된다.
        if tid not in seen and not (term.type == "loss" and term.loss in ("송금", "앱설치")):
            errors.append(f"시작점에서 닿지 않는 종료: {tid}")
        if term.type == "loss" and not term.loss:
            errors.append(f"{tid}: 실패 종료에는 loss 종류가 있어야 함")

    turns = _longest_turns(graph, errors)
    if turns > MAX_TURNS:
        errors.append(f"가장 긴 길이 {turns}차례로 {MAX_TURNS}차례를 넘음")

    if not any(r.url.startswith(("http://", "https://")) for r in graph.source_refs):
        errors.append("source_refs에 출처 주소가 없음")
    for opt in graph.closing.options:
        expected = CLOSING_POINTS.get(opt.kind)
        if expected is not None and opt.points != expected:
            errors.append(f"closing.{opt.id}: {opt.kind} 점수는 {expected}점이어야 함")
        if opt.kind == "기타" and opt.points > 0:
            errors.append(f"closing.{opt.id}: 기타 선택지는 점수를 줄 수 없음")
    kinds = {o.kind for o in graph.closing.options}
    if not {"공식번호확인", "가족확인", "신고"} <= kinds:
        errors.append("마무리 질문에 공식번호확인·가족확인·신고 선택지가 모두 있어야 함")

    for where, text in _texts(graph):
        for slot in _SLOT.findall(text):
            if slot not in KNOWN_SLOTS:
                errors.append(f"{where}: 모르는 칸 {{{slot}}}")
            elif slot not in graph.slots and slot != "otp":
                errors.append(f"{where}: slots 목록에 없는 칸 {{{slot}}}")
        for problem in scan_unsafe(text):
            errors.append(f"{where}: {problem}")
    return errors


def assert_valid(data: dict | Graph) -> Graph:
    errors = validate(data)
    if errors:
        raise ValueError("대본 그래프 검사 실패: " + "; ".join(errors))
    return data if isinstance(data, Graph) else Graph.model_validate(data)
