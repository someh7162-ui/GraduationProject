"""Public academic catalog endpoints."""

from fastapi import APIRouter, HTTPException

from app.catalog.xjie_academics import ACADEMIC_META, STUDENT_COLLEGES, get_college


from app.content_types import CONTENT_TYPES

router = APIRouter(prefix='/catalog', tags=['catalog'])


@router.get('/content-types')
def content_types():
    return [{'code': code, 'name': name} for code, name in CONTENT_TYPES.items()]


@router.get('/colleges')
def colleges():
    return {
        'meta': ACADEMIC_META,
        'items': [{'code': item['code'], 'name': item['name']} for item in STUDENT_COLLEGES],
    }


@router.get('/colleges/{college_code}/majors')
def majors(college_code: str):
    college = get_college(college_code)
    if not college or not college['student_selectable']:
        raise HTTPException(404, '学院不存在或暂不开放学生注册')
    return {
        'college': {'code': college['code'], 'name': college['name']},
        'items': college['majors'],
    }


def register(app):
    app.include_router(router)
