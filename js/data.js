// CodySafe MVP 목업 데이터 — 실제 서비스에서는 API/DB 로 대체

const FEATURES = [
  { n: 1, name: 'AI 이미지 진위 분석', route: 'image', icon: 'image' },
  { n: 2, name: 'AI 음성 탐지', route: 'voice', icon: 'audio-lines' },
  { n: 3, name: '실시간 통화 사기 탐지', route: 'call', icon: 'phone-call' },
  { n: 4, name: 'AI 사기 시뮬레이션', route: 'sim', icon: 'gamepad-2' },
  { n: 5, name: '국민 참여형 사기 제보', route: 'report', icon: 'megaphone' },
  { n: 6, name: '개인별 취약점 분석', route: 'weakness', icon: 'radar' },
  { n: 7, name: '개인 맞춤형 사기 훈련', route: 'training', icon: 'target' },
  { n: 8, name: 'AI 사기 대응 코파일럿', route: 'copilot', icon: 'bot' },
  { n: 9, name: '가족 보호 네트워크', route: 'family', icon: 'users', ext: true },
  { n: 10, name: '스미싱·피싱 URL 탐지', route: 'url', icon: 'link' },
  { n: 11, name: '기관 사칭 사실 검증', route: 'verify', icon: 'landmark' },
  { n: 12, name: '신종 사기 시나리오 자동 생성', route: 'generate', icon: 'wand-sparkles' },
  { n: 13, name: '방어 설정 점검', route: 'checkup', icon: 'shield-plus', isNew: true },
];

// 공인 도메인 DB (실서비스: 행안부 공공기관 도메인 + 금융위 등록 금융사 + 화이트리스트 RDB)
const OFFICIAL_DOMAINS = [
  { d: 'gov.kr', n: '정부24', type: 'gov' },
  { d: 'police.go.kr', n: '경찰청', type: 'gov' },
  { d: 'spo.go.kr', n: '대검찰청', type: 'gov' },
  { d: 'hometax.go.kr', n: '국세청 홈택스', type: 'gov' },
  { d: 'nts.go.kr', n: '국세청', type: 'gov' },
  { d: 'epost.go.kr', n: '우정사업본부(우체국)', type: 'gov' },
  { d: 'scourt.go.kr', n: '대법원', type: 'gov' },
  { d: 'fss.or.kr', n: '금융감독원', type: 'public' },
  { d: 'kisa.or.kr', n: '한국인터넷진흥원', type: 'public' },
  { d: 'nhis.or.kr', n: '국민건강보험공단', type: 'public' },
  { d: 'kbstar.com', n: 'KB국민은행', type: 'fin' },
  { d: 'shinhan.com', n: '신한은행', type: 'fin' },
  { d: 'wooribank.com', n: '우리은행', type: 'fin' },
  { d: 'kebhana.com', n: '하나은행', type: 'fin' },
  { d: 'nonghyup.com', n: 'NH농협', type: 'fin' },
  { d: 'toss.im', n: '토스', type: 'fin' },
  { d: 'cjlogistics.com', n: 'CJ대한통운', type: 'biz' },
  { d: 'coupang.com', n: '쿠팡', type: 'biz' },
  { d: 'naver.com', n: '네이버', type: 'biz' },
  { d: 'kakao.com', n: '카카오', type: 'biz' },
];

const URL_SAMPLES = [
  { label: '📦 택배 스미싱', text: '[CJ대한통운] 고객님 택배가 주소불명으로 보관중입니다. 주소 확인 바랍니다 http://cjlogistlcs.com/track?id=88213' },
  { label: '🏦 은행 사칭', text: '[국민은행] 고객님 계좌가 이상거래로 일시정지 되었습니다. 본인인증: https://kbsfar.com/login' },
  { label: '🏛️ 정부 사칭', text: '[정부24] 민생회복 지원금 대상자입니다. 신청 마감 임박 https://g0v-kr.site/apply' },
  { label: '🔗 단축 URL', text: '[국세청] 미납 과태료 확인 바랍니다 bit.ly/3xYk2Qa' },
  { label: '✅ 정부24 정상', text: 'https://www.gov.kr/portal/main' },
];

