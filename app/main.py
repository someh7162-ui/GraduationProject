"""Application entry point; legacy exports remain compatible with import scripts."""
from app.campus import *  # noqa: F401,F403
from app.academic.api import register as register_academic
from app.catalog.api import register as register_catalog

app.title = "新疆工程学院 Campus AI 校园智能信息服务系统"
register_catalog(app)
register_academic(app, engine, current)

from app.admin import register as register_admin
register_admin(app, engine, users, current, hp, pub, jt, now)
