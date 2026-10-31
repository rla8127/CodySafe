// 웹 MVP(js/app.js)의 라우터와 시뮬레이션을 그대로 쓰고, 나머지 화면을 실제 데이터 화면으로 바꿉니다.

const native = window.CodySafeNative || null;
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const store = {
  get: (k) => { try { return localStorage.getItem('guard.' + k) || ''; } catch (e) { return ''; } },
  set: (k, v) => { try { localStorage.setItem('guard.' + k, v); } catch (e) { } },
  del: (k) => { try { localStorage.removeItem('guard.' + k); } catch (e) { } },
};

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { Authorization: 'Bearer ' + store.get('token'), ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401 && store.get('token')) {
    store.del('token');
    native?.setToken('');
    render();
  }
  if (!res.ok) throw new Error(res.status);
  return res.json();
}

// 음성 보관 여부가 바뀌면 달라진 내용으로 다시 동의받습니다.
let keepAudio = false;
const consentVersion = () => (keepAudio ? '2' : '1');
const accepted = () => store.get('consented') === consentVersion();
const signedIn = () => accepted() && !!store.get('token');
if (store.get('token')) native?.setToken(store.get('token'));

/* ---------------- 시안 화면 제거 ---------------- */
['image', 'voice', 'call', 'url', 'verify', 'report', 'generate', 'weakness', 'training', 'copilot', 'checkup'].forEach((k) => delete SCREENS[k]);
Object.assign(TAB_OF, { home: 'home', sim: 'sim', play: 'sim', detect: 'detect', family: 'family', me: '', lock: 'home', passphrase: 'family', report: 'report', pet: 'home', quiz: 'home' });
delete PARENT.family;
PARENT.pet = 'home';
PARENT.quiz = 'pet';
// 체험 대화 중에도 아래 메뉴를 그대로 보여 줍니다.
FULL.splice(FULL.indexOf('play'), 1);
PARENT.passphrase = 'family';

renderTabs = function (on) {
  const tabs = [['home', 'house', '홈'], ['sim', 'gamepad-2', '체험'], ['detect', 'shield-check', '검사'], ['report', 'messages-square', '커뮤니티'], ['family', 'users', '가족']];
  $('#tabbar').innerHTML = `<button class="side-logo" onclick="logoHome()" aria-label="소개 페이지로"><img src="assets/brand/logo-horizontal.png" alt="Cody Safe"></button>` + tabs.map(([k, i, t]) => k === 'detect'
    ? `<button class="tab tab-center ${on === k ? 'on' : ''}" onclick="go('${k}')"><span class="fab">${ic(i)}</span><span>${t}</span></button>`
    : `<button class="tab ${on === k ? 'on' : ''}" onclick="go('${k}')">${ic(i)}<span>${t}</span></button>`).join('');
  icons();
};

// 앱 안에는 소개 페이지가 필요 없어 홈으로 보내고, 웹은 랜딩으로 나갑니다. 미리보기에서 눌러도 창 전체가 이동합니다.
function logoHome() {
  if (native) go('home');
  else window.top.location.href = '/';
}

/* ---------------- PC 화면: 오른쪽 모바일 미리보기 ---------------- */
const embedded = document.body.classList.contains('embedded');
const previewFrame = $('#previewFrame');

function previewOpen() {
  return !embedded && !native && !document.body.classList.contains('preview-closed') && window.matchMedia('(min-width: 1181px)').matches;
}

// 닫혀 있으면 앱을 한 벌 더 띄우지 않도록 필요할 때만 불러옵니다.
function syncPreview() {
  const button = $('#previewToggle');
  const closed = document.body.classList.contains('preview-closed');
  button.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="7" y="2" width="10" height="20" rx="2.5"/><path d="M11 18h2"/></svg>${closed ? '모바일 화면 보기' : '모바일 화면 접기'}`;
  button.setAttribute('aria-expanded', String(!closed));
  if (!previewOpen()) return;
  if (!previewFrame.getAttribute('src')) previewFrame.src = `./${location.hash}`;
  else if (previewFrame.contentWindow.location.hash !== location.hash) previewFrame.contentWindow.location.hash = location.hash;
}

function togglePreview() {
  const closed = document.body.classList.toggle('preview-closed');
  if (closed) store.set('previewClosed', '1');
  else store.del('previewClosed');
  syncPreview();
}

const previewClock = () => {
  const d = new Date();
  if ($('#previewClock')) $('#previewClock').textContent = `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
};

/* ---------------- 가족 역할 ---------------- */
const ROLE_INFO = {
  mom: { label: '엄마' }, dad: { label: '아빠' }, me: { label: '나' },
  child: { label: '자녀' }, son: { label: '아들' }, daughter: { label: '딸' },
  brother: { label: '형' }, sister: { label: '언니·누나' }, uncle: { label: '삼촌' }, aunt: { label: '이모·고모' },
};
const DEMO_LABEL = { me: '나', dad: '아빠', mom: '엄마', brother: '형', uncle: '삼촌' };
let demoMembers = [];

/* 웹 시연에서는 등록된 가족 중 한 명을 고릅니다. 앱은 항상 직접 등록합니다. */
async function loadServerInfo() {
  try {
    const info = await (await fetch('/healthz')).json();
    if (info.keep_audio !== keepAudio) {
      keepAudio = info.keep_audio;
      render();
    }
  } catch (e) { }
}

async function loadDemoFamily() {
  if (native) return;
  try {
    const res = await fetch('/v1/demo/family');
    if (!res.ok) return;
    demoMembers = (await res.json()).items;
    // 시연 전에 직접 등록한 브라우저도 가족을 고르는 화면으로 보냅니다.
    if (store.get('token') && store.get('demo') !== '1') {
      store.del('token');
      store.del('name');
      store.del('role');
      render();
    } else if (accepted() && !signedIn()) render();
    else if (route().r === 'me') render();
  } catch (e) { }
}

function demoPicker() {
  return `<div class="page">
    <div class="brand-hero small"><button class="logo-home" onclick="logoHome()" aria-label="소개 페이지로"><img src="assets/brand/logo-horizontal.png" alt="Cody Safe"></button></div>
    <div class="lead-text">누구로<br><em>시연</em>할까요?</div>
    <div class="demo-list">${demoMembers.map((m) => `<button class="demo-person" onclick="demoEnter('${esc(m.id)}')"><span><b>${esc(m.name)}</b><small>${DEMO_LABEL[m.role]}</small></span>${ic('chevron-right')}</button>`).join('')}</div>
    <div class="card mt soft-warn">시연용 가족입니다. 접속한 사람 모두 같은 기록을 볼 수 있으니 실제 통화는 올리지 마세요.</div>
  </div>`;
}

async function demoEnter(id) {
  try {
    const res = await fetch(`/v1/demo/family/${id}/login`, { method: 'POST' });
    if (!res.ok) throw new Error(res.status);
    const me = await res.json();
    store.set('token', me.token);
    store.set('name', me.name);
    store.set('role', me.role);
    store.set('demo', '1');
    ['lastAlert', 'lockSeen', 'seen', 'folderSince'].forEach((k) => store.del(k));
    go('home');
    render();
  } catch (e) {
    toast('들어가지 못했습니다', 'circle-alert');
  }
}
let pickedRole = '';

function rolePicker(role = '', memo = '') {
  pickedRole = role;
  const isChild = ['child', 'son', 'daughter'].includes(role);
  const main = ['mom', 'dad', 'me', 'child'].map((k) => `<button type="button" class="role-btn ${(k === 'child' ? isChild : role === k) ? 'on' : ''}" data-role="${k}" onclick="pickRole('${k}')">${ROLE_INFO[k].label}</button>`).join('');
  const sub = ['son', 'daughter'].map((k) => `<button type="button" class="chip role-sub ${role === k ? 'on' : ''}" data-role="${k}" onclick="pickRole('${k}')">${ROLE_INFO[k].label}</button>`).join('');
  return `<div class="role-grid">${main}</div>
    <div class="role-child" id="roleChild" ${isChild ? '' : 'hidden'}>
      <div class="row" style="gap:8px">${sub}</div>
      <div class="field" style="margin-top:10px"><label for="roleMemo">메모 (선택)</label><input id="roleMemo" maxlength="20" placeholder="예: 첫째" value="${esc(memo)}"></div>
    </div>`;
}

function pickRole(role) {
  pickedRole = role;
  const isChild = ['child', 'son', 'daughter'].includes(role);
  document.querySelectorAll('.role-btn').forEach((b) => b.classList.toggle('on', b.dataset.role === role || (b.dataset.role === 'child' && isChild)));
  document.querySelectorAll('.role-sub').forEach((b) => b.classList.toggle('on', b.dataset.role === role));
  $('#roleChild').hidden = !isChild;
}

function readRole() {
  const isChild = ['child', 'son', 'daughter'].includes(pickedRole);
  return { role: pickedRole, memo: isChild ? ($('#roleMemo')?.value.trim() || null) : null };
}

async function roleSheet() {
  let me = {};
  try { me = await api('GET', '/v1/devices/me'); } catch (e) { return toast('불러오지 못했습니다', 'circle-alert'); }
  openSheet(`<div class="b" style="font-size:18px">가족 안에서의 역할</div>
    <div style="margin-top:14px">${rolePicker(me.role || '', me.memo || '')}</div>
    <div class="btn-col"><button class="btn pri block" onclick="saveRole()">저장</button><button class="btn line block" onclick="closeSheet()">취소</button></div>`);
}

