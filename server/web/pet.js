/* 가족 마스코트 코디와 저녁 식탁 퀴즈. guard.js보다 먼저 읽히며 그 안의 함수는 실행할 때 씁니다. */
const CODY_ITEMS = { 2: 'search', 3: 'shield-check', 4: 'crown' };
const CODY_LINES = [
  '사기꾼은 위장하고, 저는 알아봐요!',
  '돈 얘기가 나오면 일단 끊고 다시 걸어요.',
  '두 눈으로 전화도 보고, 가족도 봐요.',
  '체험을 한 번 하면 제가 쑥 자라요!',
  '오늘의 암구호, 기억하고 있죠?',
];

function codyHtml(p, cls = '') {
  const egg = p.stage === 0;
  const item = CODY_ITEMS[p.stage];
  return `<span class="cody mood-${p.mood.key} s${p.stage} ${egg ? 'egg' : ''} ${cls}" aria-hidden="true">
    ${egg ? '<span class="cody-egg"></span>' : '<span class="cody-body"></span>'}
    ${item ? `<span class="cody-item">${ic(item)}</span>` : ''}
  </span>`;
}

const petPercent = (p) => (p.next_xp ? Math.min(100, Math.round((p.xp - p.stage_start) / (p.next_xp - p.stage_start) * 100)) : 100);

function nextScenario(p) {
  if (p.recommend && SCENARIOS[p.recommend]) return p.recommend;
  return Object.keys(SCENARIOS).find((k) => !p.played.includes(k)) || Object.keys(SCENARIOS)[0];
}

function petHomeCard(p) {
  if (!p) return '';
  const alarm = p.mood.key === 'red' || p.mood.key === 'yellow';
  const hint = alarm ? p.mood.text
    : p.trained_today ? `다음 단계까지 ${p.next_xp ? p.next_xp - p.xp : 0}XP 남았어요.` : `오늘 사기 체험을 하면 ${p.rewards.training}XP를 받아요.`;
  return `<button class="pet-home" onclick="go('pet')">
    ${codyHtml(p, 'small')}
    <span class="pet-home-text"><b>${esc(p.name)} · ${esc(p.stage_name)}</b><small>${esc(hint)}</small>
      <span class="pet-bar" style="display:block"><i style="width:${petPercent(p)}%"></i></span></span>
    ${ic('chevron-right')}
  </button>`;
}

const petPage = () => `<div class="page">
  <div class="lead" style="margin-top:6px">우리 가족 코디</div>
  <div class="lead-sub" style="margin-top:6px">가족이 함께 예방 연습을 할수록 코디가 자라요.</div>
  <div id="data"></div>
</div>`;