const SCENARIOS = {
  family: {
    title: '"엄마, 나 폰 깨졌어"', tag: '가족 사칭', icon: 'users', color: '#F79009', soft: '#FFF4E5',
    difficulty: '쉬움', mins: 3, desc: '자녀를 사칭해 새 번호로 연락, 상품권·송금을 요구하는 메신저 피싱',
    contact: { name: '딸 💕', sub: '새 번호 010-5821-****', av: '딸' },
    steps: [
      { msgs: ['엄마 나 폰 액정 깨져서 수리 맡겼어ㅠㅠ', '이거 임시로 쓰는 번호야 저장해줘!'],
        choices: [
          { t: '어머 괜찮아? 번호 저장해둘게~', ok: false, fb: '처음 보는 번호로 온 가족 연락은 일단 의심! 기존 번호로 전화해 확인하는 습관이 필요해요.' },
          { t: '원래 번호로 전화해 볼게', ok: true, fb: '정답! 기존 번호로 직접 통화해 확인하는 것이 가장 확실한 방법입니다.' },
        ] },
      { msgs: ['아 그 폰 수리점에 있다니까ㅠ 지금 통화 안돼', '급한 일이 있는데 엄마 폰으로 본인인증 좀 해줄 수 있어?'],
        choices: [
          { t: '통화가 안 되면 아무것도 못 해줘', ok: true, fb: '훌륭해요. "통화 회피"는 가족 사칭의 대표적 위험 신호입니다.' },
          { t: '뭐 해주면 되는데?', ok: false, fb: '본인인증을 대신 해주면 내 명의로 대출·계좌 개설이 될 수 있어요.' },
        ] },
      { msgs: ['문화상품권 50만원만 먼저 사서 핀번호 보내줘', '이 링크로 원격앱 깔면 내가 알아서 할게!', 'https://bit.ly/fix-app'],
        choices: [
          { t: '링크 눌러서 앱 설치하기', ok: false, fb: '원격제어 앱을 설치하면 금융앱·인증서가 통째로 탈취됩니다. 절대 금지!' },
          { t: '대화 중단하고 112·가족에게 알리기', ok: true, fb: '완벽해요! 상품권 핀번호·원격앱 요구 = 100% 사기입니다.' },
        ] },
    ],
    signals: ['새 번호로 연락', '통화 회피', '본인인증 대행 요구', '상품권·원격앱 요구'],
  },
  romance: {
    title: '해외 군의관의 고백', tag: '로맨스 스캠', icon: 'heart', color: '#E5487A', soft: '#FDECF2',
    difficulty: '보통', mins: 4, desc: 'AI 생성 프로필 사진으로 신뢰를 쌓은 뒤 통관비·투자를 요구',
    contact: { name: 'Daniel 🇺🇸', sub: 'Instagram DM', av: 'D' },
    steps: [
      { msgs: ['Hi~ 사진 보고 반해서 연락했어요 😊', '저는 시리아 파병 중인 미군 군의관 다니엘이에요'],
        choices: [
          { t: '프로필 사진을 이미지 진위 분석으로 확인한다', ok: true, fb: '좋아요! 로맨스 스캠 프로필의 상당수가 AI 생성·도용 사진입니다.' },
          { t: '와 군의관이시구나! 반가워요', ok: false, fb: 'SNS로 먼저 접근하는 해외 군인·의사·사업가는 대표적인 로맨스 스캠 페르소나예요.' },
        ] },
      { msgs: ['우리 벌써 2주째네요… 당신이 제 인생의 전부예요 ❤️', '곧 전역해서 한국 가려는데 짐에 금괴가 있어요', '통관비 300만원만 먼저 내주면 한국 가서 바로 갚을게요'],
        choices: [
          { t: '사랑하니까… 이번만 보내줄게요', ok: false, fb: '만난 적 없는 사람의 금전 요구는 무조건 사기입니다. 감정을 이용한 전형적 수법이에요.' },
          { t: '영상통화 먼저 하자고 요구한다', ok: true, fb: '좋은 대응! 다만 딥페이크 영상통화도 있으니 돈 요구 자체를 거절해야 해요.' },
        ] },
      { msgs: ['카메라가 고장나서 영상통화는 어려워요 😢', '대신 통관 담당자 연락처 줄게요. 오늘까지 안 내면 금괴 몰수래요!!'],
        choices: [
          { t: '대화를 끊고 신고한다', ok: true, fb: '정답! "오늘까지", "몰수" 같은 시간 압박은 판단력을 흐리려는 장치입니다.' },
          { t: '통관 담당자에게 연락해 본다', ok: false, fb: '"통관 담당자"도 같은 조직의 공범입니다. 추가 금전 요구로 이어져요.' },
        ] },
    ],
    signals: ['SNS 먼저 접근', '해외 파병·전문직 페르소나', '급격한 애정 표현', '영상통화 회피', '통관비 요구'],
  },
  market: {
    title: '중고 아이폰 안전결제', tag: '중고거래', icon: 'package', color: '#12B76A', soft: '#E7F8EF',
    difficulty: '보통', mins: 3, desc: '가짜 안전결제 링크로 외부 결제를 유도하는 직거래 사기',
    contact: { name: '판매자 쿨거래123', sub: '중고마켓 채팅', av: '판' },
    steps: [
      { msgs: ['아이폰 17 미개봉 75만원 맞아요~', '제가 지방이라 택배거래만 가능해요'],
        choices: [
          { t: '판매자 계좌번호를 사기 조회 사이트에 검색한다', ok: true, fb: '좋아요! 경찰청 사기 계좌 조회로 신고 이력을 먼저 확인하세요.' },
          { t: '시세보다 싸네요! 바로 살게요', ok: false, fb: '시세보다 지나치게 싼 매물은 미끼일 가능성이 높아요.' },
        ] },
      { msgs: ['안전하게 네이버페이 안전결제로 해요!', '이 링크에서 결제해주세요 👇', 'https://naverpay-safe.shop/pay/8812'],
        choices: [
          { t: '링크 주소가 공식 도메인인지 확인한다', ok: true, fb: '정답! naverpay-safe.shop 은 공식 도메인이 아닙니다. 공식 안전결제는 앱 안에서만 진행돼요.' },
          { t: '안전결제니까 바로 결제한다', ok: false, fb: '가짜 결제 페이지에 입금하면 돈은 사기범 계좌로 갑니다.' },
        ] },
      { msgs: ['아 결제 오류 났네요ㅠ 수수료 포함해서 다시 입금해주셔야 환불돼요'],
        choices: [
          { t: '수수료 포함해 다시 입금', ok: false, fb: '"오류-재입금-환불" 수법은 피해액을 두 배로 키우는 2차 사기입니다.' },
          { t: '거래를 중단하고 플랫폼에 신고', ok: true, fb: '완벽합니다! 플랫폼 밖 결제 유도 = 거래 중단이 원칙이에요.' },
        ] },
    ],
    signals: ['시세보다 저렴', '택배거래만 고집', '외부 결제 링크', '재입금 요구'],
  },
  agency: {
    title: '서울중앙지검 수사관입니다', tag: '기관 사칭', icon: 'landmark', color: '#2F5BFF', soft: '#EBF0FF',
    difficulty: '어려움', mins: 4, desc: '검찰·금감원을 사칭해 "안전계좌" 이체를 유도하는 보이스피싱',
    contact: { name: '02-3480-****', sub: '발신자 표시: 서울중앙지검(?)', av: '검' },
    steps: [
      { msgs: ['서울중앙지검 첨단범죄수사1팀 김민수 수사관입니다.', '고객님 명의 계좌가 대포통장 사건에 연루되어 연락드렸습니다.'],
        choices: [
          { t: '"제가요? 어떻게 해야 하죠?"', ok: false, fb: '수사기관은 전화로 사건 연루를 통보하며 조치를 요구하지 않아요.' },
          { t: '전화를 끊고 대검찰청 대표번호(1301)로 직접 확인', ok: true, fb: '최고의 대응! 공식 번호로 직접 걸어 확인하는 것이 핵심입니다.' },
        ] },
      { msgs: ['지금 끊으시면 공무집행방해로 구속영장이 발부됩니다.', '사건 공문 보내드릴게요. 보안상 가족에게도 말하시면 안 됩니다.', '[공문] 서울중앙지방검찰청_사건번호_2026-1182.pdf'],
        choices: [
          { t: '공문을 기관 사칭 검증 기능으로 확인', ok: true, fb: '좋아요! 검찰은 메신저로 공문을 보내지 않고, "비밀 유지" 요구도 하지 않습니다.' },
          { t: '구속은 무서우니 시키는 대로 한다', ok: false, fb: '공포·고립 유도는 판단을 마비시키는 핵심 수법이에요.' },
        ] },
      { msgs: ['자산 보호를 위해 금감원 안전계좌로 잠시 이체하시면 됩니다.', '확인 후 바로 돌려드립니다.'],
        choices: [
          { t: '안전계좌로 이체한다', ok: false, fb: '"안전계좌"는 존재하지 않습니다. 어떤 기관도 이체를 요구하지 않아요.' },
          { t: '거절하고 112에 신고한다', ok: true, fb: '완벽합니다! 정부기관은 절대 돈을 보내라고 하지 않습니다.' },
        ] },
    ],
    signals: ['수사기관 사칭', '구속·처벌 위협', '비밀 유지 요구', '메신저 공문', '안전계좌 이체'],
  },
  invest: {
    title: 'AI 주식 리딩방 VIP', tag: '투자 리딩방', icon: 'trending-up', color: '#7B4DFF', soft: '#F1EDFF',
    difficulty: '어려움', mins: 4, desc: '유명인 딥페이크 광고로 유인 후 가짜 거래소 입금을 유도',
    contact: { name: '[VIP] 수익인증방 📈', sub: '참여자 312명', av: 'V' },
    steps: [
      { msgs: ['🎉 신규 회원님 환영합니다!', '오늘도 AI 종목 추천 +38% 수익 인증 올라왔습니다 🚀', '[수익인증 캡처.jpg]'],
        choices: [
          { t: '수익 인증이 많으니 믿을 만하다', ok: false, fb: '참여자 대부분이 바람잡이일 수 있어요. 캡처는 쉽게 조작됩니다.' },
          { t: '금감원 제도권 금융회사 조회로 업체 확인', ok: true, fb: '정답! 미등록 투자자문업체는 그 자체로 불법입니다.' },
        ] },
      { msgs: ['VIP방은 전용 거래소 앱에서만 매매합니다', '원금 보장 + 월 30% 수익 확정!'],
        choices: [
          { t: '"원금 보장·확정 수익"은 불법 광고라 의심한다', ok: true, fb: '훌륭해요! 원금 보장·확정 수익 약속은 자본시장법 위반입니다.' },
          { t: '전용 거래소 앱을 설치한다', ok: false, fb: '가짜 거래소는 화면상 수익만 보여주고 출금을 막아요.' },
        ] },
    ],
    signals: ['수익 인증 캡처', '원금 보장·확정 수익', '전용 거래소 앱', '바람잡이 다수'],
  },
  wedding: {
    title: '모바일 청첩장 도착 💌', tag: '신종 · 자동생성', icon: 'mail', color: '#0EA5E9', soft: '#E0F4FE',
    difficulty: '보통', mins: 2, desc: '국민 제보로 자동 생성된 신종 시나리오 — 지인 사칭 청첩장 링크로 악성앱 설치 유도', generated: true,
    contact: { name: '010-3392-****', sub: '저장되지 않은 번호', av: '?' },
    steps: [
      { msgs: ['저희 결혼합니다 💍 바쁘시더라도 꼭 와주세요!', '모바일 청첩장 👉 http://wedding-card.kr-invite.top/m/3392'],
        choices: [
          { t: '누군지 궁금하니 링크를 열어본다', ok: false, fb: '청첩장·부고장 링크는 악성 앱(.apk) 설치로 이어지는 대표적 스미싱이에요.' },
          { t: 'URL 탐지 기능으로 링크를 먼저 검사한다', ok: true, fb: '정답! kr-invite.top 은 생성 3일 된 해외 도메인이었습니다.' },
        ] },
      { msgs: ['앗 저 OO이에요~ 번호 바꿨어요ㅎㅎ', '청첩장 앱 설치해야 보이니 꼭 확인해줘!'],
        choices: [
          { t: '지인에게 기존 연락처로 직접 확인한다', ok: true, fb: '완벽해요! 앱 설치를 요구하는 청첩장은 100% 악성입니다.' },
          { t: '아는 사람이니 앱을 설치한다', ok: false, fb: '설치 즉시 연락처·문자·인증서가 탈취되고 지인에게 2차 전파돼요.' },
        ] },
    ],
    signals: ['모르는 번호', '청첩장·부고 링크', '앱 설치 요구', '.top 등 해외 도메인'],
  },
};