async function saveRole() {
  const { role, memo } = readRole();
  if (!role) return toast('역할을 골라 주세요', 'circle-alert');
  try {
    await api('PUT', '/v1/devices/me', { role, memo });
    store.set('role', role);
    render();
    toast('저장했습니다');
  } catch (e) {
    toast('저장하지 못했습니다', 'circle-alert');
  }
}

/* ---------------- 상태 표시줄 (PC 미리보기 전용, 실제 폰에서는 숨김) ---------------- */
document.querySelectorAll('.sb-icons').forEach((el) => { el.innerHTML = `<svg width="17" height="12" viewBox="0 0 17 12" aria-hidden="true"><rect x="0" y="8" width="3" height="4" rx=".8"/><rect x="4.6" y="5.5" width="3" height="6.5" rx=".8"/><rect x="9.2" y="3" width="3" height="9" rx=".8"/><rect x="13.8" y="0" width="3" height="12" rx=".8"/></svg>
  <svg width="16" height="12" viewBox="0 0 16 12" aria-hidden="true"><path d="M8 2.4c2.3 0 4.4.9 6 2.4l1.2-1.3A10.4 10.4 0 0 0 8 .6 10.4 10.4 0 0 0 .8 3.5L2 4.8a8.6 8.6 0 0 1 6-2.4Zm0 3.5c1.3 0 2.5.5 3.5 1.4l1.2-1.3A6.9 6.9 0 0 0 8 4.1a6.9 6.9 0 0 0-4.7 1.9l1.2 1.3c1-.9 2.2-1.4 3.5-1.4Zm0 3.4c-.7 0-1.3.3-1.8.7L8 12l1.8-2c-.5-.4-1.1-.7-1.8-.7Z"/></svg>
  <span class="sb-battery"><i></i></span>`; });

/* ---------------- 첫 실행 ---------------- */
function onboardingPage() {
  if (!accepted()) {
    return `<div class="page">
      <div class="brand-hero"><button class="logo-home" onclick="logoHome()" aria-label="소개 페이지로"><img src="assets/brand/logo-vertical.png" alt="Cody Safe"></button></div>
      <div class="lead-text">AI 사기는 <em>미리 경험</em>하고,<br>가족과 <em>함께</em> 막아요</div>
      <div class="card"><ul class="notice">
        ${['앱이 통화를 직접 녹음하지 않고, 이미 저장된 파일만 읽습니다.', '폴더를 연결한 뒤에 생긴 파일만 서버로 보냅니다.', (keepAudio ? '음성은 분석 후에도 사용자별로 저장되며, 기록을 삭제하면 함께 지워집니다. 일상 통화는 글자 기록을 남기지 않습니다.' : '음성은 분석 후 삭제하고, 일상 통화는 글자 기록도 남기지 않습니다.'), '사기로 의심되는 통화의 글자 기록은 검토를 위해 보관합니다.', '분석 내용은 본인만 봅니다. 가족에게는 보이스피싱 의심 여부만 알립니다.']
          .map((t) => `<li>${ic('circle-check')}<span>${t}</span></li>`).join('')}
      </ul></div>
      <div class="card soft-warn">통화 상대의 음성도 함께 전송됩니다. 테스트 버전이므로 동의한 사람의 통화나 테스트 파일로만 사용하세요.</div>
      <button class="btn grad block mt" onclick="store.set('consented',consentVersion());render()">동의하고 시작</button>
    </div>`;
  }
  if (demoMembers.length) return demoPicker();
  return `<div class="page">
    <div class="brand-hero small"><button class="logo-home" onclick="logoHome()" aria-label="소개 페이지로"><img src="assets/brand/logo-horizontal.png" alt="Cody Safe"></button></div>
    <div class="lead-text">가족 안에서<br><em>누구</em>신가요?</div>
    <div class="card">${rolePicker()}
    <div class="field"><label for="regName">가족에게 보일 이름</label><input id="regName" maxlength="30" placeholder="예: 민수"></div>
    <div class="muted small" style="margin-top:10px">계정이나 비밀번호는 필요 없습니다.</div></div>
    <button class="btn grad block mt" onclick="registerDevice()">시작하기</button>
  </div>`;
}

async function registerDevice() {
  const { role, memo } = readRole();
  if (!role) return toast('가족 안에서의 역할을 골라 주세요', 'circle-alert');
  const name = $('#regName').value.trim() || (role !== 'me' ? ROLE_INFO[role].label : '');
  if (!name) return toast('이름을 입력하세요', 'circle-alert');
  try {
    const r = await api('POST', '/v1/devices', { name, role, memo });
    store.set('token', r.token);
    store.set('name', name);
    store.set('role', role);
    native?.setToken(r.token);
    render();
  } catch (e) {
    toast('서버에 연결할 수 없습니다', 'circle-alert');
  }
}

const gated = (fn) => (arg) => (signedIn() ? fn(arg) : onboardingPage());

/* ---------------- 공통 조각 ---------------- */
const CHIPS = {
  voice_phishing: ['danger', 'siren', '보이스피싱 의심'],
  other_scam: ['warn', 'triangle-alert', '다른 사기 의심'],
  normal: ['safe', 'shield-check', '사기 징후 못 찾음'],
};
const STEP = { queued: '대기 중', transcribing: '음성 변환 중', analyzing: '분석 중' };

function verdictChip(r, label) {
  if (r.status === 'failed') return `<span class="chip danger">${ic('circle-x')}실패</span>`;
  if (r.status !== 'done') return `<span class="chip pri">${ic('loader')}${STEP[r.status] || esc(r.status)}</span>`;
  const c = CHIPS[label];
  return c ? `<span class="chip ${c[0]}">${ic(c[1])}${c[2]}</span>` : `<span class="chip">${ic('circle-help')}판단 어려움</span>`;
}

// 파일명의 이름과 전화번호를 화면에 드러내지 않고 시각만 보여 줍니다. 파일명에 시각이 없으면 올린 시각을 씁니다.
function callTitle(r) {
  if (r.sample) return esc(r.filename);
  const m = /_\d{2}(\d{2})(\d{2})_(\d{2})(\d{2})\d{2}\./.exec(r.filename);
  if (m) return `${+m[1]}월 ${+m[2]}일 ${m[3]}:${m[4]} 통화`;
  const d = new Date(r.created_at * 1000);
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} 올린 통화`;
}

// 모델이 스스로 매긴 값이라 통계적 확률로 표현하지 않습니다. 사람이 판정을 고치면 숨깁니다.
function confidenceBar(r) {
  if (r.status !== 'done' || r.review_label || r.label !== 'voice_phishing' || r.confidence == null) return '';
  const percent = Math.round(r.confidence * 100);
  return `<div class="confidence"><div class="confidence-top"><span>AI 판단 확신도</span><b>${percent}%</b></div>
    <div class="confidence-track"><span style="width:${percent}%"></span></div>
    <div class="confidence-note">실제 사기일 확률이 아니라 AI가 판단에 얼마나 확신하는지를 나타냅니다.</div></div>`;
}

// AI가 풀어 쓴 요약은 보여 주지 않습니다. 근거 대조는 보이스피싱 의심일 때만 보여 주고 나머지는 한 줄로 넘깁니다.
function factBox(r, top) {
  if (r.status !== 'done') return '';
  const label = r.review_label || r.label;
  if (label !== 'voice_phishing' || !r.evidence.length) {
    const line = { normal: '사기로 볼 만한 말을 찾지 못했습니다.', other_scam: '보이스피싱은 아니지만 다른 사기가 의심됩니다. 판정을 확인해 주세요.', voice_phishing: '직접 보이스피싱으로 표시한 통화입니다.' }[label] || '판단하기 어려운 통화입니다. 판정을 확인해 주세요.';
    return `<div class="call-text">${line}</div>`;
  }
  return `<div class="fact-box">
    ${top ? `<small>비슷한 수법</small><b>${esc(top.name)}</b>` : '<b>확인된 말</b>'}
    <div class="fact-head">${ic('badge-check')}녹취에서 확인한 말</div>
    <ul class="fact-list">${r.evidence.map((e) => `<li>${ic('check')}<span>“${esc(e)}”</span></li>`).join('')}</ul>
    <div class="fact-note">녹취에서 그대로 옮겼습니다. 말한 내용이 사실이라는 뜻은 아니며, 음성 변환 오류가 있을 수 있습니다.</div>
    ${top ? `<div class="fact-advice"><b>이렇게 확인하세요</b><p>${esc(top.advice)}</p></div>` : ''}
  </div>`;
}

function recordingCard(r) {
  const label = r.review_label || r.label;
  const top = r.matches[0];
  return `<div class="card mt">
    ${r.sample ? '<span class="chip">예시 통화</span> ' : ''}${verdictChip(r, label)}
    <div class="call-title">${callTitle(r)}</div>
    ${confidenceBar(r)}
    ${r.status === 'failed' ? '<div class="call-text">처리에 실패했습니다. 다시 시도해 주세요.</div>' : ''}
    ${factBox(r, top)}
    <div class="link-row">
      ${r.status === 'failed' ? `<button onclick="act('POST','/v1/recordings/${r.id}/complete')">다시 시도</button>` : ''}
      ${feedbackActions(r)}
      <button class="quiet" onclick="deleteSheet('${r.id}')">삭제</button>
    </div>
  </div>`;
}

function alertCard(a) {
  const unread = !a.acked;
  return `<div class="card mt ${unread ? 'soft-danger' : ''}">
    <span class="chip ${unread ? 'danger' : ''}">${ic(unread ? 'siren' : 'check')}${unread ? '가족 경고' : '확인함'}</span>
    <div class="call-title">${esc(a.title)}</div>
    <div class="call-text">${esc(a.body)}</div>
    ${unread ? `<div class="link-row"><button onclick="act('POST','/v1/alerts/${a.id}/ack')">확인함</button></div>` : ''}
  </div>`;
}

const emptyCard = (t) => `<div class="card mt"><div class="empty">${t}</div></div>`;

async function act(method, path, body) {
  try {
    const r = await api(method, path, body);
    closeSheet();
    lastData = '';
    refresh();
    return r;
  } catch (e) {
    toast('요청에 실패했습니다', 'circle-alert');
  }
}

// 사람의 확인을 오탐률과 다음 개선의 근거로 모읍니다.
function feedbackActions(r) {
  if (r.status !== 'done' || r.sample) return '';
  if (r.review_label) return `<span class="feedback-done">${ic('circle-check')}확인 완료</span><button class="quiet" onclick="reviewSheet('${r.id}')">고치기</button>`;
  const known = ['voice_phishing', 'other_scam', 'normal'].includes(r.label);
  if (!known) return `<button onclick="reviewSheet('${r.id}')">판정 확인</button>`;
  return `<button onclick="act('POST','/v1/recordings/${r.id}/review',{label:'${r.label}'})">${ic('thumbs-up')}판정이 맞아요</button>
    <button class="quiet" onclick="reviewSheet('${r.id}')">${ic('thumbs-down')}틀렸어요</button>`;
}

function reviewSheet(id) {
  const opt = (label, t, reason) => `<button class="btn line block" onclick="act('POST','/v1/recordings/${id}/review',{label:'${label}',reason:'${reason}'})">${t}</button>`;
  openSheet(`<div class="b" style="font-size:18px">이 통화는 실제로 무엇이었나요?</div>
    <div class="muted small" style="margin-top:6px">확인 결과는 통화 내용 없이 판정 결과만 모아 정확도를 재는 데 씁니다. 잠금은 이 선택으로 풀리지 않습니다.</div>
    <div class="btn-col">${opt('voice_phishing', '보이스피싱', '사용자 확인')}${opt('other_scam', '다른 사기 (글자 기록을 데이터셋에 보관)', '사용자 확인')}${opt('normal', '사기 아님 (글자 기록 삭제)', '정상 통화')}</div>`);
}

function deleteSheet(id) {
  openSheet(`<div class="b" style="font-size:18px">이 기록을 삭제할까요?</div>
    <div class="muted small" style="margin-top:6px">서버의 분석 결과와 글자 기록을 지웁니다.</div>
    <div class="btn-col"><button class="btn danger block" onclick="act('DELETE','/v1/recordings/${id}')">삭제</button><button class="btn line block" onclick="closeSheet()">취소</button></div>`);
}

/* ---------------- 홈 ---------------- */
SCREENS.home = gated(() => `<div class="page">
  <div class="brand-bar"><button class="logo-home" onclick="logoHome()" aria-label="소개 페이지로"><img src="assets/brand/logo-horizontal.png" alt="Cody Safe"></button>
    <span class="brand-actions"><button class="brand-bell" onclick="go('family')" aria-label="가족 경고">${ic('bell')}</button><button class="brand-bell" onclick="go('me')" aria-label="MY">${ic('user-round')}</button></span></div>
  <div class="home-greeting">안녕하세요${store.get('name') ? `, ${esc(store.get('name'))}님` : ''}</div>
  <div class="home-sub">오늘도 함께 살펴볼게요.</div>
  ${showFlow() ? `<div class="flow-home">${flowDemo()}</div>` : ''}
  <div id="data"></div>
