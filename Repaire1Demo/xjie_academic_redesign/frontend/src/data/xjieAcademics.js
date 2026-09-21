export const XJIE_ACADEMIC_META = {
  updatedAt: '2026-09-21',
  registrationBasis: '新疆工程学院2026年招生专业一览表（本、专科）',
  note: '学生注册按2026年招生专业口径展示；2026年新设学院尚未在当年招生专业表中形成稳定专业归属，因此只作为组织机构信息保留。',
}

const major = (name, code, extra = {}) => ({ name, code, type: 'major', ...extra })
const group = (name, code, children = []) => ({ name, code, type: 'major_group', children })

export const XJIE_ACADEMIC_UNITS = [
  {
    name: '安全科学与工程学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      major('安全工程', '082901'),
      major('消防工程', '083102K'),
      major('应急技术与管理', '082902T'),
    ],
  },
  {
    name: '化学与环境工程学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      group('化工与制药类', '0813', ['化学工程与工艺', '材料科学与工程', '环境科学与工程', '精细化工', '能源化学工程']),
      major('化学工程与工艺', '081301'),
      major('环境科学与工程', '082501'),
      major('材料科学与工程', '080401'),
      major('精细化工', '081308T'),
      major('能源化学工程', '081304T'),
    ],
  },
  {
    name: '机电工程学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      major('材料成型及控制工程', '080203'),
      major('焊接技术与工程', '080411T'),
      major('机器人工程', '080803T'),
      major('机械电子工程', '080204'),
      major('机械设计制造及其自动化', '080202'),
      major('冶金工程', '080404'),
    ],
  },
  {
    name: '控制工程学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      major('测控技术与仪器', '080301'),
      major('自动化', '080801'),
      major('人工智能', '080717T'),
    ],
  },
  {
    name: '矿业工程与地质学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      major('采矿工程', '081501'),
      major('地质工程', '081401'),
      major('勘查技术与工程', '081402'),
      major('矿物加工工程', '081503'),
      major('资源勘查工程', '081403'),
      major('智能采矿工程', '081507T'),
    ],
  },
  {
    name: '能源工程学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      major('电气工程及其自动化', '080601'),
      major('电气工程与智能控制', '080604T'),
      major('能源与动力工程', '080501'),
      major('新能源科学与工程', '080503T'),
      major('储能科学与工程', '080504T'),
    ],
  },
  {
    name: '土木工程学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      major('土木工程', '081001'),
      major('测绘工程', '081201'),
      major('铁道工程', '081007T'),
      major('智能建造', '081008T'),
    ],
  },
  {
    name: '数理学院',
    studentSelectable: true,
    status: 'active',
    majors: [major('数学与应用数学', '070101')],
  },
  {
    name: '信息工程学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      major('数据科学与大数据技术', '080910T'),
      major('计算机科学与技术', '080901'),
      major('通信工程', '080703'),
      major('物联网工程', '080905'),
      major('数字媒体艺术', '130508', { discipline: '艺术学' }),
    ],
  },
  {
    name: '马克思主义学院',
    studentSelectable: true,
    status: 'active',
    majors: [major('马克思主义理论', '030504T', { discipline: '法学' })],
  },
  {
    name: '经济管理学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      major('能源经济', '020106T', { discipline: '经济学' }),
      major('国际商务', '120205', { discipline: '管理学' }),
      major('物流工程', '120602', { discipline: '管理学' }),
    ],
  },
  {
    name: '航空产业学院',
    studentSelectable: true,
    status: 'active',
    majors: [
      major('飞行技术', '081805K'),
      major('飞行器运维工程', '082012T'),
      major('无人驾驶航空器系统工程', '082009T'),
      major('空间信息与数字技术', '080908T'),
    ],
  },

  // 以下学院/教学单位在学校官网可查，但没有出现在2026年普通本科招生专业学院分组中。
  {
    name: '工程技能实训学院',
    studentSelectable: false,
    status: 'teaching_unit',
    majors: [],
    note: '承担工程认知、基础工业、先进制造等实践教学，不作为2026普通本科招生专业归属学院。',
  },
  {
    name: '文化艺术学院',
    studentSelectable: false,
    status: 'public_course_college',
    majors: [],
    note: '官网明确为公共课学院，目前没有自己的专业。',
  },
  {
    name: '继续教育学院（技师培训学院）',
    studentSelectable: false,
    status: 'continuing_education',
    majors: [],
    note: '继续教育与技师培训单位，不纳入普通本科学生专业选择。',
  },

  // 2026-06-25 新揭牌学院。学校2026招生专业表尚未给出稳定的本科招生专业归属，学生注册暂不直接选择。
  {
    name: '地球科学与环境工程学院（玄武岩产业学院）',
    studentSelectable: false,
    status: 'new_2026_transition',
    majors: [],
    note: '2026年6月揭牌，围绕应用地质、生态环境、玄武岩新材料建设；待学校正式公布专业归属后再进入学生注册选项。',
  },
  {
    name: '人工智能学院（机器人产业学院）',
    studentSelectable: false,
    status: 'new_2026_transition',
    majors: [],
    note: '2026年6月揭牌，围绕智慧矿山、智慧能源、智能制造建设；待学校正式公布专业归属后再进入学生注册选项。',
  },
  {
    name: '应急管理学院',
    studentSelectable: false,
    status: 'new_2026_transition',
    majors: [],
    note: '2026年6月揭牌，依托安全科学与工程学院、经济管理学院运行；应急管理专业截至2026年9月仍处于拟新增本科专业论证阶段。',
  },
]

export const XJIE_STUDENT_COLLEGES = XJIE_ACADEMIC_UNITS.filter(unit => unit.studentSelectable)

export function getXjieCollege(name) {
  return XJIE_ACADEMIC_UNITS.find(unit => unit.name === name) || null
}

export function getXjieMajors(name) {
  return getXjieCollege(name)?.majors || []
}
