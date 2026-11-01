// 모의 훈련 v2 화면: ① 프리셋·프로필 ② 시나리오 목록 ③ 문자 훈련 ④ 전화 훈련 ⑤ 마무리 질문 ⑥ 결과(안심 대응 점수).
// 사용자·모델·대본 글은 모두 textContent로만 넣는다. innerHTML에는 아이콘과 고정 문구만 쓴다.
// 탐지 결과의 "같은 수법 훈련하기" 링크(/app/#/sim2?type=<수법>)를 받아 해당 유형을 고른다.

const S2 = {
  list: null, profile: null, presets: [], caps: {}, pick: null,
  session: null, scene: null, result: null, busy: false,
  speakToken: 0, audioCtx: null, source: null, rec: null, recog: null, sttNotice: false, clock: null, callStart: 0,
  sttGen: 0, sttAbort: null,
};
const S2_AGE = [['60s', '60대'], ['70s', '70대'], ['80plus', '80대 이상']];
const S2_REGIONS = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'];
const S2_BANKS = ['농협', '국민은행', '신한은행', '우리은행', '하나은행', '기업은행', '우체국', '새마을금고', '신협'];
const S2_TYPE = {
  기관사칭: ['landmark', '#0047AB', '#E8F0FB', '기관 사칭'],
  가족지인사칭: ['users', '#F79009', '#FFF4E5', '가족 사칭'],
  스미싱: ['package', '#12B76A', '#E7F8EF', '문자 사기'],
};
const S2_CHANNEL = { call: '전화', chat: '메신저', sms: '문자', video: '영상' };
const S2_BAND = { 튼튼: ['safe', '튼튼해요'], 보통: ['pri', '보통이에요'], 주의: ['warn', '주의가 필요해요'], 위험: ['danger', '위험해요'] };
const S2_GRADE = { 정답: 'safe', 중답: 'warn', 오답: 'danger' };
const S2_MAX = { 알아차림: 30, 정보지킴: 30, 확인행동: 25, 대응속도: 15 };

/* ---------------- DOM 도우미: 글은 textContent로만 ---------------- */
function s2el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function s2icon(name) {
  const i = document.createElement('i');
  i.setAttribute('data-lucide', name);
  return i;
}
function s2btn(cls, iconName, text, onclick) {
  const b = s2el('button', cls);
  if (iconName) b.append(s2icon(iconName));
  b.append(document.createTextNode(text));
  if (onclick) b.onclick = onclick;
  return b;
}
const s2age = (v) => (S2_AGE.find(([k]) => k === v) || [, v])[1];
const s2sid = () => encodeURIComponent(S2.session.session_id);

/* ---------------- 라우트 ---------------- */
Object.assign(TAB_OF, { sim2: 'sim', sim2play: 'sim', sim2call: 'sim', sim2result: 'sim' });
Object.assign(PARENT, { sim2: 'sim', sim2play: 'sim2', sim2call: 'sim2', sim2result: 'sim2' });
FULL.push('sim2call');
DARK.push('sim2call');