</div>`);

function homeData({ recordings, recs, family, alerts, lock, reports, pet }) {
  // 예시 통화는 홈의 통화 수와 의심 건수에 넣지 않습니다.
  const items = recordings.items.filter((r) => !r.sample);
  const flagged = items.filter((r) => ['voice_phishing', 'other_scam'].includes(r.review_label || r.label)).length;
  const reviews = items.filter((r) => r.needs_review).length;
  const unread = alerts.items.filter((a) => !a.acked);
  return `${lock.locked ? `<button class="card soft-danger lock-banner" onclick="go('lock')">${ic('lock')}<span><b>금융 앱 잠금 중</b><br>${lockMinutes(lock)}분 남음 · 눌러서 확인</span></button>` : ''}
    ${petHomeCard(pet)}
    <div class="hero">
      <div class="hero-label">분석한 통화</div>
      <div class="hero-score">${recs.analyzed}<small>건</small></div>
      <div class="hero-meta">사기 의심 <b>${flagged}건</b> · 연결된 가족 <b>${family.guardians.length}명</b></div>
    </div>
    <div class="quick-grid">
      ${[['detect', 'shield-check', '통화 검사'], ['passphrase', 'key-round', '가족 암구호'], ['lock', 'lock', '금융 앱 잠금'], ['sim', 'gamepad-2', '사기 체험']]
        .map(([k, i, t]) => `<button onclick="go('${k}')"><span>${ic(i)}</span>${t}</button>`).join('')}
    </div>
    ${unread.map(alertCard).join('')}
    ${reviews ? `<button class="card mt soft-warn" style="width:100%;text-align:left" onclick="go('detect')"><b>검토가 필요한 통화 ${reviews}건</b><br>판정을 확인해 주시면 탐지 개선에 쓰입니다.</button>` : ''}
    ${recs.items.length ? `<div class="sec-title">자주 의심된 사기 유형</div>
      ${recs.items.map((r) => `<div class="card mt"><span class="chip pri">${r.count}회 의심</span>
      <div class="call-title">${esc(r.name)}</div><div class="call-text">${esc(r.advice)}</div>
      <div class="call-text" style="color:var(--pri);font-weight:700;font-size:13px">추천 훈련 · ${esc(r.training)}</div></div>`).join('')}` : ''}
    ${items.length ? `<div class="sec-title">최근 분석 <button class="more" onclick="go('detect')">전체 보기${ic('chevron-right')}</button></div>
      ${items.slice(0, 3).map(recordingCard).join('')}`
    : `<button class="home-empty" onclick="go('detect')"><span>${ic('sparkles')}</span><span><b>아직 분석한 통화가 없어요</b><small>예시 통화로 어떻게 동작하는지 먼저 볼 수 있어요.</small></span>${ic('chevron-right')}</button>`}
    ${trendsBlock()}
    ${reports.some((r) => r.rank) ? `<div class="sec-title">제보 TOP 3 <button class="more" onclick="go('report')">전체 보기${ic('chevron-right')}</button></div>
      <div class="card trend-list">${reports.filter((r) => r.rank).map((r) => `<button class="trend-row top-row" onclick="go('report')"><time>${r.rank}위</time><span><strong>${esc(r.title)}</strong><small>추천 ${r.votes} · 이용자 제보, 사실 확인 전</small></span>${ic('chevron-right')}</button>`).join('')}</div>` : ''}`;
}

/* ---------------- 웹 설명용 처리 흐름 영상 ---------------- */
const FLOW_STEPS = [
  ['phone-off', '통화 종료', '삼성 전화 앱이 통화를 녹음해 둡니다', '통화 4분 12초 종료'],
  ['folder-down', '녹음 저장', '녹음 파일이 지정한 폴더에 저장됩니다', 'Recordings/Call/통화_1432.m4a'],
  ['cloud-upload', 'S3 업로드', '앱이 15초마다 폴더를 확인해 새 파일을 올립니다', 's3://…/recordings/{기기 ID}/…m4a'],
  ['audio-lines', '음성 변환', 'STT가 음성을 글자로 바꿉니다', '"안전 계좌로 옮기셔야 합니다"'],
  ['search', 'RAG 조회', '비슷한 사기 수법을 찾아 참고 자료로 넘깁니다', '유사 수법: 기관 사칭'],
  ['brain-circuit', 'AI 판정', 'LLM이 녹취와 참고 자료를 함께 보고 판정합니다', '판정: 보이스피싱 의심'],
  ['badge-check', '녹취 대조', '근거 문장이 통화에 실제로 있었는지 확인합니다', '근거 3개 일치'],
  ['bell-ring', '후속 조치', '가족에게 알리고, 강한 의심이면 금융 앱을 잠급니다', '가족 알림 전송 · 금융 앱 잠금'],
];
const FLOW_MS = 2300;
let flowStep = 0;
let flowPaused = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const showFlow = () => !native && !embedded;

function flowDemo() {
  return `<section class="flow-video" aria-label="통화 후 처리 흐름 설명">
    <div class="flow-top"><span class="flow-title">통화 후 이렇게 동작합니다</span><span class="flow-note">예시 화면</span>
      <button class="flow-pause" id="flowPause" onclick="toggleFlow()"></button></div>
    <div class="flow-stage" id="flowStage"></div>
    <div class="flow-track" style="--count:${FLOW_STEPS.length}"><i id="flowFill"></i>
      ${FLOW_STEPS.map((s, i) => `<button class="flow-node" data-i="${i}" onclick="jumpFlow(${i})" aria-label="${s[1]}">${ic(s[0])}<span>${s[1]}</span></button>`).join('')}
    </div>
    <p class="flow-admin">${ic('info')}서비스 이해를 돕기 위한 설명 화면입니다. 안드로이드 앱 사용자에게는 표시되지 않습니다.</p>
  </section>`;
}

function drawFlow() {
  const stage = $('#flowStage');
  if (!stage) return;
  const [icon, title, text, sample] = FLOW_STEPS[flowStep];
  stage.innerHTML = `<div class="flow-icon">${ic(icon)}</div><div class="flow-copy"><small>${flowStep + 1} / ${FLOW_STEPS.length}</small><b>${title}</b><p>${text}</p><code>${esc(sample)}</code></div>`;
  document.querySelectorAll('.flow-node').forEach((n, i) => {
    n.classList.toggle('on', i === flowStep);
    n.classList.toggle('done', i < flowStep);
  });
  $('#flowFill').style.setProperty('--progress', flowStep / (FLOW_STEPS.length - 1));
  $('#flowPause').innerHTML = `${ic(flowPaused ? 'play' : 'pause')}${flowPaused ? '재생' : '일시정지'}`;
  icons();
}

let flowRun = 0;
function runFlow() {
  const run = ++flowRun;
  drawFlow();
  if (flowPaused) return;
  later(() => {
    if (run !== flowRun || flowPaused || !$('#flowStage')) return;
    flowStep = (flowStep + 1) % FLOW_STEPS.length;
    runFlow();
  }, flowStep === FLOW_STEPS.length - 1 ? FLOW_MS * 2 : FLOW_MS);
}

function toggleFlow() {
  flowPaused = !flowPaused;
  runFlow();
}

function jumpFlow(i) {
  flowStep = i;
  runFlow();
}

/* ---------------- 내 대시보드 ---------------- */
function userDashboard({ dash }) {
  const t = dash.training;
  const recommend = t.weak.filter((w) => SCENARIOS[w.scenario]);
  const stat = (v, label) => `<div class="stat"><b>${v}</b><span>${label}</span></div>`;
  return `<div class="sec-title">내 대시보드</div>
    <div class="stat-grid">${stat(t.average == null ? '-' : t.average + '점', '체험 평균')}${stat(t.count + '회', '체험 횟수')}${stat(dash.calls.total + '건', '분석한 통화')}${stat(dash.calls.confirmed + '건', '내가 확인한 판정')}</div>
    <div class="sec-title">다음에 연습할 수법</div>
    ${recommend.length ? `<div class="card trend-list">${recommend.map((w) => `<button class="trend-row top-row" onclick="go('play/${esc(w.scenario)}')"><time>${w.score}점</time><span><strong>${esc(SCENARIOS[w.scenario].title)}</strong><small>${esc(w.tag)} · 다시 풀면 추천이 갱신됩니다</small></span>${ic('chevron-right')}</button>`).join('')}</div>` : emptyCard(t.count ? '틀린 수법이 없습니다. 다른 시나리오도 도전해 보세요.' : '체험을 마치면 약한 수법을 추천해 드립니다.')}`;
}

/* ---------------- 커뮤니티 제보 ---------------- */
let reportCategories = [];

// 제보로 만든 시나리오는 이용자 글에서 나왔으므로 화면에 넣기 전에 모두 이스케이프합니다.
function registerReportScenario(r) {
  if (!r.scenario) return;
  const s = r.scenario;
  SCENARIOS['r' + r.id] = {
    title: esc(s.title), tag: '제보 기반', icon: 'megaphone', color: '#0047AB', soft: '#E8F0FB', difficulty: 'AI 생성', mins: 3,
    desc: esc(s.desc), generated: true,
    contact: { name: esc(s.contact), sub: '제보를 바탕으로 만든 가상 대화', av: esc(s.contact.slice(0, 1)) },
    steps: s.steps.map((st) => ({
      msgs: st.msgs.map(esc),
      choices: st.choices.map((c) => ({ t: esc(c.t), ok: c.ok, fb: esc(c.fb), act: c.act })),
    })),
    signals: s.signals.map(esc),
  };
}

async function loadReportScenarios() {
  if (!signedIn()) return [];
  const { items, categories } = await api('GET', '/v1/reports');
  reportCategories = categories;
  items.forEach(registerReportScenario);
  return items;
}

SCREENS.report = gated(() => `<div class="page">
  <div class="lead" style="margin-top:6px">커뮤니티</div>
  <div class="lead-sub" style="margin-top:6px">새 수법이 제보될수록 방어 훈련도 함께 늘어납니다. 추천 상위 3개 제보는 체험 시나리오로 만들 수 있어요.</div>
  <button class="btn grad block mt" onclick="reportSheet()">${ic('pencil')}내가 겪은 수법 제보하기</button>
  <div class="muted small report-note">이용자 제보이며 사실 확인 전입니다. 추천 수는 공식 피해 통계가 아닙니다.</div>
  <div id="data"></div>