const REPORTS = [
  { id: 1, cat: '스미싱', title: '모바일 청첩장 링크 누르니 앱 설치 화면이 떴어요', body: '모르는 번호로 "저희 결혼합니다" 문자가 와서 눌렀는데 .apk 설치를 요구했습니다. 지인들한테도 같은 문자가 갔대요.', region: '서울 마포구', ago: '12분 전', likes: 152, status: 'verified', generated: 'wedding', liked: false },
  { id: 2, cat: '보이스피싱', title: '금감원 직원이라며 "보호 계좌"로 옮기라고 함', body: '처음엔 은행 대출 상담인 척하다가 기존 대출이 불법이라며 금감원 직원을 연결해 줬습니다. 목소리가 너무 자연스러워서 AI 음성 같았어요.', region: '경기 수원시', ago: '38분 전', likes: 98, status: 'verified', liked: false },
  { id: 3, cat: '투자', title: '유명 경제 유튜버 딥페이크 광고 → 리딩방', body: '인스타 광고에서 유명인이 직접 종목 추천하는 영상이었는데, 입술 움직임이 조금 어색했어요. 들어가니 VIP방 가입비를 요구합니다.', region: '부산 해운대구', ago: '1시간 전', likes: 76, status: 'reviewing', liked: false },
  { id: 4, cat: '중고거래', title: '"안전결제" 링크가 naverpay-safe.shop', body: '판매자가 보낸 결제 링크 도메인이 이상해서 CodySafe로 검사했더니 위험 판정이 나왔어요. 다들 조심하세요.', region: '대전 유성구', ago: '3시간 전', likes: 64, status: 'verified', liked: true },
  { id: 5, cat: '로맨스', title: 'AI로 만든 외국인 프로필, 손가락이 6개', body: '데이팅앱에서 만난 사람 사진을 자세히 보니 손가락이 이상했어요. 이미지 분석 돌려보니 AI 생성 확률 91%.', region: '인천 연수구', ago: '5시간 전', likes: 41, status: 'ai', liked: false },
  { id: 6, cat: '스미싱', title: '[교통공단] 과태료 미납 고지 문자', body: '"과태료 미납으로 차량 압류 예정" 문자에 단축 URL이 포함. 공식 기관은 문자에 링크를 보내지 않는다고 하네요.', region: '광주 북구', ago: '어제', likes: 33, status: 'verified', liked: false },
];

