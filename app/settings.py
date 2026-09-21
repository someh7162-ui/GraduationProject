"""Fail-fast runtime configuration; secrets never appear in error output."""
import os
from urllib.parse import urlsplit


def jwt_secret():
    value = os.getenv('JWT_SECRET', '')
    if len(value) < 32 or value.lower() in {'change-me-in-production', 'dev-secret'}:
        raise RuntimeError('JWT_SECRET 必须配置为至少 32 字符的随机密钥；运行 python scripts/init_local_env.py')
    return value


def cors_origins():
    values = [v.strip().rstrip('/') for v in os.getenv('CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173').split(',') if v.strip()]
    if not values:
        raise RuntimeError('CORS_ORIGINS 不能为空')
    for value in values:
        url = urlsplit(value)
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.path or url.query or url.fragment or '*' in value:
            raise RuntimeError('CORS_ORIGINS 必须是明确的 HTTP/HTTPS origin，不允许通配符')
    return values