</div>`);

function reportCard(r) {
  const made = !!r.scenario;
  return `<div class="card mt report-card ${r.rank ? 'top' : ''}">
    <div class="row between"><div class="row" style="gap:6px">${r.rank ? `<span class="rank-badge">${r.rank}</span>` : ''}<span class="chip">${esc(r.category)}</span>${r.is_demo ? '<span class="chip">시연 예시</span>' : ''}</div>
      <button class="vote ${r.voted ? 'on' : ''}" onclick="voteReport(${r.id}, ${r.voted})" aria-label="추천">${ic('thumbs-up')}${r.votes}</button></div>
    <div class="call-title">${esc(r.title)}</div>
    <div class="call-text">${esc(r.body)}</div>
    <div class="link-row">
      ${made ? `<button onclick="go('play/r${r.id}')">${ic('play')}시뮬레이션 체험</button>` : r.rank ? `<button id="mk${r.id}" onclick="makeScenario(${r.id})">${ic('wand-sparkles')}AI 시뮬레이션 만들기</button>` : ''}
      ${r.mine ? `<button class="quiet" onclick="act('DELETE','/v1/reports/${r.id}')">삭제</button>` : ''}
    </div>
  </div>`;
}

const reportData = ({ reports }) => (reports.length ? reports.map(reportCard).join('') : emptyCard('아직 제보가 없습니다. 첫 제보를 남겨 주세요.'));

function reportSheet() {
  openSheet(`<div class="b" style="font-size:18px">사기 수법 제보</div>
    <div class="muted small" style="margin-top:6px">이름과 사진, 내 정보는 쓰지 마세요. 전화번호와 계좌번호, 링크는 자동으로 가립니다. 작성자는 공개되지 않습니다.</div>
    <div class="field"><label for="repCat">유형</label><select id="repCat">${reportCategories.map((c) => `<option>${esc(c)}</option>`).join('')}</select></div>
    <div class="field"><label for="repTitle">제목</label><input id="repTitle" maxlength="60" placeholder="예: 건강검진 결과 확인 문자"></div>
    <div class="field"><label for="repBody">어떤 일이 있었나요?</label><textarea id="repBody" maxlength="1000" placeholder="상대가 무엇을 요구했는지 적어 주세요"></textarea></div>
    <div class="btn-col"><button class="btn pri block" onclick="sendReport()">제보하기</button><button class="btn line block" onclick="closeSheet()">취소</button></div>`);
}

async function sendReport() {
  const title = $('#repTitle').value.trim();
  const body = $('#repBody').value.trim();
  if (title.length < 4 || body.length < 10) return toast('제목 4자, 내용 10자 이상 입력해 주세요', 'circle-alert');
  try {
    await api('POST', '/v1/reports', { category: $('#repCat').value, title, body });
    closeSheet();
    toast('제보를 올렸습니다');
    lastData = '';
    refresh();
  } catch (e) {
    toast(e.message === '429' ? '제보는 하루 5건까지 가능합니다' : '제보하지 못했습니다', 'circle-alert');
  }
}

async function voteReport(id, voted) {
  try {
    await api(voted ? 'DELETE' : 'POST', `/v1/reports/${id}/vote`);
    lastData = '';
    refresh();
  } catch (e) {
    toast('추천하지 못했습니다', 'circle-alert');
  }
}

async function makeScenario(id) {
  const button = $('#mk' + id);
  if (button) { button.disabled = true; button.innerHTML = `${ic('loader')}AI가 시나리오를 만드는 중입니다`; icons(); }
  try {
    await api('POST', `/v1/reports/${id}/scenario`);
    await loadReportScenarios();
    go('play/r' + id);
  } catch (e) {
    toast(e.message === '403' ? '추천 상위 3개만 만들 수 있어요' : '만들지 못했습니다. 다시 시도해 주세요', 'circle-alert');
    lastData = '';
    refresh();
  }
}

/* ---------------- 가족 암구호 ---------------- */
let phraseShown = false;
let phraseTimer = null;

function showPhrase(on) {
  phraseShown = on;
  clearTimeout(phraseTimer);
  // 켜 둔 화면을 누가 옆에서 읽지 못하게 잠시 뒤 다시 가립니다.
  if (on) phraseTimer = setTimeout(() => showPhrase(false), 30000);
  document.querySelector('.phrase-card')?.classList.toggle('shown', on);
}

function timeLeft(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.ceil((seconds % 3600) / 60);
  return h ? `${h}시간 ${m}분` : `${m}분`;
}

function phraseCard(p) {
  return `<div class="phrase-card ${phraseShown ? 'shown' : ''}">
    <div class="phrase-top"><span>${ic('key-round')}오늘의 가족 암구호</span><span>${timeLeft(p.seconds_left)} 뒤 변경</span></div>
    <button class="phrase-words" onclick="showPhrase(!phraseShown)" aria-label="암구호 보기">
      <span class="phrase-text">${p.words.map(esc).join(' ')}</span>
      <span class="phrase-mask">${ic('eye')}눌러서 보기</span>
    </button>
    <div class="phrase-note">상대가 먼저 말하게 하세요. 암구호를 먼저 알려 주지 마세요.</div>
  </div>`;
}

SCREENS.passphrase = gated(() => `<div class="page">
  <div class="lead" style="margin-top:6px">가족 암구호</div>
  <div class="lead-sub" style="margin-top:6px">가족이라며 돈을 부탁하는 전화가 오면 먼저 물어보세요. 목소리가 같아도 AI일 수 있습니다.</div>
  <div id="data"></div>
