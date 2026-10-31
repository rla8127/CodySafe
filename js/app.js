// CodySafe MVP — 해시 라우터 기반 단일 페이지 앱 (기능은 목업, 일부 URL 분석 로직만 실제 동작)

const $ = (s, el = document) => el.querySelector(s);
const view = $('#view');
const ic = (n, c = '') => `<i data-lucide="${n}" class="${c}"></i>`;
const icons = () => window.lucide && lucide.createIcons();
let timers = [];
const later = (fn, ms) => timers.push(setTimeout(fn, ms));
const clearTimers = () => { timers.forEach(clearTimeout); timers = []; };
let uid = 0;

/* ---------------- 공통 UI ---------------- */

// 정부·공공기관 공인 배지 (assets/gov-badge.svg 와 동일 디자인)
function govSvg(size = 22) {
  const id = 'gb' + (++uid);
  return `<svg width="${size * 48 / 56}" height="${size}" viewBox="0 0 48 56"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1E3A8A"/><stop offset="1" stop-color="#0B1B3F"/></linearGradient></defs><path d="M24 2 L44 9 V27 C44 40 35 49 24 54 C13 49 4 40 4 27 V9 Z" fill="url(#${id})"/><path d="M24 6 L40 11.6 V27 C40 37.6 32.8 45 24 49.4 C15.2 45 8 37.6 8 27 V11.6 Z" fill="none" stroke="#C9A227" stroke-width="1.2"/><g transform="translate(12 14)"><circle cx="12" cy="12" r="11" fill="#fff"/><circle cx="12" cy="12" r="9" fill="#0047A0"/><path d="M3 12 A9 9 0 0 1 21 12 A4.5 4.5 0 0 1 12 12 A4.5 4.5 0 0 0 3 12 Z" fill="#CD2E3A"/></g><path d="M17 41 L21.5 45 L31 37" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
const govPill = (t = '정부 공인') => `<span class="gov-pill">${govSvg(18)}${t}</span>`;

function ring(v, size = 120, sw = 12, track = '#EEF1F7', colors = ['#3B6BFF', '#7B4DFF']) {
  const id = 'rg' + (++uid), r = (size - sw) / 2, c = 2 * Math.PI * r;
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(-90deg)">
    <defs><linearGradient id="${id}"><stop offset="0" stop-color="${colors[0]}"/><stop offset="1" stop-color="${colors[1]}"/></linearGradient></defs>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${track}" stroke-width="${sw}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="url(#${id})" stroke-width="${sw}" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - v / 100)}"/></svg>`;
}

const subhead = (title, n) => `<div class="subhead"><button class="back" onclick="back()">${ic('chevron-left')}</button><h2>${title}</h2>${n ? `<div class="right"><span class="featnum">기능 ${n}</span></div>` : ''}</div>`;

function toast(msg, icon = 'circle-check') {
  const t = $('#toast');
  t.innerHTML = ic(icon) + msg;
  icons();
  t.classList.add('show');
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove('show'), 2200);
}

function openSheet(html) {
  const s = $('#sheet');
  s.innerHTML = `<div class="sheet-dim" onclick="closeSheet()"></div><div class="sheet-body"><div class="sheet-grab"></div>${html}</div>`;
  icons();
  requestAnimationFrame(() => s.classList.add('open'));
}
function closeSheet() { $('#sheet').classList.remove('open'); }

// 분석 단계 진행 애니메이션
function runSteps(el, labels, done, ms = 560) {
  el.innerHTML = `<div class="card"><div class="steps">${labels.map((l, i) => `<div class="step" id="st${i}"><span class="dot">${ic('loader')}</span>${l}</div>`).join('')}</div></div>`;
  icons();
  labels.forEach((_, i) => {
    later(() => $('#st' + i)?.classList.add('run'), i * ms);
    later(() => {
      const s = $('#st' + i);
      if (!s) return;
      s.classList.replace('run', 'done');
      s.querySelector('.dot').innerHTML = ic('check');
      icons();
    }, (i + 1) * ms - 80);
  });
  later(done, labels.length * ms + 200);
}

function vibrate(p) { try { navigator.vibrate && navigator.vibrate(p); } catch (e) { } }

/* ---------------- 라우터 ---------------- */

let depth = 0;
const PARENT = { checkup: 'detect', image: 'detect', voice: 'detect', call: 'detect', url: 'detect', verify: 'detect', copilot: 'detect', play: 'sim', training: 'me', weakness: 'me', family: 'me', generate: 'report' };
function go(path) { depth++; location.hash = '#/' + path; }
function back() {
  if (depth > 0) { depth--; history.back(); }
  else location.hash = '#/' + (PARENT[route().r] || 'home');
}
const route = () => { const [, r = 'home', arg] = location.hash.split('/'); return { r, arg }; };

const TAB_OF = { home: 'home', sim: 'sim', play: 'sim', training: 'sim', detect: 'detect', checkup: 'detect', image: 'detect', voice: 'detect', call: 'detect', url: 'detect', verify: 'detect', copilot: 'detect', report: 'report', generate: 'report', me: 'me', weakness: 'me', family: 'me' };
const FULL = ['call', 'voice', 'play'];
const DARK = ['call', 'voice'];

function render() {
  clearTimers();
  closeSheet();
  $('#alertLayer').innerHTML = '';
  let { r, arg } = route();
  if (!SCREENS[r]) r = 'home';
  const full = FULL.includes(r);
  view.classList.toggle('full', full);
  $('#tabbar').classList.toggle('hidden', full);
  $('.statusbar').classList.toggle('light', DARK.includes(r));
  view.innerHTML = SCREENS[r](arg);
  view.scrollTop = 0;
  renderTabs(TAB_OF[r]);
  icons();
  INIT[r]?.(arg);
}

function renderTabs(on) {
  const tabs = [['home', 'house', '홈'], ['sim', 'gamepad-2', '체험'], ['detect', 'shield-check', '검사'], ['report', 'megaphone', '제보'], ['me', 'user-round', 'MY']];
  $('#tabbar').innerHTML = tabs.map(([k, i, t]) => k === 'detect'
    ? `<button class="tab tab-center ${on === k ? 'on' : ''}" onclick="go('${k}')"><span class="fab">${ic(i)}</span><span>${t}</span></button>`
    : `<button class="tab ${on === k ? 'on' : ''}" onclick="go('${k}')">${ic(i)}<span>${t}</span></button>`).join('');
  icons();
}

/* ---------------- 화면들 ---------------- */

const QUICK = [
  ['link', 'URL 검사', 'url', '#2F5BFF', '#EBF0FF'],
  ['image', '이미지 분석', 'image', '#7B4DFF', '#F1EDFF'],
  ['audio-lines', '음성 탐지', 'voice', '#0EA5E9', '#E0F4FE'],
  ['landmark', '기관 검증', 'verify', '#1E3A8A', '#E8EDFB'],
  ['gamepad-2', '사기 체험', 'sim', '#F79009', '#FFF4E5'],
  ['bot', '코파일럿', 'copilot', '#12B76A', '#E7F8EF'],
  ['users', '가족 보호', 'family', '#E5487A', '#FDECF2'],
  ['megaphone', '제보하기', 'report', '#F04438', '#FEECEB'],
];

const STATUS = {
  verified: ['safe', 'badge-check', '검증 완료'],
  reviewing: ['warn', 'users', '커뮤니티 검증 중'],
  ai: ['pri', 'sparkles', 'AI 1차 분석'],
};

function trainCard(key, reason) {
  const s = SCENARIOS[key];
  return `<button class="train-card" style="background:linear-gradient(135deg, ${s.color}, ${s.color}CC)" onclick="go('play/${key}')">
    <span class="big">${ic(s.icon)}</span>
    <div class="k">${reason}</div>
    <div class="t">${s.title}</div>
    <div class="m"><span>${s.tag}</span><span>· ${s.mins}분</span><span>· ${s.difficulty}</span></div>
  </button>`;
}

function reportMini(r) {
  const [c, i, t] = STATUS[r.status];
  return `<div class="list-item" onclick="go('report')" style="cursor:pointer">
    <div class="grow"><div class="row" style="gap:6px;margin-bottom:6px"><span class="chip">${r.cat}</span><span class="chip ${c}">${ic(i)}${t}</span></div>
    <div class="t">${r.title}</div><div class="s">${r.region} · ${r.ago} · 추천 ${r.likes}</div></div></div>`;
}