function petData({ pet: p }) {
  if (!p) return emptyCard('코디를 불러오지 못했어요.');
  const scenario = nextScenario(p);
  const title = SCENARIOS[scenario]?.title || '사기 체험';
  const fresh = !p.played.includes(scenario);
  const reward = (p.trained_today ? 0 : p.rewards.training) + (fresh ? p.rewards.new_scenario : 0);
  const doneQuiz = p.quiz_answered >= p.quiz_size;
  return `<div class="pet-scene mood-${p.mood.key}">
      <div class="pet-say" id="petSay">${esc(p.mood.text)}</div>
      <button class="cody-tap" style="border:0;background:none;padding:0" onclick="pokeCody(this)" aria-label="코디 쓰다듬기">${codyHtml(p).replace('class="cody', 'style="--size:170px" class="cody')}</button>
      <div class="pet-name">${esc(p.name)} · ${esc(p.stage_name)}</div>
      <div class="pet-stage-text">${esc(p.stage_text)}</div>
      <div class="pet-progress"><div class="row-between"><span>${p.xp} XP</span><span>${p.next_xp ? `${esc(p.next_name)}까지 ${p.next_xp - p.xp} XP` : '최고 단계예요'}</span></div>
        <div class="pet-bar"><i style="width:${petPercent(p)}%"></i></div></div>
    </div>
    ${p.mood.key === 'red' ? `<button class="mission" onclick="go('family')"><span>${ic('phone-call')}</span><span class="mission-text"><b>가족에게 직접 연락하기</b><small>확인을 마치면 코디가 파랗게 돌아와요.</small></span>${ic('chevron-right')}</button>` : ''}
    <div class="sec-title">오늘 코디 키우기</div>
    <button class="mission ${reward ? '' : 'done'}" onclick="go('play/${esc(scenario)}')">
      <span>${ic('gamepad-2')}</span>
      <span class="mission-text"><b>${p.recommend ? '틀린 수법 다시 체험하기' : '사기 체험 한 판'}</b><small>${esc(title)}</small></span>
      <span class="xp">${reward ? `+${reward} XP` : '오늘 완료'}</span>
    </button>
    <button class="mission ${doneQuiz ? 'done' : ''}" onclick="go('quiz')">
      <span>${ic('utensils')}</span>
      <span class="mission-text"><b>저녁 식탁 퀴즈</b><small>${doneQuiz ? '가족 결과를 확인해 보세요.' : `이번 주 카드 ${p.quiz_size - p.quiz_answered}장이 남았어요.`}</small></span>
      <span class="xp">${doneQuiz ? '결과 보기' : '최대 +55 XP'}</span>
    </button>
    <div class="sec-title">성장 단계</div>
    <div class="stage-strip">${p.stages.map((s, i) => `<div class="${i <= p.stage ? 'on' : ''}"><i></i>${esc(s.name)}</div>`).join('')}</div>
    <div class="call-text" style="margin:12px 2px 0;font-size:12.5px;color:var(--sub)">코디 색은 의심 알림 여부만 나타내요. 통화 내용이나 사기 유형은 가족에게 보이지 않아요. 빨간색은 사기 확정이 아니라 확인이 필요하다는 뜻이에요.</div>`;
}

function pokeCody(btn) {
  const cody = btn.querySelector('.cody');
  cody.classList.remove('wiggle');
  void cody.offsetWidth;
  cody.classList.add('wiggle');
  const say = document.getElementById('petSay');
  if (say) say.textContent = CODY_LINES[Math.floor(Math.random() * CODY_LINES.length)];
}

function showPetReward(p) {
  if (!p) return;
  const host = document.querySelector('#view .page') || view;
  const text = p.grew ? `코디가 ${p.stage_name}(으)로 자랐어요!`
    : p.gained ? `코디가 ${p.gained} XP를 받았어요!` : '오늘 경험치는 이미 받았어요. 연습은 언제나 좋아요!';
  host.insertAdjacentHTML('beforeend', `<button class="mission" onclick="go('pet')"><span>${ic('sparkles')}</span>
    <span class="mission-text"><b>${esc(text)}</b><small>코디 보러 가기</small></span>${ic('chevron-right')}</button>`);
  icons();
}

/* ---------------- 저녁 식탁 퀴즈 ---------------- */
let quizState = null;

const quizPage = () => `<div class="page">
  <div class="lead" style="margin-top:6px">저녁 식탁 퀴즈</div>
  <div class="lead-sub" style="margin-top:6px">이 문자, 진짜일까요? 가족과 함께 맞혀 보세요. 모두 가상의 메시지예요.</div>
  <div id="quizHost"></div>
</div>`;

async function loadQuiz() {
  try {
    quizState = await api('GET', '/v1/quiz');
    drawQuiz();
  } catch (e) {
    const host = $('#quizHost');
    if (host) host.innerHTML = emptyCard('퀴즈를 불러오지 못했어요.');
  }
}

function markClue(card) {
  const text = esc(card.text);
  if (!card.answered) return text;
  const clue = esc(card.clue);
  return text.split(clue).join(`<mark class="${card.is_scam ? '' : 'calm'}">${clue}</mark>`);
}

function quizCardHtml(card, index, total) {
  return `<div class="quiz-progress">${index + 1} / ${total}</div>
    <div class="quiz-msg">
      <div class="quiz-sender">${ic('message-square')}${esc(card.sender)}</div>
      <div class="quiz-text">${markClue(card)}</div>
    </div>`;
}