</div>`);

function passphraseData({ phrase }) {
  if (!phrase.linked) {
    return `<div class="card mt center"><div class="empty">가족을 연결하면 매일 바뀌는 암구호가 생깁니다.</div>
      <button class="btn pri block" onclick="go('family')">가족 연결하기</button></div>`;
  }
  const steps = [['phone-incoming', '“오늘 암구호가 뭐야?”라고 먼저 물어요'], ['message-circle', '상대가 말한 단어를 화면과 비교해요'], ['circle-check', '맞을 때만 부탁을 들어 줘요']];
  const e = phrase.emergency;
  return `${phraseCard(phrase)}
    <div class="card mt phrase-steps">${steps.map(([i, t], n) => `<div class="phrase-step"><span class="step-no">${ic(i)}</span><span><small>${n + 1}단계</small>${t}</span></div>`).join('')}</div>
    <div class="phrase-verdict">
      <button class="btn line block" onclick="toast('확인했습니다. 그래도 큰돈은 다시 한번 확인하세요')">${ic('check')}맞아요</button>
      <button class="btn danger block" onclick="mismatchSheet()">${ic('x')}안 맞아요</button>
    </div>
    <div class="sec-title">비상 암구호</div>
    <div class="card">
      <div class="row between"><div class="b">폰을 잃어버린 가족 확인용</div><span class="chip ${e ? 'safe' : ''}">${e ? '설정됨' : '미설정'}</span></div>
      <div class="muted small" style="margin-top:6px">${e ? `질문: ${esc(e.question)} · ${esc(e.set_by)}님이 설정` : '오늘의 암구호를 볼 수 없는 가족도 답할 수 있도록, 가족만 아는 질문을 정해 두세요.'}</div>
      <div class="row" style="margin-top:12px">
        ${e ? '<button class="btn pri sm grow" onclick="verifySheet()">답 확인</button>' : ''}
        <button class="btn ghost sm grow" onclick="emergencySheet()">${e ? '바꾸기' : '설정하기'}</button>
      </div>
    </div>
    <div class="muted small phrase-limit">검찰, 금감원 같은 기관 사칭에는 암구호를 쓸 수 없습니다. 기관이 전화로 돈을 요구하면 끊으세요.</div>`;
}

function mismatchSheet() {
  openSheet(`<span class="chip danger">${ic('siren')}사칭 의심</span>
    <div class="b" style="font-size:20px;margin-top:10px">지금 전화를 끊으세요</div>
    <div class="call-text">가족에게는 원래 저장된 번호로 직접 다시 거세요. 상대가 알려 준 새 번호로 걸면 안 됩니다.</div>
    <div class="btn-col"><a class="btn danger block" href="tel:112">${ic('phone')}경찰 112</a><button class="btn line block" onclick="closeSheet()">닫기</button></div>`);
}

function emergencySheet() {
  openSheet(`<div class="b" style="font-size:18px">비상 암구호 정하기</div>
    <div class="muted small" style="margin-top:6px">SNS나 통화에서 쉽게 알 수 없는 답으로 정하세요. 답은 복원할 수 없게 저장되어 가족에게 말로 직접 알려 줘야 합니다.</div>
    <div class="field"><label for="emQ">질문</label><input id="emQ" maxlength="60" placeholder="예: 우리 첫 강아지 이름은?"></div>
    <div class="field"><label for="emA">답</label><input id="emA" maxlength="60" autocomplete="off"></div>
    <div class="btn-col"><button class="btn pri block" onclick="saveEmergency()">저장</button><button class="btn line block" onclick="closeSheet()">취소</button></div>`);
}

async function saveEmergency() {
  const question = $('#emQ').value.trim();
  const answer = $('#emA').value.trim();
  if (question.length < 2 || answer.length < 2) return toast('질문과 답을 두 글자 이상 입력하세요', 'circle-alert');
  await act('PUT', '/v1/family/passphrase/emergency', { question, answer });
}

function verifySheet() {
  openSheet(`<div class="b" style="font-size:18px">상대가 말한 답을 입력하세요</div>
    <div class="field"><label for="emCheck">답</label><input id="emCheck" maxlength="60" autocomplete="off"></div>
    <div class="btn-col"><button class="btn pri block" onclick="verifyEmergency()">확인</button><button class="btn line block" onclick="closeSheet()">취소</button></div>`);
}

async function verifyEmergency() {
  const answer = $('#emCheck').value.trim();
  if (!answer) return toast('답을 입력하세요', 'circle-alert');
  try {
    const { match } = await api('POST', '/v1/family/passphrase/emergency/verify', { answer });
    if (!match) return mismatchSheet();
    closeSheet();
    toast('답이 맞습니다');
  } catch (e) {
    toast(e.message === '429' ? '여러 번 틀렸습니다. 10분 뒤 다시 시도하세요' : '확인하지 못했습니다', 'circle-alert');
  }
}

/* ---------------- 금융 앱 잠금 ---------------- */
const lockMinutes = (lock) => Math.ceil(lock.remaining / 60);

SCREENS.lock = gated(() => `<div class="page">
  <div class="lead" style="margin-top:6px">금융 앱 잠금</div>
  <div class="lead-sub" style="margin-top:6px">보이스피싱이 강하게 의심되면 은행, 간편결제, 증권, 원격제어 앱을 잠시 막습니다.</div>
  <div id="data"></div>
</div>`);

function blockerBlock() {
  if (!native?.blockerEnabled) {
    return `<div class="card mt soft-warn">${native ? '앱을 최신 버전으로 업데이트하면 금융 앱을 실제로 막을 수 있습니다.' : '브라우저에서는 다른 앱을 막을 수 없습니다. 안드로이드 앱에서만 실제로 막습니다.'}</div>`;
  }
  const on = native.blockerEnabled();
  return `<div class="card mt"><div class="row between"><div class="b">앱 차단 권한</div><span class="chip ${on ? 'safe' : 'danger'}">${on ? '켜짐' : '꺼짐'}</span></div>
    <div class="muted small" style="margin-top:6px">접근성 권한으로 지금 열린 앱의 이름만 확인합니다. 화면 내용과 입력한 글자는 읽지 않습니다.</div>
    ${on ? '' : '<button class="btn pri block mt" onclick="CodySafeNative.openBlockerSettings()">접근성 설정 열기</button><div class="muted small" style="margin-top:8px">설치된 서비스에서 CodySafe를 켜 주세요. 제한된 설정이라고 나오면 앱 정보 오른쪽 위 메뉴에서 제한을 먼저 풀어야 합니다.</div>'}
  </div>`;
}

function lockData({ lock }) {
  if (!lock.locked) {
    return `<div class="card mt"><span class="chip safe">${ic('shield-check')}잠금 없음</span>
        <div class="call-text">이상한 전화를 받았다면 판정을 기다리지 말고 직접 잠글 수 있습니다.</div>
        <div class="btn-col"><button class="btn danger block" onclick="lockNow(60)">1시간 잠그기</button><button class="btn line block" onclick="lockNow(2)">2분만 시험해 보기</button></div></div>
      ${blockerBlock()}`;
  }
  return `<div class="card mt soft-danger"><span class="chip danger">${ic('siren')}잠금 중</span>
      <div class="call-title" style="font-size:20px">지금 돈을 보내지 마세요</div>
      <div class="call-text">${lockMinutes(lock)}분 뒤 풀립니다. 검찰, 금감원, 은행은 전화로 이체나 앱 설치를 요구하지 않습니다. 누군가 이 잠금을 풀라고 시켰다면 사기일 가능성이 높습니다.</div></div>
    <div class="btn-col">
      <a class="btn danger block" href="tel:112">${ic('phone')}경찰 112</a>
      <a class="btn line block" href="tel:1332">${ic('phone')}금융감독원 1332</a>
    </div>
    <div class="card mt"><div class="b">잠금을 풀려면</div>
      <div class="call-text">먼저 가족에게 직접 전화해 확인하세요. 연결된 가족은 오늘의 암구호로 서로 확인한 뒤 가족 탭에서 바로 풀 수 있습니다.</div>
      <div class="link-row"><button onclick="go('passphrase')">오늘의 암구호 보기</button><button class="quiet" onclick="releaseSheet()">사기가 아니에요, 직접 풀기</button></div></div>
    ${blockerBlock()}`;
}

/* 잠금이 걸리면 어느 화면에 있든 바로 알립니다. 잠금마다 한 번만 띄웁니다. */
function closeLockAlert() {
  document.querySelector('#lockAlert')?.remove();
  store.set('lockSeen', '1');
}

function showLockAlert(lock) {
  if (document.querySelector('#lockAlert')) return;
  const box = document.createElement('div');
  box.id = 'lockAlert';
  box.setAttribute('role', 'alertdialog');
  box.innerHTML = `<div class="lock-alert-body">
    <div class="lock-alert-icon">${ic('siren')}</div>
    <div class="lock-alert-title">지금 돈을 보내지 마세요</div>
    <div class="lock-alert-text">보이스피싱이 의심되어 금융 앱을 ${lockMinutes(lock)}분 동안 잠갔습니다. 누군가 이체나 앱 설치, 잠금 해제를 시키고 있다면 전화를 끊으세요.</div>
    <div class="btn-col">
      <a class="btn danger block" href="tel:112">${ic('phone')}경찰 112</a>
      <button class="btn pri block" onclick="closeLockAlert();go('passphrase')">${ic('key-round')}가족 암구호 확인</button>
      <button class="btn line block" onclick="closeLockAlert();go('lock')">잠금 내용 보기</button>
    </div></div>`;
  document.querySelector('.screen').appendChild(box);
  icons();
  vibrate([300, 150, 300]);
  beep();
}

async function pollLock() {
  if (embedded || !signedIn()) return;
  try {
    const lock = await api('GET', '/v1/lock');
    if (!lock.locked) {
      store.del('lockSeen');
      document.querySelector('#lockAlert')?.remove();
    } else if (!store.get('lockSeen')) {
      // 직접 잠갔거나 차단되어 잠금 화면으로 들어온 경우에는 이미 보고 있습니다.
      if (route().r === 'lock') store.set('lockSeen', '1');
      else showLockAlert(lock);
    }
  } catch (e) {
    // 다음 주기에 다시 확인합니다.
  }
}

async function lockNow(minutes) {
  await act('POST', '/v1/lock', { minutes });
  native?.syncLock?.();
}

function releaseSheet() {
  openSheet(`<div class="b" style="font-size:18px">정말 직접 푸시겠어요?</div>
    <div class="muted small" style="margin-top:6px">10분 뒤에 풀립니다. 그동안 가족이나 112에 확인해 보세요.</div>
    <div class="btn-col"><button class="btn danger block" onclick="act('POST','/v1/lock/release')">아무도 시키지 않았습니다. 10분 뒤 풀기</button><button class="btn line block" onclick="closeSheet()">취소</button></div>`);
}

async function unlockSheet(id) {
  let phrase = {};
  try { phrase = await api('GET', '/v1/family/passphrase'); } catch (e) { }
  openSheet(`<div class="b" style="font-size:18px">가족의 금융 앱 잠금을 풀까요?</div>
    <div class="muted small" style="margin-top:6px">저장된 번호로 본인에게 직접 전화해 오늘의 암구호를 물어본 뒤에 풀어 주세요.</div>
    ${phrase.words ? `<div class="type-box center"><b>오늘의 암구호</b><p class="unlock-phrase">${phrase.words.map(esc).join(' ')}</p></div>` : ''}
    <div class="btn-col"><button class="btn danger block" onclick="act('POST','/v1/family/protected/${esc(id)}/unlock')">암구호를 확인했습니다. 잠금 풀기</button><button class="btn line block" onclick="closeSheet()">취소</button></div>`);
}

/* ---------------- 검사 ---------------- */
SCREENS.detect = gated(() => `<div class="page">
  <div class="lead" style="margin-top:6px">통화 검사</div>
  <div class="lead-sub" style="margin-top:6px">${native ? '통화가 끝나면 새 녹음 파일을 자동으로 STT로 분석한 뒤 진단 결과를 알려 드립니다.' : '녹음 파일을 올리면 STT로 분석한 뒤 진단 결과를 알려 드립니다. 통화 후 자동 분석은 안드로이드 앱에서 동작합니다.'} 결과는 본인만 볼 수 있습니다.</div>
  ${showFlow() ? flowDemo() : `<div class="detect-flow">${['통화 종료', 'STT 변환', 'AI 진단', '결과 확인'].map((t, i) => `${i ? ic('chevron-right') : ''}<span>${t}</span>`).join('')}</div>`}
  <div class="card mt">${folderBlock()}<button class="guide-link" onclick="folderGuide()">${ic('circle-help')}녹음 폴더 설정 가이드${ic('chevron-right')}</button></div>
  <button class="btn grad block mt" onclick="$('#filePick').click()">${ic('upload')}파일 직접 올려 검사</button>
  <div class="sec-title">예시로 체험하기</div>
  <div class="muted small sample-intro">가상의 통화 대본으로 분석 결과를 미리 봅니다. ${native ? '기록에 남지 않고' : '아래 분석 결과에 예시로 표시되며,'} 가족 알림과 잠금은 일어나지 않습니다.</div>
  <div id="samples"></div>
  <div class="sec-title">분석 결과</div>
  <div id="data"></div>
