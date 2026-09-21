"""Explicit local operator command; there is no public role-escalation endpoint."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.campus import engine, users
from sqlalchemy import select


def main():
    parser = argparse.ArgumentParser(description='设置已有账号的政策管理员权限')
    parser.add_argument('username')
    parser.add_argument('--revoke', action='store_true')
    args = parser.parse_args()
    with engine.begin() as conn:
        user = conn.execute(select(users).where(users.c.username == args.username)).mappings().first()
        if not user or not user['is_active']:
            parser.error('账号不存在或已停用，请先注册一个账号')
        role = 'student' if args.revoke else 'admin'
        conn.execute(users.update().where(users.c.id == user['id']).values(role=role))
    print(f'{args.username}: {role}')


if __name__ == '__main__':
    main()
