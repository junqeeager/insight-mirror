"""账号安全工具：密码哈希、会话令牌、数据源凭据加密。"""

import base64
import hashlib
import hmac
import logging
import os
import secrets

logger = logging.getLogger("core.auth")

_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_TOKEN_BYTES = 32
_FALLBACK_SECRET = "dev-only-fallback-secret-do-not-use-in-production"

_SENSITIVE_KEYWORDS = ("cookie", "csrf", "token", "secret")


def get_encryption_key() -> bytes:
    """从 APP_SECRET_KEY 派生 Fernet 兼容的 32 字节 key。"""
    secret = os.environ.get("APP_SECRET_KEY", "")
    if not secret:
        logger.warning("未设置 APP_SECRET_KEY，使用开发用兜底密钥（生产环境请配置）")
        secret = _FALLBACK_SECRET
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def hash_password(password: str) -> str:
    """scrypt 加盐哈希，格式：scrypt$N$r$p$salt$digest。"""
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """常量时间校验 scrypt 密码哈希。"""
    try:
        algo, n, r, p, salt, expected = encoded.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt.encode("utf-8"),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(digest.hex(), expected)
    except Exception:
        return False


def generate_session_token() -> tuple:
    """生成会话 token，返回 (明文 token, SHA-256 哈希)。"""
    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    """对会话 token 取哈希，数据库只存哈希。"""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def encrypt_value(value: str) -> str:
    """用 APP_SECRET_KEY 派生的 Fernet 密钥加密字符串。"""
    from cryptography.fernet import Fernet

    return "enc:" + Fernet(get_encryption_key()).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(blob: str) -> str:
    """解密 encrypt_value 的结果；非 enc: 前缀原样返回。"""
    if not blob.startswith("enc:"):
        return blob
    from cryptography.fernet import Fernet

    return Fernet(get_encryption_key()).decrypt(blob[4:].encode("utf-8")).decode("utf-8")


def encrypt_config(config: dict) -> dict:
    """加密数据源配置中的敏感字段（cookie/csrf/token/secret）。"""
    out = {}
    for key, value in config.items():
        if (
            isinstance(value, str)
            and value
            and any(kw in key.lower() for kw in _SENSITIVE_KEYWORDS)
        ):
            out[key] = encrypt_value(value)
        else:
            out[key] = value
    return out


def decrypt_config(config: dict) -> dict:
    """解密数据源配置中的加密字段，解密失败按空字符串处理。"""
    out = {}
    for key, value in config.items():
        if isinstance(value, str) and value.startswith("enc:"):
            try:
                out[key] = decrypt_value(value)
            except Exception:
                logger.warning("凭据解密失败: %s", key)
                out[key] = ""
        else:
            out[key] = value
    return out


def mask_config(config: dict) -> dict:
    """返回用于展示的配置（敏感字段只显示 ***）。"""
    return {
        key: ("***" if any(kw in key.lower() for kw in _SENSITIVE_KEYWORDS) and value else value)
        for key, value in config.items()
    }
