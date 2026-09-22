from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Source(Strict):
    document_id: str | None = None
    filename: str = ''
    locator: str


class Course(Strict):
    academic_year: str = Field(pattern=r'^\d{4}-\d{4}$')
    term: int = Field(ge=1, le=3)
    name: str = Field(min_length=1, max_length=150)
    category: str = ''
    credits: float | None = Field(default=None, ge=0, le=100)
    score: float = Field(ge=0, le=100)
    sources: list[Source] = Field(default_factory=list)


class CourseCorrection(Strict):
    course: Course
    reason: str = Field(min_length=2, max_length=500)
    revision: int


class Fact(Strict):
    value: Any
    academic_year: str | None = None
    sources: list[Source] = Field(default_factory=list)
    confirmed: bool = False


class ConfirmImport(Strict):
    courses: list[Course] = Field(max_length=500)
    facts: dict[str, Fact] = Field(default_factory=dict)


class ProfileUpdate(Strict):
    facts: dict[str, Fact]


class ClassScoreStudent(Strict):
    student_id: str = Field(pattern=r'^\d{6,20}$')
    name: str = Field(min_length=1, max_length=80)
    scores: list[float] = Field(default_factory=list, max_length=40)
    reported_average: float | None = Field(default=None, ge=0, le=100)
    reported_total: float | None = Field(default=None, ge=0)
    reported_rank: int | None = Field(default=None, ge=1)
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode='after')
    def validate_scores(self):
        if any(score < 0 or score > 100 for score in self.scores):
            raise ValueError('课程成绩必须位于 0 到 100 之间')
        return self


class ClassScoreSheet(Strict):
    academic_year: str = Field(pattern=r'^\d{4}-\d{4}$')
    term: int = Field(ge=1, le=3)
    class_name: str = Field(min_length=1, max_length=120)
    source_name: str = Field(default='', max_length=255)
    course_names: list[str] = Field(default_factory=list, max_length=40)
    students: list[ClassScoreStudent] = Field(default_factory=list, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=500)


class ClassRankingConfirm(Strict):
    sheets: list[ClassScoreSheet] = Field(min_length=2, max_length=6)
    rank_method: Literal['competition'] = 'competition'


class Clause(Strict):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1)
    locator: str = Field(min_length=1)


class Rule(Strict):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    clause_id: str
    field: str = Field(pattern=r'^[a-z][a-z0-9_]{0,79}$')
    operator: Literal['eq', 'le', 'lt', 'ge', 'gt', 'in']
    value: Any
    scope: str | None = None
    year_bound: bool = True


class Branch(Strict):
    id: str
    label: str
    rules: list[Rule] = Field(min_length=1)


class Requirement(Strict):
    text: str = Field(min_length=1)
    clause_id: str


class Deadline(Strict):
    name: str = Field(min_length=1, max_length=120)
    due_at: str
    audience: Literal['student', 'class', 'college', 'school']
    clause_id: str


class Quota(Strict):
    category: str = Field(min_length=1, max_length=80)
    count: int = Field(ge=0)
    clause_id: str


class PolicyDraft(Strict):
    title: str = Field(min_length=1, max_length=200)
    school: str = Field(min_length=1)
    scholarship: str = Field(default='国家奖学金', min_length=1)
    selection_year: int = Field(ge=2000, le=2200)
    academic_year: str = Field(pattern=r'^\d{4}-\d{4}$')
    audience: str = Field(min_length=1)
    source_url: str = ''
    effective_from: str | None = None
    effective_until: str | None = None
    application_start: str | None = None
    application_end: str | None = None
    clauses: list[Clause] = Field(default_factory=list)
    common_rules: list[Rule] = Field(default_factory=list)
    branches: list[Branch] = Field(default_factory=list)
    materials: list[Requirement] = Field(default_factory=list)
    steps: list[Requirement] = Field(default_factory=list)
    deadlines: list[Deadline] = Field(default_factory=list)
    quotas: list[Quota] = Field(default_factory=list)
    course_categories: list[str] = Field(default_factory=list)
    missing_attachments: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    reviewed: bool = False

    @model_validator(mode='after')
    def validate_references(self):
        ids = [c.id for c in self.clauses]
        rules = self.common_rules + [r for b in self.branches for r in b.rules]
        if len(ids) != len(set(ids)) or len({r.id for r in rules}) != len(rules):
            raise ValueError('条款和规则编号必须唯一')
        referenced = [*rules, *self.materials, *self.steps, *self.deadlines, *self.quotas]
        if any(r.clause_id not in ids for r in referenced):
            raise ValueError('规则、材料和步骤必须引用存在的条款')
        for r in rules:
            if r.operator in ('le', 'lt', 'ge', 'gt') and (isinstance(r.value, bool) or not isinstance(r.value, (int, float))):
                raise ValueError('数值比较规则必须提供数值阈值')
            if r.operator == 'in' and not isinstance(r.value, list):
                raise ValueError('in 规则必须提供列表')
            if r.field.endswith('_rank_ratio') and not r.scope:
                raise ValueError('排名规则必须明确排名范围 scope')
        from datetime import datetime
        for field in ('effective_from', 'effective_until', 'application_start', 'application_end'):
            value = getattr(self, field)
            if value:
                datetime.fromisoformat(value.replace('Z', '+00:00'))
        for deadline in self.deadlines:
            datetime.fromisoformat(deadline.due_at.replace('Z', '+00:00'))
        for start, end in ((self.application_start, self.application_end), (self.effective_from, self.effective_until)):
            if start and end and start[:10] > end[:10]:
                raise ValueError('结束日期不能早于开始日期')
        return self


class SessionCreate(Strict):
    school: str = Field(default='新疆工程学院', min_length=1)
    scholarship: str = Field(default='国家奖学金', min_length=1)
    selection_year: int | None = Field(default=None, ge=2000, le=2200)
    academic_year: str | None = Field(default=None, pattern=r'^\d{4}-\d{4}$')


class Message(Strict):
    text: str = Field(default='', max_length=4000)
    facts: dict[str, Fact] = Field(default_factory=dict)
    selection_year: int | None = Field(default=None, ge=2000, le=2200)
    academic_year: str | None = Field(default=None, pattern=r'^\d{4}-\d{4}$')
    deep_think: bool = False
    web_search: bool = False


class SessionRename(Strict):
    title: str = Field(min_length=1, max_length=80)
