// 홈의 사기 동향. 공식 발표나 보도에서 확인한 내용만 출처, 날짜와 함께 적습니다. 새 경보가 나오면 직접 갱신합니다.
const TRENDS_CHECKED = '2026-10-31';
const FSS_ALERTS = 'https://www.fss.or.kr/fss/bbs/B0000175/list.do?menuNo=200204';

const TREND_STAT = {
  value: '78.6%',
  text: '2025년 보이스피싱 피해액 중 기관 사칭형 비중',
  detail: '전체 1조 2,578억 원 중 9,884억 원',
  source: '국회 제출 자료, 매일신문 2026-09-23',
  url: 'https://www.imaeil.com/page/view/2026092313520671312',
};

const TREND_ALERTS = [
  { date: '10.22', title: '가상자산거래소를 사칭한 "가짜 체인"', source: '금융감독원 소비자경보 2026-27호', url: FSS_ALERTS },
  { date: '10.06', title: '유출된 개인정보를 쓴 맞춤형 대출 빙자 사기', source: '금융위원회 보도자료', url: 'https://fsc.go.kr/no010101/87882' },
  { date: '09.22', title: '연휴를 앞두고 주의할 "가짜 투자"', source: '금융감독원 소비자경보 2026-25호', url: FSS_ALERTS },
  { date: '08.10', title: '"상품권을 사면 대출이 된다"는 권유', source: '금융감독원 소비자경보 2026-24호', url: FSS_ALERTS },
];

function trendsBlock() {
  const link = (url, inner, cls) => `<a class="${cls}" href="${url}" target="_blank" rel="noopener noreferrer">${inner}</a>`;
  return `<div class="sec-title">지금 주의할 사기</div>
    ${link(TREND_STAT.url, `<b>${TREND_STAT.value}</b><span><strong>${TREND_STAT.text}</strong><small>${TREND_STAT.detail}</small><small>${TREND_STAT.source}</small></span>`, 'trend-stat')}
    <div class="card trend-list">
      ${TREND_ALERTS.map((t) => link(t.url, `<time>${t.date}</time><span><strong>${t.title}</strong><small>${t.source}</small></span>${ic('external-link')}`, 'trend-row')).join('')}
    </div>
    <div class="trend-note">공식 경보를 최신순으로 모았으며, 피해 순위가 아닙니다. ${TRENDS_CHECKED} 확인</div>`;
}
