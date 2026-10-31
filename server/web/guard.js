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

const accepted = () => store.get('consented') === '1';
const signedIn = () => accepted() && !!store.get('token');
if (store.get('token')) native?.setToken(store.get('token'));

/* ---------------- 시안 화면 제거 ---------------- */
['image', 'voice', 'call', 'url', 'verify', 'report', 'generate', 'weakness', 'training', 'copilot', 'checkup'].forEach((k) => delete SCREENS[k]);
Object.assign(TAB_OF, { home: 'home', sim: 'sim', play: 'sim', detect: 'detect', family: 'family', me: 'me' });
delete PARENT.family;

renderTabs = function (on) {
  const tabs = [['home', 'house', '홈'], ['sim', 'gamepad-2', '체험'], ['detect', 'shield-check', '검사'], ['family', 'users', '가족'], ['me', 'user-round', 'MY']];
  $('#tabbar').innerHTML = tabs.map(([k, i, t]) => k === 'detect'
    ? `<button class="tab tab-center ${on === k ? 'on' : ''}" onclick="go('${k}')"><span class="fab">${ic(i)}</span><span>${t}</span></button>`
    : `<button class="tab ${on === k ? 'on' : ''}" onclick="go('${k}')">${ic(i)}<span>${t}</span></button>`).join('');
  icons();
};

/* ---------------- 첫 실행 ---------------- */
function onboardingPage() {
  if (!accepted()) {
    return `<div class="page">
      <div class="home-top"><div class="brand"><img src="assets/logo.svg" width="30" height="30" alt="">CodySafe</div></div>
      <div class="lead-text">AI 사기는 <em>미리 경험</em>하고,<br>가족과 <em>함께</em> 막아요</div>
      <div class="card"><ul class="notice">
        ${['앱이 통화를 직접 녹음하지 않고, 이미 저장된 파일만 읽습니다.', '폴더를 연결한 뒤에 생긴 파일만 서버로 보냅니다.', '음성은 분석 후 삭제하고, 일상 통화는 글자 기록도 남기지 않습니다.', '사기로 의심되는 통화의 글자 기록은 검토를 위해 보관합니다.', '분석 내용은 본인만 봅니다. 가족에게는 보이스피싱 의심 여부만 알립니다.']
          .map((t) => `<li>${ic('circle-check')}<span>${t}</span></li>`).join('')}
      </ul></div>
      <div class="card soft-warn">통화 상대의 음성도 함께 전송됩니다. 테스트 버전이므로 동의한 사람의 통화나 테스트 파일로만 사용하세요.</div>
      <button class="btn grad block mt" onclick="store.set('consented','1');render()">동의하고 시작</button>
    </div>`;
  }
  return `<div class="page">
    <div class="home-top"><div class="brand"><img src="assets/logo.svg" width="30" height="30" alt="">CodySafe</div></div>
    <div class="lead-text">가족에게 보일<br><em>이름</em>을 정해 주세요</div>
    <div class="card"><div class="field" style="margin-top:0"><label for="regName">이름</label><input id="regName" maxlength="30" placeholder="예: 민수"></div>
    <div class="muted small" style="margin-top:10px">계정이나 비밀번호는 필요 없습니다.</div></div>
    <button class="btn grad block mt" onclick="registerDevice()">시작하기</button>
  </div>`;
}

