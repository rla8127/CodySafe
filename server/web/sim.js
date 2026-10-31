// 체험 시나리오. 웹 MVP의 대화 화면을 쓰고, 내용과 진행 방식만 바꿉니다.
// 모든 이름, 번호, 주소는 가상이며 주소는 실제로 열리지 않는 example 도메인을 씁니다.

const simSay = (t, ok, fb) => ({ t, ok, fb });
const simAct = (t, ok, fb) => ({ t, ok, fb, act: true });

Object.keys(SCENARIOS).forEach((k) => delete SCENARIOS[k]);
Object.assign(SCENARIOS, {
  agency: {
    title: '서울중앙지검 수사관입니다', tag: '기관 사칭', icon: 'landmark', color: '#0047AB', soft: '#E8F0FB',
    difficulty: '어려움', mins: 2, desc: '수사기관을 사칭해 공포를 주고 "안전 계좌" 이체를 요구하는 전화',
    contact: { name: '02-3480-****', sub: '수사관을 자칭하는 전화', av: '검' },
    steps: [
      { msgs: ['서울중앙지검 수사관 김민수입니다.', '고객님 명의 계좌가 범죄에 쓰여 연락드렸습니다.'],
        choices: [
          simSay('제가요? 어떻게 해야 하죠?', false, '상대의 말을 전제로 답하면 다음 지시로 끌려가기 쉬워요. 먼저 끊고 확인하세요.'),
          simAct('전화를 끊고 대검찰청 1301에 직접 전화한다', true, '좋아요. 받은 번호가 아니라 직접 찾은 공식 번호로 확인하는 것이 핵심이에요.'),
        ] },
      { sys: '잠시 뒤 같은 사람에게 다시 전화가 왔어요', msgs: ['지금 끊으면 구속영장이 발부됩니다.', '수사 중이니 가족에게도 말하면 안 됩니다.', '[공문] 사건번호_2026-1182.pdf'],
        choices: [
          simAct('공문을 열지 않고 가족에게 알린다', true, '좋아요. 비밀을 지키라는 요구는 혼자 판단하게 만들려는 위험 신호예요.'),
          simSay('구속은 무서워요. 시키는 대로 할게요', false, '공포와 고립은 판단을 흐리게 하는 수법이에요.'),
        ] },
      { msgs: ['자산 보호를 위해 안전 계좌로 옮기셔야 합니다.', '확인 후 바로 돌려드립니다.'],
        choices: [
          simAct('안내받은 계좌로 이체한다', false, '수사기관과 금융감독원은 전화로 돈을 옮기라고 요구하지 않아요.'),
          simAct('거절하고 112에 신고한다', true, '정답이에요. 돈을 옮기라는 요구가 나오면 끊고 신고하세요.'),
        ] },
    ],
    signals: ['수사기관 사칭', '구속 위협', '비밀 유지 요구', '안전 계좌 이체'],
  },
  family: {
    title: '"엄마, 나 폰 깨졌어"', tag: '가족 사칭', icon: 'users', color: '#F79009', soft: '#FFF4E5',
    difficulty: '쉬움', mins: 2, desc: '자녀를 사칭해 새 번호로 연락하고 인증과 상품권을 요구하는 메시지',
    contact: { name: '딸 💕', sub: '새 번호 010-5821-****', av: '딸' },
    steps: [
      { msgs: ['엄마 나 폰 액정 깨져서 수리 맡겼어ㅠㅠ', '이거 임시 번호야 저장해 줘!'],
        choices: [
          simSay('어머 괜찮아? 번호 저장해 둘게~', false, '처음 보는 번호의 가족 연락은 일단 확인이 먼저예요.'),
          simAct('딸의 원래 번호로 전화한다', true, '정답이에요. 원래 알던 번호로 직접 확인하세요.'),
        ] },
      { sys: '원래 번호는 연결되지 않았어요', msgs: ['폰이 수리점에 있어서 통화 안 돼ㅠ', '급한데 엄마 폰으로 본인인증 좀 해 줘'],
        choices: [
          simSay('오늘의 가족 암구호가 뭐야?', true, '좋아요. 폰이 고장 났다고 하면 비상 암구호나 다른 가족을 통해 확인하세요.'),
          simSay('뭐 해 주면 되는데?', false, '본인인증을 대신 하면 내 명의로 금융 거래가 일어날 수 있어요.'),
        ] },
      { msgs: ['그런 거 지금 모르겠어ㅠ 상품권 50만 원만 사서 번호 보내 줘', '이 앱 깔면 내가 알아서 할게!', 'https://fix-app.example/install'],
        choices: [
          simAct('링크를 눌러 앱을 설치한다', false, '원격제어 앱을 설치하면 폰의 금융 앱까지 조작당할 수 있어요.'),
          simAct('대화를 멈추고 다른 가족에게 확인한다', true, '정답이에요. 상품권 번호와 앱 설치 요구는 멈춰야 할 신호예요.'),
        ] },
    ],
    signals: ['새 번호', '통화 회피', '인증 대행 요구', '상품권 요구', '앱 설치 요구'],
  },
  romance: {
    title: '배우라는 사람의 DM', tag: '로맨스 스캠', icon: 'heart', color: '#E5487A', soft: '#FDECF2',
    difficulty: '보통', mins: 2, desc: '유명 배우 사진으로 친밀감을 쌓은 뒤 팬 미팅 비용과 투자를 요구',
    contact: { name: '배우 강서진 (가상)', sub: 'Instagram DM', av: '강' },
    steps: [
      { msgs: ['안녕하세요, 배우 강서진입니다 😊', { photo: '셀카라며 보낸 프로필 사진' }, '회사 몰래 개인 계정으로 연락드려요. 비밀 지켜 주실 거죠?'],
        choices: [
          simSay('와 진짜요? 팬이에요!', false, '유명인 사진은 쉽게 도용되고, 공개 사진으로 합성도 할 수 있어요.'),
          simAct('소속사 공식 채널에서 계정을 확인한다', true, '좋아요. 사진이나 목소리보다 공식 채널 확인이 믿을 만해요.'),
        ] },
      { sys: '2주 동안 매일 다정한 메시지가 왔어요', msgs: ['요즘 당신 덕분에 버텨요 ❤️', '우리 비공개 팬 미팅에서 꼭 만나요', '자리 잡으려면 오늘까지 300만 원 보내 주셔야 해요'],
        choices: [
          simSay('이번만 보내 드릴게요', false, '만난 적 없는 사람의 돈 요구에는 응하지 마세요. 친밀감이 수법의 핵심이에요.'),
          simSay('영상통화로 먼저 얘기해요', true, '좋은 대응이에요. 다만 영상도 합성될 수 있으니 돈 요구 자체를 거절해야 해요.'),
        ] },
      { msgs: ['촬영장이라 영상통화는 어려워요 😢', '대신 매니저 번호 드릴게요. 오늘 안 보내면 자리가 사라져요!'],
        choices: [
          simAct('매니저에게 연락해 입금 계좌를 묻는다', false, '매니저라는 사람도 같은 일당일 수 있어요. 추가 입금 요구로 이어지기 쉬워요.'),
          simAct('대화를 끊고 증거를 저장해 신고한다', true, '정답이에요. 시간 압박은 판단을 흐리려는 신호예요.'),
        ] },
    ],
    signals: ['유명인 사칭', '비밀 유지 요구', '급격한 친밀감', '영상통화 회피', '오늘까지 입금 압박'],
  },
  loan: {
    title: '저금리로 갈아타세요', tag: '대출 사기', icon: 'banknote', color: '#0E9F8E', soft: '#E3F7F4',
    difficulty: '보통', mins: 2, desc: '대환대출을 미끼로 기존 대출 상환금과 앱 설치를 요구하는 전화',
    contact: { name: '1800-****', sub: '대출 상담을 자칭하는 전화', av: '상' },
    steps: [
      { msgs: ['정부지원 저금리 대환대출 대상자로 선정되셨습니다.', '연 3%대로 갈아타실 수 있어요.'],
        choices: [
          simSay('제가요? 얼마나 낮아져요?', false, '먼저 받은 대출 권유는 조건을 묻기 전에 업체부터 확인하세요.'),
          simAct('끊고 거래 중인 은행 대표번호로 확인한다', true, '좋아요. 받은 번호가 아닌 대표번호로 확인하세요.'),
        ] },
      { sys: '다음 날 다시 전화가 왔어요', msgs: ['심사하려면 전용 앱을 설치하셔야 해요.', 'https://loan-check.example/app'],
        choices: [
          simAct('링크로 앱을 설치한다', false, '출처가 불분명한 앱은 전화와 문자를 가로채는 데 쓰일 수 있어요.'),
          simSay('앱은 설치하지 않을게요', true, '정답이에요. 앱 설치 요구는 멈춰야 할 신호예요.'),
        ] },
      { msgs: ['신용점수를 올리려면 기존 대출 일부를 먼저 갚으셔야 해요.', '저희 담당자 계좌로 입금하시면 처리됩니다.'],
        choices: [
          simAct('담당자 계좌로 입금한다', false, '대출 상환금은 본인 명의의 금융회사 계좌로만 갚아요.'),
          simAct('거절하고 1332에 상담한다', true, '좋아요. 금융감독원 1332에서 상담받을 수 있어요.'),
        ] },
    ],
    signals: ['먼저 온 대출 권유', '전용 앱 설치', '개인 계좌 입금', '선입금 요구'],
  },
  bank: {
    title: '해외 결제가 승인됐습니다', tag: '카드사 사칭', icon: 'credit-card', color: '#7A5AF8', soft: '#F0EDFF',
    difficulty: '쉬움', mins: 1, desc: '결제 문자로 놀라게 한 뒤 인증번호와 앱 설치를 요구',
    contact: { name: '02-1588-****', sub: '문자에 적힌 고객센터', av: '카' },
    steps: [
      { msgs: ['[해외 승인] 97만 원 결제. 본인이 아니면 고객센터로 연락 바랍니다.'],
        choices: [
          simAct('문자에 적힌 번호로 바로 전화한다', false, '문자 속 번호가 사기범에게 연결될 수 있어요.'),
          simAct('카드 뒷면 번호로 직접 전화한다', true, '정답이에요. 카드나 공식 앱에 적힌 번호를 쓰세요.'),
        ] },
      { sys: '문자에 적힌 번호에서 전화가 왔어요', msgs: ['명의 도용 같습니다. 취소하려면 문자로 간 인증번호를 불러 주세요.'],
        choices: [
          simSay('인증번호는 알려 드릴 수 없어요', true, '정답이에요. 인증번호는 누구에게도 알려 주지 마세요.'),
          simSay('번호 불러 드릴게요', false, '인증번호를 주면 내 계정이나 결제가 뚫릴 수 있어요.'),
        ] },
    ],
    signals: ['결제 문자로 불안 조성', '문자 속 번호 유도', '인증번호 요구'],
  },
  delivery: {
    title: '택배 주소를 확인해 주세요', tag: '스미싱', icon: 'package', color: '#12B76A', soft: '#E7F8EF',
    difficulty: '쉬움', mins: 1, desc: '택배 문자 속 링크로 가짜 사이트와 악성 앱 설치를 유도',
    contact: { name: '010-7741-****', sub: '문자 메시지', av: '택' },
    steps: [
      { msgs: ['[택배] 주소 불일치로 배송이 보류되었습니다. 확인: https://parcel-kr.example/a7'],
        choices: [
          simAct('링크를 눌러 주소를 입력한다', false, '가짜 사이트에 입력한 정보가 그대로 넘어갈 수 있어요.'),
          simAct('쓰는 택배 앱에서 운송장을 직접 조회한다', true, '정답이에요. 링크 대신 공식 앱으로 확인하세요.'),
        ] },
      { sys: '다음 날 같은 번호에서 문자가 왔어요', msgs: ['재배송 앱을 설치해야 받을 수 있습니다.', 'https://parcel-kr.example/app.apk'],
        choices: [
          simAct('스팸으로 신고하고 문자를 지운다', true, '좋아요. 118이나 통신사 앱으로 신고할 수 있어요.'),
          simAct('.apk 파일을 설치한다', false, '문자로 받은 설치 파일은 열지 마세요.'),
        ] },
    ],
    signals: ['모르는 번호', '단축·낯선 주소', '배송 보류로 재촉', '.apk 설치 요구'],
  },
  wedding: {
    title: '모바일 청첩장 도착 💌', tag: '스미싱', icon: 'mail', color: '#0EA5E9', soft: '#E0F4FE',
    difficulty: '보통', mins: 1, desc: '지인인 척 청첩장과 부고 링크를 보내 앱 설치를 유도',
    contact: { name: '010-3392-****', sub: '저장되지 않은 번호', av: '?' },
    steps: [
      { msgs: ['저희 결혼합니다 💍 꼭 와 주세요!', '모바일 청첩장 👉 https://wedding-card.example/m/3392'],
        choices: [
          simAct('누군지 궁금하니 링크를 연다', false, '청첩장과 부고는 궁금해서 누르게 만드는 대표적인 미끼예요.'),
          simSay('누구세요? 성함을 알려 주세요', true, '좋아요. 링크를 누르기 전에 보낸 사람부터 확인하세요.'),
        ] },
      { msgs: ['앗 저 OO이에요~ 번호 바꿨어요ㅎㅎ', '청첩장 앱을 설치해야 보여요!'],
        choices: [
          simAct('지인의 원래 번호로 직접 확인한다', true, '정답이에요. 청첩장을 보는 데 앱 설치는 필요 없어요.'),
          simAct('아는 사람 같으니 앱을 설치한다', false, '설치한 앱이 연락처를 빼내 지인에게 다시 퍼질 수 있어요.'),
        ] },
    ],
    signals: ['모르는 번호', '청첩장·부고 링크', '앱 설치 요구'],
  },
  market: {
    title: '중고 폰 안전결제', tag: '중고거래', icon: 'smartphone', color: '#16A34A', soft: '#E7F8EF',
    difficulty: '보통', mins: 2, desc: '가짜 안전결제 링크로 플랫폼 밖 결제를 유도',
    contact: { name: '판매자 쿨거래123', sub: '중고마켓 채팅', av: '판' },
    steps: [
      { msgs: ['미개봉 75만 원 맞아요~', '지방이라 택배거래만 돼요'],
        choices: [
          simAct('판매자 계좌와 번호의 신고 이력을 조회한다', true, '좋아요. 조회 결과가 없어도 안전이 보장되는 건 아니니 끝까지 조심하세요.'),
          simSay('시세보다 싸네요! 바로 살게요', false, '시세보다 지나치게 싼 매물은 미끼일 수 있어요.'),
        ] },
      { msgs: ['안전결제로 해요! 이 링크에서 결제해 주세요 👇', 'https://safe-pay.example/pay/8812'],
        choices: [
          simAct('링크 대신 거래 앱 안의 결제만 쓰겠다고 한다', true, '정답이에요. 채팅으로 받은 결제 링크는 가짜일 수 있어요.'),
          simAct('안전결제니까 링크에서 결제한다', false, '이름이 안전결제여도 가짜 페이지일 수 있어요.'),
        ] },
      { msgs: ['결제 오류예요ㅠ 수수료까지 다시 입금하셔야 환불돼요'],
        choices: [
          simAct('수수료까지 다시 입금한다', false, '오류와 환불을 핑계로 추가 입금을 받아 내는 수법이에요.'),
          simAct('거래를 멈추고 플랫폼에 신고한다', true, '정답이에요. 입금했다면 은행과 112에 바로 알리세요.'),
        ] },
    ],
    signals: ['시세보다 저렴', '택배거래 고집', '외부 결제 링크', '재입금 요구'],
  },
  invest: {
    title: 'AI 주식 리딩방 VIP', tag: '투자 사기', icon: 'trending-up', color: '#6366F1', soft: '#EEF0FF',
    difficulty: '어려움', mins: 2, desc: '수익 인증과 바람잡이로 믿게 한 뒤 가짜 거래 앱 입금을 유도',
    contact: { name: '[VIP] 수익인증방 📈', sub: '참여자 312명', av: 'V' },
    steps: [
      { msgs: ['🎉 신규 회원님 환영합니다!', '오늘도 추천 종목 +38% 인증 올라왔습니다 🚀', '[수익 인증 캡처.jpg]'],
        choices: [
          simSay('인증이 많으니 믿을 만하네요', false, '대화방 참여자는 바람잡이일 수 있고, 캡처는 쉽게 조작돼요.'),
          simAct('금융소비자 정보포털 파인에서 업체를 확인한다', true, '좋아요. 등록 여부를 먼저 확인하세요.'),
        ] },
      { msgs: ['VIP방은 전용 거래 앱에서만 매매합니다', '원금 보장, 월 30% 확정 수익!'],
        choices: [
          simAct('전용 거래 앱을 설치한다', false, '가짜 앱은 화면에 수익만 보여 주고 출금을 막을 수 있어요.'),
          simSay('원금 보장은 믿기 어려워요', true, '좋아요. 원금 보장과 확정 수익 약속은 대표적인 위험 신호예요.'),
        ] },
      { sys: '소액을 넣자 화면에 수익이 표시됐어요', msgs: ['출금하려면 세금 200만 원을 먼저 내셔야 합니다.'],
        choices: [
          simAct('출금을 위해 세금을 입금한다', false, '출금 조건으로 돈을 더 요구하면 입금을 멈추세요.'),
          simAct('입금을 멈추고 은행과 112에 알린다', true, '정답이에요. 입금 내역과 대화를 저장해 두세요.'),
        ] },
    ],
    signals: ['수익 인증 캡처', '원금 보장 약속', '전용 거래 앱', '출금 전 추가 입금'],
  },
  job: {
    title: '재택 고수익 알바', tag: '통장·현금 수거', icon: 'briefcase', color: '#D97706', soft: '#FEF3E2',
    difficulty: '보통', mins: 1, desc: '쉬운 알바라며 통장을 빌리거나 현금 전달을 시켜 범죄에 끌어들임',
    contact: { name: '채용 담당자', sub: '오픈채팅', av: '채' },
    steps: [
      { msgs: ['재택으로 일당 30만 원 가능합니다.', '체크카드만 잠깐 빌려주시면 돼요.'],
        choices: [
          simSay('통장과 카드는 빌려줄 수 없어요', true, '정답이에요. 빌려준 계좌가 범죄에 쓰이면 처벌받을 수 있어요.'),
          simSay('빌려주기만 하면 되나요?', false, '통장이나 카드를 넘기는 것 자체가 위험해요.'),
        ] },
      { msgs: ['그럼 고객 돈을 받아 지정 계좌로 전달만 해 주세요.', '법무 쪽 일이라 문제없어요.'],
        choices: [
          simAct('제안을 거절하고 대화를 신고한다', true, '정답이에요. 이미 응했다면 경찰에 먼저 알리세요.'),
          simSay('전달만 하면 되니 해 볼게요', false, '모르고 했어도 사기 범죄에 가담한 것으로 수사받을 수 있어요.'),
        ] },
    ],
    signals: ['과한 일당', '통장·카드 대여', '현금 전달 업무'],
  },
  kidnap: {
    title: '아드님을 데리고 있습니다', tag: '납치 협박', icon: 'siren', color: '#DC2626', soft: '#FEECEB',
    difficulty: '어려움', mins: 1, desc: '가족의 울음소리를 들려주며 전화를 못 끊게 하고 송금을 요구',
    contact: { name: '발신 번호 표시 제한', sub: '협박 전화', av: '?' },
    steps: [
      { msgs: ['아드님을 데리고 있습니다. (우는 소리)', '전화 끊거나 신고하면 큰일 납니다.'],
        choices: [
          simAct('다른 폰으로 주변 사람에게 112 신고를 부탁한다', true, '좋아요. 협박이 있어도 신고가 먼저예요.'),
          simSay('제발 시키는 대로 할게요', false, '겁에 질리게 만들어 확인할 시간을 빼앗는 수법이에요.'),
        ] },
      { msgs: ['30분 안에 500만 원 보내세요. 계좌 부릅니다.'],
        choices: [
          simAct('아들에게 직접 연락하거나 암구호로 확인한다', true, '정답이에요. 우는 소리나 목소리만으로 판단하지 마세요.'),
          simAct('확인 없이 바로 송금한다', false, '확인 전에 송금하면 돌려받기 어려울 수 있어요.'),
        ] },
    ],
    signals: ['전화 못 끊게 함', '신고 금지 협박', '짧은 시간 압박', '가족 목소리 이용'],
  },
  refund: {
    title: '환급금을 찾아가세요', tag: '정부 사칭', icon: 'badge-percent', color: '#0891B2', soft: '#E2F6FA',
    difficulty: '쉬움', mins: 1, desc: '환급금과 지원금을 미끼로 계좌 비밀번호와 수수료를 요구',
    contact: { name: '02-1577-****', sub: '공단 직원을 자칭하는 전화', av: '공' },
    steps: [
      { msgs: ['미수령 환급금 48만 원이 있어 안내드립니다.', '오늘까지 신청하지 않으면 소멸됩니다.'],
        choices: [
          simAct('끊고 해당 기관 공식 사이트에서 조회한다', true, '정답이에요. 안내받은 링크 말고 직접 찾아 들어가세요.'),
          simSay('오늘까지요? 어떻게 신청하죠?', false, '기한으로 재촉하면 먼저 멈추고 확인하세요.'),
        ] },
      { sys: '같은 사람에게 다시 전화가 왔어요', msgs: ['입금받을 계좌 비밀번호와 수수료 3만 원만 보내 주세요.'],
        choices: [
          simSay('비밀번호는 알려 드리지 않습니다', true, '정답이에요. 돈을 받는 데 계좌 비밀번호는 필요 없어요.'),
          simAct('수수료를 보내고 비밀번호를 알려 준다', false, '비밀번호를 알려 주면 계좌의 돈이 빠져나갈 수 있어요.'),
        ] },
    ],
    signals: ['기한 압박', '수수료 선입금', '계좌 비밀번호 요구'],
  },
});

