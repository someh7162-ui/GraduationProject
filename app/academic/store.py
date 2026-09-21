"""JSON snapshots with transactional ownership checks, portable to MySQL/SQLite."""
import json
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import MetaData, Table, Column, String, Integer, Text, select, update

metadata = MetaData()
migrations = Table('academic_schema_versions', metadata, Column('version', Integer, primary_key=True), Column('applied_at', String(40)))


def entity(name):
    return Table(name, metadata, Column('id', String(36), primary_key=True),
                 Column('user_id', Integer, nullable=False, index=True),
                 Column('status', String(40), nullable=False),
                 Column('revision', Integer, nullable=False, default=0),
                 Column('payload', Text, nullable=False), Column('created_at', String(40), nullable=False))


documents = entity('academic_documents')
profiles = entity('academic_profiles')
policies = entity('academic_policies')
sessions = entity('academic_sessions')
assessments = entity('academic_assessments')
rankings = entity('academic_class_rankings')


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def migrate(engine):
    with engine.begin() as conn:
        metadata.create_all(conn)
        if conn.execute(select(migrations).where(migrations.c.version == 1)).first() is None:
            conn.execute(migrations.insert().values(version=1, applied_at=now()))


def recover(engine):
    with engine.begin() as conn:
        conn.execute(sessions.update().where(sessions.c.status == 'running').values(status='retryable'))


def decode(row):
    data = dict(row)
    data['payload'] = json.loads(data['payload'])
    return data


def get(conn, table, identifier, user_id=None):
    query = select(table).where(table.c.id == identifier)
    if user_id is not None:
        query = query.where(table.c.user_id == user_id)
    row = conn.execute(query).mappings().first()
    if row is None:
        raise HTTPException(404, '记录不存在')
    return decode(row)


def listing(conn, table, user_id=None):
    query = select(table)
    if user_id is not None:
        query = query.where(table.c.user_id == user_id)
    return [decode(r) for r in conn.execute(query.order_by(table.c.created_at.desc())).mappings()]


def create(conn, table, user_id, payload, status='draft', identifier=None):
    identifier = identifier or str(uuid.uuid4())
    conn.execute(table.insert().values(id=identifier, user_id=user_id, status=status, revision=0, payload=dump(payload), created_at=now()))
    return get(conn, table, identifier, user_id)


def save(conn, table, record, payload, status=None):
    result = conn.execute(update(table).where(table.c.id == record['id'], table.c.revision == record['revision']).values(
        payload=dump(payload), status=status or record['status'], revision=record['revision'] + 1))
    if result.rowcount != 1:
        raise HTTPException(409, '记录已更新，请刷新后重试')
    return get(conn, table, record['id'], record['user_id'])


def profile(conn, user_id):
    rows = listing(conn, profiles, user_id)
    return rows[0] if rows else create(conn, profiles, user_id, {'courses': [], 'facts': {}}, 'confirmed', identifier=str(user_id))