const SCREENS = {
  home: () => `<div class="page">
    <div class="home-top">
      <div class="brand"><img src="assets/logo.svg" width="30" height="30" alt="">CodySafe</div>
      <button class="bell" onclick="go('family')">${ic('bell')}</button>
    </div>
    <div class="hello" style="margin:0 2px 14px">안녕하세요, <b>지민님</b> 👋 오늘도 안전한 하루 보내세요</div>

    <div class="hero">
      <div class="ring">${ring(72, 92, 10, 'rgba(255,255,255,.2)', ['#fff', '#DCE4FF'])}
        <span style="position:absolute;inset:0;display:grid;place-items:center">${ic('shield-check')}</span></div>
      <div class="hero-label">나의 AI 사기 대응력</div>
      <div class="hero-score">72<small>점</small></div>
      <div class="hero-meta">상위 34% · 지난주보다 <b>+6점</b></div>
      <div class="hero-actions">
        <button class="w" onclick="go('weakness')">${ic('radar')}취약점 분석</button>
        <button onclick="go('training')">${ic('target')}맞춤 훈련</button>
      </div>
    </div>

    ${checkCard()}

    <div class="card mt guard">
      <div class="icon-box" style="background:var(--safe-soft);color:var(--safe)">${ic('phone-call')}</div>
      <div class="grow">
        <div class="row" style="gap:8px"><span class="pulse"></span><b style="font-size:15px">실시간 통화 보호 중</b></div>
        <div class="muted small" style="margin-top:3px">오늘 의심 통화 1건 · 스미싱 차단 3건</div>
      </div>
      <button class="switch on" onclick="this.classList.toggle('on');toast(this.classList.contains('on')?'실시간 보호를 켰어요':'실시간 보호를 껐어요', this.classList.contains('on')?'shield-check':'shield-off')"></button>
    </div>

    <div class="sec-title">빠른 검사</div>
    <div class="card quick">
      ${QUICK.map(([i, t, r, c, bg]) => `<button onclick="go('${r}')"><span class="icon-box" style="background:${bg};color:${c}">${ic(i)}</span>${t}</button>`).join('')}
    </div>

    <div class="sec-title">🚨 오늘의 사기 경보</div>
    <button class="alert-banner" style="width:100%;text-align:left" onclick="go('generate')">
      <span class="icon-box sm" style="background:#FF5A4E;color:#fff">${ic('siren')}</span>
      <div class="grow"><div class="t">모바일 청첩장 스미싱 급증</div><div class="s">최근 24시간 제보 ▲212% · 훈련 시나리오 자동 생성됨</div></div>
      ${ic('chevron-right')}
    </button>

    <div class="sec-title">나를 위한 맞춤 훈련 <button class="more" onclick="go('training')">전체${ic('chevron-right')}</button></div>
    <div class="hscroll">
      ${trainCard('invest', '🎯 가장 취약한 유형')}
      ${trainCard('agency', '⚠️ 취약 2순위')}
      ${trainCard('wedding', '✨ 신종 사기 · NEW')}
    </div>

    <div class="sec-title">국민 제보 <button class="more" onclick="go('report')">더보기${ic('chevron-right')}</button></div>
    <div class="card">${REPORTS.slice(0, 3).map(reportMini).join('')}</div>
  </div>`,

  detect: () => `<div class="page">
    <div class="lead" style="margin-top:6px">무엇이 의심되나요?</div>
    <div class="lead-sub">AI가 링크·사진·음성·통화를 분석해 위험을 알려드려요.</div>
    <div style="margin-bottom:12px">${checkCard()}</div>
    <div class="tool-grid">
      ${[
        ['url', 'link', 'URL·문자·QR', '스미싱 링크와 가짜 사이트 스펠링 탐지', '#2F5BFF', '#EBF0FF', 10],
        ['image', 'image', '이미지 진위', 'AI 생성·조작 사진 위험 분석', '#7B4DFF', '#F1EDFF', 1],
        ['voice', 'audio-lines', 'AI 음성 탐지', '모르는 번호의 합성 음성 판별', '#0EA5E9', '#E0F4FE', 2],
        ['call', 'phone-call', '실시간 통화', 'STT + LLM으로 사기 발언 감지', '#F04438', '#FEECEB', 3],
        ['verify', 'landmark', '기관 사칭 검증', '검찰·경찰·금융기관 주장 팩트체크', '#1E3A8A', '#E8EDFB', 11],
        ['copilot', 'bot', '대응 코파일럿', '지금 뭘 해야 할지 단계별 안내', '#12B76A', '#E7F8EF', 8],
      ].map(([r, i, t, s, c, bg, n]) => `<button class="tool" onclick="go('${r}')">
        <div class="row between"><span class="icon-box" style="background:${bg};color:${c}">${ic(i)}</span><span class="featnum">${n}</span></div>
        <div><div class="t">${t}</div><div class="s">${s}</div></div></button>`).join('')}
    </div>
    <div class="gov-card mt2">
      ${govSvg(46)}
      <div class="grow"><div class="t">공인 기관 데이터와 대조합니다</div><div class="s">정부·공공기관 도메인, 금융기관 대표번호, KISA 피싱 DB 기반</div></div>
    </div>
  </div>`,

  /* ---------- 10. URL 탐지 ---------- */
  url: () => `<div class="page">
    ${subhead('스미싱·피싱 URL 탐지', 10)}
    <div class="seg">
      <button class="on" id="segText" onclick="urlMode('text')">${ic('message-square-text')}문자·링크</button>
      <button id="segQr" onclick="urlMode('qr')">${ic('qr-code')}QR 코드</button>
    </div>
    <div id="urlInput">
      <div class="input-card"><textarea id="urlText" placeholder="받은 문자나 링크를 붙여넣으세요"></textarea></div>
      <div class="samples">${URL_SAMPLES.map((s, i) => `<button onclick="$('#urlText').value=URL_SAMPLES[${i}].text">${s.label}</button>`).join('')}</div>
      <button class="btn grad block" onclick="analyzeUrl()">${ic('scan-search')}위험도 분석하기</button>
    </div>
    <div id="qrInput" style="display:none">
      <div style="position:relative;aspect-ratio:1;border-radius:24px;overflow:hidden;background:linear-gradient(135deg,#1B2440,#0B1020)">
        <div class="grid-ov" style="opacity:.4"></div>
        <div style="position:absolute;inset:22%;border-radius:18px;box-shadow:0 0 0 999px rgba(0,0,0,.35)">
          ${['top:0;left:0;border-width:4px 0 0 4px;border-radius:18px 0 0 0', 'top:0;right:0;border-width:4px 4px 0 0;border-radius:0 18px 0 0', 'bottom:0;left:0;border-width:0 0 4px 4px;border-radius:0 0 0 18px', 'bottom:0;right:0;border-width:0 4px 4px 0;border-radius:0 0 18px 0']
            .map(s => `<i style="position:absolute;width:34px;height:34px;border:solid #7FA2FF;${s}"></i>`).join('')}
          <div class="scanline"></div>
        </div>
        <div style="position:absolute;bottom:16px;left:0;right:0;text-align:center;color:#fff;font-size:13px;opacity:.8">QR 코드를 사각형 안에 맞춰주세요</div>
      </div>
      <button class="btn grad block mt" onclick="$('#urlText').value=URL_SAMPLES[2].text;analyzeUrl()">${ic('camera')}샘플 QR 스캔하기</button>
    </div>
    <div id="urlRes" class="mt2"></div>
  </div>`,

  /* ---------- 1. 이미지 ---------- */
  image: () => `<div class="page">
    ${subhead('AI 이미지 진위 분석', 1)}
    <div class="lead">이 사진, 진짜 사람일까요?</div>
    <div class="lead-sub">데이팅앱 프로필, 투자 광고 속 인물, 메신저로 받은 사진의 AI 생성·조작 여부를 분석해요.</div>
    <div id="imgArea">
      <label class="drop">
        <input type="file" accept="image/*" hidden onchange="imgUpload(this)">
        <span class="icon-box" style="background:var(--pri-soft);color:var(--pri)">${ic('upload')}</span>
        <div class="b">사진 업로드</div><div class="muted small" style="margin-top:4px">JPG, PNG · 최대 10MB</div>
      </label>
      <div class="samples" style="justify-content:center">
        <button onclick="imgAnalyze('ai')">💘 로맨스 스캠 프로필 (샘플)</button>
        <button onclick="imgAnalyze('real')">📷 일반 사진 (샘플)</button>
      </div>
    </div>
    <div id="imgRes" class="mt"></div>
  </div>`,

  /* ---------- 2. 음성 ---------- */
  voice: () => `<div class="callscreen">
    <button class="back-light" onclick="back()">${ic('chevron-left')}</button>
    <div class="caller">
      <div class="row" style="justify-content:center;margin-bottom:18px"><span class="chip" style="background:rgba(255,255,255,.12);color:#fff">${ic('audio-lines')}기능 2 · AI 음성 탐지</span></div>
      <div class="avatar">${ic('user-round')}</div>
      <div class="num">010-7731-2290</div>
      <div class="st" id="vSt">모르는 번호 · 휴대전화</div>
    </div>
    <div class="wave" id="vWave">${Array.from({ length: 28 }, (_, i) => `<i style="--h:${12 + Math.round(Math.abs(Math.sin(i * 1.7)) * 50)}px;animation-delay:${(i % 7) * .09}s;animation-play-state:paused"></i>`).join('')}</div>
    <div class="glass" id="vPanel">
      <div class="row between"><b>AI 합성 음성 분석</b><span class="chip" style="background:rgba(255,255,255,.12);color:#fff">대기</span></div>
      <div class="small" style="opacity:.7;margin-top:6px">전화를 받으면 처음 5초 음성으로 합성 여부를 분석합니다. 통화 내용은 기기 밖으로 전송되지 않아요.</div>
    </div>
    <div id="vFind"></div>
    <div class="call-actions" id="vActs">
      <button class="call-btn" onclick="back()"><span class="c red">${ic('phone-off')}</span>거절</button>
      <button class="call-btn" onclick="voiceStart()"><span class="c green">${ic('phone')}</span>받기</button>
    </div>
  </div>`,

  /* ---------- 3. 실시간 통화 ---------- */
  call: () => `<div class="callscreen">
    <button class="back-light" onclick="back()">${ic('chevron-left')}</button>
    <div class="caller" style="margin-top:0">
      <div class="row" style="justify-content:center;margin-bottom:14px"><span class="chip" style="background:rgba(255,255,255,.12);color:#fff">${ic('shield-check')}기능 3 · 실시간 통화 보호</span></div>
      <div class="num">02-3480-1172</div>
      <div class="st" id="cSt">통화 대기</div>
    </div>
    <div class="glass mt2">
      <div class="row between"><b>실시간 사기 위험도</b><b id="cRisk" style="font-size:20px">0%</b></div>
      <div class="risk-meter"><i id="cMeter"></i></div>
      <div class="row between tiny" style="opacity:.6;margin-top:6px"><span>안전</span><span>주의</span><span>위험</span></div>
    </div>
    <div class="glass">
      <div class="row between" style="margin-bottom:10px"><b>${ic('captions', '')} 실시간 STT</b><span class="tiny" style="opacity:.6">LLM 사기 패턴 분석</span></div>
      <div class="transcript" id="cTr"><div class="small" style="opacity:.6">시작 버튼을 누르면 기관 사칭 보이스피싱 통화가 재생됩니다.</div></div>
    </div>
    <div class="call-actions" id="cActs">
      <button class="call-btn" onclick="back()"><span class="c red">${ic('phone-off')}</span>종료</button>
      <button class="call-btn" onclick="callStart()"><span class="c green">${ic('play')}</span>시뮬레이션 시작</button>
    </div>
  </div>`,

  /* ---------- 4. 시뮬레이션 목록 ---------- */
  sim: () => {
    const keys = Object.keys(SCENARIOS);
    return `<div class="page">
      <div class="row between" style="margin-top:6px"><div class="lead" style="margin:0">AI 사기 시뮬레이션</div><span class="featnum">기능 4</span></div>
      <div class="lead-sub" style="margin-top:6px">실제처럼 겪어보고, 안전하게 배우세요. 내 선택에 따라 사기범의 대화가 달라집니다.</div>
      <button class="hero" style="width:100%;text-align:left;background:linear-gradient(135deg,#1E3A8A,#5B3FD9)" onclick="go('play/agency')">
        <div class="hero-label">🔥 이번 주 가장 많이 당한 수법</div>
        <div style="font-size:22px;font-weight:800;margin-top:8px;line-height:1.3;position:relative;z-index:1">"서울중앙지검<br/>수사관입니다"</div>
        <div class="hero-meta" style="margin-top:8px">기관 사칭 · 평균 정답률 41% · 4분</div>
        <div class="hero-actions"><span class="btn sm" style="background:#fff;color:#1E3A8A">${ic('play')}지금 체험하기</span></div>
      </button>
      <div class="sec-title">전체 시나리오 <span class="muted small">${keys.length}개</span></div>
      ${keys.map(k => {
        const s = SCENARIOS[k];
        return `<button class="card scn" onclick="go('play/${k}')">
          <span class="icon-box" style="background:${s.soft};color:${s.color}">${ic(s.icon)}</span>
          <div class="grow"><div class="t">${s.title}</div><div class="s">${s.desc}</div>
          <div class="meta"><span class="chip" style="background:${s.soft};color:${s.color}">${s.tag}</span><span class="chip">${ic('clock')}${s.mins}분</span><span class="chip">${s.difficulty}</span>${s.generated ? `<span class="chip pri">${ic('wand-sparkles')}제보 기반</span>` : ''}</div></div>
        </button>`;
      }).join('')}
    </div>`;
  },

  /* ---------- 4. 시뮬레이션 플레이 ---------- */
  play: (k) => {
    const s = SCENARIOS[k] || SCENARIOS.family;
    return `<div class="chat-wrap" id="playWrap">
      <div class="chat-head">
        <button class="back" onclick="back()">${ic('chevron-left')}</button>
        <div class="msg" style="gap:0"><span class="av" style="width:36px;height:36px">${s.contact.av}</span></div>
        <div class="grow"><div class="nm">${s.contact.name}</div><div class="sb">${s.contact.sub}</div></div>
        <span class="chip" style="background:rgba(255,255,255,.6)">${ic('gamepad-2')}훈련 모드</span>
      </div>
      <div class="sim-progress" id="simProg">${s.steps.map(() => '<i></i>').join('')}</div>
      <div class="chat" id="chat"><div class="sysmsg">시뮬레이션 · 실제 사기 수법을 재구성한 대화입니다</div></div>
      <div class="choices" id="choices" style="display:none"></div>
    </div>`;
  },

  /* ---------- 5. 제보 ---------- */
  report: () => `<div class="page">
    <div class="row between" style="margin-top:6px"><div class="lead" style="margin:0">국민 사기 제보</div><span class="featnum">기능 5</span></div>
    <div class="lead-sub" style="margin-top:6px">내가 겪은 신종 수법이 누군가의 피해를 막습니다.</div>
    <div class="card row" style="justify-content:space-around;text-align:center">
      <div><div style="font-size:20px;font-weight:800">1,284</div><div class="tiny muted b">이번 주 제보</div></div>
      <div style="width:1px;height:30px;background:var(--line)"></div>
      <div><div style="font-size:20px;font-weight:800;color:var(--safe)">862</div><div class="tiny muted b">검증 완료</div></div>
      <div style="width:1px;height:30px;background:var(--line)"></div>
      <div><div style="font-size:20px;font-weight:800;color:var(--pri2)">14</div><div class="tiny muted b">훈련 시나리오화</div></div>
    </div>
    <div class="chips mt2" id="repFilter">
      ${['전체', '스미싱', '보이스피싱', '투자', '로맨스', '중고거래'].map((c, i) => `<button class="filter ${i ? '' : 'on'}" onclick="repFilter(this,'${c}')">${c}</button>`).join('')}
    </div>
    <div id="repList" class="mt"></div>
    <button class="fab-write" onclick="reportSheet()">${ic('pen-line')}제보하기</button>
  </div>`,

  /* ---------- 6. 취약점 분석 ---------- */
  weakness: () => {
    const sorted = [...RADAR].sort((a, b) => a.v - b.v);
    const avg = Math.round(RADAR.reduce((s, d) => s + d.v, 0) / RADAR.length);
    return `<div class="page">
      ${subhead('나의 사기 취약점 분석', 6)}
      <div class="card center">
        <div class="muted small b">시뮬레이션 23회 · 판단 기록 기반</div>
        <div style="margin-top:4px">${radarSvg(RADAR)}</div>
        <div class="row" style="justify-content:center;gap:24px">
          <div><div style="font-size:24px;font-weight:800">${avg}<small style="font-size:13px">점</small></div><div class="tiny muted b">평균 대응력</div></div>
          <div><div style="font-size:24px;font-weight:800;color:var(--danger)">${sorted[0].k}</div><div class="tiny muted b">가장 취약</div></div>
        </div>
      </div>
      <div class="sec-title">유형별 점수</div>
      <div class="card">
        ${sorted.map(d => `<div style="margin-top:12px"><div class="row between small b" style="margin-bottom:6px"><span>${d.k}</span><span style="color:${d.v < 50 ? 'var(--danger)' : d.v < 70 ? 'var(--warn)' : 'var(--safe)'}">${d.v}점</span></div>
          <div class="bar"><i style="width:${d.v}%;${d.v < 50 ? 'background:linear-gradient(90deg,#FF7A6E,#F04438)' : ''}"></i></div></div>`).join('').replace('margin-top:12px', 'margin-top:0')}
      </div>
      <div class="sec-title">AI 판단 패턴 분석</div>
      <div class="card">
        ${[
          ['crown', '#F04438', '#FEECEB', '권위에 쉽게 순응해요', '"검찰", "금감원" 등 기관명이 나오면 확인 없이 지시를 따르는 비율이 68%로 높아요.'],
          ['timer', '#F79009', '#FFF4E5', '시간 압박에 판단이 빨라져요', '"오늘까지", "지금 바로" 문구가 있을 때 응답 시간이 평균 2.1배 빨라지고 오답률이 올라갑니다.'],
          ['trending-up', '#7B4DFF', '#F1EDFF', '고수익 제안에 관심이 높아요', '투자 시나리오에서 "확정 수익" 메시지 클릭률이 평균보다 1.8배 높아요.'],
          ['heart-handshake', '#12B76A', '#E7F8EF', '가족 사칭에는 강해요 💪', '새 번호 연락 시 기존 번호로 확인하는 습관이 잘 잡혀 있어요.'],
        ].map(([i, c, bg, t, s]) => `<div class="finding"><span class="icon-box sm" style="background:${bg};color:${c}">${ic(i)}</span><div><div class="t">${t}</div><div class="s">${s}</div></div></div>`).join('')}
      </div>
      <button class="btn grad block mt2" onclick="go('training')">${ic('target')}취약 유형 맞춤 훈련 시작</button>
    </div>`;
  },

  /* ---------- 7. 맞춤 훈련 ---------- */
  training: () => `<div class="page">
    ${subhead('개인 맞춤형 사기 훈련', 7)}
    <div class="card">
      <div class="row between"><div><div class="b">🔥 5일 연속 훈련 중</div><div class="muted small" style="margin-top:2px">이번 주 목표 3 / 5회</div></div>
        <div style="position:relative">${ring(60, 56, 7)}<span style="position:absolute;inset:0;display:grid;place-items:center;font-size:12px;font-weight:800">60%</span></div></div>
      <div class="week mt">${['월', '화', '수', '목', '금', '토', '일'].map((d, i) => `<div><div class="d">${d}</div><div class="c ${i < 5 ? 'on' : ''} ${i === 4 ? 'today' : ''}">${i < 5 ? ic('check') : ''}</div></div>`).join('')}</div>
    </div>
    <div class="sec-title">오늘의 맞춤 미션</div>
    ${[
      ['invest', '투자 리딩 38점 — 가장 취약한 유형이에요'],
      ['agency', '기관 사칭 52점 — 권위 순응 패턴 개선'],
      ['wedding', '이번 주 급증한 신종 수법 대비'],
    ].map(([k, why], i) => {
      const s = SCENARIOS[k];
      return `<button class="card scn" onclick="go('play/${k}')">
        <span class="icon-box" style="background:${s.soft};color:${s.color}">${ic(s.icon)}</span>
        <div class="grow"><div class="tiny b" style="color:${s.color}">미션 ${i + 1} · ${s.tag}</div><div class="t" style="margin-top:2px">${s.title}</div><div class="s">${why}</div></div>
        ${ic('chevron-right')}
      </button>`;
    }).join('')}
    <div class="sec-title">획득한 배지</div>
    <div class="badge-row">
      <div class="badge"><div class="e">🛡️</div><div class="n">첫 방어 성공</div></div>
      <div class="badge"><div class="e">👨‍👩‍👧</div><div class="n">가족 지킴이</div></div>
      <div class="badge"><div class="e">🔍</div><div class="n">링크 탐정</div></div>
      <div class="badge lock"><div class="e">🏛️</div><div class="n">기관사칭 마스터</div></div>
    </div>
    <div class="card mt2 row" style="background:linear-gradient(135deg,#F1EDFF,#EAF0FF);box-shadow:none">
      <span class="icon-box sm" style="background:#fff;color:var(--pri2)">${ic('brain')}</span>
      <div class="small" style="line-height:1.5"><b>추천 알고리즘</b> · 취약점 점수 × 최근 피해 급증도 × 미경험 수법을 반영해 매일 미션을 갱신합니다.</div>
    </div>
  </div>`,

  /* ---------- 8. 코파일럿 ---------- */
  copilot: () => `<div class="page">
    ${subhead('AI 사기 대응 코파일럿', 8)}
    <div class="cp-wrap">
      <div class="sos">
        <a href="tel:112"><b>112</b><span>경찰 신고·지급정지</span></a>
        <a href="tel:1332"><b>1332</b><span>금융감독원</span></a>
        <a href="tel:118"><b>118</b><span>KISA 스미싱</span></a>
      </div>
      <div class="cp-chat mt2" id="cpChat">
        <div class="cp-msg ai"><div class="ai-h">${ic('bot')}CodySafe 코파일럿</div>지금 어떤 상황인가요? 의심되는 상황을 말씀해 주시면 <b>지금 당장 해야 할 일</b>을 순서대로 알려드릴게요.</div>
        <div class="chips" style="flex-wrap:wrap">${COPILOT.map((c, i) => `<button class="filter" onclick="cpSend(COPILOT[${i}].q)">${c.q}</button>`).join('')}</div>
      </div>
      <form class="cp-input" onsubmit="event.preventDefault();cpSend($('#cpIn').value)">
        <input id="cpIn" placeholder="상황을 입력하세요…" autocomplete="off"><button>${ic('send')}</button>
      </form>
    </div>
  </div>`,

  /* ---------- 9. 가족 보호 ---------- */
  family: () => `<div class="page">
    ${subhead('가족 보호 네트워크', 9)}
    <div class="alert-banner">
      <span class="icon-box sm" style="background:#FF5A4E;color:#fff">${ic('phone-incoming')}</span>
      <div class="grow"><div class="t">엄마가 의심 통화 중이에요</div><div class="s">기관 사칭 위험도 86% · 2분째 통화 중</div></div>
      <button class="btn danger sm" onclick="toast('엄마에게 전화를 겁니다','phone')">${ic('phone')}전화</button>
    </div>
    <div class="sec-title">우리 가족 <button class="more" onclick="toast('초대 링크를 복사했어요','link')">${ic('user-plus')}&nbsp;초대</button></div>
    <div class="card">
      ${[
        ['엄마', '68세 · 보호 대상', '#FDECF2', '#E5487A', 'var(--danger)', '<span class="chip danger">위험 1건</span>'],
        ['아빠', '71세 · 보호 대상', '#EBF0FF', '#2F5BFF', 'var(--safe)', '<span class="chip safe">안전</span>'],
        ['동생', '24세 · 보호자', '#E7F8EF', '#12B76A', 'var(--safe)', '<span class="chip safe">안전</span>'],
      ].map(([n, s, bg, c, st, chip]) => `<div class="list-item member">
        <span class="av" style="background:${bg};color:${c}">${n}<i class="st" style="background:${st}"></i></span>
        <div class="grow"><div class="t">${n}</div><div class="s">${s}</div></div>${chip}</div>`).join('')}
    </div>
    <div class="sec-title">최근 알림</div>
    <div class="card timeline">
      <div class="tl" style="--c:var(--danger)"><div class="t">엄마 · 기관 사칭 의심 통화 수신</div><div class="s">"서울중앙지검", "안전계좌" 키워드 감지 → 엄마 폰 진동 경고 발송 · 방금 전</div></div>
      <div class="tl" style="--c:var(--warn)"><div class="t">아빠 · 스미싱 문자 자동 차단</div><div class="s">[교통공단] 과태료 미납 단축 URL · 오늘 09:12</div></div>
      <div class="tl" style="--c:var(--safe)"><div class="t">엄마 · 가족 사칭 시뮬레이션 완료</div><div class="s">정답률 100% 🎉 · 어제</div></div>
      <div class="tl" style="--c:var(--pri)"><div class="t">주간 가족 안전 리포트 도착</div><div class="s">가족 평균 대응력 64점 (+4) · 월요일</div></div>
    </div>
    <div class="sec-title">보호 설정</div>
    <div class="card">
      ${[
        ['의심 통화 실시간 알림', '보호 대상이 위험 통화 시 나에게 즉시 알림', true],
        ['고액 이체 지연 요청', '100만원 이상 이체 시 보호자 확인 후 진행', true],
        ['스미싱 문자 대리 차단', '위험 링크 자동 차단 후 보호자에게 공유', true],
        ['주간 안전 리포트', '가족 훈련 현황과 취약점 요약', false],
      ].map(([t, s, on]) => `<div class="list-item"><div class="grow"><div class="t">${t}</div><div class="s">${s}</div></div><button class="switch ${on ? 'on' : ''}" onclick="this.classList.toggle('on')"></button></div>`).join('')}
    </div>
  </div>`,

  /* ---------- 11. 기관 사칭 검증 ---------- */
  verify: () => `<div class="page">
    ${subhead('기관 사칭 사실 검증', 11)}
    <div class="gov-card">${govSvg(42)}<div class="grow"><div class="t">공식 기관 정보와 대조합니다</div><div class="s">대표번호 · 공식 도메인 · 기관 업무 지침</div></div></div>
    <div class="field mt2"><label>어느 기관이라고 했나요?</label>
      <div class="chips" style="flex-wrap:wrap" id="agChips">${Object.keys(AGENCIES).map((a, i) => `<button class="filter ${i ? '' : 'on'}" onclick="pickAgency(this)">${a}</button>`).join('')}</div></div>
    <div class="field"><label>연락 온 번호</label><input id="vfNum" placeholder="예) 02-3480-1172" value=""></div>
    <div class="field"><label>상대가 한 말·요구</label><textarea id="vfClaim" placeholder="예) 계좌가 범죄에 연루되어 안전계좌로 이체해야 한대요"></textarea></div>
    <div class="samples"><button onclick="vfSample()">📞 검찰 사칭 예시 불러오기</button></div>
    <button class="btn grad block" onclick="verifyRun()">${ic('scale')}사실 검증하기</button>
    <div id="vfRes" class="mt2"></div>
  </div>`,

  /* ---------- 12. 신종 사기 시나리오 자동 생성 ---------- */
  generate: () => {
    const r = REPORTS[0];
    return `<div class="page">
      ${subhead('신종 사기 시나리오 자동 생성', 12)}
      <div class="lead">제보가 훈련이 되기까지</div>
      <div class="lead-sub">검증된 국민 제보를 AI가 분석해 새로운 훈련 시나리오로 변환하고, 취약한 사용자에게 먼저 배포합니다.</div>
      <div class="report">
        <div class="row" style="gap:6px"><span class="chip">${r.cat}</span><span class="chip safe">${ic('badge-check')}검증 완료</span><span class="chip">${ic('thumbs-up')}${r.likes}</span></div>
        <div class="t">${r.title}</div><div class="body">${r.body}</div>
      </div>
      <button class="btn grad block mt" id="genBtn" onclick="genRun()">${ic('wand-sparkles')}AI 시나리오 생성 시작</button>
      <div class="card mt2 pipe" id="pipe">
        ${GEN_STEPS.map(([i, t, s], k) => `<div class="pstep" id="ps${k}"><span class="icon-box" style="background:#EEF1F7;color:var(--mute)">${ic(i)}</span><div class="grow"><div class="t">${t}</div><div class="s">${s}</div><div class="out" id="po${k}"></div></div></div>`).join('')}
      </div>
      <div id="genOut"></div>
      <div class="sec-title">최근 자동 생성된 시나리오</div>
      <div class="card">
        ${[
          ['mail', '#0EA5E9', '모바일 청첩장 악성앱', '제보 37건 · 오늘', 'wedding'],
          ['mic', '#F04438', 'AI 목소리 자녀 납치 협박', '제보 21건 · 2일 전', ''],
          ['package', '#F79009', '해외직구 관세 환급 스미싱', '제보 54건 · 4일 전', ''],
        ].map(([i, c, t, s, k]) => `<div class="list-item" style="cursor:pointer" onclick="${k ? `go('play/${k}')` : `toast('배포 대기 중인 시나리오예요','clock')`}"><span class="icon-box sm" style="background:${c}1A;color:${c}">${ic(i)}</span><div class="grow"><div class="t">${t}</div><div class="s">${s}</div></div>${k ? '<span class="chip pri">체험 가능</span>' : '<span class="chip">배포 대기</span>'}</div>`).join('')}
      </div>
    </div>`;
  },

  /* ---------- 13. 방어 설정 점검 ---------- */
  checkup: () => `<div class="page">
    ${subhead('방어 설정 점검', 13)}
    <div class="lead">이미 있는 무료 방어,<br/>다 켜져 있나요?</div>
    <div class="lead-sub">통신사·제조사·경찰청·금융권에 흩어진 사기 방어 기능을 한 번에 점검하고 켜 드려요.</div>
    <div class="chips" style="margin-bottom:14px"><span class="chip">${ic('smartphone')}Galaxy S24</span><span class="chip">One UI 8.0</span><span class="chip">SKT</span></div>
    <div id="ckBody"></div>
  </div>`,

  /* ---------- MY ---------- */
  me: () => `<div class="page">
    <div class="card row" style="margin-top:6px;gap:14px">
      <span class="icon-box" style="width:58px;height:58px;border-radius:20px;background:var(--grad);color:#fff;font-weight:800;font-size:20px">지</span>
      <div class="grow"><div class="b" style="font-size:18px">김지민</div><div class="muted small">대응력 72점 · 훈련 23회 · 제보 4건</div></div>
      ${govPill('본인인증')}
    </div>
    <div class="card mt">
      ${[
        ['radar', '나의 취약점 분석', 'weakness', 6],
        ['target', '맞춤형 사기 훈련', 'training', 7],
        ['users', '가족 보호 네트워크', 'family', 9],
        ['wand-sparkles', '신종 사기 시나리오 생성', 'generate', 12],
      ].map(([i, t, r, n]) => `<div class="list-item" style="cursor:pointer" onclick="go('${r}')"><span class="icon-box sm" style="background:var(--pri-soft);color:var(--pri)">${ic(i)}</span><div class="grow t">${t}</div><span class="featnum">${n}</span>${ic('chevron-right')}</div>`).join('')}
    </div>
    <div class="sec-title">CodySafe 전체 기능</div>
    <div class="card">
      ${FEATURES.map(f => `<div class="list-item" style="cursor:pointer;padding:11px 0" onclick="go('${f.route}')"><span class="featnum" style="min-width:28px;text-align:center">${f.n}</span>${ic(f.icon)}<div class="grow t" style="font-size:14px">${f.name}</div>${f.ext ? '<span class="chip">확장</span>' : ''}${f.isNew ? '<span class="chip pri">NEW</span>' : ''}</div>`).join('')}
    </div>
    <div class="center muted tiny mt2">CodySafe MVP · 데모용 목업 데이터</div>
  </div>`,
};

