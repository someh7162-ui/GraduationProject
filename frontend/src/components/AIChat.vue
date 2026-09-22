<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import AssessmentReport from './AssessmentReport.vue'
const props = defineProps({request:Function,user:Object,initialQuestion:{type:String,default:''}})
const sessions = ref([]), session = ref(null), text = ref(props.initialQuestion), error = ref(''), assessment = ref(null), inputs = ref({}), busy = ref(false)
const context = ref({school:'新疆工程学院',scholarship:'国家奖学金',selection_year:new Date().getFullYear(),academic_year:''})
let timer, alive = true
const statuses = {ready:'等待提问',running:'正在评估',waiting:'等待补充',policy_missing:'缺少适用政策',retryable:'可重试',completed:'已完成'}
const json = body => ({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
async function load() { sessions.value = await props.request('/assistant/sessions') }
async function select(item) { clearTimeout(timer); session.value = item; inputs.value={}; context.value={...item.payload.context}; await refresh(item.id) }
async function refresh(id) {
  try {
    const result = await props.request(`/assistant/sessions/${id}`)
    if (!alive || session.value?.id !== id) return
    session.value = result
    for(const [key,fact] of Object.entries(result.payload.suggested_facts || {})){if(inputs.value[key]===undefined)inputs.value[key]=typeof fact.value==='boolean'?String(fact.value):fact.value}
    assessment.value = result.status === 'completed' && result.payload.assessment_id ? await props.request(`/assessments/${result.payload.assessment_id}`) : null
    if (result.status === 'running') timer=setTimeout(()=>refresh(id),1200)
    else await load()
  } catch(e) { error.value=e.message }
}
function newSession() {clearTimeout(timer); session.value=null; assessment.value=null; inputs.value={}}
async function start() {
  busy.value=true; error.value=''
  try { const item=await props.request('/assistant/sessions',json({...context.value,academic_year:context.value.academic_year || null})); await select(item); await load() }
  catch(e){error.value=e.message} finally {busy.value=false}
}
async function send(facts={}) {
  busy.value=true;error.value=''
  try {
    if(!session.value) { await start(); if(!session.value)return }
    await props.request(`/assistant/sessions/${session.value.id}/messages`,json({text:text.value,facts,selection_year:Number(context.value.selection_year) || null,academic_year:context.value.academic_year || null}))
    text.value=''; inputs.value={}; await refresh(session.value.id)
  } catch(e){error.value=e.message} finally{busy.value=false}
}
function submitFacts() {
  const facts={}
  for(const q of session.value.payload.pending) {
    const value=inputs.value[q.field]
    if(value===undefined || value==='' || (q.kind==='rank' && !value.rank && !value.total))continue
    facts[q.field]={value:q.kind==='rank'?{rank:Number(value.rank),total:Number(value.total),scope:value.scope,type:q.field}:q.kind==='boolean'?value==='true':q.kind==='number'?Number(value):value,academic_year:q.academic_year}
  }
  send(facts)
}
async function interpret() {
  busy.value=true;error.value=''
  try { const result=await props.request(`/assistant/sessions/${session.value.id}/interpret`,json({text:text.value})); for(const [key,fact] of Object.entries(result.suggestions)){inputs.value[key]=typeof fact.value==='boolean'?String(fact.value):fact.value} }
  catch(e){error.value=e.message} finally{busy.value=false}
}
function rankInput(field) { if(!inputs.value[field])inputs.value[field]={rank:'',total:'',scope:''}; return inputs.value[field] }
onMounted(async()=>{try{await load(); if(!props.initialQuestion && sessions.value.length)await select(sessions.value[0])}catch(e){error.value=e.message}})
onUnmounted(()=>{alive=false;clearTimeout(timer)})
</script>
<template><section class="academic-view"><div class="assistant-heading"><div><p class="eyebrow blue">教务智能服务</p><h1>我能申请这个奖学金吗？</h1><p class="muted">按年度政策读取档案、计算指标，并在信息不足时向你追问。</p></div><button @click="newSession">新建评估</button></div>
  <p v-if="error" class="inline-error" role="alert">{{error}}</p>
  <div class="academic-chat-grid"><aside class="academic-card session-list"><h3>评估记录</h3><button v-for="item in sessions" :key="item.id" :class="{selected:session?.id===item.id}" @click="select(item)">{{item.payload.context.scholarship}} · {{item.payload.context.selection_year || '年度待定'}}<small>{{statuses[item.status]}}</small></button><p v-if="!sessions.length" class="muted">还没有评估记录</p></aside>
  <div><article class="academic-card"><div class="academic-form-row"><label>学校<input v-model="context.school" :disabled="!!session" /></label><label>奖学金<input v-model="context.scholarship" :disabled="!!session" /></label><label>评选年度<input v-model.number="context.selection_year" type="number" min="2000" max="2200" /></label><label>考核学年<input v-model="context.academic_year" placeholder="例如 2025-2026" /></label></div>
    <p class="muted">请按通知确认评选年度和考核学年，两者分别填写。</p>
    <div v-if="session" class="conversation" aria-live="polite"><p class="muted">{{statuses[session.status]}} · {{session.payload.mode==='local-tools'?'本地工具模式':'教务助手'}}</p><div v-for="(m,i) in session.payload.messages" :key="i" :class="['message',m.role]"><strong>{{m.role==='user'?'你':'教务助手'}}</strong><p>{{m.text}}</p></div></div>
    <form class="academic-message-form" @submit.prevent="send()"><textarea v-model="text" rows="2" placeholder="例如：我能申请国家奖学金吗？" aria-label="你的问题"></textarea><button class="primary-button" :disabled="busy || session?.status==='running'">{{session?.status==='running'?'正在评估…':'发送 / 继续评估'}}</button></form>
    <section v-if="session?.status==='waiting'" class="followup-panel"><h3>补充信息</h3><p>以下信息确认后保存到你的档案。</p>
      <template v-for="q in session.payload.pending" :key="q.field"><div v-if="q.kind!=='context'" class="followup-field"><label>{{q.label}}<small>{{q.academic_year}} {{q.help}}</small></label>
        <div v-if="q.kind==='rank'" class="academic-form-row"><label>名次<input v-model.number="rankInput(q.field).rank" type="number" min="1" /></label><label>总人数<input v-model.number="rankInput(q.field).total" type="number" min="1" /></label><label>实际排名范围<input v-model="rankInput(q.field).scope" :placeholder="`政策要求：${q.scope}`" /></label></div>
        <select v-else-if="q.kind==='boolean'" v-model="inputs[q.field]"><option value="">请选择</option><option value="true">是</option><option value="false">否</option></select>
        <p v-else-if="['courses','course_credits'].includes(q.field)">请在“学业档案”导入或核对成绩单，再返回继续评估。</p>
        <input v-else v-model="inputs[q.field]" :type="q.kind==='number'?'number':'text'" />
      </div></template>
      <button :disabled="busy" @click="submitFacts">确认补充并继续</button> <button v-if="text.trim()" :disabled="busy" @click="interpret">将回复提取为待确认信息</button>
    </section>
    <details v-if="session?.payload.tools?.length"><summary>查看执行记录</summary><ol><li v-for="(event,i) in session.payload.tools" :key="i">{{event.summary}} · {{event.status==='done'?'完成':event.status==='blocked'?'待处理':'处理中'}}</li></ol></details>
  </article><AssessmentReport v-if="assessment" :assessment="assessment" /></div></div>
</section></template>
