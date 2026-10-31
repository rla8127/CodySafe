"""음성 저장소와 STT. 기기에 AWS 자격 증명을 두지 않도록 S3 업로드는 presigned URL만 내려줍니다."""
import json
import logging
import time
from pathlib import Path

from . import config, stt_client, tracing

log = logging.getLogger("guard.providers")

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        import boto3
        from botocore.config import Config

        _s3 = boto3.client(
            "s3",
            region_name=config.S3_REGION,
            endpoint_url=f"https://s3.{config.S3_REGION}.amazonaws.com",
            config=Config(signature_version="s3v4"),
        )
    return _s3


def local_path(key: str) -> Path:
    return config.LOCAL_AUDIO_DIR / key.replace("/", "_")


def upload_url(key: str, content_type: str, upload_token: str, rec_id: str, direct: bool = True) -> str:
    if config.STORAGE == "s3" and direct:
        return s3().generate_presigned_url(
            "put_object",
            Params={"Bucket": config.S3_BUCKET, "Key": key, "ContentType": content_type},
            ExpiresIn=3600,
        )
    return f"{config.PUBLIC_BASE_URL}/v1/local-upload/{rec_id}?token={upload_token}"


def store_uploaded(key: str) -> None:
    """서버를 거쳐 올라온 파일을 S3로 옮기고 임시 파일을 지웁니다."""
    if config.STORAGE != "s3":
        return
    path = local_path(key)
    try:
        s3().upload_file(str(path), config.S3_BUCKET, key)
    finally:
        path.unlink(missing_ok=True)


def uploaded_size(key: str) -> int | None:
    if config.STORAGE == "s3":
        try:
            return s3().head_object(Bucket=config.S3_BUCKET, Key=key)["ContentLength"]
        except s3().exceptions.ClientError:
            return None
    path = local_path(key)
    return path.stat().st_size if path.exists() else None


def delete_audio(key: str) -> None:
    if config.STORAGE == "s3":
        s3().delete_object(Bucket=config.S3_BUCKET, Key=key)
    else:
        local_path(key).unlink(missing_ok=True)


def _transcribe(rec_id: str, key: str) -> str:
    import boto3

    client = boto3.client("transcribe", region_name=config.AWS_REGION)
    job = f"guard-{rec_id}"
    output_key = f"transcripts/{rec_id}.json"
    client.start_transcription_job(
        TranscriptionJobName=job,
        LanguageCode="ko-KR",
        Media={"MediaFileUri": f"s3://{config.S3_BUCKET}/{key}"},
        OutputBucketName=config.S3_BUCKET,
        OutputKey=output_key,
    )
    try:
        while True:
            info = client.get_transcription_job(TranscriptionJobName=job)["TranscriptionJob"]
            status = info["TranscriptionJobStatus"]
            if status == "COMPLETED":
                break
            if status == "FAILED":
                raise RuntimeError(info.get("FailureReason", "Transcribe 실패"))
            time.sleep(5)
        body = s3().get_object(Bucket=config.S3_BUCKET, Key=output_key)["Body"].read()
        return json.loads(body)["results"]["transcripts"][0]["transcript"]
    finally:
        s3().delete_object(Bucket=config.S3_BUCKET, Key=output_key)
        client.delete_transcription_job(TranscriptionJobName=job)


def _read(key: str) -> bytes:
    if config.STORAGE == "s3":
        return s3().get_object(Bucket=config.S3_BUCKET, Key=key)["Body"].read()
    return local_path(key).read_bytes()


_openai = None


def _as_m4a(data: bytes) -> bytes:
    """삼성 통화 녹음은 AAC인데 컨테이너 표기가 3gp4입니다. 음성은 그대로 두고 표기만 바꿉니다."""
    if data[4:8] != b"ftyp" or data[8:11] != b"3gp" or b"mp4a" not in data:
        return data
    out = bytearray(data)
    out[8:12] = b"M4A "
    for i in range(16, int.from_bytes(data[:4], "big"), 4):
        if out[i : i + 3] == b"3gp":
            out[i : i + 4] = b"M4A "
    return bytes(out)


def _openai_transcribe(key: str) -> str:
    global _openai
    data = _as_m4a(_read(key))
    if len(data) > config.OPENAI_STT_MAX_BYTES:
        raise ValueError("OpenAI 전사 크기 제한 초과")
    if _openai is None:
        from openai import OpenAI

        _openai = OpenAI()
    result = _openai.audio.transcriptions.create(
        model=config.OPENAI_STT_MODEL, file=(key.rsplit("/", 1)[-1], data), language="ko"
    )
    return result.text.strip()


def _server_transcribe(key: str) -> str:
    """자체 STT를 먼저 쓰고, 부하나 장애로 못 쓰면 OpenAI로 넘깁니다. 파일 자체가 잘못된 400은 넘기지 않습니다."""
    try:
        return stt_client.transcribe(key.rsplit("/", 1)[-1], _as_m4a(_read(key)))
    except stt_client.SttBadRequest:
        raise
    except stt_client.SttError as exc:
        if config.STT_FALLBACK != "openai":
            raise
        reason = type(exc).__name__
    log.warning("자체 STT 실패, OpenAI로 전환: %s", reason)
    with tracing.observe("음성 변환 대체", metadata={"engine": "openai", "reason": reason}):
        return _openai_transcribe(key)


def transcribe(rec_id: str, key: str) -> str:
    if config.STT == "server":
        return _server_transcribe(key)
    if config.STT == "transcribe":
        return _transcribe(rec_id, key)
    if config.STT == "openai":
        return _openai_transcribe(key)
    # text 모드: 업로드한 .txt를 녹취로 간주합니다. 글자가 아니면 LLM에 넘기지 않고 실패 처리합니다.
    return _read(key).decode("utf-8").strip()