</div>`);

function folderBlock() {
  if (!native) return webFolderBlock();
  const folder = native.folderLabel();
  return `<div class="row between"><div class="b">녹음 폴더</div><span class="chip ${folder ? 'safe' : ''}">${folder ? '연결됨' : '연결 안 됨'}</span></div>
    <div class="muted small" style="margin-top:6px">${folder ? esc(folder) + ' · ' : ''}연결한 뒤에 새로 저장된 파일만 분석합니다.</div>
    <div class="row" style="margin-top:12px"><button class="btn ghost sm grow" onclick="CodySafeNative.pickFolder()">폴더 선택</button><button class="btn line sm grow" onclick="CodySafeNative.syncNow();toast('동기화를 요청했습니다')">지금 동기화</button></div>`;
}

/* ---------------- 예시 통화 ---------------- */
let sampleList = [];

async function loadSamples() {
  if (!signedIn()) return;
  try {
    if (!sampleList.length) sampleList = (await api('GET', '/v1/samples')).items;
    const host = $('#samples');
    if (!host) return;
    const button = (s) => `<button class="sample-card" onclick="openSample('${esc(s.id)}')"><span>${esc(s.title)}</span>${ic('chevron-right')}</button>`;
    const group = (kind, chip, title) => `<div class="sample-group"><span class="chip ${chip}">${title}</span>${sampleList.filter((s) => s.expected === kind).map(button).join('')}</div>`;
    host.innerHTML = group('voice_phishing', 'danger', '보이스피싱 예시') + group('normal', 'safe', '정상 대화 예시');
    icons();
  } catch (e) {
    if ($('#samples')) $('#samples').innerHTML = emptyCard('예시를 불러오지 못했습니다.');
  }
}

function sampleResultHtml(r) {
  const label = r.label;
  const matched = label === r.expected;
  return `<div class="sample-result">${verdictChip(r, label)}
    ${confidenceBar(r)}
    ${factBox(r, r.matches[0])}
    <div class="sample-expected ${matched ? 'ok' : 'miss'}">${ic(matched ? 'circle-check' : 'circle-alert')}대본의 의도와 ${matched ? '같은 결과입니다' : '다른 결과입니다'}</div></div>`;
}

async function openSample(id) {
  const s = sampleList.find((x) => x.id === id);
  if (!s) return;
  openSheet(`<div class="sample-sheet"><span class="chip">가상 대본</span>
    <div class="b" style="font-size:18px;margin-top:8px">${esc(s.title)}</div>
    <div class="sample-chat">${s.turns.map((t, i) => `<div class="sample-line ${i % 2 ? 'me' : ''}">${esc(t)}</div>`).join('')}</div>
    <div id="sampleResult"><div class="sample-wait">${ic('loader')}AI가 대본을 분석하고 있습니다</div></div>
    <div class="muted small" style="margin-top:10px">음성 변환 단계는 건너뛰고 분석만 보여 줍니다.</div>
    <button class="btn line block mt" onclick="closeSheet()">닫기</button></div>`);
  icons();
  try {
    const r = await api('POST', `/v1/samples/${id}/analyze?record=${native ? 0 : 1}`);
    if ($('#sampleResult')) $('#sampleResult').innerHTML = sampleResultHtml(r);
    if (!native) { lastData = ''; refresh(); }
  } catch (e) {
    if ($('#sampleResult')) $('#sampleResult').innerHTML = '<div class="sample-wait">분석에 실패했습니다. 잠시 뒤 다시 시도해 주세요.</div>';
  }
  icons();
}

/* ---------------- 폴더 설정 가이드 ---------------- */
function pickCallFolder() {
  closeSheet();
  if (native) (native.pickCallFolder || native.pickFolder).call(native);
  else if (canWatch()) connectFolder();
  else $('#dirPick').click();
}

const guideSteps = (steps) => `<div class="phrase-steps guide-steps">${steps.map((t, i) => `<div class="phrase-step"><span class="step-no">${i + 1}</span><span>${t}</span></div>`).join('')}</div>`;

function folderGuide() {
  openSheet(`<div class="b" style="font-size:18px">녹음 폴더 설정 가이드</div>
    <div class="muted small" style="margin-top:6px">삼성 전화 앱의 통화 녹음 기준입니다.</div>
    ${guideSteps([
      '전화 앱 오른쪽 위 <b>⋮</b>를 눌러 <b>설정 → 통화 녹음</b>으로 들어갑니다.',
      '<b>통화 자동 녹음</b>을 켜고 녹음할 범위를 고릅니다.',
      native ? '아래 버튼을 누르고, 폴더 화면 아래쪽의 <b>이 폴더 사용 → 허용</b>을 누릅니다.' : '아래 버튼을 누르고 <b>내장 저장공간 → Recordings → Call</b> 폴더를 고릅니다.',
      native ? '이제 통화가 끝나면 새 녹음을 자동으로 검사합니다. 바로 검사하려면 <b>지금 동기화</b>를 누릅니다.' : '폴더를 고른 뒤 새로 생긴 녹음은 다시 검사해야 분석됩니다. 자동 검사는 안드로이드 앱에서 동작합니다.',
    ])}
    <button class="btn pri block mt" onclick="pickCallFolder()">${ic('folder-open')}녹음 폴더 열기</button>
    <div class="muted small guide-note">폴더가 바로 열리지 않으면 Recordings 안의 Call을 고르세요. 오래된 기기는 내장 저장공간의 Call 폴더일 수 있습니다. 메뉴 이름은 기기와 버전에 따라 다릅니다.</div>
    <button class="btn line block" style="margin-top:8px" onclick="closeSheet()">닫기</button>`);
}

const detectData = ({ recordings }) => (recordings.items.length ? recordings.items.map(recordingCard).join('') : emptyCard('아직 올린 파일이 없습니다.'));

async function uploadFile(file, clientKey) {
  const r = await api('POST', '/v1/recordings', { filename: file.name, client_key: clientKey, content_type: 'application/octet-stream', direct: false });
  if (r.already_uploaded) return false;
  const url = new URL(r.upload_url);
  // 서버의 공개 주소 설정과 무관하게 지금 접속한 주소로 보냅니다.
  const target = url.pathname + url.search;
  const put = await fetch(target, { method: 'PUT', headers: { 'Content-Type': 'application/octet-stream' }, body: file });
  if (!put.ok) throw new Error(put.status);
  await api('POST', `/v1/recordings/${r.id}/complete`);
  return true;
}

/* ---------------- 웹 폴더 검사 ----------------
   HTTPS 브라우저: 폴더를 연결해 두면 페이지를 연 동안 새 파일을 자동으로 올립니다.
   그 외: 폴더를 고를 때마다 확인을 받고 아직 안 보낸 파일을 올립니다. */
const AUDIO_EXT = /\.(m4a|mp3|mp4|wav|flac|ogg|amr|webm|txt)$/i;
const SCAN_MS = 30000;
const SETTLE_MS = 30000;
const fileKey = (f) => `${f.name}|${f.size}|${f.lastModified}`;
const canWatch = () => !native && window.isSecureContext && !!window.showDirectoryPicker;
let folderHandle = null;
let folderGranted = false;
let scanning = false;
let pendingFiles = [];

function seenKeys() {
  try { return new Set(JSON.parse(store.get('seen') || '[]')); } catch (e) { return new Set(); }
}
function markSeen(key) {
  const seen = seenKeys();
  seen.add(key);
  store.set('seen', JSON.stringify([...seen]));
}

async function sendFiles(files) {
  let sent = 0;
  for (const f of files) {
    const key = fileKey(f);
    try {
      if (await uploadFile(f, key)) sent++;
      markSeen(key);
    } catch (e) {
      // 받지 않는 형식은 다시 시도하지 않고, 그 외 오류는 다음 검사에서 다시 올립니다.
      if (e.message === '415') markSeen(key);
    }
  }
  lastData = '';
  refresh();
  return sent;
}

function idb(mode, fn) {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open('guard', 1);
    open.onupgradeneeded = () => open.result.createObjectStore('kv');
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const req = fn(open.result.transaction('kv', mode).objectStore('kv'));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    };
  });
}

async function connectFolder() {
  try {
    folderHandle = await window.showDirectoryPicker({ mode: 'read' });
  } catch (e) {
    return; // 사용자가 취소함
  }
  await idb('readwrite', (s) => s.put(folderHandle, 'folder')).catch(() => {});
  store.set('folderSince', String(Date.now()));
  folderGranted = true;
  render();
}

async function regrantFolder() {
  folderGranted = (await folderHandle.requestPermission({ mode: 'read' })) === 'granted';
  render();
  scanFolder();
}

async function restoreFolder() {
  if (!canWatch()) return;
  folderHandle = await idb('readonly', (s) => s.get('folder')).catch(() => null);
  if (!folderHandle) return;
  folderGranted = (await folderHandle.queryPermission({ mode: 'read' })) === 'granted';
  if (route().r === 'detect') render();
}

async function scanFolder() {
  if (!folderHandle || !folderGranted || scanning || !signedIn()) return 0;
  scanning = true;
  try {
    const since = Number(store.get('folderSince')) || 0;
    const seen = seenKeys();
    const files = [];
    for await (const entry of folderHandle.values()) {
      if (entry.kind !== 'file' || !AUDIO_EXT.test(entry.name)) continue;
      const f = await entry.getFile();
      if (f.lastModified >= since && Date.now() - f.lastModified >= SETTLE_MS && !seen.has(fileKey(f))) files.push(f);
    }
    return await sendFiles(files);
  } catch (e) {
    folderGranted = false;
    return 0;
  } finally {
    scanning = false;
  }
}

function webFolderBlock() {
  if (canWatch()) {
    const on = folderHandle && folderGranted;
    return `<div class="row between"><div class="b">녹음 폴더</div><span class="chip ${on ? 'safe' : ''}">${on ? '자동 검사 중' : folderHandle ? '권한 필요' : '연결 안 됨'}</span></div>
      <div class="muted small" style="margin-top:6px">${folderHandle ? esc(folderHandle.name) + ' · ' : ''}이 페이지를 열어 둔 동안, 연결 후 새로 저장된 파일을 자동으로 분석합니다.</div>
      <div class="row" style="margin-top:12px">
        ${folderHandle && !folderGranted ? '<button class="btn pri sm grow" onclick="regrantFolder()">권한 다시 허용</button>' : ''}
        <button class="btn ghost sm grow" onclick="connectFolder()">폴더 선택</button>
        ${on ? `<button class="btn line sm grow" onclick="scanFolder().then((n)=>toast(n?n+'개 파일을 올렸습니다':'새 파일이 없습니다'))">지금 검사</button>` : ''}
      </div>`;
  }
  return `<div class="row between"><div class="b">녹음 폴더</div><span class="chip">선택할 때 검사</span></div>
    <div class="muted small" style="margin-top:6px">폴더를 고르면 아직 보내지 않은 녹음을 확인한 뒤 올립니다. 자동 감시는 HTTPS 접속이나 안드로이드 앱에서 동작합니다.</div>
    <button class="btn ghost sm block" style="margin-top:12px" onclick="$('#dirPick').click()">폴더 골라 검사</button>`;
}

$('#dirPick').addEventListener('change', (e) => {
  const seen = seenKeys();
  pendingFiles = [...e.target.files].filter((f) => AUDIO_EXT.test(f.name) && !seen.has(fileKey(f)));
  e.target.value = '';
  if (!pendingFiles.length) return toast('새로 보낼 파일이 없습니다', 'circle-alert');
  openSheet(`<div class="b" style="font-size:18px">파일 ${pendingFiles.length}개를 분석할까요?</div>
    <div class="muted small" style="margin-top:6px">선택한 폴더의 녹음이 서버로 전송되고, 통화 상대의 음성도 포함됩니다.</div>
    <div class="btn-col"><button class="btn pri block" onclick="confirmFolderUpload()">보내기</button><button class="btn line block" onclick="closeSheet()">취소</button></div>`);
});

async function confirmFolderUpload() {
  closeSheet();
  toast('업로드 중입니다', 'upload');
  const sent = await sendFiles(pendingFiles);
  pendingFiles = [];
  toast(`${sent}개 파일을 올렸습니다`);
}

$('#filePick').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  toast('업로드 중입니다', 'upload');
  try {
    await uploadFile(file, `manual|${file.name}|${Date.now()}`);
    toast('업로드 완료. 분석 중입니다');
    lastData = '';
    refresh();
  } catch (err) {
    toast(err.message === '415' ? '지원하지 않는 파일 형식입니다' : '업로드에 실패했습니다', 'circle-alert');
  }
});

/* ---------------- 가족 ---------------- */
SCREENS.family = gated(() => `<div class="page">
  <div class="lead" style="margin-top:6px">가족 보호</div>
  <div class="lead-sub" style="margin-top:6px">통화 내용은 공유되지 않습니다. 가족에게는 보이스피싱 의심 여부만 전달됩니다.</div>
  <div id="data"></div>
  <div class="sec-title">가족 연결하기</div>
  <button class="btn ghost block" onclick="createInvite()">${ic('user-plus')}내 초대 코드 만들기</button>
  <div class="card mt"><div class="field" style="margin-top:0"><label for="linkCode">가족에게 받은 초대 코드</label><input id="linkCode" autocapitalize="characters" autocomplete="off" placeholder="8자리 코드"></div>
  <button class="btn pri block mt" onclick="linkFamily()">연결</button></div>
