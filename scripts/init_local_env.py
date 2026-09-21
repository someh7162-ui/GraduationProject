"""Create/repair local JWT configuration without displaying its secret."""
import re
import secrets
from pathlib import Path


def main():
    path = Path(__file__).resolve().parents[1] / '.env'
    source = path.read_text(encoding='utf-8') if path.exists() else ''
    match = re.search(r'^JWT_SECRET=(.*)$', source, re.MULTILINE)
    value = match.group(1).strip().strip('"\'') if match else ''
    if len(value) >= 32:
        print('JWT_SECRET 已配置，保持不变。')
        return
    line = 'JWT_SECRET=' + secrets.token_urlsafe(48)
    source = re.sub(r'^JWT_SECRET=.*$', line, source, flags=re.MULTILINE) if match else source.rstrip() + '\n' + line + '\n'
    path.write_text(source.lstrip('\n'), encoding='utf-8')
    print('本地 JWT_SECRET 已安全生成；旧登录令牌需要重新登录。')


if __name__ == '__main__':
    main()
