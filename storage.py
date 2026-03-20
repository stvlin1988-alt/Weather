"""Cloudflare R2 storage helper (S3-compatible via boto3)."""
import os
import io
import uuid
from flask import current_app

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


def _get_client():
    cfg = current_app.config
    return boto3.client(
        "s3",
        endpoint_url=cfg["R2_ENDPOINT_URL"],
        aws_access_key_id=cfg["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=cfg["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def upload_face_photo(image_bytes: bytes, user_id: int) -> str | None:
    """
    Upload face photo JPEG bytes to Cloudflare R2 private bucket.
    Returns the object key (not a public URL — use signed URL for access).
    Returns None if R2 is not configured or boto3 unavailable.
    """
    if not BOTO3_AVAILABLE:
        return None

    cfg = current_app.config
    if not cfg.get("R2_ENDPOINT_URL"):
        return None

    bucket = cfg["R2_BUCKET_NAME"]
    filename = f"faces/{user_id}/{uuid.uuid4().hex}.jpg"

    client = _get_client()
    client.put_object(
        Bucket=bucket,
        Key=filename,
        Body=image_bytes,
        ContentType="image/jpeg",
    )
    return filename


def get_signed_url(object_key: str, expires_in: int = 3600) -> str | None:
    """
    Generate a pre-signed URL for a private R2 object (valid for expires_in seconds).
    """
    if not BOTO3_AVAILABLE or not object_key:
        return None

    cfg = current_app.config
    if not cfg.get("R2_ENDPOINT_URL"):
        return None

    client = _get_client()
    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": cfg["R2_BUCKET_NAME"], "Key": object_key},
            ExpiresIn=expires_in,
        )
        return url
    except ClientError:
        return None
