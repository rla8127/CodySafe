from pathlib import Path
import json, wave, hashlib
import boto3
import numpy as np
from scipy.signal import butter,sosfilt,resample_poly

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'dataset'
OUT.mkdir(exist_ok=True)
texts=[
 ('daily','일상','안녕하세요. 오늘 오후에는 비가 내릴 수 있으니 우산을 챙겨 주세요. 약속 장소는 지하철역 이 번 출구 앞입니다.'),
 ('support','상담','고객님, 주문하신 상품은 내일 도착할 예정입니다. 배송지를 변경하려면 상담원에게 새로운 주소를 알려 주세요.'),
 ('fraud','보이스피싱 예방','검사나 금융기관 직원을 사칭하며 안전 계좌로 돈을 보내라고 하면 보이스피싱을 의심해야 합니다. 통화를 끊고 공식 번호로 확인하세요.'),
 ('names','이름과 주소','박철민 씨와 김민수 씨는 서울특별시 강남구 테헤란로에서 만나기로 했습니다. 담당자는 이서연이며 방문 시간은 오후 세 시입니다.'),
 ('finance','금융과 수량','이번 달 카드 결제 금액은 십이만 삼천 원입니다. 계좌 잔액을 확인한 뒤 이체 한도를 오십만 원으로 변경해 주세요.'),
 ('medical','의료 용어','진료 예약을 변경하고 싶습니다. 알레르기 비염으로 약을 복용 중이며 최근에는 기침과 두통이 함께 나타났습니다.'),
 ('technical','기술 용어','서버의 메모리 사용량과 응답 시간을 확인해 주세요. 음성 인식 모델을 교체한 뒤 데이터베이스 연결 오류가 발생했습니다.'),
 ('conversation','구어체','아, 그게 아니라요. 제가 어제 말씀드렸던 건 다음 주 수요일 회의였어요. 혹시 시간 괜찮으시면 자료를 미리 보내 주실 수 있을까요?'),
]
client=boto3.client('polly',region_name='ap-northeast-2')
manifest=[]
def save(path,audio):
 with wave.open(str(path),'wb') as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(audio)
for voice in ['Seoyeon','Jihye']:
 for name,category,text in texts:
  sid=f'{voice.lower()}_{name}'
  path=OUT/f'{sid}.wav'
  if not path.exists():
   r=client.synthesize_speech(Text=text,TextType='text',VoiceId=voice,Engine='neural',OutputFormat='pcm',SampleRate='16000',LanguageCode='ko-KR')
   save(path,r['AudioStream'].read())
  with wave.open(str(path)) as w:
   pcm=w.readframes(w.getnframes());duration=w.getnframes()/w.getframerate()
  row={'id':sid,'file':str(path.relative_to(ROOT)),'reference':text,'category':category,'voice':voice,'engine':'neural','condition':'clean','duration':duration,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
  manifest.append(row)
  if name in ['fraud','names']:
   degraded=OUT/f'{sid}_telephone_noise.wav'
   x=np.frombuffer(pcm,dtype='<i2').astype(float)/32768
   x=sosfilt(butter(5,[300,3400],btype='bandpass',fs=16000,output='sos'),x)
   x=resample_poly(resample_poly(x,1,2),2,1)[:len(x)]
   noise=np.random.default_rng(20261101).normal(size=len(x))
   noise*=np.sqrt(np.mean(x*x)/(10*np.mean(noise*noise)))
   y=np.clip(x+noise,-1,1)
   save(degraded,(y*32767).astype('<i2').tobytes())
   manifest.append({**row,'id':sid+'_telephone_noise','file':str(degraded.relative_to(ROOT)),'condition':'telephone_band_8khz_plus_10dB_noise','sha256':hashlib.sha256(degraded.read_bytes()).hexdigest()})
(ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({'samples':len(manifest),'total_seconds':sum(x['duration'] for x in manifest),'region':'ap-northeast-2','seed':20261101},ensure_ascii=False))
