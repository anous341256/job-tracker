from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet():
    key = settings.AI_CREDENTIAL_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured('请先配置 AI_CREDENTIAL_ENCRYPTION_KEY。')
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured('AI_CREDENTIAL_ENCRYPTION_KEY 不是有效的 Fernet 密钥。') from exc


def encrypt_api_key(value): return _fernet().encrypt(value.encode()).decode()


def decrypt_api_key(value):
    if not value: return ''
    try: return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc: raise ImproperlyConfigured('无法解密 OpenAI API Key，请重新保存。') from exc
