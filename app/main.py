"""Application entry point; legacy exports remain compatible with import scripts."""
from app.campus import *  # noqa: F401,F403
from app.academic.api import register as register_academic

app.title = "教务智能服务系统"
register_academic(app, engine, current)