</div>`);

function familyData({ family, alerts, phrase }) {
  const person = (p, note, removable) => `<div class="card mt"><div class="row between"><div class="grow"><div class="b">${esc(p.name)}${p.memo ? ` <span class="muted small">${esc(p.memo)}</span>` : ''}${p.locked ? ` <span class="chip danger">${ic('lock')}금융 앱 잠금 중</span>` : ''}</div><div class="muted small" style="margin-top:2px">${note}</div></div>
    ${removable ? `<button class="btn line sm" onclick="act('DELETE','/v1/family/guardians/${esc(p.id)}')">해제</button>` : ''}
    ${p.locked ? `<button class="btn danger sm" onclick="unlockSheet('${esc(p.id)}')">잠금 풀기</button>` : ''}</div></div>`;
  return `${phrase.linked ? `<div class="mt">${phraseCard(phrase)}</div><button class="btn ghost block phrase-link" onclick="go('passphrase')">암구호 쓰는 법과 비상 암구호${ic('chevron-right')}</button>` : ''}
    <div class="sec-title">받은 가족 경고</div>
    ${alerts.items.length ? alerts.items.map(alertCard).join('') : emptyCard('받은 경고가 없습니다.')}
    <div class="sec-title">내 경고를 받는 가족</div>
    ${family.guardians.length ? family.guardians.map((p) => person(p, '내 보이스피싱 의심 여부만 받습니다.', true)).join('') : emptyCard('연결된 가족이 없습니다.')}
    <div class="sec-title">내가 지키는 가족</div>
    ${family.protected.length ? family.protected.map((p) => person(p, '이 가족의 보이스피싱 의심 여부를 받습니다.', false)).join('') : emptyCard('아직 없습니다.')}`;
}

async function createInvite() {
  try {
    const r = await api('POST', '/v1/family/invite');
    openSheet(`<div class="b center" style="font-size:18px">내 초대 코드</div><div class="code-big">${esc(r.code)}</div>
      <div class="muted small center">10분 안에 가족 폰에 입력하세요. 이 코드를 받은 사람은 내 보이스피싱 의심 여부를 알림으로 받습니다.</div>
      <button class="btn pri block mt" onclick="closeSheet()">닫기</button>`);
  } catch (e) {
    toast('코드를 만들지 못했습니다', 'circle-alert');
  }
}

async function linkFamily() {
  const code = $('#linkCode').value.trim();
  if (!code) return toast('초대 코드를 입력하세요', 'circle-alert');
  try {
    const r = await api('POST', '/v1/family/link', { code });
    $('#linkCode').value = '';
    toast(`${r.protected_name}님과 연결했습니다`);
    lastData = '';
    refresh();
  } catch (e) {
    toast('코드가 맞지 않거나 만료됐습니다', 'circle-alert');
  }
}

/* ---------------- MY ---------------- */
SCREENS.me = gated(() => `<div class="page">
  <div class="lead" style="margin-top:6px">MY</div>
  <div class="card mt">
    <div class="kv"><span>이름</span><span>${esc(store.get('name') || '-')}</span></div>
    <button class="kv role-kv" onclick="roleSheet()"><span>가족 역할</span><span>${ROLE_INFO[store.get('role')]?.label || '선택하기'}${ic('chevron-right')}</span></button>
    <div class="kv"><span>서버</span><span>${esc(location.host)}</span></div>
    <div class="kv"><span>실행 환경</span><span>${native ? '안드로이드 앱' : '브라우저'}</span></div>
  </div>
  <div id="data"></div>
  <button class="btn ghost block mt" onclick="go('lock')">${ic('lock')}금융 앱 잠금</button>
  <div class="sec-title">데이터 처리</div>
  <div class="card"><ul class="notice">
    ${[keepAudio ? '음성은 사용자별로 저장되며, 기록을 삭제하면 함께 지워집니다.' : '음성은 분석 후 삭제합니다. 실패한 음성은 재시도나 삭제 전까지 남습니다.', '일상 통화는 글자 기록을 남기지 않습니다.', '분석 내용은 본인만 볼 수 있습니다.', '가족에게는 보이스피싱 의심 여부만 전달됩니다.'].map((t) => `<li>${ic('lock')}<span>${t}</span></li>`).join('')}
  </ul></div>
  ${browserNotifyBlock()}
  <button class="btn line block mt" onclick="signOut()">${demoMembers.length ? '다른 가족으로 보기' : '이 기기 등록 해제'}</button>
