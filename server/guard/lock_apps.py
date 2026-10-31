"""잠금 대상 앱. Android에는 금융 앱 분류가 없어 앱 ID로 판별합니다.

앱은 이 목록을 서버에서 받으므로 APK를 다시 빌드하지 않고 추가할 수 있습니다.
ID는 Google Play 상세 페이지의 id= 값입니다.
"""
LOCK_APPS = [
    # 은행
    "com.kbstar.kbbank",  # KB스타뱅킹
    "com.shinhan.sbanking",  # 신한 슈퍼SOL
    "com.hanabank.oqf",  # 뉴 하나원큐
    "com.kebhana.hanapush",  # (구)하나원큐
    "com.wooribank.smart.npib",  # 우리WON뱅킹
    "nh.smart.banking",  # NH스마트뱅킹
    "com.nonghyup.nhallonebank",  # NH올원뱅크
    "com.ibk.android.ionebank",  # IBK i-ONE Bank
    "com.kakaobank.channel",  # 카카오뱅크
    "com.kbankwith.smartbank",  # 케이뱅크
    "com.scbank.ma30",  # SC제일은행
    "kr.co.citibank.citimobile",  # 씨티모바일
    "co.kr.kdb.android.smartkdb",  # 스마트KDB
    "com.epost.psf.sdsi",  # 우체국뱅킹
    "com.suhyup.pesmb",  # 수협 헤이뱅크
    "kr.co.cu.onbank",  # 신협 온뱅크
    "com.smg.spbs",  # MG더뱅킹
    "kr.co.busanbank.mbp",  # BNK부산은행
    "com.knb.psb",  # BNK경남은행
    "kr.co.dgb.dgbm",  # iM뱅크
    "com.kjbank.asb.pbanking",  # 광주 와뱅크
    "kr.co.jbbank.privatebank",  # 전북은행 쏙뱅크
    "com.jejubank.smartnew",  # 제주은행
    # 간편결제·송금
    "viva.republica.toss",  # 토스
    "com.kakaopay.app",  # 카카오페이
    "com.naverfin.payapp",  # 네이버페이
    "nh.smart.nhallonepay",  # NH페이
    # 증권
    "com.kiwoom.heromts",  # 키움증권
    "com.miraeasset.trade",  # 미래에셋증권
    "com.samsungpop.android.mpop",  # 삼성증권
    "com.truefriend.neosmartarenewal",  # 한국투자증권
    "com.kbsec.mts.iplustarngm2",  # KB증권
    "com.wooriwm.txsmart",  # 나무증권
    "com.shinhaninvest.nsmts",  # 신한 SOL증권
    "com.hanasec.stock",  # 하나증권 원큐프로
    # 원격제어: 사기범이 피해자 폰을 조작할 때 설치를 유도합니다.
    "com.teamviewer.quicksupport.market",  # TeamViewer QuickSupport
    "com.teamviewer.teamviewer.market.mobile",  # TeamViewer Remote Control
    "com.anydesk.anydeskandroid",  # AnyDesk
]
