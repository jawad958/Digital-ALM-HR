"""Cloudflare R2 (S3-compatible) storage for CVs, offer PDFs, passports, etc.

Everything uploaded gets a UUID key, so we never trust client-supplied filenames.
Presigned URLs are short-lived (15 min) for candidate downloads of their offer.
"""

from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import boto3
from botocore.client import Config

from alpago.core.config import settings


_client = None


def _s3():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.r2_endpoint or f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.r2_access_key,
            aws_secret_access_key=settings.r2_secret_key,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _client


def upload_bytes(data: bytes, *, folder: str, content_type: str, ext: str = "bin") -> str:
    """Upload bytes and return the storage key."""
    key = f"{folder}/{uuid4()}.{ext.lstrip('.')}"
    _s3().upload_fileobj(
        BytesIO(data),
        settings.r2_bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return key


def presigned_download(key: str, *, expires_in: int = 900) -> str:
    return _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.r2_bucket, "Key": key},
        ExpiresIn=expires_in,
    )