/* 기다리지 않도록 메시지 간격을 짧게 둡니다. */
const SIM_GAP = 520;
const SIM_TYPING = 280;

function simBubble(m) {
  if (m.photo) {
    return `<div class="bubble sim-photo"><span class="sim-face">${ic('user-round')}</span><small>${m.photo}</small><em>가상 예시 이미지</em></div>`;
  }
  return `<div class="bubble ${/https?:\/\//.test(m) ? 'link' : ''}">${m}</div>`;
}

simStep = function () {
  const s = sim.s, step = s.steps[sim.i];
  const chat = $('#chat');
  $('#choices').style.display = 'none';
  document.querySelectorAll('#simProg i').forEach((e, k) => e.classList.toggle('on', k <= sim.i));
  if (step.sys) chat.insertAdjacentHTML('beforeend', `<div class="sysmsg">${step.sys}</div>`);
  step.msgs.forEach((m, k) => {
    later(() => {
      chat.insertAdjacentHTML('beforeend', `<div class="msg" id="typing"><span class="av">${s.contact.av}</span><div class="bubble typing"><i></i><i></i><i></i></div></div>`);
      view.scrollTop = view.scrollHeight;
    }, k * SIM_GAP);
    later(() => {
      $('#typing')?.remove();
      chat.insertAdjacentHTML('beforeend', `<div class="msg ${k ? 'cont' : ''}"><span class="av">${s.contact.av}</span>${simBubble(m)}</div>`);
      icons();
      view.scrollTop = view.scrollHeight;
    }, k * SIM_GAP + SIM_TYPING);
  });
  later(() => {
    const c = $('#choices');
    c.style.display = '';
    c.innerHTML = `<div class="q">${ic('mouse-pointer-click')}어떻게 할까요? (${sim.i + 1}/${s.steps.length})</div>
      ${step.choices.map((ch, j) => `<button class="choice" onclick="simChoose(${j})">${ch.act ? `<span class="choice-act">행동</span>` : ''}${ch.t}</button>`).join('')}`;
    icons();
    view.scrollTop = view.scrollHeight;
  }, (step.msgs.length - 1) * SIM_GAP + SIM_TYPING + 120);
};

// 행동은 상대에게 보내는 말이 아니므로 말풍선이 아니라 안내 줄로 남깁니다.
const baseSimChoose = simChoose;
simChoose = function (j) {
  const ch = sim.s.steps[sim.i].choices[j];
  if (!ch.act) return baseSimChoose(j);
  baseSimChoose(j);
  const sent = $('#chat').querySelector('.msg.me:last-child');
  if (sent) sent.outerHTML = `<div class="sysmsg sim-act">${ic('hand')} 내 행동: ${ch.t}</div>`;
  icons();
};
