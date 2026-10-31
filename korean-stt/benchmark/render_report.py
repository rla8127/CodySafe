"""Build a standalone HTML report with embedded evaluation audio."""
from pathlib import Path
import base64,html,json,zipfile
from markdown_it import MarkdownIt
root=Path(__file__).resolve().parent
summary=json.loads((root/'summary.json').read_text())
manifest=json.loads((root/'manifest.json').read_text())
rows=[]
for p in (root/'results').glob('*.jsonl'):
 rows.extend({r['id']:r for r in map(json.loads,p.read_text().splitlines())}.values())
parts=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>한국어 STT 비교 평가</title><style>body{font:16px/1.7 system-ui,sans-serif;max-width:1150px;margin:40px auto;padding:0 20px;color:#18212c;background:#f5f7fb}table{border-collapse:collapse;width:100%;background:white;font-size:14px}th,td{border:1px solid #d6dce6;padding:8px;text-align:left}pre{white-space:pre-wrap;background:#e8edf6;padding:16px}h1,h2,h3{line-height:1.3}h2{margin-top:42px}details{margin:12px 0;background:white;border:1px solid #d6dce6;padding:14px;border-radius:8px}summary{cursor:pointer;font-weight:600}.bars{display:grid;grid-template-columns:1fr 1fr;gap:24px}.bar{background:#3868d7;height:20px;min-width:1px;border-radius:3px}.label{font-size:14px;margin-top:12px}audio{width:100%}.scroll{overflow:auto}td{overflow-wrap:anywhere}a{color:#2459be}</style>']
parts.append('<h1>한국어 STT 모델 비교</h1><p>2026-11-01 · Amazon Polly 합성 음성 20개 · CPU 2 vCPU / RAM 3.7 GiB</p>')
parts.append('<div class="bars">')
for metric,title in [('cer','문자 오류율 (낮을수록 좋음)'),('rtf','실시간 대비 처리 시간 RTF (낮을수록 좋음)')]:
 parts.append('<section><h3>'+title+'</h3>')
 maximum=max(r[metric] for r in summary) or 1
 for r in summary:
  value=f'{r[metric]:.2%}' if metric=='cer' else f'{r[metric]:.3f}'
  parts.append(f'<div class="label">{html.escape(r["model"])} · {value}</div><div class="bar" style="width:{r[metric]/maximum*100:.2f}%"></div>')
 parts.append('</section>')
parts.append('</div>')
original=root.parent/'박철민검사.mp3'
if original.exists():
 encoded=base64.b64encode(original.read_bytes()).decode()
 parts.append(f'<details><summary>사용자 제공 실제 녹음 듣기 (정답 대본 없음, 점수 제외)</summary><audio controls preload="none" src="data:audio/mpeg;base64,{encoded}"></audio></details>')
body=(root/'internal/REPORT.md').read_text().split('\n',1)[1]
parts.append(MarkdownIt('commonmark',{'html':False}).enable('table').render(body).replace('<table>','<div class="scroll"><table>').replace('</table>','</table></div>'))
parts.append('<h2>샘플별 음성·정답·모델 출력</h2><p>각 항목을 펼치면 음성을 듣고 전사문을 비교할 수 있습니다. 음성은 HTML 안에 포함되어 인터넷 없이 재생할 수 있습니다.</p>')
for sample in manifest:
 parts.append(f'<details><summary>{html.escape(sample["id"])} · {sample["duration"]:.2f}초</summary>')
 encoded=base64.b64encode((root/sample['file']).read_bytes()).decode()
 parts.append(f'<audio controls preload="none" src="data:audio/wav;base64,{encoded}"></audio><p><b>정답:</b> {html.escape(sample["reference"])}</p><table><tr><th>모델</th><th>전사문</th><th>CER</th></tr>')
 from score import norm,distance
 for row in rows:
  if row['id']==sample['id'] and row['status']=='ok':
   cer=distance(norm(sample['reference']),norm(row['text']))/len(norm(sample['reference']))
   parts.append(f'<tr><td>{html.escape(row["model"])}</td><td>{html.escape(row["text"])}</td><td>{cer:.2%}</td></tr>')
 parts.append('</table></details>')
parts.append('</html>')
(root/'REPORT.html').write_text('\n'.join(parts))
with zipfile.ZipFile(root/'korean-stt-evaluation.zip','a',zipfile.ZIP_DEFLATED) as z:
 z.write(root/'REPORT.html','REPORT.html')
 z.write(root/'render_report.py','render_report.py')
print('Report HTML ready')
