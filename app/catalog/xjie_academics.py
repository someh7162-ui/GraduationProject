"""Canonical colleges and majors used by registration and student profiles."""

ACADEMIC_META = {
    'updated_at': '2026-09-21',
    'registration_basis': '新疆工程学院2026年招生专业一览表（本、专科）',
    'note': '学生注册按2026年招生专业口径展示；新设学院待正式公布专业归属后更新。',
}


def major(name, code, kind='major', **extra):
    return {'name': name, 'code': code, 'type': kind, **extra}


ACADEMIC_UNITS = [
    {
        'code': 'safety_engineering', 'name': '安全科学与工程学院', 'student_selectable': True, 'status': 'active',
        'majors': [major('安全工程', '082901'), major('消防工程', '083102K'), major('应急技术与管理', '082902T')],
    },
    {
        'code': 'chemical_environment', 'name': '化学与环境工程学院', 'student_selectable': True, 'status': 'active',
        'majors': [
            major('化工与制药类', '0813', 'major_group', children=['化学工程与工艺', '材料科学与工程', '环境科学与工程', '精细化工', '能源化学工程']),
            major('化学工程与工艺', '081301'), major('环境科学与工程', '082501'), major('材料科学与工程', '080401'),
            major('精细化工', '081308T'), major('能源化学工程', '081304T'),
        ],
    },
    {
        'code': 'mechanical_electrical', 'name': '机电工程学院', 'student_selectable': True, 'status': 'active',
        'majors': [
            major('材料成型及控制工程', '080203'), major('焊接技术与工程', '080411T'), major('机器人工程', '080803T'),
            major('机械电子工程', '080204'), major('机械设计制造及其自动化', '080202'), major('冶金工程', '080404'),
        ],
    },
    {
        'code': 'control_engineering', 'name': '控制工程学院', 'student_selectable': True, 'status': 'active',
        'majors': [major('测控技术与仪器', '080301'), major('自动化', '080801'), major('人工智能', '080717T')],
    },
    {
        'code': 'mining_geology', 'name': '矿业工程与地质学院', 'student_selectable': True, 'status': 'active',
        'majors': [
            major('采矿工程', '081501'), major('地质工程', '081401'), major('勘查技术与工程', '081402'),
            major('矿物加工工程', '081503'), major('资源勘查工程', '081403'), major('智能采矿工程', '081507T'),
        ],
    },
    {
        'code': 'energy_engineering', 'name': '能源工程学院', 'student_selectable': True, 'status': 'active',
        'majors': [
            major('电气工程及其自动化', '080601'), major('电气工程与智能控制', '080604T'), major('能源与动力工程', '080501'),
            major('新能源科学与工程', '080503T'), major('储能科学与工程', '080504T'),
        ],
    },
    {
        'code': 'civil_engineering', 'name': '土木工程学院', 'student_selectable': True, 'status': 'active',
        'majors': [major('土木工程', '081001'), major('测绘工程', '081201'), major('铁道工程', '081007T'), major('智能建造', '081008T')],
    },
    {
        'code': 'mathematics_physics', 'name': '数理学院', 'student_selectable': True, 'status': 'active',
        'majors': [major('数学与应用数学', '070101')],
    },
    {
        'code': 'information_engineering', 'name': '信息工程学院', 'student_selectable': True, 'status': 'active',
        'majors': [
            major('数据科学与大数据技术', '080910T'), major('计算机科学与技术', '080901'), major('通信工程', '080703'),
            major('物联网工程', '080905'), major('数字媒体艺术', '130508', discipline='艺术学'),
        ],
    },
    {
        'code': 'marxism', 'name': '马克思主义学院', 'student_selectable': True, 'status': 'active',
        'majors': [major('马克思主义理论', '030504T', discipline='法学')],
    },
    {
        'code': 'economics_management', 'name': '经济管理学院', 'student_selectable': True, 'status': 'active',
        'majors': [major('能源经济', '020106T', discipline='经济学'), major('国际商务', '120205', discipline='管理学'), major('物流工程', '120602', discipline='管理学')],
    },
    {
        'code': 'aviation_industry', 'name': '航空产业学院', 'student_selectable': True, 'status': 'active',
        'majors': [major('飞行技术', '081805K'), major('飞行器运维工程', '082012T'), major('无人驾驶航空器系统工程', '082009T'), major('空间信息与数字技术', '080908T')],
    },
    {'code': 'engineering_training', 'name': '工程技能实训学院', 'student_selectable': False, 'status': 'teaching_unit', 'majors': []},
    {'code': 'culture_arts', 'name': '文化艺术学院', 'student_selectable': False, 'status': 'public_course_college', 'majors': []},
    {'code': 'continuing_education', 'name': '继续教育学院（技师培训学院）', 'student_selectable': False, 'status': 'continuing_education', 'majors': []},
    {'code': 'earth_environment', 'name': '地球科学与环境工程学院（玄武岩产业学院）', 'student_selectable': False, 'status': 'new_2026_transition', 'majors': []},
    {'code': 'artificial_intelligence', 'name': '人工智能学院（机器人产业学院）', 'student_selectable': False, 'status': 'new_2026_transition', 'majors': []},
    {'code': 'emergency_management', 'name': '应急管理学院', 'student_selectable': False, 'status': 'new_2026_transition', 'majors': []},
]

STUDENT_COLLEGES = [unit for unit in ACADEMIC_UNITS if unit['student_selectable']]
COLLEGES_BY_CODE = {unit['code']: unit for unit in ACADEMIC_UNITS}
COLLEGES_BY_NAME = {unit['name']: unit for unit in ACADEMIC_UNITS}


def get_college(value):
    normalized = (value or '').strip()
    return COLLEGES_BY_CODE.get(normalized) or COLLEGES_BY_NAME.get(normalized)


def get_major(college, value):
    normalized = (value or '').strip()
    return next((item for item in college['majors'] if item['code'] == normalized or item['name'] == normalized), None)


def resolve_student_selection(college_value, major_value):
    college = get_college(college_value)
    if not college or not college['student_selectable']:
        raise ValueError('请选择有效的学生所属学院')
    selected_major = get_major(college, major_value)
    if not selected_major:
        raise ValueError('请选择该学院下的有效专业')
    return college, selected_major