/* ---------------- 10. URL 분석 로직 (실제 동작) ---------------- */

function urlMode(m) {
  $('#segText').classList.toggle('on', m === 'text');
  $('#segQr').classList.toggle('on', m === 'qr');
  $('#urlInput').style.display = m === 'text' ? '' : 'none';
  $('#qrInput').style.display = m === 'qr' ? '' : 'none';
  $('#urlRes').innerHTML = '';
}

// 편집 거리 + 역추적으로 어떤 글자가 다른지 표시
function diffMarks(a, b) {
  const m = a.length, n = b.length;
  const D = Array.from({ length: m + 1 }, (_, i) => Array.from({ length: n + 1 }, (_, j) => i === 0 ? j : j === 0 ? i : 0));
  for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++)
    D[i][j] = Math.min(D[i - 1][j] + 1, D[i][j - 1] + 1, D[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
  const ma = Array(m).fill(false), mb = Array(n).fill(false);
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && D[i][j] === D[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)) {
      if (a[i - 1] !== b[j - 1]) ma[i - 1] = mb[j - 1] = true;
      i--; j--;
    } else if (i > 0 && D[i][j] === D[i - 1][j] + 1) { ma[i - 1] = true; i--; }
    else { mb[j - 1] = true; j--; }
  }
  return { d: D[m][n], ma, mb };
}
const markStr = (s, marks, cls) => [...s].map((ch, i) => marks[i] ? `<span class="${cls}">${ch}</span>` : ch).join('');

