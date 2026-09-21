"""Authenticated administrative provisioning and auditable scope assignments."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.access import metadata, classes, audit, can_manage_class, require_class, profile_identity
from app.catalog.xjie_academics import get_college, resolve_student_selection
from app.academic import store


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ClassCreate(Strict):
    name: str = Field(min_length=1, max_length=120, pattern=r'\S')
    college_code: str


class StaffCreate(Strict):
    username: str = Field(min_length=3, max_length=40, pattern=r'^[A-Za-z0-9_]+$')
    name: str = Field(min_length=1, max_length=120, pattern=r'\S')
    password: str = Field(min_length=12, max_length=256)
    role: Literal['teacher', 'counselor', 'academic_admin', 'admin']
    college_code: str = ''
    managed_classes: list[str] = Field(default_factory=list, max_length=100)


class AccessUpdate(Strict):
    role: Literal['student', 'teacher', 'counselor', 'academic_admin', 'admin']
    college_code: str = ''
    managed_classes: list[str] = Field(default_factory=list, max_length=100)
    class_name: str = ''


def register(app, engine, users, current, hp, pub, jt, now):
    with engine.begin() as conn:
        metadata.create_all(conn)
    router = APIRouter()

    def admin(user=Depends(current)):
        if user['role'] != 'admin':
            raise HTTPException(403, '仅系统管理员可维护账号与授权')
        return user

    def audit_change(conn, actor, action, target, details):
        conn.execute(audit.insert().values(actor_id=actor['id'], action=action, target=str(target), details=jt(details), created_at=now()))

    def scope_values(conn, body):
        college = get_college(body.college_code) if body.college_code else None
        if body.college_code and not college:
            raise HTTPException(422, '学院不存在')
        if body.role == 'academic_admin' and not college:
            raise HTTPException(422, '学院管理员必须指定学院')
        names = sorted(set(body.managed_classes))
        if names and body.role != 'counselor':
            raise HTTPException(422, '只有辅导员可分配负责班级')
        for name in names:
            if not conn.execute(select(classes).where(classes.c.name == name)).first():
                raise HTTPException(422, '负责班级不存在')
        return dict(role=body.role, college=college['name'] if college else '', college_code=college['code'] if college else '', managed_classes=jt(names))

    @router.get('/admin/users')
    def list_users(q: str = '', limit: int = Query(100, ge=1, le=200), user=Depends(admin)):
        query = select(users).order_by(users.c.id)
        if q:
            query = query.where(users.c.username.contains(q, autoescape=True))
        with engine.connect() as conn:
            return [pub(row) for row in conn.execute(query.limit(limit)).mappings()]

    @router.post('/admin/users')
    def create_staff(body: StaffCreate, user=Depends(admin)):
        try:
            with engine.begin() as conn:
                values = scope_values(conn, body)
                identifier = conn.execute(users.insert().values(**values, username=body.username, name=body.name.strip(), password_hash=hp(body.password), major='', major_code='', grade='', interests='[]', onboarding_completed=False, is_active=True, created_at=now())).inserted_primary_key[0]
                audit_change(conn, user, 'create_staff', identifier, [body.role, body.college_code, body.managed_classes])
                return pub(conn.execute(select(users).where(users.c.id == identifier)).mappings().one())
        except IntegrityError:
            raise HTTPException(409, '用户名已存在')

    @router.patch('/admin/users/{identifier}/access')
    def update_access(identifier: int, body: AccessUpdate, user=Depends(admin)):
        if identifier == user['id']:
            raise HTTPException(409, '不可通过此入口修改自己的授权')
        with engine.begin() as conn:
            target = conn.execute(select(users).where(users.c.id == identifier)).mappings().first()
            if not target:
                raise HTTPException(404, '用户不存在')
            values = scope_values(conn, body)
            if body.role == 'student':
                if body.college_code != target['college_code']:
                    raise HTTPException(422, '学生学院必须与注册专业保持一致')
                try:
                    resolve_student_selection(target['college_code'], target['major_code'])
                except ValueError:
                    raise HTTPException(422, '该账号缺少有效学生专业，不可直接转为学生')
                values.update(college=target['college'], college_code=target['college_code'])
            if body.class_name:
                if body.role != 'student':
                    raise HTTPException(422, '仅学生设置所属班级')
                record = require_class(conn, user, body.class_name)
                if record['college_code'] != target['college_code']:
                    raise HTTPException(422, '班级学院与学生学院不一致')
            values['class_name'] = body.class_name
            conn.execute(users.update().where(users.c.id == identifier).values(**values))
            audit_change(conn, user, 'update_access', identifier, [dict(target_role=target['role'], target_college=target['college_code'], target_classes=target['managed_classes'], target_class=target['class_name']), values])
            return pub(conn.execute(select(users).where(users.c.id == identifier)).mappings().one())

    @router.get('/classes')
    def list_classes(user=Depends(current)):
        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(select(classes).order_by(classes.c.name)).mappings() if can_manage_class(user, row)]

    @router.post('/admin/classes')
    def create_class(body: ClassCreate, user=Depends(admin)):
        college = get_college(body.college_code)
        if not college:
            raise HTTPException(422, '学院不存在')
        try:
            with engine.begin() as conn:
                conn.execute(classes.insert().values(name=body.name.strip(), college_code=college['code']))
                audit_change(conn, user, 'create_class', body.name, [college['code']])
        except IntegrityError:
            raise HTTPException(409, '班级名称已存在')
        return {'name': body.name.strip(), 'college_code': college['code']}

    @router.get('/admin/audit')
    def audit_log(user=Depends(admin)):
        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(select(audit).order_by(audit.c.id.desc()).limit(100)).mappings()]

    @router.get('/management/students')
    def managed_students(user=Depends(current)):
        if user['role'] not in {'admin', 'academic_admin', 'counselor'}:
            raise HTTPException(403, '无权查询学生档案')
        with engine.connect() as conn:
            directory = {r['name']: r for r in conn.execute(select(classes)).mappings()}
            rows = conn.execute(select(users).where(users.c.role == 'student')).mappings()
            return [{k: row[k] for k in ('id', 'name', 'college', 'major', 'grade', 'class_name')} for row in rows
                    if user['role'] == 'admin' or (user['role'] == 'academic_admin' and bool(user.get('college_code')) and row['college_code'] == user['college_code']) or (user['role'] == 'counselor' and row['class_name'] in directory and can_manage_class(user, directory[row['class_name']]))]

    @router.get('/management/students/{identifier}/profile')
    def student_profile(identifier: int, user=Depends(current)):
        if identifier not in {row['id'] for row in managed_students(user)}:
            raise HTTPException(404, '学生不存在或不在负责范围')
        with engine.begin() as conn:
            record = store.profile(conn, identifier)
            record['payload'] = profile_identity(conn, identifier, record['payload'])
            audit_change(conn, user, 'read_student_profile', identifier, [])
            return record

    app.include_router(router)