</div>`);

function browserNotifyBlock() {
  if (native) return '';
  const available = window.isSecureContext && 'Notification' in window;
  if (!available) return '<div class="muted small mt">시스템 알림은 HTTPS 접속에서 켤 수 있습니다. 지금은 페이지를 열어 둔 동안 화면 경고와 소리로 알려 드립니다.</div>';
  if (Notification.permission === 'granted') return '<div class="muted small mt">시스템 알림이 켜져 있습니다. 브라우저가 실행 중인 동안 받을 수 있습니다.</div>';
  return '<button class="btn ghost block mt" onclick="Notification.requestPermission().then(render)">브라우저 알림 켜기</button>';
}

function signOut() {
  store.del('token');
  store.del('name');
  store.del('role');
  native?.setToken('');
  go('home');
  render();
}

/* ---------------- 체험: 검증되지 않은 수치와 없는 화면 연결 제거 ---------------- */
const baseSim = SCREENS.sim;
SCREENS.sim = () => baseSim()
  .replace('🔥 이번 주 가장 많이 당한 수법', '대표 수법 체험')
  .replace('기관 사칭 · 평균 정답률 41% · 4분', '기관 사칭 · 3분')
  .replace('내 선택에 따라 사기범의 대화가 달라집니다.', '선택할 때마다 왜 위험한지 바로 알려 드립니다.')
  .replace(/<span class="featnum">기능 \d+<\/span>/, '');

const baseSimResult = simResult;
simResult = function () {
  baseSimResult();
  const buttons = view.querySelectorAll('.row.mt2 .btn');
  view.querySelector('.card.mt.row')?.remove();
  buttons[1].innerHTML = `${ic('list')}다른 시나리오`;
  buttons[1].setAttribute('onclick', "go('sim')");
  icons();
  saveTraining();
};

function saveTraining() {
  const { r, arg } = route();
  if (r !== 'play' || !signedIn() || !sim) return;
  const ok = sim.answers.filter((a) => a.ok).length;
  api('POST', '/v1/training', { scenario: arg || 'family', tag: sim.s.tag, score: Math.round(ok / sim.s.steps.length * 100) })
    .then((res) => showPetReward(res.pet)).catch(() => {});
}

/* ---------------- 데이터 갱신 ---------------- */
SCREENS.pet = gated(petPage);
SCREENS.quiz = gated(quizPage);
const DATA_VIEWS = { pet: petData, home: homeData, detect: detectData, family: familyData, lock: lockData, passphrase: passphraseData, report: reportData, me: userDashboard };
const REPORT_VIEWS = ['home', 'report'];
const PHRASE_VIEWS = ['family', 'passphrase'];
let lastData = '';

async function refresh() {
  const { r } = route();
  const key = SCREENS[r] ? r : 'home';
  const draw = DATA_VIEWS[key];
  if (!draw || !signedIn() || !$('#data')) return;
  try {
    const [recordings, recs, family, alerts, lock] = await Promise.all([
      api('GET', '/v1/recordings'), api('GET', '/v1/recommendations'), api('GET', '/v1/family'), api('GET', '/v1/alerts'), api('GET', '/v1/lock'),
    ]);
    const phrase = PHRASE_VIEWS.includes(key) ? await api('GET', '/v1/family/passphrase') : null;
    // 제보를 못 불러와도 홈의 나머지 내용은 보여 줍니다.
    const reportList = REPORT_VIEWS.includes(key) ? await loadReportScenarios().catch(() => []) : [];
    const dash = key === 'me' ? await api('GET', '/v1/dashboard/me') : null;
    // 코디를 못 불러와도 나머지 화면은 보여 줍니다.
    const pet = ['home', 'pet'].includes(key) ? await api('GET', '/v1/pet').catch(() => null) : null;
    const shownPhrase = phrase && { ...phrase, seconds_left: Math.ceil((phrase.seconds_left || 0) / 60) };
    const snapshot = key + JSON.stringify([recordings, recs, family, alerts, lockMinutes(lock), lock.locked, shownPhrase, reportList, dash, pet]);
    const host = $('#data');
    if (snapshot === lastData || !host || (route().r || 'home') !== r) return;
    lastData = snapshot;
    host.innerHTML = draw({ recordings, recs, family, alerts, lock, phrase, reports: reportList, dash, pet });
    icons();
  } catch (e) {
    if ($('#data') && !$('#data').innerHTML) $('#data').innerHTML = emptyCard('서버에 연결할 수 없습니다.');
  }
}

/* ---------------- 웹 가족 경고 (앱은 네이티브 알림을 씁니다) ---------------- */
const baseTitle = document.title;

function beep() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    osc.frequency.value = 880;
    osc.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch (e) { }
}

async function pollAlerts() {
  if (native || embedded || !signedIn()) return;
  try {
    const known = store.get('lastAlert');
    const { items } = await api('GET', `/v1/alerts?after=${known || 0}`);
    if (!items.length) {
      if (!known) store.set('lastAlert', '0');
      return;
    }
    store.set('lastAlert', String(items[0].id));
    // 처음 접속한 기기에는 지난 경고를 한꺼번에 울리지 않습니다. 가족 탭에서 볼 수 있습니다.
    if (!known) return;
    const a = items[0];
    document.title = '🚨 가족 경고 · ' + baseTitle;
    vibrate([200, 100, 200]);
    beep();
    if (window.isSecureContext && window.Notification?.permission === 'granted') new Notification(a.title, { body: a.body });
    openSheet(`<span class="chip danger">${ic('siren')}가족 경고</span>
      <div class="b" style="font-size:18px;margin-top:10px">${esc(a.title)}</div>
      <div class="call-text">${esc(a.body)}</div>
      <button class="btn danger block mt" onclick="document.title=baseTitle;closeSheet();go('family')">확인하기</button>`);
    lastData = '';
    refresh();
  } catch (e) {
    // 다음 주기에 다시 확인합니다.
  }
}

INIT.quiz = () => loadQuiz();
['home', 'pet', 'detect', 'family', 'lock', 'passphrase', 'report', 'me'].forEach((k) => { INIT[k] = () => { lastData = ''; refresh(); if (k === 'detect') loadSamples(); if ($('#flowStage')) runFlow(); }; });
setInterval(refresh, 5000);
setInterval(pollAlerts, 5000);
setInterval(pollLock, 5000);
setInterval(scanFolder, SCAN_MS);
render();
pollAlerts();
pollLock();
restoreFolder().then(scanFolder);
// PC 화면과 미리보기가 같은 로그인과 같은 화면을 보여 주게 합니다.
window.addEventListener('storage', (e) => { if (e.key === 'guard.token' || e.key === 'guard.consented') render(); });
window.addEventListener('hashchange', syncPreview);
window.addEventListener('resize', syncPreview);
syncPreview();
previewClock();
setInterval(previewClock, 15000);
loadServerInfo();
loadDemoFamily();
// 제보 시나리오 주소로 바로 들어온 경우 시나리오를 먼저 불러온 뒤 다시 그립니다.
loadReportScenarios().then(() => { if (route().r === 'play' || route().r === 'sim') render(); }).catch(() => {});
