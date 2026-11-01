// 통화 검사 결과 카드에 AI 의심 점수 구간·근거 사례·후속 조치·같은 수법 훈련 링크를 덧붙입니다.
// 서버의 GUARD_RAG_FIRST=1(rag_first.py)일 때만 값이 오고, 꺼져 있으면 아무것도 그리지 않습니다.
// guard.js는 고치지 않고 화면이 바뀔 때마다 카드를 찾아 붙입니다. 서버 값은 textContent로만 넣습니다.
(() => {
  const BAND_STYLE = { log: 'safe', caution: 'warn', alert: 'danger', lock: 'danger', unclear: '' };
  const FOLLOW_UPS = [
    { title: '112·1394 신고(지급정지)', note: '돈을 보냈다면 바로 전화해 지급정지를 요청하세요.', links: [['112 전화', 'tel:112'], ['1394 전화', 'tel:1394']] },
    { title: '어카운트인포', note: '내 이름으로 된 계좌를 한눈에 확인합니다.', links: [['열기', 'https://www.payinfo.or.kr']] },
    { title: '개인정보노출자 사고예방시스템', note: '신분증·개인정보가 새어 나갔다면 등록해 금융거래를 막습니다.', links: [['열기', 'https://pd.fss.or.kr']] },
    { title: '엠세이퍼(명의도용 휴대폰 확인)', note: '내 이름으로 개통된 휴대폰을 확인합니다. PASS 앱 경로는 11-20까지 일부 중단되어 홈페이지로 연결합니다.', links: [['열기', 'https://www.msafer.or.kr']] },
    { title: '여신거래·비대면계좌 안심차단', note: '은행 앱에서 대출과 비대면 계좌 개설을 미리 막는 방법(금융위원회 안내).', links: [['안내 보기', 'https://www.fsc.go.kr/no010101/84607']] },
  ];
  const CAUTION_CHECKS = [
    '상대가 말한 기관·회사의 대표번호로 직접 다시 걸어 확인하기',
    '돈 이체, 인증번호, 앱 설치, 비밀 유지 요구는 따르지 않기',
    '혼자 정하지 말고 가족에게 물어보기',
  ];
  const cache = {};
  const missedAt = {}; // 아직 값이 없던 id(분석 중 등)는 3초 뒤에 다시 묻습니다.
  let pending = null;
  let sampleId = '';

  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };
  const safeUrl = (u) => (/^(https:\/\/|tel:)/.test(u || '') ? u : '');

  function link(label, href, cls = 'dx-btn') {
    const a = el('a', cls, label);
    a.href = href;
    if (href.startsWith('https://')) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
    return a;
  }

  function scoreBlock(x) {
    const box = el('div', 'dx-score');
    const top = el('div', 'dx-row');
    top.append(el('span', '', 'AI 의심 점수(보정 전)'));
    const chip = el('span', `chip ${BAND_STYLE[x.band] || ''}`, x.score == null ? x.band_name : `${x.score}점 · ${x.band_name}`);
    top.append(chip);
    box.append(top);
    if (x.score != null) {
      const track = el('div', 'dx-track');
      const fill = el('span', `dx-fill ${x.band}`);
      fill.style.width = `${Math.max(0, Math.min(100, x.score))}%`;
      track.append(fill);
      box.append(track);
    }
    box.append(el('div', 'dx-note', x.band === 'unclear'
      ? '녹취에서 근거가 되는 말을 확인하지 못해 자동 알림·잠금을 하지 않았습니다. 판정을 확인해 주세요.'
      : '수법별로 AI가 매긴 의심 정도 중 가장 큰 값입니다. 실제 사기일 확률이 아닙니다. 0–39 기록 · 40–69 주의 · 70–89 위험 · 90 이상 매우 위험'));
    return box;
  }

  function bandBlock(x) {
    const box = el('div', 'dx-band');
    if (x.band === 'caution' || x.band === 'unclear') {
      box.append(el('b', '', '본인 확인 목록'));
      const ul = el('ul', 'dx-list');
      CAUTION_CHECKS.forEach((t) => ul.append(el('li', '', t)));
      box.append(ul);
      box.append(link('가족에게 물어보기', '#/family'));
    }
    if (x.band === 'alert' || x.band === 'lock') {
      box.append(el('b', '', x.sample ? '예시 통화라 가족 알림·잠금은 하지 않았습니다' : x.family_alert ? '가족에게 알림을 보냈습니다' : '가족 알림은 보내지 않았습니다(판정 확인 필요)'));
      if (x.lock) box.append(el('div', 'dx-note', '금융앱을 잠갔습니다. 가족은 바로 풀 수 있고, 본인은 10분 기다린 뒤 풀 수 있으며, 1시간 뒤 저절로 풀립니다.'));
      const row = el('div', 'dx-links');
      [['112 경찰', 'tel:112'], ['1394 지급정지', 'tel:1394'], ['1332 금융감독원', 'tel:1332']].forEach(([t, h]) => row.append(link(t, h)));
      box.append(row);
    }
    return box.childNodes.length ? box : null;
  }

  function referencesBlock(x) {
    if (!x.references || !x.references.length) return null;
    const box = el('div', 'dx-refs');
    box.append(el('b', '', x.reference_source === 'es' ? '근거 사례(사례 검색)' : '근거 사례(기본 수법 설명)'));
    const ul = el('ul', 'dx-list');
    x.references.forEach((r) => {
      const li = el('li');
      li.append(el('span', '', [r.title, r.scam_type, r.source].filter(Boolean).join(' · ')));
      const href = safeUrl(r.url);
      if (href) { li.append(document.createTextNode(' ')); li.append(link('출처', href, 'dx-src')); }
      ul.append(li);
    });
    box.append(ul);
    box.append(el('div', 'dx-note', '판정에 참고한 자료입니다. 이 통화가 그 사례와 같다는 뜻은 아닙니다.'));
    return box;
  }

  function followUpBlock() {
    const box = el('details', 'dx-follow');
    box.append(el('summary', '', '후속 조치 5가지'));
    FOLLOW_UPS.forEach((f) => {
      const item = el('div', 'dx-follow-item');
      item.append(el('b', '', f.title));
      item.append(el('div', 'dx-note', f.note));
      const row = el('div', 'dx-links');
      f.links.forEach(([t, h]) => row.append(link(t, h)));
      item.append(row);
      box.append(item);
    });
    return box;
  }

  function build(x) {
    const root = el('div', 'dx');
    root.append(scoreBlock(x));
    [bandBlock(x), referencesBlock(x)].forEach((b) => b && root.append(b));
    if (x.band !== 'log') root.append(followUpBlock());
    if (x.training_url) {
      const train = el('button', 'btn ghost sm block dx-train', '같은 수법 훈련하기');
      train.type = 'button';
      train.addEventListener('click', () => { location.href = x.training_url; });
      root.append(train);
    }
    return root;
  }

  function attach(card, x) {
    if (!x || card.querySelector(':scope > .dx')) return;
    const before = card.querySelector(':scope > .link-row, :scope > .sample-expected');
    card.insertBefore(build(x), before || null);
  }

  function cardId(card) {
    const b = card.querySelector('button[onclick^="deleteSheet(\'"]');
    const m = b && /deleteSheet\('([0-9a-f]+)'\)/.exec(b.getAttribute('onclick'));
    return m ? m[1] : '';
  }

  async function decorate() {
    pending = null;
    const cards = [...document.querySelectorAll('#view .card')].map((c) => [c, cardId(c)]).filter(([, id]) => id);
    const now = Date.now();
    const missing = cards.map(([, id]) => id).filter((id) => !(id in cache) && !(now - (missedAt[id] || 0) < 3000));
    if (missing.length && typeof api === 'function') {
      try {
        const res = await api('GET', `/v1/detect/extra?ids=${missing.join(',')}`);
        if (!res.enabled) return;
        Object.assign(cache, res.items);
        missing.forEach((id) => { if (!(id in cache)) missedAt[id] = now; });
      } catch (e) { return; }
    }
    cards.forEach(([c, id]) => attach(c, cache[id]));
    decorateSample();
  }

  async function decorateSample() {
    const host = document.querySelector('#sampleResult .sample-result');
    if (!host || !sampleId || host.querySelector('.dx')) return;
    const key = 'sample:' + sampleId;
    if (!(key in cache)) {
      try { cache[key] = (await api('POST', `/v1/samples/${encodeURIComponent(sampleId)}/analyze?record=0`)).detect || null; } catch (e) { return; }
    }
    attach(host, cache[key]);
  }

  // 예시 통화 창은 어떤 예시인지 화면에 남지 않으므로 여는 순간의 id를 기억합니다.
  if (typeof window.openSample === 'function') {
    const open = window.openSample;
    window.openSample = function (id) { sampleId = id; return open.apply(this, arguments); };
  }

  const schedule = () => { if (!pending) pending = setTimeout(decorate, 120); };
  new MutationObserver(schedule).observe(document.body, { childList: true, subtree: true });

  const css = el('style');
  css.textContent = `
.dx { margin-top: 12px; display: grid; gap: 10px; }
.dx-score, .dx-band, .dx-refs { padding: 12px 14px; border-radius: 14px; background: var(--bg, #F3F5FA); }
.dx-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 13.5px; font-weight: 700; }
.dx-track { height: 8px; border-radius: 4px; background: #E6EAF2; margin-top: 8px; overflow: hidden; }
.dx-fill { display: block; height: 100%; background: var(--safe, #12B76A); }
.dx-fill.caution { background: var(--warn, #F79009); }
.dx-fill.alert, .dx-fill.lock { background: var(--danger, #F04438); }
.dx-note { font-size: 12px; color: var(--sub, #64748B); margin-top: 6px; line-height: 1.45; }
.dx b { display: block; font-size: 14px; }
.dx-list { margin: 6px 0 0; padding-left: 18px; font-size: 13px; line-height: 1.55; }
.dx-links { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.dx-btn { display: inline-flex; align-items: center; height: 34px; padding: 0 12px; border-radius: 10px; background: var(--pri-soft, #EBF0FF); color: var(--pri, #2F5BFF); font-size: 13px; font-weight: 700; text-decoration: none; margin-top: 8px; }
.dx-links .dx-btn { margin-top: 0; }
.dx-src { font-size: 12px; color: var(--pri, #2F5BFF); }
.dx-follow { padding: 10px 14px; border-radius: 14px; border: 1.5px solid var(--line, #E6EAF2); }
.dx-follow summary { font-size: 14px; font-weight: 800; cursor: pointer; }
.dx-follow-item { margin-top: 10px; }
.dx-train { margin-top: 2px; }`;
  document.head.append(css);
  schedule();
})();
