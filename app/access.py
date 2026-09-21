"""Staff scopes are assigned by admins; ownership alone never grants class access."""
import copy
from sqlalchemy import MetaData, Table, Column, String, Text, Integer, select, text
from fastapi import HTTPException
from app.recommendation import array

metadata = MetaData()
classes = Table('campus_classes', metadata, Column('name', String(120), primary_key=True), Column('college_code', String(80), nullable=False))
audit = Table('access_audit', metadata, Column('id', Integer, primary_key=True, autoincrement=True), Column('actor_id', Integer), Column('action', String(40)), Column('target', String(120)), Column('details', Text), Column('created_at', String(40)))
IDENTITY_FIELDS = {'college', 'college_code', 'major', 'major_code', 'grade', 'class_name', 'grade_level'}


def can_manage_class(user, record):
    if user.get('role') == 'admin':
        return True
    if not record:
        return False
    if user.get('role') == 'counselor':
        return record['name'] in array(user.get('managed_classes'))
    return user.get('role') == 'academic_admin' and bool(user.get('college_code')) and record['college_code'] == user['college_code']


def require_class(conn, user, name):
    record = conn.execute(select(classes).where(classes.c.name == name)).mappings().first()
    if not record:
        raise HTTPException(422, '班级未登记，请由管理员先维护班级目录')
    if not can_manage_class(user, record):
        raise HTTPException(403, '无权管理该班级')
    return record


def profile_identity(conn, user_id, payload):
    account = conn.execute(text('SELECT college, college_code, major, major_code, grade, class_name FROM users WHERE id=:id'), {'id': user_id}).mappings().first()
    data = copy.deepcopy(payload)
    data.setdefault('facts', {})
    # Remove stale or user-supplied identity before applying authoritative account data.
    for key in IDENTITY_FIELDS:
        data['facts'].pop(key, None)
    if account:
        values = dict(account)
        values['grade_level'] = {'大一': 1, '大二': 2, '大三': 3, '大四': 4}.get(account['grade'])
        for key, value in values.items():
            if value is not None and value != '':
                data['facts'][key] = {'value': value, 'academic_year': None, 'confirmed': True,
                                      'sources': [{'document_id': None, 'filename': '统一账户身份', 'locator': '账户信息 / 管理员班级分配'}]}
    return data


def validate_identity(facts, user):
    expected = dict(user)
    expected['grade_level'] = {'大一': 1, '大二': 2, '大三': 3, '大四': 4}.get(user.get('grade'))
    for key in IDENTITY_FIELDS.intersection(facts):
        value = facts[key].value if hasattr(facts[key], 'value') else facts[key]['value']
        if value != expected.get(key):
            raise HTTPException(422, f'{key} 与账户身份不一致，请联系管理员核对')