const SHORTENERS = ['bit.ly', 'han.gl', 'me2.do', 'tinyurl.com', 't.ly', 'vo.la', 'url.kr', 'buly.kr', 'goo.gl', 'is.gd'];
const BAD_TLD = ['top', 'xyz', 'site', 'shop', 'icu', 'cc', 'buzz', 'click', 'live', 'online', 'vip', 'info', 'link', 'cn'];
const SMISH_WORDS = ['본인인증', '주소불명', '주소 확인', '미납', '과태료', '지원금', '정지', '마감', '환급', '압류', '보관중'];
const homoglyph = s => s.replace(/0/g, 'o').replace(/1/g, 'l').replace(/rn/g, 'm').replace(/vv/g, 'w').replace(/3/g, 'e').replace(/5/g, 's');

function analyzeUrlText(text) {
  const m = text.match(/(https?:\/\/)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:\/[^\s]*)?/i);
  if (!m) return null;
  const hasProto = /^https?:/i.test(m[0]);
  let url;
  try { url = new URL(hasProto ? m[0] : 'http://' + m[0]); } catch (e) { return null; }
  const host = url.hostname.toLowerCase().replace(/^www\./, '');
  const labels = host.split('.');
  const sld2 = ['go', 'or', 'co', 'ac', 'ne', 're'].includes(labels[labels.length - 2]);
  const reg = labels.slice(sld2 ? -3 : -2).join('.');
  const main = labels[labels.length - (sld2 ? 3 : 2)];
  const base = { host, reg, url, findings: [], score: 0 };

  const off = OFFICIAL_DOMAINS.find(o => host === o.d || host.endsWith('.' + o.d));
  if (off) return { ...base, level: ['gov', 'public'].includes(off.type) ? 'gov' : 'safe', off, score: 2 };
  if (host.endsWith('.go.kr')) return { ...base, level: 'gov', off: { d: host, n: '정부기관 전용 도메인(.go.kr)', type: 'gov' }, score: 3 };

  const r = base;
  const add = (pts, icon, t, s) => { r.score += pts; r.findings.push({ pts, icon, t, s }); };

  if (SHORTENERS.includes(host)) add(35, 'link-2', '단축 URL 사용', '실제 목적지를 숨기는 단축 주소입니다. 공공기관·금융사는 문자로 단축 URL을 보내지 않아요.');
  if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) add(40, 'server', 'IP 주소로 직접 접속', '정상 서비스는 도메인 대신 IP 주소를 쓰지 않습니다.');
  if (host.includes('xn--')) add(35, 'languages', '국제화 도메인(퓨니코드)', '키릴 문자 등으로 영문을 흉내 낸 도메인일 수 있어요.');

  // 공식 도메인 흉내 (스펠링 1~2글자 차이) / 브랜드명 사칭
  const nm = homoglyph(main);
  let best = null;
  for (const o of OFFICIAL_DOMAINS) {
    const oMain = o.d.split('.')[0];
    const dist = diffMarks(nm, oMain).d;
    if (oMain.length >= 4 && dist > 0 && dist <= 2 && (!best || dist < best.dist)) best = { o, dist, kind: 'typo' };
  }
  if (!best) for (const o of OFFICIAL_DOMAINS) {
    const oMain = o.d.split('.')[0];
    if ((oMain.length >= 4 || oMain === 'gov') && homoglyph(host).includes(oMain)) { best = { o, kind: 'brand' }; break; }
  }
  if (best) {
    r.diff = { ...diffMarks(reg, best.o.d), a: reg, b: best.o.d, o: best.o };
    if (best.kind === 'typo') add(45, 'spell-check', `공식 도메인과 철자 ${r.diff.d}글자 차이`, `${best.o.n} 공식 도메인(${best.o.d})을 교묘하게 흉내 낸 주소입니다.`);
    else add(40, 'badge-alert', `'${best.o.n}' 이름 사칭`, `${best.o.n}을(를) 연상시키지만 공식 도메인(${best.o.d})이 아닙니다.`);
    if (nm !== main) add(15, 'binary', '숫자로 알파벳 위장', `"${main}" → 0↔o, 1↔l 처럼 비슷한 글자로 눈속임했어요.`);
  }

  const tld = labels[labels.length - 1];
  if (BAD_TLD.includes(tld)) add(20, 'globe', `의심 최상위 도메인 (.${tld})`, '스미싱에 자주 쓰이는 저가 해외 도메인입니다.');
  if (url.protocol === 'http:' && hasProto) add(10, 'lock-open', '암호화되지 않은 연결 (HTTP)', '입력한 정보가 그대로 노출될 수 있어요.');
  if (/login|verify|auth|apply|pay|track|apk|bank|cert/i.test(url.pathname + url.search)) add(10, 'key-round', '개인정보 입력 유도 경로', `"${url.pathname}" — 로그인·결제·인증 페이지로 유도합니다.`);
  const words = SMISH_WORDS.filter(w => text.includes(w));
  if (words.length) add(10, 'message-square-warning', '스미싱 문구 패턴', `"${words.join('", "')}" 등 긴급성·불안을 유도하는 표현이 있어요.`);
  add(15, 'shield-question', '공인 도메인 DB 미등록', '정부·공공·금융기관 공인 목록에 없는 사이트입니다. 개인정보 입력에 주의하세요.');

  r.score = Math.min(99, r.score);
  r.level = r.score >= 60 ? 'danger' : 'warn';
  return r;
}