async function registerDevice() {
  const name = $('#regName').value.trim();
  if (!name) return toast('이름을 입력하세요', 'circle-alert');
  try {
    const r = await api('POST', '/v1/devices', { name });
    store.set('token', r.token);
    store.set('name', name);
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
  normal: ['safe', 'shield-check', '사기 징후 없음'],
};
const STEP = { queued: '대기 중', transcribing: '음성 변환 중', analyzing: '분석 중' };

function verdictChip(r, label) {
  if (r.status === 'failed') return `<span class="chip danger">${ic('circle-x')}실패</span>`;
  if (r.status !== 'done') return `<span class="chip pri">${ic('loader')}${STEP[r.status] || esc(r.status)}</span>`;
  const c = CHIPS[label];
  return c ? `<span class="chip ${c[0]}">${ic(c[1])}${c[2]}</span>` : `<span class="chip">${ic('circle-help')}판단 어려움</span>`;
}

// 삼성 녹음 파일명의 전화번호를 화면에 드러내지 않고 통화 시각만 보여 줍니다.
function callTitle(filename) {
  const m = /_\d{2}(\d{2})(\d{2})_(\d{2})(\d{2})\d{2}\./.exec(filename);
  return m ? `${+m[1]}월 ${+m[2]}일 ${m[3]}:${m[4]} 통화` : esc(filename.replace(/\.[^.]+$/, ''));
}

function recordingCard(r) {
  const label = r.review_label || r.label;
  const top = r.matches[0];
  return `<div class="card mt">
    ${verdictChip(r, label)}
    <div class="call-title">${callTitle(r.filename)}</div>
    ${r.summary ? `<div class="call-text">${esc(r.summary)}</div>` : ''}
    ${r.status === 'failed' ? '<div class="call-text">처리에 실패했습니다. 다시 시도해 주세요.</div>' : ''}
    ${r.evidence.map((e) => `<div class="quote">“${esc(e)}”</div>`).join('')}
    ${top ? `<div class="type-box"><b>${esc(top.name)}</b><p>${esc(top.advice)}</p></div>` : ''}
    <div class="link-row">
      ${r.status === 'failed' ? `<button onclick="act('POST','/v1/recordings/${r.id}/complete')">다시 시도</button>` : ''}
      ${r.status === 'done' ? `<button onclick="reviewSheet('${r.id}')">${r.needs_review ? '판정 확인' : '판정 고치기'}</button>` : ''}
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

function reviewSheet(id) {
  const opt = (label, t) => `<button class="btn line block" onclick="act('POST','/v1/recordings/${id}/review',{label:'${label}'})">${t}</button>`;
  openSheet(`<div class="b" style="font-size:18px">이 통화는 실제로 무엇이었나요?</div>
    <div class="btn-col">${opt('voice_phishing', '보이스피싱')}${opt('other_scam', '다른 사기 (학습 데이터로 보관)')}${opt('normal', '사기 아님 (글자 기록 삭제)')}</div>`);
}

function deleteSheet(id) {
  openSheet(`<div class="b" style="font-size:18px">이 기록을 삭제할까요?</div>
    <div class="muted small" style="margin-top:6px">서버의 분석 결과와 글자 기록을 지웁니다.</div>
    <div class="btn-col"><button class="btn danger block" onclick="act('DELETE','/v1/recordings/${id}')">삭제</button><button class="btn line block" onclick="closeSheet()">취소</button></div>`);
}

/* ---------------- 홈 ---------------- */
SCREENS.home = gated(() => `<div class="page">
  <div class="home-top"><div class="brand"><img src="assets/logo.svg" width="30" height="30" alt="">CodySafe</div></div>
  <div class="hello" style="margin:0 2px 14px">안녕하세요${store.get('name') ? `, <b>${esc(store.get('name'))}님</b>` : ''} 오늘도 안전한 하루 보내세요</div>
  <div id="data"></div>
</div>`);

function homeData({ recordings, recs, family, alerts }) {
  const items = recordings.items;
  const flagged = items.filter((r) => ['voice_phishing', 'other_scam'].includes(r.review_label || r.label)).length;
  const reviews = items.filter((r) => r.needs_review).length;
  const unread = alerts.items.filter((a) => !a.acked);
  return `<div class="hero">
      <div class="hero-label">분석한 통화</div>
      <div class="hero-score">${recs.analyzed}<small>건</small></div>
      <div class="hero-meta">사기 의심 <b>${flagged}건</b> · 연결된 가족 <b>${family.guardians.length}명</b></div>
      <div class="hero-actions"><button class="w" onclick="go('detect')">${ic('shield-check')}통화 검사</button><button onclick="go('sim')">${ic('gamepad-2')}사기 체험</button></div>
    </div>
    ${unread.map(alertCard).join('')}
    ${reviews ? `<button class="card mt soft-warn" style="width:100%;text-align:left" onclick="go('detect')"><b>검토가 필요한 통화 ${reviews}건</b><br>판정을 확인해 주시면 탐지 개선에 쓰입니다.</button>` : ''}
    <div class="sec-title">자주 노출된 사기 유형</div>
    ${recs.items.length ? recs.items.map((r) => `<div class="card mt"><span class="chip pri">${r.count}회 노출</span>
      <div class="call-title">${esc(r.name)}</div><div class="call-text">${esc(r.advice)}</div>
      <div class="call-text" style="color:var(--pri);font-weight:700;font-size:13px">추천 훈련 · ${esc(r.training)}</div></div>`).join('') : emptyCard('아직 사기로 판정된 통화가 없습니다.')}
    <div class="sec-title">최근 분석 <button class="more" onclick="go('detect')">전체 보기${ic('chevron-right')}</button></div>
    ${items.length ? items.slice(0, 3).map(recordingCard).join('') : emptyCard('아직 분석한 통화가 없습니다.')}`;
}

/* ---------------- 검사 ---------------- */
SCREENS.detect = gated(() => `<div class="page">
  <div class="lead" style="margin-top:6px">통화 검사</div>
  <div class="lead-sub" style="margin-top:6px">저장된 통화 녹음을 AI가 분석합니다. 결과는 본인만 볼 수 있습니다.</div>
  <div class="card mt">${folderBlock()}</div>
  <button class="btn grad block mt" onclick="$('#filePick').click()">${ic('upload')}파일 직접 올려 검사</button>
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

const detectData = ({ recordings }) => (recordings.items.length ? recordings.items.map(recordingCard).join('') : emptyCard('아직 올린 파일이 없습니다.'));

async function uploadFile(file, clientKey) {
  const r = await api('POST', '/v1/recordings', { filename: file.name, client_key: clientKey, content_type: 'application/octet-stream' });
  if (r.already_uploaded) return false;
  const url = new URL(r.upload_url);
  // 로컬 저장 모드는 지금 접속한 주소로 보내 주소 설정과 무관하게 동작하게 합니다.
  const target = url.pathname.startsWith('/v1/local-upload/') ? url.pathname + url.search : r.upload_url;
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

function familyData({ family, alerts }) {
  const person = (p, note, removable) => `<div class="card mt"><div class="row between"><div class="grow"><div class="b">${esc(p.name)}</div><div class="muted small" style="margin-top:2px">${note}</div></div>
    ${removable ? `<button class="btn line sm" onclick="act('DELETE','/v1/family/guardians/${esc(p.id)}')">해제</button>` : ''}</div></div>`;
  return `<div class="sec-title">받은 가족 경고</div>
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
    <div class="kv"><span>서버</span><span>${esc(location.host)}</span></div>
    <div class="kv"><span>실행 환경</span><span>${native ? '안드로이드 앱' : '브라우저'}</span></div>
  </div>
  <div class="sec-title">데이터 처리</div>
  <div class="card"><ul class="notice">
    ${['음성은 분석 후 삭제합니다. 실패한 음성은 재시도나 삭제 전까지 남습니다.', '일상 통화는 글자 기록을 남기지 않습니다.', '분석 내용은 본인만 볼 수 있습니다.', '가족에게는 보이스피싱 의심 여부만 전달됩니다.'].map((t) => `<li>${ic('lock')}<span>${t}</span></li>`).join('')}
  </ul></div>
  ${browserNotifyBlock()}
  <button class="btn line block mt" onclick="signOut()">이 기기 등록 해제</button>
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
  native?.setToken('');
  go('home');
  render();
}

/* ---------------- 체험: 검증되지 않은 수치와 없는 화면 연결 제거 ---------------- */
const baseSim = SCREENS.sim;
SCREENS.sim = () => baseSim()
  .replace('🔥 이번 주 가장 많이 당한 수법', '대표 수법 체험')
  .replace('기관 사칭 · 평균 정답률 41% · 4분', '기관 사칭 · 4분')
  .replace(/<span class="featnum">기능 \d+<\/span>/, '');

const baseSimResult = simResult;
simResult = function () {
  baseSimResult();
  const buttons = view.querySelectorAll('.row.mt2 .btn');
  view.querySelector('.card.mt.row')?.remove();
  buttons[1].innerHTML = `${ic('list')}다른 시나리오`;
  buttons[1].setAttribute('onclick', "go('sim')");
  icons();
};

/* ---------------- 데이터 갱신 ---------------- */
const DATA_VIEWS = { home: homeData, detect: detectData, family: familyData };
let lastData = '';

async function refresh() {
  const { r } = route();
  const key = SCREENS[r] ? r : 'home';
  const draw = DATA_VIEWS[key];
  if (!draw || !signedIn() || !$('#data')) return;
  try {
    const [recordings, recs, family, alerts] = await Promise.all([
      api('GET', '/v1/recordings'), api('GET', '/v1/recommendations'), api('GET', '/v1/family'), api('GET', '/v1/alerts'),
    ]);
    const snapshot = key + JSON.stringify([recordings, recs, family, alerts]);
    const host = $('#data');
    if (snapshot === lastData || !host || (route().r || 'home') !== r) return;
    lastData = snapshot;
    host.innerHTML = draw({ recordings, recs, family, alerts });
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
  if (native || !signedIn()) return;
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

['home', 'detect', 'family'].forEach((k) => { INIT[k] = () => { lastData = ''; refresh(); }; });
setInterval(refresh, 5000);
setInterval(pollAlerts, 5000);
setInterval(scanFolder, SCAN_MS);
render();
pollAlerts();
restoreFolder().then(scanFolder);