const RADAR = [
  { k: '기관 사칭', v: 52 },
  { k: '가족 사칭', v: 84 },
  { k: '로맨스', v: 71 },
  { k: '투자 리딩', v: 38 },
  { k: '중고거래', v: 79 },
  { k: '스미싱', v: 66 },
];

const COPILOT = [
  { key: ['검찰', '경찰', '수사', '금감원', '기관', '구속'], q: '검찰이라며 돈을 보내래요',
    a: `<b>지금 바로 전화를 끊으세요.</b> 검찰·경찰·금감원은 <span class="hl-danger">절대 전화로 이체나 현금 전달을 요구하지 않습니다.</span>
      <ol><li>통화를 즉시 종료하세요 (상대가 협박해도 괜찮아요)</li><li>대검찰청 <b>1301</b> 또는 경찰 <b>112</b>로 직접 걸어 사실 확인</li><li>받은 공문·번호는 <b>기관 사칭 검증</b>으로 확인</li></ol>`,
    acts: [['phone', '112 신고', 'tel:112'], ['landmark', '기관 검증', '#/verify']] },
  { key: ['송금', '이체', '보냈', '입금'], q: '이미 송금했어요',
    a: `<b>골든타임은 30분입니다.</b> 지금 순서대로 진행하세요.
      <ol><li><b>112</b> 또는 송금한 은행 고객센터에 <span class="hl-danger">지급정지 신청</span></li><li>경찰서 방문해 <b>사건사고사실확인원</b> 발급</li><li>3일 이내 은행에 피해구제 신청서 제출</li><li>명의도용 방지: <b>엠세이퍼</b>·<b>계좌정보통합관리</b> 조회</li></ol>`,
    acts: [['phone', '112 지급정지', 'tel:112'], ['phone', '금감원 1332', 'tel:1332']] },
  { key: ['링크', '눌렀', '앱', '설치', 'url', 'apk'], q: '문자 링크를 눌렀어요',
    a: `<b>침착하세요. 아직 막을 수 있어요.</b>
      <ol><li>휴대폰을 <b>비행기 모드</b>로 전환</li><li>최근 설치된 모르는 앱 삭제 (설정 → 애플리케이션)</li><li>모바일 백신으로 검사 후, 다른 기기로 금융 비밀번호 변경</li><li>KISA 상담센터 <b>118</b>에 신고</li></ol>`,
    acts: [['link', 'URL 검사', '#/url'], ['phone', 'KISA 118', 'tel:118']] },
  { key: ['가족', '엄마', '아빠', '딸', '아들', '폰 고장', '액정'], q: '가족이 폰이 고장났대요',
    a: `<b>가족 사칭 메신저 피싱일 가능성이 높아요.</b>
      <ol><li>답장하지 말고 <b>기존 번호로 직접 전화</b></li><li>상품권 핀번호·본인인증·원격앱 요청은 <span class="hl-danger">모두 거절</span></li><li>가족 보호 네트워크로 다른 가족에게 알림 전송</li></ol>`,
    acts: [['users', '가족에게 알리기', '#/family']] },
];