function analyzeUrl() {
  const text = $('#urlText').value.trim();
  const res = $('#urlRes');
  if (!text) { toast('문자나 링크를 입력해 주세요', 'info'); return; }
  const r = analyzeUrlText(text);
  if (!r) { res.innerHTML = `<div class="card empty">${ic('search-x')}<div class="mt">링크를 찾지 못했어요. URL이 포함된 문자를 붙여넣어 주세요.</div></div>`; icons(); return; }
  runSteps(res, ['링크 추출 및 도메인 분해', '정부·금융기관 공인 도메인 DB 대조', '유사 스펠링·문자 위장 분석', 'KISA 피싱 DB · WHOIS 평판 조회'], () => {
    res.innerHTML = urlResult(r);
    icons();
    if (r.level === 'danger') vibrate([200, 80, 200]);
    res.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 480);
}

function urlResult(r) {
  if (r.level === 'gov' || r.level === 'safe') {
    const gov = r.level === 'gov';
    return `<div class="verdict ${gov ? 'gov' : 'safe'}">
      <div class="score"><b>${r.score}</b><span>위험 점수</span></div>
      <div class="lvl">${ic('shield-check')}${gov ? '공인 사이트' : '안전'}</div>
      <div class="head">${gov ? '대한민국 정부<br/>공인 사이트입니다' : '공식 등록된<br/>안전한 사이트입니다'}</div>
      <div class="desc">${r.off.n} · ${r.host}</div>
    </div>
    <div class="gov-card mt">${govSvg(52)}<div class="grow"><div class="t">${gov ? '정부·공공기관 공인 도메인' : '금융·주요 기업 공식 도메인'}</div><div class="s">공인 도메인 DB 일치 · HTTPS 인증서 정상 · 피싱 신고 이력 없음</div></div></div>
    <div class="card mt">
      <div class="kv"><span>접속 도메인</span><b>${r.host}</b></div>
      <div class="kv"><span>등록 기관</span><b>${r.off.n}</b></div>
      <div class="kv"><span>공인 DB</span><b style="color:var(--safe)">일치 ✓</b></div>
    </div>`;
  }
  const danger = r.level === 'danger';
  return `<div class="verdict ${danger ? 'danger' : 'warn'}">
    <div class="score"><b>${r.score}</b><span>위험 점수</span></div>
    <div class="lvl">${ic(danger ? 'triangle-alert' : 'shield-alert')}${danger ? '위험' : '주의'}</div>
    <div class="head">${danger ? '피싱 사이트로<br/>강하게 의심돼요' : '국가가 공인하지 않은<br/>사이트입니다'}</div>
    <div class="desc">${danger ? '링크를 누르거나 개인정보를 입력하지 마세요.' : '확인되지 않은 사이트예요. 로그인·결제 전 공식 앱으로 확인하세요.'}</div>
  </div>
  ${r.diff ? `<div class="card mt">
    <div class="b" style="margin-bottom:10px">🔎 스펠링 비교</div>
    <div class="domain-diff"><span class="lbl">받은 링크</span>${markStr(r.diff.a, r.diff.ma, 'x')}</div>
    <div class="domain-diff"><span class="lbl">${r.diff.o.n} 공식 ${['gov', 'public'].includes(r.diff.o.type) ? govPill('공인') : ''}</span>${markStr(r.diff.b, r.diff.mb, 'o')}</div>
  </div>` : ''}
  <div class="card mt">
    <div class="b" style="margin-bottom:12px">탐지 근거 ${r.findings.length}건</div>
    ${r.findings.map(f => `<div class="finding"><span class="icon-box sm" style="background:var(--danger-soft);color:var(--danger)">${ic(f.icon)}</span><div class="grow"><div class="t">${f.t}</div><div class="s">${f.s}</div></div><span class="pts">+${f.pts}</span></div>`).join('')}
  </div>
  <div class="card mt">
    <div class="kv"><span>도메인</span><b>${r.host}</b></div>
    <div class="kv"><span>공인 도메인 DB</span><b style="color:var(--danger)">미등록</b></div>
    <div class="kv"><span>도메인 생성일 (WHOIS)</span><b>${danger ? '3일 전' : '2년 전'}</b></div>
    <div class="kv"><span>KISA 피싱 신고</span><b>${danger ? '2건' : '없음'}</b></div>
  </div>
  <div class="row mt">
    <button class="btn line grow" onclick="go('copilot')">${ic('bot')}대처 방법</button>
    <button class="btn danger grow" onclick="reportSheet('스미싱')">${ic('megaphone')}제보하기</button>
  </div>`;
}

/* ---------------- 1. 이미지 ---------------- */

function portrait(kind) {
  const ai = kind === 'ai';
  const bg = ai ? ['#F7C9A6', '#C48BC0'] : ['#A9BFD1', '#5D7A8E'];
  const hand = ai ? `<g transform="translate(58 300) rotate(-12)">
      <ellipse cx="40" cy="62" rx="34" ry="30" fill="#E2B096"/>
      ${[0, 1, 2, 3, 4, 5].map(i => `<rect x="${6 + i * 11}" y="${8 + Math.abs(2.5 - i) * 6}" width="10" height="46" rx="5" fill="#E8B9A0"/>`).join('')}
    </g>` : '';
  return `<svg class="portrait" viewBox="0 0 320 400" preserveAspectRatio="xMidYMid slice">
    <defs><linearGradient id="pbg${kind}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${bg[0]}"/><stop offset="1" stop-color="${bg[1]}"/></linearGradient>
    <radialGradient id="psk${kind}" cx=".45" cy=".4" r=".7"><stop offset="0" stop-color="#F7D8C4"/><stop offset="1" stop-color="#D9A88A"/></radialGradient></defs>
    <rect width="320" height="400" fill="url(#pbg${kind})"/>
    <circle cx="255" cy="70" r="70" fill="#fff" opacity=".18"/>
    ${ai ? '<path d="M200 40 Q230 60 220 120 Q260 90 300 130" stroke="#fff" stroke-opacity=".35" stroke-width="10" fill="none"/>' : '<rect x="20" y="40" width="70" height="120" rx="6" fill="#fff" opacity=".12"/>'}
    <path d="M50 400 C62 305 118 282 160 282 C202 282 258 305 270 400Z" fill="${ai ? '#2D3B5E' : '#3E4A3D'}"/>
    <rect x="140" y="226" width="40" height="66" rx="18" fill="#D9A88A"/>
    <ellipse cx="160" cy="172" rx="62" ry="78" fill="url(#psk${kind})"/>
    <path d="M94 176 C86 96 130 76 166 78 C214 80 236 118 226 178 C222 140 202 116 160 116 C124 116 102 140 94 176Z" fill="#3A2A22"/>
    <ellipse cx="136" cy="176" rx="7" ry="5" fill="#2B211C"/><ellipse cx="184" cy="176" rx="7" ry="5" fill="#2B211C"/>
    <path d="M128 162 Q136 157 145 161 M175 161 Q184 157 192 162" stroke="#3A2A22" stroke-width="3" fill="none" stroke-linecap="round"/>
    <path d="M160 184 L155 204 L164 206" stroke="#C48E73" stroke-width="3" fill="none" stroke-linecap="round"/>
    <path d="M144 222 Q160 233 176 222" stroke="#A8574F" stroke-width="4" fill="none" stroke-linecap="round"/>
    ${hand}
  </svg>`;
}

function imgUpload(input) {
  const f = input.files[0];
  if (!f) return;
  const rd = new FileReader();
  rd.onload = () => imgAnalyze('upload', rd.result);
  rd.readAsDataURL(f);
}

function imgAnalyze(kind, src) {
  const ai = kind !== 'real';
  $('#imgArea').innerHTML = `<div class="img-stage" id="imgStage">
    ${src ? `<img src="${src}" alt="">` : portrait(kind)}
    <div class="grid-ov"></div><div class="scanline"></div>
    <div class="img-badge">${ic('scan-face')}AI 분석 중…</div>
  </div>`;
  icons();
  runSteps($('#imgRes'), ['얼굴·신체 구조 이상 탐지', '피부·배경 텍스처 분석', 'EXIF 메타데이터 확인', '확산모델 주파수 지문 검사', '역이미지 검색 (도용 여부)'], () => {
    const st = $('#imgStage');
    st.querySelector('.scanline').remove();
    st.querySelector('.grid-ov').style.opacity = '.35';
    if (ai) st.insertAdjacentHTML('beforeend', `
      <i class="heat" style="left:6%;top:66%;width:44%;height:30%;background:rgba(255,60,60,.7)"></i>
      <i class="heat" style="left:58%;top:6%;width:40%;height:30%;background:rgba(255,160,40,.55)"></i>
      <i class="heat" style="left:26%;top:18%;width:48%;height:22%;background:rgba(255,200,60,.35)"></i>
      <div class="marker" style="left:9%;top:72%;width:34%;height:22%;animation-delay:.2s"><span>손가락 6개</span></div>
      <div class="marker" style="left:60%;top:10%;width:34%;height:26%;animation-delay:.4s"><span>배경 왜곡</span></div>
      <div class="marker" style="left:28%;top:24%;width:44%;height:14%;animation-delay:.6s"><span>머리카락 경계 융합</span></div>`);
    st.querySelector('.img-badge').innerHTML = ai ? `${ic('triangle-alert')}AI 생성 의심 영역 3곳` : `${ic('circle-check')}이상 영역 없음`;
    $('#imgRes').innerHTML = ai ? `
      <div class="verdict danger"><div class="score"><b>87%</b><span>AI 생성 확률</span></div>
        <div class="lvl">${ic('triangle-alert')}위험</div><div class="head">AI로 생성된<br/>가짜 인물로 보여요</div>
        <div class="desc">로맨스 스캠·투자 사기 프로필에 자주 쓰이는 유형입니다.</div></div>
      <div class="card mt"><div class="b" style="margin-bottom:12px">판별 근거</div>
        ${[
          ['hand', '손·손가락 구조 이상', '손가락이 6개로 생성된 전형적인 AI 오류', 30],
          ['sparkles', '피부 텍스처 과도하게 매끄러움', '모공·잔털이 없고 조명 반사가 균일해요', 18],
          ['image-off', '배경 비대칭·왜곡', '배경의 직선 구조가 휘어져 있어요', 14],
          ['file-x', 'EXIF 메타데이터 없음', '촬영 기기·일시 정보가 존재하지 않아요', 10],
          ['waves', '확산모델(Diffusion) 지문 검출', '주파수 영역에서 생성 모델 특유의 패턴 확인', 15],
        ].map(([i, t, s, p]) => `<div class="finding"><span class="icon-box sm" style="background:var(--danger-soft);color:var(--danger)">${ic(i)}</span><div class="grow"><div class="t">${t}</div><div class="s">${s}</div></div><span class="pts">+${p}</span></div>`).join('')}
      </div>
      <div class="card mt">
        <div class="kv"><span>판별 모델</span><b>CNN + ViT 앙상블</b></div>
        <div class="kv"><span>추정 생성 모델</span><b>Diffusion 계열</b></div>
        <div class="kv"><span>역이미지 검색</span><b>유사 얼굴 해외 SNS 3건</b></div>
      </div>
      <div class="row mt"><button class="btn line grow" onclick="go('play/romance')">${ic('gamepad-2')}로맨스 스캠 체험</button><button class="btn pri grow" onclick="render()">${ic('rotate-ccw')}다시 분석</button></div>`
      : `<div class="verdict safe"><div class="score"><b>9%</b><span>AI 생성 확률</span></div>
        <div class="lvl">${ic('shield-check')}안전</div><div class="head">실제 촬영된<br/>사진으로 보여요</div>
        <div class="desc">EXIF 촬영 정보와 자연스러운 노이즈 패턴이 확인됐어요.</div></div>
      <div class="card mt"><div class="kv"><span>촬영 기기</span><b>Galaxy S26</b></div><div class="kv"><span>센서 노이즈</span><b style="color:var(--safe)">자연 패턴 ✓</b></div><div class="kv"><span>역이미지 검색</span><b>도용 이력 없음</b></div></div>
      <div class="card mt row small" style="box-shadow:none;background:#FFF8EC">${ic('info')}<span>실제 사진이라도 <b>타인 사진 도용</b> 가능성은 남아 있어요. 금전 요구가 있다면 의심하세요.</span></div>
      <button class="btn pri block mt" onclick="render()">${ic('rotate-ccw')}다른 사진 분석</button>`;
    icons();
    if (ai) vibrate(200);
  }, 520);
}

/* ---------------- 2. 음성 ---------------- */

function voiceStart() {
  $('#vSt').textContent = '통화 중 · 00:00';
  $('#vWave').querySelectorAll('i').forEach(i => i.style.animationPlayState = 'running');
  $('#vActs').innerHTML = `<button class="call-btn" onclick="back()"><span class="c red">${ic('phone-off')}</span>종료</button>`;
  icons();
  let sec = 0;
  const tick = () => { sec++; const e = $('#vSt'); if (e) { e.textContent = `통화 중 · 00:${String(sec).padStart(2, '0')}`; later(tick, 1000); } };
  later(tick, 1000);
  $('#vPanel').innerHTML = `<div class="row between"><b>AI 합성 음성 확률</b><b id="vPct" style="font-size:22px">0%</b></div>
    <div class="risk-meter"><i id="vMeter"></i></div><div class="small" style="opacity:.7;margin-top:8px" id="vMsg">음성 특징 추출 중…</div>`;
  let p = 0;
  const up = () => {
    p = Math.min(82, p + 3 + Math.round(Math.random() * 4));
    $('#vPct').textContent = p + '%';
    $('#vMeter').style.width = p + '%';
    if (p < 82) later(up, 130);
  };
  later(up, 400);
  const finds = [
    ['wind', '호흡·침 삼킴 소리 부재', '자연 발화의 미세 호흡음이 전혀 감지되지 않아요'],
    ['activity', '피치 변화가 비정상적으로 균일', '감정 변화 구간에서도 음높이 편차가 0.8%'],
    ['audio-waveform', '고주파 보코더 아티팩트', '8kHz 이상 대역에서 TTS 합성 흔적 검출'],
    ['repeat', '배경 잡음 루프 반복', '동일한 잡음 패턴이 2.4초 간격으로 반복'],
  ];
  finds.forEach((f, i) => later(() => {
    $('#vFind').insertAdjacentHTML('beforeend', `<div class="glass" style="display:flex;gap:12px;animation:pageIn .3s ease;padding:12px 14px">
      <span style="color:#FCA5A5">${ic(f[0])}</span><div><div class="b small">${f[1]}</div><div class="tiny" style="opacity:.65;margin-top:2px">${f[2]}</div></div></div>`);
    icons();
  }, 1200 + i * 700));
  later(() => {
    $('#vMsg').innerHTML = '<b style="color:#FCA5A5">⚠️ AI 합성 음성으로 의심됩니다.</b> 가족·지인 목소리라도 끊고 직접 다시 걸어 확인하세요.';
    vibrate([300, 100, 300]);
    $('#vActs').innerHTML = `<button class="call-btn" onclick="back()"><span class="c red">${ic('phone-off')}</span>끊기</button>
      <button class="call-btn" onclick="go('call')"><span class="c">${ic('shield-check')}</span>통화 내용 감시</button>
      <button class="call-btn" onclick="go('copilot')"><span class="c">${ic('bot')}</span>코파일럿</button>`;
    icons();
  }, 4200);
}

/* ---------------- 3. 실시간 통화 ---------------- */

const CALL_SCRIPT = [
  { who: '상대', t: '여보세요, 김지민 씨 본인 맞으십니까?', r: 4 },
  { who: '나', t: '네, 맞는데요. 누구세요?', r: 0 },
  { who: '상대', t: '여기는 <mark>서울중앙지검</mark> 첨단범죄수사팀 김민수 <mark>수사관</mark>입니다.', r: 18, tag: '기관 사칭' },
  { who: '상대', t: '본인 명의 계좌가 <mark>대포통장</mark> 사건에 연루되어 연락드렸습니다.', r: 16, tag: '사건 연루 통보' },
  { who: '나', t: '네? 저는 그런 적 없는데요…', r: 0 },
  { who: '상대', t: '이 통화는 녹취되며, <mark>제3자에게 알리면</mark> 공무집행방해가 됩니다.', r: 20, tag: '고립 유도' },
  { who: '상대', t: '자산 보호를 위해 <mark>안전계좌</mark>로 <mark>이체</mark>하셔야 합니다.', r: 34, tag: '금전 요구' },
];

function callStart() {
  $('#cTr').innerHTML = '';
  $('#cActs').innerHTML = `<button class="call-btn" onclick="back()"><span class="c red">${ic('phone-off')}</span>종료</button>`;
  icons();
  let sec = 0, risk = 0;
  const tick = () => { sec++; const e = $('#cSt'); if (e) { e.textContent = `통화 중 · 00:${String(sec).padStart(2, '0')}`; later(tick, 1000); } };
  tick();
  CALL_SCRIPT.forEach((l, i) => later(() => {
    risk = Math.min(97, risk + l.r);
    const tr = $('#cTr');
    tr.insertAdjacentHTML('beforeend', `<div class="tline ${l.who === '나' ? 'me' : ''}"><div class="who"><span>${l.who}</span>${l.tag ? `<span class="tag">⚠ ${l.tag} +${l.r}</span>` : ''}</div>${l.t}</div>`);
    tr.scrollTop = tr.scrollHeight;
    $('#cRisk').textContent = risk + '%';
    $('#cRisk').style.color = risk >= 70 ? '#FCA5A5' : risk >= 35 ? '#FDE68A' : '#fff';
    $('#cMeter').style.width = risk + '%';
    if (risk >= 35 && risk < 70 && l.tag) vibrate(120);
    if (risk >= 70) later(callAlert, 700);
  }, 900 + i * 2000));
}

function callAlert() {
  vibrate([400, 120, 400, 120, 400]);
  $('#alertLayer').innerHTML = `<div class="big-alert">
    <div class="ring-alert">${ic('siren')}</div>
    <h3>보이스피싱 의심!</h3>
    <p><b>기관 사칭 · 안전계좌 이체 요구</b>가 감지됐어요.<br/>검찰·경찰은 절대 돈을 요구하지 않습니다.<br/>지금 바로 통화를 끊으세요.</p>
    <div class="acts">
      <button class="btn w block" onclick="$('#alertLayer').innerHTML='';toast('통화를 종료했어요. 잘하셨어요!','shield-check');later(()=>go('home'),900)">${ic('phone-off')}지금 통화 끊기</button>
      <button class="btn t block" onclick="go('copilot')">${ic('bot')}코파일럿에게 대처법 묻기</button>
      <button class="btn t block" onclick="toast('가족에게 위험 알림을 보냈어요','users')">${ic('users')}가족에게 알리기</button>
    </div>
  </div>`;
  icons();
  $('.screen').classList.add('shake');
  setTimeout(() => $('.screen').classList.remove('shake'), 700);
}

/* ---------------- 4. 시뮬레이션 진행 ---------------- */

let sim = null;

function simStep() {
  const s = sim.s, step = s.steps[sim.i];
  const chat = $('#chat');
  $('#choices').style.display = 'none';
  document.querySelectorAll('#simProg i').forEach((e, k) => e.classList.toggle('on', k <= sim.i));
  step.msgs.forEach((m, k) => {
    later(() => {
      chat.insertAdjacentHTML('beforeend', `<div class="msg" id="typing"><span class="av">${s.contact.av}</span><div class="bubble typing"><i></i><i></i><i></i></div></div>`);
      view.scrollTop = view.scrollHeight;
    }, k * 1100 + 150);
    later(() => {
      $('#typing')?.remove();
      const link = /^https?:\/\//.test(m);
      chat.insertAdjacentHTML('beforeend', `<div class="msg ${k ? 'cont' : ''}"><span class="av">${s.contact.av}</span><div class="bubble ${link ? 'link' : ''}">${m}</div></div>`);
      view.scrollTop = view.scrollHeight;
    }, k * 1100 + 850);
  });
  later(() => {
    const c = $('#choices');
    c.style.display = '';
    c.innerHTML = `<div class="q">${ic('mouse-pointer-click')}어떻게 답할까요? (${sim.i + 1}/${s.steps.length})</div>
      ${step.choices.map((ch, j) => `<button class="choice" onclick="simChoose(${j})">${ch.t}</button>`).join('')}`;
    icons();
    view.scrollTop = view.scrollHeight;
  }, step.msgs.length * 1100 + 300);
}

function simChoose(j) {
  const ch = sim.s.steps[sim.i].choices[j];
  sim.answers.push(ch);
  $('#chat').insertAdjacentHTML('beforeend', `<div class="msg me"><div class="bubble">${ch.t}</div></div>`);
  const last = sim.i === sim.s.steps.length - 1;
  $('#choices').innerHTML = `<div class="feedback ${ch.ok ? 'ok' : 'bad'}">${ic(ch.ok ? 'circle-check' : 'circle-x')}<div><b>${ch.ok ? '안전한 선택!' : '위험한 선택이에요'}</b><br/>${ch.fb}</div></div>
    <button class="btn pri block mt" onclick="${last ? 'simResult()' : 'sim.i++;simStep()'}">${last ? '결과 보기' : '다음 대화'}${ic('arrow-right')}</button>`;
  icons();
  if (!ch.ok) vibrate(150);
  view.scrollTop = view.scrollHeight;
}

function simResult() {
  const s = sim.s, ok = sim.answers.filter(a => a.ok).length, score = Math.round(ok / s.steps.length * 100);
  const wrong = sim.answers.filter(a => !a.ok);
  view.classList.remove('full');
  $('#tabbar').classList.remove('hidden');
  view.innerHTML = `<div class="page">
    ${subhead('훈련 결과')}
    <div class="card center">
      <span class="chip" style="background:${s.soft};color:${s.color}">${s.tag}</span>
      <div class="b mt" style="font-size:17px">${s.title}</div>
      <div class="result-ring">${ring(score, 150, 14, '#EEF1F7', score >= 70 ? ['#1CC27B', '#0E9F8E'] : score >= 40 ? ['#FFA53A', '#F0712C'] : ['#FF5A4E', '#D92D6B'])}
        <div class="v"><div><b>${score}</b><span class="muted small b">점</span></div></div></div>
      <div class="b mt" style="font-size:18px">${score === 100 ? '완벽하게 방어했어요! 🛡️' : score >= 60 ? '잘 대응했지만 아쉬운 순간이 있었어요' : '실제였다면 피해를 입을 수 있었어요'}</div>
      <div class="muted small" style="margin-top:4px">${s.steps.length}번의 선택 중 ${ok}번 안전하게 대응</div>
    </div>
    <div class="sec-title">이 수법의 위험 신호</div>
    <div class="card"><div class="chips" style="flex-wrap:wrap">${s.signals.map(x => `<span class="chip danger">${ic('flag')}${x}</span>`).join('')}</div></div>
    ${wrong.length ? `<div class="sec-title">이렇게 했어야 해요</div><div class="card">${wrong.map(w => `<div class="finding"><span class="icon-box sm" style="background:var(--danger-soft);color:var(--danger)">${ic('lightbulb')}</span><div><div class="t">"${w.t}"</div><div class="s">${w.fb}</div></div></div>`).join('')}</div>` : ''}
    <div class="card mt row" style="background:linear-gradient(135deg,#F1EDFF,#EAF0FF);box-shadow:none">
      <span class="icon-box sm" style="background:#fff;color:var(--pri2)">${ic('radar')}</span>
      <div class="grow small"><b>${s.tag}</b> 대응력이 반영됐어요. 취약점 분석에서 변화를 확인하세요.</div>
    </div>
    <div class="row mt2"><button class="btn line grow" onclick="render()">${ic('rotate-ccw')}다시 하기</button><button class="btn pri grow" onclick="go('weakness')">${ic('radar')}취약점 보기</button></div>
  </div>`;
  icons();
  view.scrollTop = 0;
}

/* ---------------- 5. 제보 ---------------- */

let repCat = '전체';
function repRender() {
  const list = REPORTS.filter(r => repCat === '전체' || r.cat === repCat);
  $('#repList').innerHTML = list.length ? list.map(r => {
    const [c, i, t] = STATUS[r.status];
    return `<div class="report">
      <div class="row" style="gap:6px"><span class="chip">${r.cat}</span><span class="chip ${c}">${ic(i)}${t}</span><span class="tiny muted" style="margin-left:auto">${r.ago}</span></div>
      <div class="t">${r.title}</div><div class="body">${r.body}</div>
      ${r.generated ? `<button class="gen" onclick="go('generate')">${ic('wand-sparkles')}AI가 훈련 시나리오로 변환했어요 · 체험하기 ${ic('chevron-right')}</button>` : ''}
      <div class="foot">
        <button class="${r.liked ? 'on' : ''}" onclick="repLike(${r.id})">${ic('thumbs-up')}도움돼요 ${r.likes}</button>
        <button onclick="toast('검증 의견을 남겼어요','message-circle')">${ic('message-circle')}검증 의견</button>
        <span style="margin-left:auto" class="row">${ic('map-pin')}&nbsp;${r.region}</span>
      </div></div>`;
  }).join('') : `<div class="card empty">아직 제보가 없어요</div>`;
  icons();
}
function repFilter(btn, c) {
  repCat = c;
  document.querySelectorAll('#repFilter .filter').forEach(b => b.classList.toggle('on', b === btn));
  repRender();
}
function repLike(id) {
  const r = REPORTS.find(x => x.id === id);
  r.liked = !r.liked;
  r.likes += r.liked ? 1 : -1;
  repRender();
}
function reportSheet(cat = '') {
  openSheet(`<div class="row between"><div class="b" style="font-size:20px">신종 사기 제보</div><span class="featnum">기능 5</span></div>
    <div class="muted small" style="margin-top:4px">개인정보(이름·번호·계좌)는 AI가 자동 마스킹해요.</div>
    <div class="field"><label>사기 유형</label><select id="rpCat">${['스미싱', '보이스피싱', '투자', '로맨스', '중고거래', '기타'].map(c => `<option ${c === cat ? 'selected' : ''}>${c}</option>`).join('')}</select></div>
    <div class="field"><label>제목</label><input id="rpTitle" placeholder="예) 택배 주소 확인 문자에 이상한 링크"></div>
    <div class="field"><label>어떤 일이 있었나요?</label><textarea id="rpBody" placeholder="받은 문자, 통화 내용, 요구 사항을 적어주세요">${$('#urlText')?.value || ''}</textarea></div>
    <div class="row mt" style="gap:8px">
      <button class="btn line sm grow" onclick="toast('스크린샷을 첨부했어요','image')">${ic('image-plus')}스크린샷</button>
      <button class="btn line sm grow" onclick="toast('녹음 파일을 첨부했어요','file-audio')">${ic('file-audio')}통화 녹음</button>
    </div>
    <button class="btn grad block mt2" onclick="reportSubmit()">${ic('send')}제보하기</button>`);
}
function reportSubmit() {
  const title = $('#rpTitle').value.trim() || '새로운 사기 수법 제보';
  REPORTS.unshift({ id: Date.now(), cat: $('#rpCat').value, title, body: $('#rpBody').value.trim() || '내용 없음', region: '내 위치', ago: '방금', likes: 0, status: 'ai', liked: false });
  closeSheet();
  toast('제보 접수! AI가 1차 분석 중이에요', 'sparkles');
  if (route().r === 'report') repRender();
}

/* ---------------- 6. 레이더 차트 ---------------- */

function radarSvg(data) {
  const cx = 150, cy = 128, R = 88, n = data.length;
  const pt = (i, r) => { const a = -Math.PI / 2 + i * 2 * Math.PI / n; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; };
  const poly = r => data.map((_, i) => pt(i, r).join(',')).join(' ');
  const vals = data.map((d, i) => pt(i, R * d.v / 100));
  return `<svg viewBox="-34 0 368 260" width="100%" style="max-width:340px">
    <defs><linearGradient id="rdg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3B6BFF" stop-opacity=".35"/><stop offset="1" stop-color="#7B4DFF" stop-opacity=".35"/></linearGradient></defs>
    ${[.25, .5, .75, 1].map(f => `<polygon points="${poly(R * f)}" fill="${f === 1 ? '#F7F8FC' : 'none'}" stroke="#E2E7F0"/>`).join('')}
    ${data.map((_, i) => { const [x, y] = pt(i, R); return `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="#E2E7F0"/>`; }).join('')}
    <polygon points="${vals.map(p => p.join(',')).join(' ')}" fill="url(#rdg)" stroke="#4F5BFF" stroke-width="2.5" stroke-linejoin="round"/>
    ${vals.map(([x, y], i) => `<circle cx="${x}" cy="${y}" r="4.5" fill="#fff" stroke="${data[i].v < 50 ? '#F04438' : '#4F5BFF'}" stroke-width="2.5"/>`).join('')}
    ${data.map((d, i) => { const [x, y] = pt(i, R + 22); const anchor = Math.abs(x - cx) < 5 ? 'middle' : x > cx ? 'start' : 'end';
      return `<text x="${x}" y="${y + 4}" text-anchor="${anchor}" font-size="12" font-weight="700" fill="${d.v < 50 ? '#F04438' : '#334155'}">${d.k} ${d.v}</text>`; }).join('')}
  </svg>`;
}

/* ---------------- 8. 코파일럿 ---------------- */

function cpSend(q) {
  q = (q || '').trim();
  if (!q) return;
  $('#cpIn').value = '';
  const chat = $('#cpChat');
  chat.insertAdjacentHTML('beforeend', `<div class="cp-msg me">${q}</div><div class="cp-msg ai" id="cpTyping"><div class="typing" style="padding:4px 0"><i></i><i></i><i></i></div></div>`);
  view.scrollTop = view.scrollHeight;
  const hit = COPILOT.find(c => c.q === q) || COPILOT.find(c => c.key.some(k => q.toLowerCase().includes(k)));
  later(() => {
    $('#cpTyping').remove();
    const a = hit ? hit.a : `상황을 조금 더 알려주세요. 다음 중 하나라도 해당하면 <b>사기일 가능성이 높아요.</b><ol><li>돈·상품권·코인 송금 요구</li><li>앱 설치나 링크 클릭 요구</li><li>"비밀로 하라", "지금 당장" 같은 압박</li></ol>의심되면 우선 대화를 멈추고 <b>112</b>에 문의하세요.`;
    const acts = hit ? hit.acts : [['phone', '112 문의', 'tel:112'], ['link', 'URL 검사', '#/url']];
    chat.insertAdjacentHTML('beforeend', `<div class="cp-msg ai"><div class="ai-h">${ic('bot')}CodySafe 코파일럿</div>${a}
      <div class="acts">${acts.map(([i, t, h]) => `<a class="btn ${h.startsWith('tel') ? 'danger' : 'ghost'} sm" href="${h}" ${h.startsWith('#') ? `onclick="depth++"` : ''}>${ic(i)}${t}</a>`).join('')}</div></div>`);
    icons();
    view.scrollTop = view.scrollHeight;
  }, 900);
}

/* ---------------- 11. 기관 검증 ---------------- */

const AGENCIES = {
  '검찰청': { tel: '1301', site: 'spo.go.kr', facts: [
    ['안전계좌·보호계좌로 이체', '검찰은 어떤 경우에도 전화로 계좌 이체·현금 전달을 요구하지 않습니다.'],
    ['메신저·문자로 공문·영장 발송', '수사 서류는 우편·직접 송달로만 전달되며, 메신저로 보내지 않습니다.'],
    ['가족에게 알리지 말라', '수사기관은 비밀 유지를 이유로 가족과의 연락을 막지 않습니다.'],
    ['앱 설치·원격 조사', '검찰은 보안 앱이나 원격제어 앱 설치를 요구하지 않습니다.'],
  ] },
  '경찰청': { tel: '112 · 182', site: 'police.go.kr', facts: [
    ['계좌 동결 해제를 위한 송금', '경찰은 계좌 보호·동결 해제를 이유로 송금을 요구하지 않습니다.'],
    ['출석 대신 전화 조사', '정식 조사는 출석 요구서를 통해 진행됩니다.'],
  ] },
  '금융감독원': { tel: '1332', site: 'fss.or.kr', facts: [
    ['금감원 직원의 자금 보호 이체', '금감원은 개인 계좌의 돈을 보관하거나 이체를 지시하지 않습니다.'],
    ['대출 상담·저금리 대환', '금감원은 대출 상품을 안내하거나 중개하지 않습니다.'],
  ] },
  '국세청': { tel: '126', site: 'nts.go.kr', facts: [
    ['문자 링크로 세금 환급', '국세청은 환급을 위해 문자 링크·개인 계좌 입력을 요구하지 않습니다.'],
    ['체납 즉시 압류 협박', '체납 처분은 공식 고지서 발송 후 법적 절차로 진행됩니다.'],
  ] },
  '법원': { tel: '02-3480-1100', site: 'scourt.go.kr', facts: [
    ['전화로 벌금·공탁금 납부', '법원은 전화로 벌금·공탁금 입금을 요구하지 않습니다.'],
  ] },
  '은행': { tel: '각 은행 대표번호', site: 'kbstar.com 등', facts: [
    ['보안 강화를 위한 OTP·비밀번호 요구', '은행은 전화·문자로 OTP 번호, 비밀번호 전체를 묻지 않습니다.'],
  ] },
};
let agency = '검찰청';
function pickAgency(btn) {
  agency = btn.textContent;
  document.querySelectorAll('#agChips .filter').forEach(b => b.classList.toggle('on', b === btn));
}
function vfSample() {
  $('#vfNum').value = '02-3480-1172';
  $('#vfClaim').value = '서울중앙지검 김민수 수사관이라며 제 계좌가 대포통장 사건에 연루됐대요. 가족한테 말하면 안 되고, 메신저로 공문을 보내줬어요. 자산 보호를 위해 안전계좌로 이체하래요.';
  pickAgency(document.querySelector('#agChips .filter'));
}
function verifyRun() {
  const claim = $('#vfClaim').value.trim();
  const num = $('#vfNum').value.trim();
  if (!claim) { toast('상대가 한 말을 입력해 주세요', 'info'); return; }
  const A = AGENCIES[agency];
  const kw = [['계좌', '이체', '송금', '안전계좌', '보호', '입금', '돈'], ['공문', '메신저', '문자', '영장', '서류'], ['가족', '비밀', '알리'], ['앱', '설치', '원격']];
  const hits = A.facts.filter((_, i) => i >= kw.length || kw[i].some(k => claim.includes(k)));
  const facts = hits.length ? hits : A.facts.slice(0, 1);
  runSteps($('#vfRes'), [`${agency} 공식 연락처 DB 대조`, '기관 업무 지침 검색 (RAG)', '사칭 수법 패턴 매칭', '팩트체크 리포트 생성'], () => {
    const official = num && A.tel.replace(/\D/g, '').includes(num.replace(/\D/g, ''));
    $('#vfRes').innerHTML = `
      <div class="verdict danger"><div class="score"><b>${Math.min(98, 70 + facts.length * 7)}%</b><span>사칭 가능성</span></div>
        <div class="lvl">${ic('triangle-alert')}사칭 의심</div><div class="head">실제 ${agency}의<br/>업무 방식이 아니에요</div>
        <div class="desc">주장 ${facts.length}건이 공식 지침과 다릅니다.</div></div>
      <div class="card mt"><div class="b" style="margin-bottom:12px">팩트체크</div>
        ${facts.map(([c, f]) => `<div class="finding"><span class="icon-box sm" style="background:var(--danger-soft);color:var(--danger)">${ic('x')}</span><div>
          <div class="tiny b" style="color:var(--danger)">상대 주장</div><div class="t">"${c}"</div>
          <div class="tiny b" style="color:var(--safe);margin-top:8px">공식 사실</div><div class="s" style="color:var(--ink2)">${f}</div></div></div>`).join('')}
      </div>
      ${num ? `<div class="card mt"><div class="kv"><span>입력한 번호</span><b>${num}</b></div><div class="kv"><span>공식 대표번호 일치</span><b style="color:${official ? 'var(--safe)' : 'var(--danger)'}">${official ? '일치' : '불일치'}</b></div>
        <div class="tiny muted" style="margin-top:6px">※ 발신번호는 변작될 수 있어요. 번호가 같아도 반드시 끊고 직접 걸어 확인하세요.</div></div>` : ''}
      <div class="gov-card mt">${govSvg(50)}<div class="grow"><div class="t">${agency} 공식 연락처</div><div class="s">대표번호 <b>${A.tel}</b> · ${A.site}</div></div></div>
      <a class="btn danger block mt" href="tel:${A.tel.split(' ')[0].replace(/\D/g, '') || '112'}">${ic('phone')}공식 번호로 직접 확인하기</a>`;
    icons();
    vibrate(200);
  }, 520);
}

/* ---------------- 12. 시나리오 생성 ---------------- */

const GEN_STEPS = [
  ['inbox', '유사 제보 수집·클러스터링', '임베딩 유사도로 같은 수법의 제보를 묶습니다', ['유사 제보 37건', '서울 12 · 경기 9 · 기타 16']],
  ['badge-check', '커뮤니티·전문가 검증', '추천 수, 검증 의견, KISA 피싱 DB 대조', ['추천 152', 'KISA DB 일치', '검증 완료 ✓']],
  ['brain', '수법 패턴 추출 (LLM)', '접근 방식, 미끼, 요구 행동, 위험 신호를 구조화', ['지인 사칭', '청첩장 링크', '.apk 설치', '해외 도메인']],
  ['wand-sparkles', '훈련 시나리오 생성', '대화 흐름·선택지·피드백을 자동 작성', ['대화 2턴', '선택지 4개', '난이도 보통']],
  ['rocket', '비식별화 · 맞춤 배포', '개인정보 마스킹 후 취약 사용자에게 우선 배포', ['번호 마스킹', '우선 배포 2,140명']],
];
function genRun() {
  $('#genBtn').disabled = true;
  $('#genOut').innerHTML = '';
  GEN_STEPS.forEach((st, k) => {
    later(() => {
      const el = $('#ps' + k);
      el.classList.add('on', 'run');
      el.querySelector('.icon-box').innerHTML = ic('loader');
      icons();
    }, k * 900);
    later(() => {
      const el = $('#ps' + k);
      el.classList.remove('run');
      el.querySelector('.icon-box').innerHTML = ic(st[0]);
      $('#po' + k).innerHTML = st[3].map(x => `<span class="chip pri">${x}</span>`).join('');
      icons();
    }, k * 900 + 750);
  });
  later(() => {
    const s = SCENARIOS.wedding;
    $('#genOut').innerHTML = `<div class="sec-title">✨ 생성 완료</div>
      <div class="card" style="border:2px solid #C9BBFF">
        <div class="row"><span class="icon-box" style="background:${s.soft};color:${s.color}">${ic(s.icon)}</span>
          <div class="grow"><div class="b" style="font-size:16px">${s.title}</div><div class="muted small">${s.tag} · ${s.mins}분 · ${s.difficulty}</div></div></div>
        <div class="small" style="margin-top:12px;line-height:1.55;color:var(--ink2)">${s.desc}</div>
        <div class="chips mt" style="flex-wrap:wrap">${s.signals.map(x => `<span class="chip danger">${x}</span>`).join('')}</div>
        <button class="btn grad block mt" onclick="go('play/wedding')">${ic('play')}생성된 시나리오 체험하기</button>
      </div>`;
    icons();
    $('#genBtn').disabled = false;
    $('#genOut').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, GEN_STEPS.length * 900 + 200);
}

/* ---------------- 13. 방어 설정 점검 ---------------- */

let ckScanned = false;
const ckItems = () => CHECKUP.flatMap(g => g.items);
function ckStats() {
  const all = ckItems();
  const n = st => all.filter(i => i.st === st).length;
  return { score: Math.round((n('ok') * 100 + n('check') * 40) / all.length), ok: n('ok'), check: n('check'), bad: n('bad') };
}
const CK_ST = { ok: ['safe', 'circle-check', '켜짐'], check: ['warn', 'circle-help', '확인 필요'], bad: ['danger', 'circle-alert', '위험'] };

function checkCard() {
  const s = ckStats();
  return `<button class="card mt guard" style="width:100%;text-align:left" onclick="go('checkup')">
    <span class="icon-box" style="background:var(--warn-soft);color:var(--warn)">${ic('shield-plus')}</span>
    <div class="grow"><b style="font-size:15px">내 폰 방어 설정 점검</b>
      <div class="muted small" style="margin-top:3px">위험 ${s.bad}개 · 확인 필요 ${s.check}개</div></div>
    <span class="chip ${s.score >= 80 ? 'safe' : 'warn'}">${s.score}점</span>${ic('chevron-right')}
  </button>`;
}

function ckRender() {
  const s = ckStats();
  const color = s.score >= 80 ? ['#1CC27B', '#0E9F8E'] : s.score >= 50 ? ['#FFA53A', '#F0712C'] : ['#FF5A4E', '#D92D6B'];
  $('#ckBody').innerHTML = `
    <div class="card row" style="gap:18px">
      <div style="position:relative">${ring(s.score, 96, 11, '#EEF1F7', color)}
        <span style="position:absolute;inset:0;display:grid;place-items:center;text-align:center"><span><b style="font-size:26px;display:block;line-height:1">${s.score}</b><span class="tiny muted b">방어 점수</span></span></span></div>
      <div class="grow">
        <div class="b" style="font-size:16px;line-height:1.4">${s.bad + s.check === 0 ? '모든 방어가 켜져 있어요 🛡️' : `꺼져 있거나 확인 안 된<br/>방어가 ${s.bad + s.check}개 있어요`}</div>
        <div class="chips mt" style="flex-wrap:wrap"><span class="chip safe">켜짐 ${s.ok}</span><span class="chip warn">확인 ${s.check}</span><span class="chip danger">위험 ${s.bad}</span></div>
      </div>
    </div>
    ${CHECKUP.map(g => `<div class="sec-title"><span class="row" style="gap:8px">${ic(g.icon)}${g.g}</span><span class="muted tiny b">${g.sub}</span></div>
      <div class="card">${g.items.map(i => {
        const [c, icn, label] = CK_ST[i.st];
        return `<div class="list-item" ${i.st !== 'ok' ? `style="cursor:pointer" onclick="ckOpen('${i.id}')"` : ''}>
          <span class="icon-box sm" style="background:var(--${c}-soft);color:var(--${c})">${ic(icn)}</span>
          <div class="grow"><div class="t">${i.t}</div><div class="s">${i.s}</div></div>
          ${i.st === 'ok' ? `<span class="chip safe">${label}</span>` : `<span class="chip ${c}">${label}</span>${ic('chevron-right')}`}
        </div>`;
      }).join('')}</div>`).join('')}
    <div class="card mt2 row small" style="box-shadow:none;background:#F1F4FA;line-height:1.5">${ic('info')}<span>다른 앱의 설정은 보안상 직접 읽을 수 없어요. 설정 화면으로 안내한 뒤 <b>켰어요</b>를 누르면 점수에 반영됩니다.</span></div>`;
  icons();
}

function ckOpen(id) {
  const i = ckItems().find(x => x.id === id);
  const [c, icn, label] = CK_ST[i.st];
  openSheet(`<div class="row"><span class="icon-box" style="background:var(--${c}-soft);color:var(--${c})">${ic(icn)}</span>
      <div class="grow"><div class="b" style="font-size:18px">${i.t}</div><div class="muted small">${i.s}</div></div></div>
    <div class="card mt2" style="box-shadow:none;background:#F7F8FC">
      ${i.steps.map((st, k) => `<div class="row" style="align-items:flex-start;margin-top:${k ? 12 : 0}px"><span class="featnum" style="min-width:22px;text-align:center">${k + 1}</span><span style="font-size:14.5px;line-height:1.5">${st}</span></div>`).join('')}
    </div>
    <button class="btn line block mt2" onclick="toast('설정 화면으로 이동합니다 (데모)','external-link')">${ic('external-link')}${i.fix}</button>
    <button class="btn grad block mt" onclick="ckDone('${i.id}')">${ic('check')}켰어요</button>`);
}

function ckDone(id) {
  const i = ckItems().find(x => x.id === id);
  i.st = 'ok';
  i.s = i.auto ? '조치 완료 · 다시 확인했어요' : '사용자 확인 완료';
  closeSheet();
  ckRender();
  toast(`방어 점수 ${ckStats().score}점으로 올랐어요`, 'shield-check');
}

/* ---------------- 화면 초기화 ---------------- */

const INIT = {
  play: (k) => { sim = { s: SCENARIOS[k] || SCENARIOS.family, i: 0, answers: [] }; simStep(); },
  report: () => repRender(),
  checkup: () => {
    if (ckScanned) return ckRender();
    runSteps($('#ckBody'), ['기기 보안 상태 확인', '설치된 앱 권한 점검', '통신사·제조사 방어 기능 확인', '명의 보호 서비스 확인'], () => { ckScanned = true; ckRender(); }, 450);
  },
};

/* ---------------- 부트 ---------------- */

$('#introList').innerHTML = FEATURES.map(f => `<li><button onclick="go('${f.route}')"><span class="num">${f.n}</span>${f.name}${f.ext ? '<span class="ext">확장</span>' : ''}${f.isNew ? '<span class="ext">NEW</span>' : ''}</button></li>`).join('');
const clock = () => { const d = new Date(); $('#sbTime').textContent = `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`; };
clock();
setInterval(clock, 30000);
window.addEventListener('hashchange', render);
render();
