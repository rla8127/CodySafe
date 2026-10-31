from pathlib import Path
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer
from ctranslate2.converters import TransformersConverter

repo = 'seastar105/whisper-medium-komixv2'
revision = '752b1b5bfa0c8219bca737ea180a4ad7eed1e621'
root = Path(__file__).resolve().parent
snapshot = Path(snapshot_download(repo, revision=revision, allow_patterns=['*.json', '*.txt', 'model.safetensors']))
source = root / 'models/source'
source.mkdir(parents=True, exist_ok=True)
for path in snapshot.iterdir():
    if path.is_file() and path.name not in ['tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'added_tokens.json']:
        target = source / path.name
        if not target.exists():
            target.symlink_to(path.resolve())
AutoTokenizer.from_pretrained(snapshot).save_pretrained(source)
TransformersConverter(str(source), copy_files=['tokenizer.json', 'preprocessor_config.json']).convert(str(root / 'models/komix-medium-int8'), quantization='int8', force=True)
(root / 'models/provenance.json').write_text(__import__('json').dumps({'model': repo, 'revision': revision, 'quantization': 'int8', 'converter': 'ctranslate2 4.8.4'}, indent=2))
print('Conversion complete', flush=True)