// 13. 방어 설정 점검 — st: ok(켜짐) / check(확인 필요) / bad(위험)
// auto: 앱이 직접 읽을 수 있는 항목. 나머지는 다른 앱 설정이라 안내 후 사용자 확인
const CHECKUP = [
  { g: '폰 보안', sub: '앱이 자동으로 확인했어요', icon: 'smartphone', items: [
    { id: 'lock', t: '화면 잠금', s: '지문·PIN 잠금 사용 중', st: 'ok', auto: true },
    { id: 'patch', t: '보안 패치', s: '2026년 10월 · 최신', st: 'ok', auto: true },
    { id: 'adb', t: 'USB 디버깅', s: '꺼짐', st: 'ok', auto: true },
    { id: 'a11y', t: '화면 제어 권한을 가진 앱', s: '"원격지원 도우미"가 화면을 조작할 수 있어요', st: 'bad', auto: true, fix: '권한 해제하기',
      steps: ['설정 → 접근성 → 설치된 앱', '"원격지원 도우미" 선택 → 끄기', '직접 설치한 기억이 없다면 앱을 삭제하세요'] },
    { id: 'unknown', t: '출처 모를 앱 설치', s: 'Chrome에 허용됨 · 문자 링크로 악성앱이 깔릴 수 있어요', st: 'bad', auto: true, fix: '차단하기',
      steps: ['설정 → 애플리케이션 → ⋮ → 특별한 접근', '출처를 알 수 없는 앱 설치 → Chrome 끄기', '설정 → 보안 및 개인정보 보호 → 자동 차단 기능 켜기'] },
  ] },
  { g: '통화·문자 방어', sub: '다른 앱 설정이라 직접 확인이 필요해요', icon: 'phone-call', items: [
    { id: 'samsung', t: '보이스피싱 의심 전화 알림', s: '삼성 전화 앱 · One UI 8.0 이상', st: 'check', fix: '전화 앱 설정 열기',
      steps: ['전화 앱 → 오른쪽 위 ⋮ → 설정', '"보이스피싱 의심 전화 알림" 켜기', '메뉴가 없으면 설정 → 소프트웨어 업데이트'] },
    { id: 'carrier', t: '통신사 AI 보이스피싱 탐지', s: 'SKT 가입자 · 에이닷 전화 무료', st: 'check', fix: '에이닷 열기',
      steps: ['에이닷 전화 앱 설치·실행', '설정 → AI 보이스피싱 탐지 켜기', '※ iPhone 기본 전화 앱에서는 지원되지 않아요'] },
    { id: 'msg', t: '스팸·피싱 메시지 차단', s: '삼성 메시지 · 의심 링크 자동 차단', st: 'check', fix: '메시지 설정 열기',
      steps: ['메시지 앱 → ⋮ → 설정', '"스팸 및 피싱 차단" 켜기'] },
    { id: 'conan', t: '악성 앱·스미싱 검사', s: '경찰청 연계 시티즌코난 · 미설치', st: 'bad', fix: '설치하기',
      steps: ['Play 스토어에서 "시티즌코난" 설치', '실행 후 정밀 검사 한 번 하기'] },
  ] },
  { g: '명의 보호', sub: '폰 밖에서 내 이름을 지켜요', icon: 'id-card', items: [
    { id: 'msafer', t: '휴대폰 명의도용 개통 차단', s: '엠세이퍼 가입제한 서비스', st: 'check', fix: '신청하기',
      steps: ['엠세이퍼(msafer.or.kr) 접속', '가입제한 서비스 신청', '내 명의로 새 휴대폰 개통이 막혀요'] },
    { id: 'loan', t: '비대면 대출 차단', s: '여신거래 안심차단 서비스', st: 'check', fix: '신청하기',
      steps: ['거래 은행 앱 또는 영업점', '여신거래 안심차단 신청', '내 명의로 새 대출이 막혀요'] },
    { id: 'account', t: '내 명의 계좌 점검', s: '어카운트인포 · 모르는 계좌 확인', st: 'check', fix: '조회하기',
      steps: ['어카운트인포 앱 접속', '내 계좌 한눈에 조회', '모르는 계좌는 즉시 해지'] },
  ] },
];