// '#/sim2?type=X'를 '#/sim2/X'로 바꾼다. app.js 라우터는 '?'를 모르므로 그보다 먼저(capture) 처리한다.
function s2NormalizeHash() {
  const m = location.hash.match(/^#\/sim2\?(.*)$/);
  if (!m) return false;
  const type = new URLSearchParams(m[1]).get('type') || '';
  history.replaceState(null, '', '#/sim2' + (type ? '/' + encodeURIComponent(type) : ''));
  return true;
}
window.addEventListener('hashchange', (e) => {
  if (!/^#\/sim2(play|call)\//.test(location.hash)) s2StopAudio();
  if (s2NormalizeHash()) { e.stopImmediatePropagation(); render(); }
}, true);

/* ---------------- 체험 탭에 새 훈련 배너 ---------------- */
const s2BaseSim = SCREENS.sim;
SCREENS.sim = (a) => s2BaseSim(a).replace('<div class="page">', `<div class="page">
  <button class="hero s2-banner" onclick="go('sim2')">
    <div class="hero-label">${ic('sparkles')}새 훈련 · 내 상황에 맞춘 대본</div>
    <div style="font-size:21px;font-weight:800;margin-top:8px;line-height:1.3;position:relative;z-index:1">답에 따라 달라지는<br/>사기 대응 훈련</div>
    <div class="hero-meta" style="margin-top:8px">문자 훈련 · 전화 훈련 · 안심 대응 점수</div>
    <div class="hero-actions"><span class="btn sm" style="background:#fff;color:#1E3A8A">${ic('play')}시작하기</span></div>
  </button>`);

/* ---------------- ①② 프로필과 시나리오 목록 ---------------- */
SCREENS.sim2 = gated(() => `<div class="page s2">
  ${subhead('안심 대응 훈련')}
  <div class="lead">내 상황에 맞춘<br/>사기 대응 훈련</div>
  <div class="lead-sub">답에 따라 상대의 말이 달라져요. 끝나면 '안심 대응 점수'와 장면별 해설을 보여 드려요. 모든 대화와 번호는 가상이에요.</div>
  <div class="sec-title">① 누구를 위한 훈련인가요?</div>
  <div class="card" id="s2Profile"><div class="muted small">불러오는 중…</div></div>
  <div class="sec-title">② 어떤 수법을 연습할까요?</div>
  <div id="s2List"></div>
  <div id="s2Start"></div>
  <div class="sec-title">내 안심 대응 점수</div>
  <div class="card" id="s2Score"><div class="muted small">불러오는 중…</div></div>
</div>`);
INIT.sim2 = (arg) => s2LoadHome(arg);

async function s2LoadHome(arg) {
  if (!signedIn()) return;
  try {
    const [list, score] = await Promise.all([api('GET', '/v1/sim/scenarios'), api('GET', '/v1/me/score')]);
    S2.list = list.items;
    S2.profile = list.profile;
    S2.presets = list.presets;
    S2.caps = { tts: list.tts, stt: list.stt, llm: list.llm };
    S2.pick = s2resolve(arg ? decodeURIComponent(arg) : null) || S2.pick || list.default;
    if (!S2.list.some((i) => i.id === S2.pick)) S2.pick = list.default;
    s2RenderProfile();
    s2RenderList();
    s2RenderStart();
    s2RenderScore(score);
  } catch (e) {
    toast('훈련 목록을 불러오지 못했어요', 'circle-alert');
  }
}

function s2resolve(want) {
  if (!want || !S2.list) return null;
  const hit = S2.list.find((i) => i.id === want || i.scam_type === want || (i.aliases || []).includes(want));
  if (hit) return hit.id;
  // 모르는 수법이면 조용히 기관 사칭으로 떨어뜨리지 않고 목록에서 고르게 한다.
  toast('이 수법의 훈련은 아직 없어요. 목록에서 골라 주세요', 'info');
  return null;
}

function s2same(a, b) {
  return a && b && a.age_band === b.age_band && a.main_bank === b.main_bank && a.region === b.region
    && JSON.stringify(a.family_terms) === JSON.stringify(b.family_terms);
}

function s2RenderProfile() {
  const box = $('#s2Profile');
  if (!box) return;
  box.textContent = '';
  const p = S2.profile;
  box.append(s2el('div', 'small muted', '비슷한 분을 고르면 대사 속 호칭·은행·지역이 그분에게 맞춰져요. 보호자가 대신 골라도 돼요.'));
  const grid = s2el('div', 's2-presets');
  S2.presets.forEach((pr) => {
    const b = s2el('button', 's2-big' + (s2same(p, pr.profile) ? ' on' : ''));
    b.append(s2el('b', '', pr.label), s2el('span', 'tiny muted', `${s2age(pr.profile.age_band)} · ${pr.profile.family_terms.join('·')} · ${pr.profile.main_bank} · ${pr.profile.region}`));
    b.onclick = () => s2SaveProfile({ preset: pr.id });
    grid.append(b);
  });
  box.append(grid);
  const sum = s2el('div', 's2-sum');
  sum.textContent = p
    ? `지금: ${s2age(p.age_band)} · 가족 호칭 ${p.family_terms.join('·')} · ${p.main_bank} · ${p.region} · ${p.entered_by === 'guardian' ? '보호자가 입력' : '본인이 입력'}`
    : '아직 정하지 않았어요. 고르지 않으면 "혼자 사시는 70대 어머니"로 연습해요.';
  box.append(sum, s2btn('btn line block mt', 'pencil', '직접 고치기', s2EditProfile));
  icons();
}

async function s2SaveProfile(body) {
  try {
    await api('PUT', '/v1/devices/me', body);
    toast('프로필을 저장했어요');
    s2LoadHome(route().arg);
  } catch (e) {
    toast('저장하지 못했어요', 'circle-alert');
  }
}

function s2EditProfile() {
  const p = S2.profile || (S2.presets[0] || {}).profile || { age_band: '70s', family_terms: ['아들'], main_bank: '농협', region: '서울' };
  openSheet(`<div class="b" style="font-size:18px">훈련 프로필</div>
    <div class="tiny muted" style="margin-top:6px">실명·전화번호는 받지 않아요. 적은 내용은 훈련 대사에만 쓰여요.</div>
    <div class="s2-label">나이대</div><div class="s2-seg" id="s2fAge">${S2_AGE.map(([v, t]) => `<button data-v="${v}">${t}</button>`).join('')}</div>
    <div class="s2-label">자녀·가족 호칭 (쉼표로 나눠 최대 4개)</div><input class="s2-input" id="s2fTerms" maxlength="40" placeholder="예: 큰아들, 딸" />
    <div class="s2-label">주로 쓰는 은행</div><select class="s2-input" id="s2fBank">${S2_BANKS.map((b) => `<option>${b}</option>`).join('')}</select>
    <div class="s2-label">사는 곳</div><select class="s2-input" id="s2fRegion">${S2_REGIONS.map((r) => `<option>${r}</option>`).join('')}</select>
    <div class="s2-label">누가 입력하나요?</div><div class="s2-seg" id="s2fBy"><button data-v="self">본인</button><button data-v="guardian">보호자</button></div>
    <button class="btn pri block mt2" id="s2fSave">${ic('check')}저장</button>`);
  const seg = (id, value) => {
    document.querySelectorAll(`#${id} button`).forEach((b) => {
      b.classList.toggle('on', b.dataset.v === value);
      b.onclick = () => document.querySelectorAll(`#${id} button`).forEach((x) => x.classList.toggle('on', x === b));
    });
  };
  seg('s2fAge', p.age_band);
  seg('s2fBy', p.entered_by || 'self');
  $('#s2fTerms').value = (p.family_terms || []).join(', ');
  const bank = $('#s2fBank');
  if (![...bank.options].some((o) => o.value === p.main_bank)) bank.append(s2el('option', '', p.main_bank));
  bank.value = p.main_bank;
  const region = $('#s2fRegion');
  if (![...region.options].some((o) => o.value === p.region)) region.append(s2el('option', '', p.region));
  region.value = p.region;
  $('#s2fSave').onclick = () => {
    const terms = $('#s2fTerms').value.split(/[,，·]/).map((t) => t.trim()).filter(Boolean).slice(0, 4);
    if (!terms.length || terms.some((t) => t.length > 8)) return toast('가족 호칭을 1–8글자로 적어 주세요', 'circle-alert');
    closeSheet();
    s2SaveProfile({
      age_band: $('#s2fAge button.on')?.dataset.v || '70s', family_terms: terms,
      main_bank: bank.value, region: region.value, entered_by: $('#s2fBy button.on')?.dataset.v || 'self',
    });
  };
}

function s2RenderList() {
  const box = $('#s2List');
  if (!box) return;
  box.textContent = '';
  S2.list.forEach((it) => {
    const [icon, color, soft, tag] = S2_TYPE[it.scam_type] || ['shield-alert', '#475467', '#F2F4F7', it.scam_type];
    const on = it.id === S2.pick;
    const b = s2el('button', 'card scn s2-scn' + (on ? ' on' : ''));
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    const iconBox = s2el('span', 'icon-box');
    iconBox.style.background = soft;
    iconBox.style.color = color;
    iconBox.append(s2icon(icon));
    const body = s2el('div', 'grow');
    body.append(s2el('div', 't', it.title), s2el('div', 's', it.summary));
    const meta = s2el('div', 'meta');
    if (it.badge) meta.append(s2el('span', 'chip danger', it.badge));
    const tagChip = s2el('span', 'chip', tag);
    tagChip.style.background = soft;
    tagChip.style.color = color;
    meta.append(tagChip, s2el('span', 'chip', S2_CHANNEL[it.channel] || it.channel), s2el('span', 'chip', it.difficulty));
    if (it.plays) meta.append(s2el('span', 'chip', `${it.plays}번 함`));
    body.append(meta);
    const check = s2el('span', 's2-check');
    check.append(s2icon(on ? 'circle-check' : 'circle'));
    b.append(iconBox, body, check);
    b.onclick = () => { S2.pick = it.id; s2RenderList(); s2RenderStart(); };
    box.append(b);
  });
  icons();
}

function s2RenderStart() {
  const box = $('#s2Start');
  if (!box) return;
  box.textContent = '';
  const it = S2.list.find((i) => i.id === S2.pick);
  box.append(s2btn('btn pri block s2-go', 'message-circle', '문자로 연습하기', () => s2Start('chat')));
  const call = s2btn('btn grad block s2-go', 'phone-incoming', '전화로 연습하기', () => s2Start('call'));
  if (it.channel !== 'call') {
    call.disabled = true;
    call.classList.add('off');
  }
  box.append(call);
  if (it.channel !== 'call') box.append(s2el('div', 'tiny muted s2-note', '전화 훈련은 전화 대본(기관 사칭)에서 할 수 있어요.'));
  box.append(s2el('div', 'tiny muted s2-note', S2.caps.llm === 'gpu'
    ? '직접 쓴 답은 규칙으로 먼저 보고, 애매하면 AI가 판정해요.'
    : '직접 쓴 답은 정해진 규칙으로 판정해요. 애매하면 선택지로 다시 물어요.'));
  icons();
}

function s2RenderScore(score) {
  const box = $('#s2Score');
  if (!box) return;
  box.textContent = '';
  if (!score.latest) {
    box.append(s2el('div', 'muted small', '아직 훈련 기록이 없어요. 한 번 해 보면 여기에 점수와 약한 수법이 나와요.'));
    return;
  }
  const top = s2el('div', 'row between');
  const left = s2el('div');
  left.append(s2el('div', 'tiny muted b', '최근 안심 대응 점수'));
  const big = s2el('div', 's2-total', `${score.latest.total}점`);
  left.append(big);
  const [cls, word] = S2_BAND[score.latest.band] || ['pri', score.latest.band];
  top.append(left, s2el('span', 'chip ' + cls, word));
  box.append(top);
  if (score.history.length >= 2) {
    const d = score.delta_first_last;
    box.append(s2el('div', 'small mt', `처음보다 ${d >= 0 ? d + '점 올랐어요' : -d + '점 내려갔어요'} · 훈련 ${score.history.length}번 · ${score.streak_days}일 연속`));
  }
  if (score.weakness_top3.length) {
    const chips = s2el('div', 'chips mt');
    score.weakness_top3.forEach((w) => chips.append(s2el('span', 'chip warn', `${(S2_TYPE[w.scam_type] || [, , , w.scam_type])[3]} 취약도 ${Math.round(w.value * 100)}`)));
    box.append(s2el('div', 'tiny muted b mt', '더 연습하면 좋은 수법'), chips);
  }
  box.append(s2el('div', 'tiny muted mt', score.label));
}

async function s2Start(mode) {
  if (S2.busy) return;
  s2CancelStt();
  S2.busy = true;
  try {
    const r = await api('POST', '/v1/sim/sessions', { scenario_id: S2.pick, mode });
    S2.session = r;
    S2.scene = r.scene;
    S2.result = null;
    go((mode === 'call' ? 'sim2call/' : 'sim2play/') + r.session_id);
  } catch (e) {
    toast('훈련을 시작하지 못했어요', 'circle-alert');
  } finally {
    S2.busy = false;
  }
}

// 새로고침 등으로 화면 상태가 없으면 서버에서 이어 받는다.
async function s2Resume(sid, mode) {
  if (S2.session && S2.session.session_id === sid) return 'active';
  try {
    const r = await api('GET', `/v1/sim/sessions/${encodeURIComponent(sid)}/result`);
    S2.session = { session_id: sid, mode, persona: r.persona || { name: '모르는 번호', role: '' }, scenario: { title: r.title || '' } };
    if (r.status === 'done') { S2.result = r; history.replaceState(null, '', '#/sim2result/' + sid); render(); return 'done'; }
    if (r.status === 'closing') { s2ClosingPage(r.terminal, r.closing); return 'closing'; }
    S2.scene = r.scene;
    return 'active';
  } catch (e) {
    toast('훈련을 찾을 수 없어요', 'circle-alert');
    location.hash = '#/sim2';
    return 'gone';
  }
}

function s2Quit() {
  openSheet(`<div class="b" style="font-size:18px">훈련을 그만할까요?</div>
    <div class="small muted" style="margin-top:6px">지금까지 한 답은 점수에 들어가지 않아요.</div>
    <div class="row mt2"><button class="btn line grow" onclick="closeSheet()">계속하기</button><button class="btn danger grow" onclick="s2StopNow()">그만하기</button></div>`);
}
function s2StopNow() {
  closeSheet();
  s2StopAudio();
  s2CancelStt();
  S2.session = null;
  location.hash = '#/sim2';
}

/* ---------------- ③ 문자 훈련: 기존 대화 화면 재사용 ---------------- */
SCREENS.sim2play = gated(() => `<div class="chat-wrap s2-chat" id="playWrap">
  <div class="chat-head">
    <button class="back" onclick="s2Quit()">${ic('chevron-left')}</button>
    <div class="msg" style="gap:0"><span class="av" id="s2Av" style="width:36px;height:36px"></span></div>
    <div class="grow"><div class="nm" id="s2Name"></div><div class="sb" id="s2Sub"></div></div>
    <button class="chip s2-stop" onclick="s2Quit()">${ic('square')}그만하기</button>
  </div>
  <div class="sim-progress" id="simProg">${'<i></i>'.repeat(8)}</div>
  <div class="chat" id="chat"><div class="sysmsg">훈련용 가상 대화예요 · 번호와 주소는 모두 가짜예요</div></div>
  <div class="choices" id="choices" style="display:none"></div>
</div>`);
INIT.sim2play = async (sid) => {
  if (!signedIn() || !sid) return;
  if ((await s2Resume(sid, 'chat')) !== 'active') return;
  const persona = S2.session.persona || {};
  $('#s2Av').textContent = (persona.name || '?').slice(0, 1);
  $('#s2Name').textContent = persona.name || '';
  $('#s2Sub').textContent = `${persona.role || ''} · 훈련 모드`;
  s2ChatScene(S2.scene);
};

function s2Progress(turn) {
  document.querySelectorAll('#simProg i').forEach((e, k) => e.classList.toggle('on', k < turn));
}

function s2Bubble(who, text, kind) {
  const chat = $('#chat');
  if (!chat) return;
  const row = s2el('div', 'msg' + (who === 'me' ? ' me' : ''));
  if (who !== 'me') row.append(s2el('span', 'av', $('#s2Av')?.textContent || '?'));
  row.append(s2el('div', 'bubble' + (kind === 'link' ? ' link' : kind === 'sms' ? ' s2-sms' : ''), text));
  chat.append(row);
  view.scrollTop = view.scrollHeight;
}

function s2Typing(on) {
  $('#s2Typing')?.remove();
  if (!on) return;
  const row = s2el('div', 'msg');
  row.id = 's2Typing';
  row.append(s2el('span', 'av', $('#s2Av')?.textContent || '?'));
  const b = s2el('div', 'bubble typing');
  b.append(s2el('i'), s2el('i'), s2el('i'));
  row.append(b);
  $('#chat').append(row);
  view.scrollTop = view.scrollHeight;
}

function s2Items(scene) {
  const items = scene.lines.map((t) => ({ text: t, kind: /^https?:\/\//.test(t) ? 'link' : '' }));
  if (scene.media) items.push({ text: scene.media.text, kind: scene.media.kind === 'link' ? 'link' : 'sms' });
  return items;
}

function s2ChatScene(scene, reask) {
  S2.scene = scene;
  s2ChatChoices(scene, reask, true); // 상대가 쓰는 동안 입력창은 잠가 둔다
  s2Progress(scene.turn - 1);
  const items = s2Items(scene);
  items.forEach((m, k) => {
    later(() => s2Typing(true), k * 900 + 150);
    later(() => { s2Typing(false); s2Bubble('them', m.text, m.kind); }, k * 900 + 750);
  });
  later(() => s2ChatChoices(scene, reask), items.length * 900 + 250);
}

// 아래 입력창: 기본은 직접 답하기, 왼쪽 '선택지'를 누르면 선택지 3개가 펼쳐진다. 알아듣지 못했을 때만 저절로 펼친다.
function s2ChatChoices(scene, reask, locked) {
  const c = $('#choices');
  if (!c) return;
  c.textContent = '';
  c.style.display = '';
  c.classList.add('s2-dock');
  if (reask && !locked) c.append(s2el('div', 's2-reask', '잘 알아듣지 못했어요. 아래 선택지에서 골라 주세요'));
  const form = s2el('form', 's2-inbar');
  const pick = s2el('button', 's2-pick');
  pick.type = 'button';
  const input = s2el('input', 's2-input');
  input.maxLength = 300;
  input.placeholder = locked ? '상대가 쓰는 중…' : '직접 답하기';
  input.setAttribute('aria-label', '직접 답하기');
  const send = s2el('button', 's2-send');
  send.type = 'submit';
  send.setAttribute('aria-label', '보내기');
  send.append(s2icon('arrow-up'));
  form.append(pick, input, send);
  const list = s2el('div', 's2-picks');
  scene.choices.forEach((ch) => {
    const label = ch.act === 'do' ? `(행동) ${ch.text}` : ch.text;
    list.append(s2btn('choice', '', label, () => s2Answer({ choice_id: ch.id, input_type: 'choice' }, label)));
  });
  const setOpen = (open) => {
    list.hidden = !open;
    pick.textContent = '';
    pick.append(s2icon(open ? 'x' : 'list'), document.createTextNode(open ? '닫기' : '선택지'));
    pick.setAttribute('aria-expanded', open ? 'true' : 'false');
    icons();
    view.scrollTop = view.scrollHeight;
  };
  pick.onclick = () => setOpen(list.hidden);
  form.onsubmit = (e) => {
    e.preventDefault();
    const t = input.value.trim();
    if (t) s2Answer({ text: t, input_type: 'text' }, t);
  };
  [pick, input, send].forEach((el) => { el.disabled = !!locked; });
  c.append(form, list);
  setOpen(!!reask && !locked);
  if (!locked && !reask) input.focus({ preventScroll: true });
}

// 음성 인식 표: 녹음을 시작한 세션·장면·차례를 적어 두고, 결과가 늦게 오면 지금과 같은지 본다.
// 답을 내거나(선택지 포함) 그만두거나 새 훈련을 시작하면 세대값을 올려 옛 결과를 버린다(GAF 검토 11-01).
function s2Ticket() {
  return { gen: S2.sttGen, sid: S2.session && S2.session.session_id, node: S2.scene && S2.scene.node_id, turn: S2.scene && S2.scene.turn };
}
function s2Fresh(t) {
  return !!t && t.gen === S2.sttGen && !S2.busy && !!S2.session && S2.session.session_id === t.sid
    && !!S2.scene && S2.scene.node_id === t.node && S2.scene.turn === t.turn && !!$('#c2Tr');
}
function s2CancelStt() {
  S2.sttGen++;
  if (S2.sttAbort) { try { S2.sttAbort.abort(); } catch (e) { } }
  S2.sttAbort = null;
}

async function s2Answer(payload, shown) {
  if (S2.busy || !S2.session) return;
  s2CancelStt();
  S2.busy = true;
  const isCall = !!$('#c2Tr');
  if (isCall) s2CallLine('me', shown); else s2Bubble('me', shown);
  if (!isCall) s2ChatChoices(S2.scene, false, true);
  else { $('#c2Ans').hidden = true; s2Status('상대가 듣는 중…'); }
  try {
    const r = await api('POST', `/v1/sim/sessions/${s2sid()}/turn`, payload);
    if (r.status !== 'active') {
      s2StopAudio();
      later(() => s2ClosingPage(r.terminal, r.closing), 600);
    } else if (isCall) {
      s2CallScene(r.scene, r.judge.reask);
    } else {
      s2ChatScene(r.scene, r.judge.reask);
    }
  } catch (e) {
    toast('답을 보내지 못했어요. 다시 해 주세요', 'circle-alert');
    if (isCall) s2CallAnswer(S2.scene); else s2ChatChoices(S2.scene);
  } finally {
    S2.busy = false;
  }
}

/* ---------------- ④ 전화 훈련 ---------------- */
SCREENS.sim2call = gated(() => `<div class="callscreen s2-call">
  <button class="s2-stop-light" onclick="s2Quit()">${ic('square')}그만하기</button>
  <div class="caller" style="margin-top:0">
    <div class="row" style="justify-content:center;margin-bottom:14px"><span class="chip" style="background:rgba(255,255,255,.12);color:#fff">${ic('gamepad-2')}훈련 전화 · 가상 통화</span></div>
    <div class="avatar s2-ring" id="c2Avatar">${ic('user-round')}</div>
    <div class="num" id="c2Name">모르는 번호</div>
    <div class="st" id="c2St">전화가 왔어요</div>
  </div>
  <div class="glass mt2"><div class="row between" style="margin-bottom:8px"><b>상대 말</b><span class="tiny" style="opacity:.65" id="c2Voice"></span></div>
    <div class="transcript" id="c2Tr"><div class="small" style="opacity:.6">받기를 누르면 통화가 시작돼요. 소리를 켜 주세요.</div></div></div>
  <div class="glass" id="c2Ans" hidden></div>
  <div class="call-actions" id="c2Acts">
    <button class="call-btn" id="c2Decline"><span class="c red">${ic('phone-off')}</span>거절</button>
    <button class="call-btn" id="c2Accept"><span class="c green">${ic('phone')}</span>받기</button>
  </div>
</div>`);
INIT.sim2call = async (sid) => {
  if (!signedIn() || !sid) return;
  if ((await s2Resume(sid, 'call')) !== 'active') return;
  $('#c2Voice').textContent = S2.caps.tts ? '임대 GPU 음성 · 전화 음질' : '브라우저 음성(ko-KR)';
  vibrate([300, 200, 300]);
  const started = S2.scene && S2.scene.turn > 1;
  if (started) return s2Pickup();
  $('#c2Accept').onclick = s2Pickup;
  // 모르는 전화를 받지 않는 것도 안전한 대응이다(끊기로 판정).
  $('#c2Decline').onclick = () => s2HangUp();
};

function s2Status(text) {
  const st = $('#c2St');
  if (st) st.textContent = text;
}

function s2Pickup() {
  $('#c2Avatar')?.classList.remove('s2-ring');
  $('#c2Tr').textContent = '';
  S2.callStart = Date.now();
  clearInterval(S2.clock);
  S2.clock = setInterval(() => {
    if (!$('#c2St')) return clearInterval(S2.clock);
    const s = Math.floor((Date.now() - S2.callStart) / 1000);
    // 받은 뒤에는 상대가 밝힌 이름(대본 persona, 가상 인물)과 통화 시간을 함께 보인다.
    const who = (S2.session && S2.session.persona && S2.session.persona.name) || '모르는 번호';
    $('#c2Name').textContent = `${who} · ${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }, 1000);
  const acts = $('#c2Acts');
  acts.textContent = '';
  const hang = s2el('button', 'call-btn');
  const red = s2el('span', 'c red');
  red.append(s2icon('phone-off'));
  hang.append(red, document.createTextNode('끊기'));
  hang.onclick = () => s2HangUp();
  acts.append(hang);
  icons();
  s2CallScene(S2.scene);
}

function s2HangUp() {
  if (S2.busy) return;
  s2StopAudio();
  s2Answer({ text: '전화를 끊는다', input_type: 'hangup' }, '(전화를 끊었어요)');
}

function s2CallLine(who, text) {
  const tr = $('#c2Tr');
  if (!tr) return;
  const p = s2el('div', 's2-line' + (who === 'me' ? ' me' : ''));
  p.append(s2el('b', '', who === 'me' ? '나 ' : '상대 '), document.createTextNode(text));
  tr.append(p);
  tr.scrollTop = tr.scrollHeight;
  view.scrollTop = view.scrollHeight;
}

async function s2CallScene(scene, reask) {
  S2.scene = scene;
  $('#c2Ans').hidden = true;
  s2Status('상대가 말하는 중…');
  const items = s2Items(scene);
  const token = ++S2.speakToken;
  for (const m of items) {
    if (token !== S2.speakToken || !$('#c2Tr')) return;
    if (m.kind === 'sms' || m.kind === 'link') { s2CallLine('them', `[문자로 온 것] ${m.text}`); continue; }
    s2CallLine('them', m.text);
    await s2Speak(m.text, token, scene.tone);
  }
  if (token !== S2.speakToken || !$('#c2Tr')) return;
  s2CallAnswer(scene, reask);
}

function s2CallAnswer(scene, reask) {
  const box = $('#c2Ans');
  if (!box) return;
  box.textContent = '';
  box.hidden = false;
  s2Status(reask ? '잘 알아듣지 못했어요. 선택지로 답해 주세요' : '내 차례예요. 말하거나 고르세요');
  const head = s2el('div', 'row between');
  head.append(s2el('b', '', '내 답'), s2el('span', 'tiny', `${scene.turn}/${scene.max_turns}`));
  box.append(head);
  const canVoice = (S2.caps.stt && window.MediaRecorder && navigator.mediaDevices) || window.SpeechRecognition || window.webkitSpeechRecognition;
  if (canVoice && !reask) {
    const mic = s2btn('s2-mic', 'mic', '눌러서 말하기', s2Listen);
    mic.id = 'c2Mic';
    box.append(mic);
  }
  const notice = s2el('div', 'tiny s2-notice');
  notice.id = 'c2Notice';
  box.append(notice);
  const list = s2el('div', 's2-callchoices');
  list.append(s2el('div', 'tiny', canVoice && !reask ? '말하기가 어려우면 고르세요' : '아래에서 고르세요'));
  scene.choices.forEach((ch) => {
    const label = ch.act === 'do' ? `(행동) ${ch.text}` : ch.text;
    list.append(s2btn('', '', label, () => { s2StopRec(); s2Answer({ choice_id: ch.id, input_type: 'choice' }, label); }));
  });
  box.append(list);
  icons();
  view.scrollTop = view.scrollHeight;
}

function s2Mic(state, text) {
  const mic = $('#c2Mic');
  if (!mic) return;
  mic.classList.toggle('rec', state === 'rec');
  mic.textContent = '';
  mic.append(s2icon(state === 'rec' ? 'square' : 'mic'), document.createTextNode(text || (state === 'rec' ? '듣는 중… 다 말하면 누르세요' : '눌러서 말하기')));
  icons();
}

function s2Hint(text) {
  const n = $('#c2Notice');
  if (n) n.textContent = text;
}

function s2Listen() {
  if (S2.rec || S2.recog) return s2StopRec(true);
  if (S2.caps.stt && window.MediaRecorder && navigator.mediaDevices) return s2RecordGpu();
  return s2RecognizeBrowser();
}

// 임대 GPU STT: 녹음해 서버로 보낸다. 실패하면 브라우저 인식, 그다음 선택지.
async function s2RecordGpu() {
  const ticket = s2Ticket();
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    S2.caps.stt = false;
    return s2Hint('마이크를 쓸 수 없어요. 아래에서 골라 주세요');
  }
  const rec = new MediaRecorder(stream);
  const chunks = [];
  rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  rec.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    S2.rec = null;
    if (rec.s2cancel || !s2Fresh(ticket)) return s2Mic('idle');
    s2Mic('idle', '알아듣는 중…');
    const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
    const t0 = performance.now();
    const ctrl = window.AbortController ? new AbortController() : null;
    S2.sttAbort = ctrl;
    try {
      const res = await fetch('/v1/sim/stt', { method: 'POST', headers: { Authorization: 'Bearer ' + store.get('token'), 'Content-Type': blob.type || 'audio/webm' }, body: blob, signal: ctrl ? ctrl.signal : undefined });
      if (!res.ok) throw new Error(res.status);
      const { text } = await res.json();
      if (!s2Fresh(ticket)) return; // 그사이 선택지로 답했거나 장면·세션이 바뀌었으면 버린다
      if (S2.sttAbort === ctrl) S2.sttAbort = null;
      const ms = Math.round(performance.now() - t0);
      s2Mic('idle');
      if (!text) return s2Hint('잘 들리지 않았어요. 다시 말하거나 아래에서 골라 주세요');
      s2Answer({ text, input_type: 'voice', stt_ms: ms }, text);
    } catch (e) {
      if (!s2Fresh(ticket)) return; // 취소된 요청
      if (S2.sttAbort === ctrl) S2.sttAbort = null;
      S2.caps.stt = false; // 다음부터는 브라우저 인식으로
      S2.sttNotice = true; // Google 전송 안내를 지금 함께 보여 주므로 다음 한 번 누르면 바로 인식한다
      s2Mic('idle');
      s2Hint('음성 인식 서버를 쓸 수 없어요. 다시 누르면 브라우저 인식을 써요(Chrome은 말소리를 Google 서버로 보내 글자로 바꿔요). 원하지 않으면 아래에서 골라 주세요');
    }
  };
  rec.start();
  S2.rec = rec;
  s2Mic('rec');
  setTimeout(() => { if (S2.rec === rec) rec.stop(); }, 10000);
}

// 브라우저 인식: Chrome은 말소리를 Google 서버로 보내므로 처음 한 번 알리고 다시 눌러야 시작한다.
function s2RecognizeBrowser() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return s2Hint('이 브라우저는 음성 인식을 지원하지 않아요. 아래에서 골라 주세요');
  if (!S2.sttNotice) {
    S2.sttNotice = true;
    s2Hint('안내: 브라우저 음성 인식은 Chrome이 말소리를 Google 서버로 보내 글자로 바꿔요. 괜찮으면 마이크를 한 번 더 누르고, 원하지 않으면 아래에서 골라 주세요.');
    return;
  }
  s2Hint('');
  const ticket = s2Ticket();
  const r = new SR();
  r.lang = 'ko-KR';
  r.interimResults = false;
  r.maxAlternatives = 1;
  let t0 = 0;
  let got = false;
  r.onspeechend = () => { t0 = performance.now(); };
  r.onresult = (e) => {
    got = true;
    const text = e.results[0][0].transcript;
    const ms = t0 ? Math.round(performance.now() - t0) : null;
    S2.recog = null;
    s2Mic('idle');
    if (!s2Fresh(ticket)) return;
    s2Answer({ text, input_type: 'voice', stt_ms: ms }, text);
  };
  r.onerror = () => { s2Hint('알아듣지 못했어요. 다시 말하거나 아래에서 골라 주세요'); };
  r.onend = () => { S2.recog = null; if (!got) s2Mic('idle'); };
  try {
    r.start();
    S2.recog = r;
    s2Mic('rec');
  } catch (e) {
    s2Hint('음성 인식을 시작하지 못했어요. 아래에서 골라 주세요');
  }
}

function s2StopRec(submit) {
  if (!submit) s2CancelStt();
  if (S2.rec) { if (!submit) S2.rec.s2cancel = true; try { S2.rec.stop(); } catch (e) { } }
  if (S2.recog) { try { submit ? S2.recog.stop() : S2.recog.abort(); } catch (e) { } if (!submit) S2.recog = null; }
}

// 대사 읽기: 임대 GPU TTS(전화 음질 300–3400Hz) → 안 되면 브라우저 speechSynthesis(ko-KR).
async function s2Speak(text, token, tone) {
  if (S2.caps.tts && await s2PlayTts(text, token, tone)) return;
  await s2SpeakBrowser(text, token, tone);
}

// 임대 GPU는 처음 만드는 대사 하나에 7–16초가 걸린다(11-01 실측). 이만큼 기다려도 안 오면 이번 대사만 브라우저 음성으로 읽는다.
// 서버는 하던 합성을 끝내 캐시에 두므로 다음 훈련부터는 GPU 음성이 바로 나온다.
const S2_TTS_WAIT_MS = 3500;

async function s2PlayTts(text, token, tone) {
  const ctrl = window.AbortController ? new AbortController() : null;
  const timer = ctrl ? setTimeout(() => ctrl.abort(), S2_TTS_WAIT_MS) : null;
  const label = (t) => { $('#c2Voice') && ($('#c2Voice').textContent = t); };
  try {
    const res = await fetch('/v1/sim/tts', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + store.get('token'), 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, tone }),
      signal: ctrl ? ctrl.signal : undefined,
    });
    if (!res.ok) {
      if (res.status === 501 || res.status === 502) S2.caps.tts = false;
      label('브라우저 음성(ko-KR)');
      return false;
    }
    const buf = await res.arrayBuffer();
    clearTimeout(timer);
    if (token !== S2.speakToken) return true;
    label('임대 GPU 음성 · 전화 음질');
    const ctx = S2.audioCtx || (S2.audioCtx = new (window.AudioContext || window.webkitAudioContext)());
    if (ctx.state === 'suspended') await ctx.resume();
    const audio = await ctx.decodeAudioData(buf);
    const src = ctx.createBufferSource();
    src.buffer = audio;
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 300;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 3400;
    src.connect(hp).connect(lp).connect(ctx.destination);
    S2.source = src;
    await new Promise((resolve) => { src.onended = resolve; src.start(); });
    return true;
  } catch (e) {
    if (e && e.name === 'AbortError') label('브라우저 음성(ko-KR) · GPU 음성 준비 중');
    return false;
  } finally {
    clearTimeout(timer);
  }
}

// 브라우저 음성은 감정을 낼 수 없어 말투마다 빠르기·높낮이만 바꾼다. 자연스러운 감정 음성은 임대 GPU TTS 몫이다.
const S2_PROSODY = { calm: [1, 1], official: [0.95, 0.85], urgent: [1.2, 1.05], threat: [0.9, 0.75], tremble: [0.95, 1.2], sob: [0.85, 1.25], friendly: [1.05, 1.15] };
function s2Voice() {
  const ko = speechSynthesis.getVoices().filter((v) => (v.lang || '').toLowerCase().startsWith('ko'));
  const rank = (v) => (/premium|enhanced|고급|향상|natural|neural/i.test(v.name) ? 0 : /google/i.test(v.name) ? 1 : /유나|yuna/i.test(v.name) ? 2 : 3);
  return ko.sort((a, b) => rank(a) - rank(b))[0];
}

function s2SpeakBrowser(text, token, tone) {
  return new Promise((resolve) => {
    if (!('speechSynthesis' in window) || token !== S2.speakToken) return resolve();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'ko-KR';
    const voice = s2Voice();
    if (voice) u.voice = voice;
    const [rate, pitch] = S2_PROSODY[tone] || S2_PROSODY.calm;
    u.rate = rate;
    u.pitch = pitch;
    const done = () => { clearTimeout(guard); resolve(); };
    u.onend = done;
    u.onerror = done;
    const guard = setTimeout(done, 4000 + text.length * 250);
    speechSynthesis.speak(u);
  });
}

function s2StopAudio() {
  S2.speakToken++;
  try { speechSynthesis.cancel(); } catch (e) { }
  try { S2.source && S2.source.stop(); } catch (e) { }
  S2.source = null;
  s2StopRec();
  clearInterval(S2.clock);
}

/* ---------------- ⑤ 마무리 질문 ---------------- */
function s2ClosingPage(term, closing) {
  clearTimers();
  closeSheet();
  view.classList.remove('full');
  $('#tabbar').classList.remove('hidden');
  $('.statusbar').classList.remove('light');
  view.innerHTML = `<div class="page s2">
    ${subhead('마무리 질문')}
    <div class="card s2-term" id="s2Term"></div>
    <div class="sec-title" id="s2Q"></div>
    <div id="s2Opts"></div>
    <button class="btn pri block mt2 s2-go" id="s2Done">${ic('flag')}결과 보기</button>
  </div>`;
  const t = $('#s2Term');
  t.classList.add(term.type === 'safe' ? 's2-ok' : 's2-bad');
  t.append(s2el('div', 'b', term.type === 'safe' ? (term.by === 'user' ? '안전하게 끝냈어요' : '상대가 먼저 끊었어요') : '피해가 생길 뻔했어요'));
  t.append(s2el('div', 'small mt', term.message));
  $('#s2Q').textContent = closing.question;
  const picked = new Set();
  const opts = $('#s2Opts');
  closing.options.forEach((o) => {
    const b = s2btn('s2-big s2-opt', 'square', o.text);
    b.setAttribute('aria-pressed', 'false');
    b.onclick = () => {
      if (picked.has(o.id)) picked.delete(o.id); else picked.add(o.id);
      const on = picked.has(o.id);
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.firstChild.replaceWith(s2icon(on ? 'square-check' : 'square'));
      icons();
    };
    opts.append(b);
  });
  $('#s2Done').onclick = async () => {
    if (S2.busy) return;
    S2.busy = true;
    try {
      S2.result = await api('POST', `/v1/sim/sessions/${s2sid()}/closing`, { option_ids: [...picked] });
      history.replaceState(null, '', '#/sim2result/' + S2.session.session_id);
      render();
    } catch (e) {
      toast('결과를 만들지 못했어요. 다시 눌러 주세요', 'circle-alert');
    } finally {
      S2.busy = false;
    }
  };
  icons();
  view.scrollTop = 0;
}

/* ---------------- ⑥ 결과: 안심 대응 점수 ---------------- */
SCREENS.sim2result = gated(() => `<div class="page s2">${subhead('훈련 결과')}<div id="s2Res"><div class="card muted small">불러오는 중…</div></div></div>`);
INIT.sim2result = async (sid) => {
  if (!signedIn() || !sid) return;
  let r = S2.result && S2.result.session_id === sid ? S2.result : null;
  if (!r) {
    try { r = await api('GET', `/v1/sim/sessions/${encodeURIComponent(sid)}/result`); } catch (e) { return toast('결과를 찾을 수 없어요', 'circle-alert'); }
  }
  if (r.status !== 'done') { location.hash = '#/sim2play/' + sid; return; }
  s2RenderResult(r);
};

function s2RenderResult(r) {
  const box = $('#s2Res');
  if (!box) return;
  box.textContent = '';
  const s = r.score;
  const [cls, word] = S2_BAND[s.band] || ['pri', s.band];
  const [, color, soft, tag] = S2_TYPE[r.scam_type] || [, '#475467', '#F2F4F7', r.scam_type];

  const head = s2el('div', 'card center');
  const chip = s2el('span', 'chip', tag);
  chip.style.background = soft;
  chip.style.color = color;
  head.append(chip, s2el('div', 'b mt', r.title));
  const ringBox = s2el('div', 'result-ring');
  const colors = s.total >= 70 ? ['#1CC27B', '#0E9F8E'] : s.total >= 50 ? ['#FFA53A', '#F0712C'] : ['#FF5A4E', '#D92D6B'];
  ringBox.innerHTML = ring(Math.max(0, Math.min(100, Number(s.total) || 0)), 150, 14, '#EEF1F7', colors); // 숫자만 들어감
  const v = s2el('div', 'v');
  const inner = s2el('div');
  inner.append(s2el('b', '', String(s.total)), s2el('span', 'muted small b', '점'));
  v.append(inner);
  ringBox.append(v);
  head.append(ringBox, s2el('div', 'b', '안심 대응 점수'), s2el('span', 'chip mt ' + cls, word));
  head.append(s2el('div', 'tiny muted mt', r.label));
  box.append(head);

  box.append(s2el('div', 'sec-title', '네 가지로 나눠 보면'));
  const parts = s2el('div', 'card');
  const HELP = { 알아차림: '얼마나 빨리 사기를 알아챘나', 정보지킴: '인증번호·계좌·신분증을 지켰나', 확인행동: '끊은 뒤 공식 번호·가족·신고로 확인하나', 대응속도: '위험 신호가 나온 뒤 얼마나 빨리 끊었나' };
  Object.keys(S2_MAX).forEach((k) => {
    const row = s2el('div', 's2-row');
    const name = s2el('div');
    name.append(s2el('b', 'small', k), s2el('div', 'tiny muted', HELP[k]));
    const bar = s2el('div', 's2-bar');
    const fill = s2el('i');
    fill.style.width = `${Math.round((s.breakdown[k] / S2_MAX[k]) * 100)}%`;
    bar.append(fill);
    row.append(name, bar, s2el('b', 'small', `${s.breakdown[k]}/${S2_MAX[k]}`));
    parts.append(row);
  });
  box.append(parts);

  if (r.terminal) {
    const term = s2el('div', 'card mt ' + (r.terminal.type === 'safe' ? 's2-ok' : 's2-bad'));
    term.append(s2el('div', 'small', r.terminal.message));
    box.append(term);
  }

  box.append(s2el('div', 'sec-title', '장면별 해설'));
  r.scenes.forEach((sc, i) => {
    const card = s2el('div', 'card s2-scene');
    card.append(s2el('span', 'chip', `장면 ${i + 1} · ${sc.stage}`));
    card.append(s2el('div', 'small mt s2-them', `상대: ${sc.line}`));
    sc.answers.forEach((a) => {
      const row = s2el('div', 's2-ans');
      row.append(s2el('span', 'chip ' + (S2_GRADE[a.grade] || ''), a.grade), s2el('span', 'small', `내 답: ${a.text}`));
      card.append(row);
    });
    card.append(s2el('div', 'small mt s2-best', `이렇게 하면 좋아요: ${sc.best}`));
    const flags = s2el('div', 'chips mt');
    flags.style.flexWrap = 'wrap';
    sc.red_flags.forEach((f) => flags.append(s2el('span', 'chip danger', f)));
    card.append(flags, s2el('div', 'small mt muted', sc.debrief));
    box.append(card);
  });

  box.append(s2el('div', 'sec-title', '마무리 질문'));
  const closing = s2el('div', 'card');
  r.closing.forEach((o) => {
    const good = o.points > 0;
    const row = s2el('div', 's2-ans');
    row.append(s2el('span', 'chip ' + (o.chosen ? (good ? 'safe' : 'danger') : ''), o.chosen ? '고름' : (good ? '놓침' : '안 고름')));
    const txt = s2el('div', 'grow');
    txt.append(s2el('div', 'small', o.text), s2el('div', 'tiny muted', o.why));
    row.append(txt);
    closing.append(row);
  });
  box.append(closing);

  if (r.next) {
    box.append(s2el('div', 'sec-title', '다음에 연습할 훈련'));
    const next = s2btn('card scn s2-scn', 'arrow-right', `${r.next.title} (${S2_CHANNEL[r.next.channel] || ''})`, () => { S2.pick = r.next.id; go('sim2/' + encodeURIComponent(r.next.id)); });
    box.append(next);
  }

  const src = s2el('div', 'tiny muted mt2');
  src.append(document.createTextNode('대사 바탕: '));
  (r.sources || []).forEach((ref) => {
    if (!/^https:\/\//.test(ref.url)) return;
    const a = s2el('a', '', `${ref.publisher ? ref.publisher + ' ' : ''}「${ref.title}」(${ref.published_at || '날짜 없음'})`);
    a.href = ref.url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    src.append(a, document.createTextNode(' '));
  });
  src.append(document.createTextNode('· 대화는 훈련용으로 새로 쓴 가상 대화예요.'));
  box.append(src);

  const btns = s2el('div', 'row mt2');
  btns.append(
    s2btn('btn line grow', 'list', '목록으로', () => { location.hash = '#/sim2'; }),
    s2btn('btn pri grow', 'rotate-ccw', '다시 하기', () => { S2.pick = r.scenario_id; location.hash = '#/sim2/' + encodeURIComponent(r.scenario_id); }),
  );
  box.append(btns);
  icons();
}

/* ---------------- 모양 ---------------- */
(function s2Style() {
  const css = `
  .s2-presets { display: grid; gap: 10px; margin-top: 12px; }
  .s2-big { text-align: left; padding: 16px; border-radius: 16px; border: 2px solid var(--line); background: #fff; display: flex; flex-direction: column; gap: 4px; font-size: 16px; width: 100%; }
  .s2-big.on { border-color: var(--pri); background: var(--pri-soft); }
  .s2-opt { flex-direction: row; align-items: center; gap: 10px; margin-top: 10px; font-weight: 700; line-height: 1.45; }
  .s2-opt svg.lucide { flex: none; color: var(--pri); }
  .s2-sum { margin-top: 12px; font-size: 14px; line-height: 1.55; }
  .s2-scn { width: 100%; text-align: left; border: 2px solid transparent; align-items: center; }
  .s2-scn.on { border-color: var(--pri); }
  .s2-scn + .s2-scn { margin-top: 10px; }
  .s2-check { color: var(--pri); flex: none; }
  .s2-go { height: 58px; font-size: 17px; margin-top: 14px; }
  .btn.off { opacity: .45; box-shadow: none; }
  .s2-note { margin-top: 8px; line-height: 1.5; }
  .s2-total { font-size: 30px; font-weight: 800; }
  .s2-label { font-weight: 700; margin: 16px 2px 8px; font-size: 14px; }
  .s2-seg { display: flex; gap: 8px; }
  .s2-seg button { flex: 1; height: 52px; border-radius: 14px; border: 2px solid var(--line); background: #fff; font-size: 16px; font-weight: 700; }
  .s2-seg button.on { border-color: var(--pri); color: var(--pri); background: var(--pri-soft); }
  .s2-input { width: 100%; height: 50px; border-radius: 14px; border: 1px solid var(--line); padding: 0 14px; font-size: 16px; background: #fff; }
  .s2-dock { padding: 10px 12px 16px; }
  .s2-inbar { display: flex; align-items: center; gap: 8px; background: var(--bg); border-radius: 30px; padding: 6px; }
  .s2-pick { flex: none; display: flex; align-items: center; gap: 4px; height: 46px; padding: 0 14px; border-radius: 23px; background: #fff; color: var(--pri); font-size: 15px; font-weight: 800; border: 1.5px solid var(--pri-soft); }
  .s2-pick svg.lucide { width: 18px; height: 18px; }
  .s2-inbar .s2-input { flex: 1; min-width: 0; height: 46px; border: 0; background: transparent; padding: 0 6px; font-size: 17px; }
  .s2-inbar .s2-input:focus { outline: none; }
  .s2-send { flex: none; width: 46px; height: 46px; border-radius: 50%; background: var(--pri); color: #fff; display: grid; place-items: center; }
  .s2-inbar button:disabled, .s2-inbar .s2-input:disabled { opacity: .45; }
  .s2-picks { margin-top: 4px; }
  .s2-picks .choice { font-size: 16px; }
  .s2-reask { margin: 0 4px 8px; font-size: 13.5px; font-weight: 700; color: #C46A00; }
  .s2-chat .choice { font-size: 16px; }
  .s2-stop { background: rgba(255,255,255,.7); }
  .bubble.s2-sms { background: #FFF8E1; border: 1px dashed #E0B000; }
  .s2-term.s2-ok, .card.s2-ok { background: var(--safe-soft); }
  .s2-term.s2-bad, .card.s2-bad { background: var(--danger-soft); }
  .s2-row { display: grid; grid-template-columns: 1fr 34% 48px; align-items: center; gap: 10px; padding: 9px 0; }
  .s2-row + .s2-row { border-top: 1px solid var(--line); }
  .s2-bar { height: 10px; border-radius: 99px; background: #EEF1F7; overflow: hidden; }
  .s2-bar i { display: block; height: 100%; background: var(--pri); border-radius: 99px; }
  .s2-scene + .s2-scene { margin-top: 10px; }
  .s2-ans { display: flex; gap: 8px; align-items: flex-start; margin-top: 8px; }
  .s2-ans .chip { flex: none; }
  .s2-them { line-height: 1.5; }
  .s2-best { color: #08875A; font-weight: 700; }
  .s2-call { padding-bottom: 24px; }
  .s2-call .caller { margin-top: 34px !important; }
  @media (min-width: 501px) { .statusbar:has(~ #view .s2-call) { background: #121A33; } }
  .s2-call .transcript { max-height: 220px; overflow-y: auto; }
  .s2-line { font-size: 15px; line-height: 1.5; padding: 4px 0; }
  .s2-line b { opacity: .6; font-size: 12px; }
  .s2-line.me { color: #9EE6C3; }
  .s2-mic { width: 100%; height: 62px; margin-top: 10px; border-radius: 18px; background: rgba(255,255,255,.16); color: #fff; font-size: 17px; font-weight: 800; display: flex; align-items: center; justify-content: center; gap: 8px; }
  .s2-mic.rec { background: #EF4444; }
  .s2-notice { margin-top: 8px; line-height: 1.5; opacity: .85; }
  .s2-callchoices { margin-top: 10px; }
  .s2-callchoices button { width: 100%; text-align: left; padding: 12px 14px; border-radius: 14px; background: rgba(255,255,255,.1); color: #fff; margin-top: 8px; font-size: 15px; line-height: 1.45; }
  .s2-stop-light { position: absolute; top: 52px; right: 14px; z-index: 3; display: flex; gap: 6px; align-items: center; color: #fff; font-size: 13px; font-weight: 700; padding: 8px 12px; border-radius: 12px; background: rgba(255,255,255,.14); }
  .s2-stop-light svg.lucide { width: 14px; height: 14px; }
  .s2-ring { animation: s2ring 1.2s infinite; }
  @keyframes s2ring { 0%, 100% { box-shadow: 0 0 0 0 rgba(34,197,94,.5); } 50% { box-shadow: 0 0 0 16px rgba(34,197,94,0); } }
  @media (max-width: 500px) { .s2-stop-light { top: 10px; } }`;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.append(style);
})();

// 처음 열 때 '#/sim2?type=X'로 들어왔으면 바로잡아 다시 그린다.
if (s2NormalizeHash() || /^#\/sim2/.test(location.hash)) render();
