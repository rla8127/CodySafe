"""음성 저장소와 STT. 기기에 AWS 자격 증명을 두지 않도록 S3 업로드는 presigned URL만 내려줍니다."""
import json
import time
from pathlib import Path

from . import config

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        import boto3
        from botocore.config import Config

        _s3 = boto3.client(
            "s3",
            region_name=config.AWS_REGION,
            endpoint_url=f"https://s3.{config.AWS_REGION}.amazonaws.com",
            config=Config(signature_version="s3v4"),
        )
    return _s3


def local_path(key: str) -> Path:
    return config.LOCAL_AUDIO_DIR / key.replace("/", "_")


def upload_url(key: str, content_type: str, upload_token: str, rec_id: str) -> str:
    if config.STORAGE == "s3":
        return s3().generate_presigned_url(
            "put_object",
            Params={"Bucket": config.S3_BUCKET, "Key": key, "ContentType": content_type},
            ExpiresIn=3600,
        )
    return f"{config.PUBLIC_BASE_URL}/v1/local-upload/{rec_id}?token={upload_token}"


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


def transcribe(rec_id: str, key: str) -> str:
    if config.STT == "transcribe":
        return _transcribe(rec_id, key)
    # text 모드: 업로드한 .txt를 녹취로 간주합니다.
    if config.STORAGE == "s3":
        data = s3().get_object(Bucket=config.S3_BUCKET, Key=key)["Body"].read()
    else:
        data = local_path(key).read_bytes()
    return data.decode("utf-8", errors="ignore").strip()
