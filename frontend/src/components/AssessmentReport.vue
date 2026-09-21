<script setup>
import { computed } from 'vue'
const props = defineProps({ assessment: Object })
const data = computed(() => props.assessment.payload)
const report = computed(() => data.value.report)
const labels = {pass:'满足', fail:'不满足', unknown:'待核实'}
const windows = {open:'申请窗口开放', closed:'申请窗口已结束', not_started:'申请尚未开始', unknown:'申请时间待核实'}
function display(value) { return typeof value === 'boolean' ? (value ? '是' : '否') : value == null ? '待补充' : typeof value === 'object' ? JSON.stringify(value) : value }
const operators = {eq:'等于', le:'不超过',lt:'小于',ge:'不低于',gt:'大于',in:'属于'}
const rows = computed(() => [...report.value.common_conditions,...report.value.branches.flatMap(b => b.conditions.map(c=>({...c,branch:b.label})))])
</script>
<template><article class="academic-card assessment-report">
  <div class="report-heading"><div><p class="eyebrow blue">资格初评</p><h2>{{report.conclusion}}</h2></div><span>{{windows[report.application_window]}}</span></div>
  <p>{{data.policy_snapshot.title}} · {{data.policy_snapshot.selection_year}} 年评选 · {{data.policy_snapshot.academic_year}} 学年</p>
  <p class="muted">{{report.notice}}</p>
  <div class="table-scroll"><table><thead><tr><th>条件</th><th>政策要求</th><th>个人情况</th><th>核验</th></tr></thead><tbody>
    <tr v-for="row in rows" :key="row.rule_id"><td>{{row.label}}<small v-if="row.branch" class="source-line">分支：{{row.branch}}</small></td><td>{{operators[row.operator]}} {{display(row.expected)}}<details><summary>政策依据 · {{row.clause.locator}}</summary><p>{{row.clause.text}}</p></details></td><td>{{display(row.actual)}}<details v-if="row.evidence.length"><summary>个人材料依据</summary><p v-for="(e,i) in row.evidence" :key="i">{{e.filename}} {{e.locator}}</p></details></td><td :class="`condition-${row.status}`">{{labels[row.status]}}</td></tr>
  </tbody></table></div>
  <p v-for="branch in report.branches" :key="branch.id">{{branch.label}}：{{labels[branch.status]}}</p>
  <h3>计算结果</h3><p>课程 {{report.metrics.course_count}} 门；总分 {{report.metrics.total_score}}；总学分 {{report.metrics.total_credits ?? '待补充'}}；算术均分 {{report.metrics.average?.toFixed(4) ?? '待补充'}}；加权均分 {{report.metrics.weighted_average?.toFixed(4) ?? '待补充'}}。</p>
  <p>当前年级：{{report.metrics.grade_level ?? '待补充'}}；挂科课程：{{report.metrics.failed_course_count}} 门；最低单科成绩：{{report.metrics.min_course_score ?? '待补充'}}；政策体育成绩：{{report.metrics.pe_policy_score ?? '待补充'}}<span v-if="report.metrics.pe_policy_academic_year">（{{report.metrics.pe_policy_academic_year}} 学年）</span>。</p>
  <details><summary>计算口径与输入</summary><p>考核学年：{{report.metrics.academic_year}}；课程范围：{{report.metrics.course_categories.join('、') || '全部已确认课程'}}；完整性：{{report.metrics.complete ? '已确认' : '待确认'}}。</p><p v-for="(formula,key) in report.metrics.formulas" :key="key">{{formula}}</p><p v-for="c in report.metrics.inputs" :key="`${c.term}-${c.name}`">{{c.name}}：{{c.score}} 分 / {{c.credits ?? '未知'}} 学分</p></details>
  <h3>材料清单</h3><ul><li v-for="(item,i) in report.materials" :key="i">{{item.text}}<details><summary>依据</summary><p>{{data.policy_snapshot.clauses.find(c=>c.id===item.clause_id)?.text}}</p></details></li></ul>
  <h3>办理流程</h3><ol><li v-for="(item,i) in report.steps" :key="i">{{item.text}}<details><summary>依据</summary><p>{{data.policy_snapshot.clauses.find(c=>c.id===item.clause_id)?.text}}</p></details></li></ol>
  <template v-if="report.deadlines?.length"><h3>截止节点</h3><ul><li v-for="item in report.deadlines" :key="`${item.name}-${item.due_at}`">{{item.name}}：{{new Date(item.due_at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}}</li></ul></template>
  <template v-if="report.quotas?.length"><h3>名额说明</h3><ul><li v-for="item in report.quotas" :key="item.category">{{item.category}}：{{item.count}} 人</li></ul><p class="muted">满足资格条件不等于最终获奖，最终结果以学院评审和学校审核为准。</p></template>
  <h3>待核实与复核记录</h3><p>{{report.missing.length ? report.missing.join('、') : '本次规则核验无缺失字段。材料真实性仍以学校审核为准。'}}</p>
  <p v-for="review in data.reviews" :key="review.round">第 {{review.round}} 轮：{{review.issues.length ? review.issues.join('；') : '未发现计算或证据一致性问题'}}（{{review.model_checked ? '程序与模型复核' : '本地程序复核，未启用模型'}}）</p>
</article></template>