function drawQuiz(lastCard) {
  const host = $('#quizHost');
  if (!host || !quizState) return;
  const { cards } = quizState;
  if (lastCard) {
    const index = cards.findIndex((c) => c.id === lastCard.id);
    const more = cards.some((c) => !c.answered);
    host.innerHTML = `${quizCardHtml(lastCard, index, cards.length)}
      <div class="quiz-result">
        <h3 class="${lastCard.correct ? 'right' : 'wrong'}">${lastCard.correct ? '정답이에요!' : '아쉬워요!'} 이건 ${lastCard.is_scam ? '사기' : '정상 메시지'}예요</h3>
        <p>${esc(lastCard.why)}</p>
        ${lastCard.gained ? `<p style="color:var(--pri);font-weight:800">코디 +${lastCard.gained} XP</p>` : ''}
      </div>
      ${lastCard.is_scam && SCENARIOS[lastCard.scenario] ? `<button class="mission" onclick="go('play/${esc(lastCard.scenario)}')"><span>${ic('gamepad-2')}</span><span class="mission-text"><b>이 수법 직접 겪어 보기</b><small>${esc(SCENARIOS[lastCard.scenario].title)}</small></span>${ic('chevron-right')}</button>` : ''}
      <button class="btn pri block mt" onclick="drawQuiz()">${more ? '다음 카드' : '결과 보기'}</button>`;
    icons();
    return;
  }
  const index = cards.findIndex((c) => !c.answered);
  if (index >= 0) {
    host.innerHTML = `${quizCardHtml(cards[index], index, cards.length)}
      <div class="quiz-choice">
        <button onclick="answerQuiz('${esc(cards[index].id)}', false)">진짜</button>
        <button onclick="answerQuiz('${esc(cards[index].id)}', true)">사기</button>
      </div>`;
    icons();
    return;
  }
  drawQuizResult();
}

async function answerQuiz(id, isScam) {
  document.querySelectorAll('.quiz-choice button').forEach((b) => { b.disabled = true; });
  try {
    const result = await api('POST', `/v1/quiz/${id}/answer`, { is_scam: isScam });
    const card = quizState.cards.find((c) => c.id === id);
    Object.assign(card, result);
    if (result.finished) {
      const fresh = await api('GET', '/v1/quiz');
      quizState = fresh;
    }
    drawQuiz(result);
  } catch (e) {
    toast('답을 보내지 못했어요', 'circle-alert');
    drawQuiz();
  }
}

function drawQuizResult() {
  const q = quizState;
  const mine = q.members.find((m) => m.me);
  const waiting = q.members.filter((m) => !m.done).map((m) => m.name);
  const alone = q.members.length === 1;
  $('#quizHost').innerHTML = `<div class="quiz-result" style="text-align:center">
      <h3>${mine.score} / ${q.cards.length}장 맞혔어요</h3>
      <p>${alone ? '가족을 연결하면 함께 풀 수 있어요.' : q.reveal ? '가족 결과가 나왔어요.' : `${esc(waiting.join(', '))}님이 풀면 함께 공개돼요. 늦어도 일요일 밤 9시에 공개해요.`}</p>
    </div>
    ${alone ? '' : `<div class="card mt">${q.members.map((m) => `<div class="family-score"><span>${esc(m.name)}${m.me ? ' (나)' : ''}</span><small>${m.score !== null ? `${m.score}장 정답` : m.done ? '풀었어요' : '아직이에요'}</small></div>`).join('')}</div>`}
    ${q.dishes ? `<div class="dishes">이번 주 설거지 당번<b>${esc(q.dishes)}</b></div>` : ''}
    <div class="talk-card">${ic('utensils')} 오늘 저녁 이야기해 봐요. "우리 집이라면 이런 메시지가 왔을 때 누구에게, 어떻게 확인할까?"</div>
    <button class="btn pri block mt" onclick="go('pet')">코디 보러 가기</button>
    <button class="btn block mt" onclick="go('sim')">사기 체험 더 하기</button>`;
  icons();
}
