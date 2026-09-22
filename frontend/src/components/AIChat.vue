<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import AssessmentReport from './AssessmentReport.vue'
import AppIcon from './AppIcon.vue'
import ChatComposer from './chat/ChatComposer.vue'
import ChatHistory from './chat/ChatHistory.vue'
import ChatMessage from './chat/ChatMessage.vue'
import './chat/chat.css'

const props = defineProps({request:Function,user:Object,initialQuestion:{type:String,default:''}})
const sessions = ref([]), session = ref(null), text = ref(props.initialQuestion), error = ref('')
const assessment = ref(null), inputs = ref({}), busy = ref(false), historyLoading = ref(true)
const deepThink = ref(false), webSearch = ref(false), streamController = ref(null)
const initialContext = () => ({school:'新疆工程学院',scholarship:'国家奖学金',selection_year:new Date().getFullYear(),academic_year:''})
const context = ref(initialContext())
const historyOpen = ref(window.innerWidth > 1100), settingsOpen = ref(false)
const scroll = ref(null), composer = ref(null), followup = ref(null), atBottom = ref(true)
const statuses = {ready:'等待提问',running:'正在评估',cancelling:'正在停止',cancelled:'已停止',waiting:'等待补充',policy_missing:'缺少适用政策',retryable:'可继续评估',completed:'评估完成'}
const running = computed(()=>['running','cancelling'].includes(session.value?.status))
const messages = computed(()=>session.value?.payload.messages || [])
const pending = computed(()=>session.value?.payload.pending || [])
const progress = computed(()=>session.value?.payload.tools?.findLast(event=>event.status==='running')?.summary || '正在核对政策与学业资料')
const suggestions = [
  {icon:'shield',title:'了解申请资格',text:'我能申请国家奖学金吗？'},
  {icon:'chart',title:'核对成绩与排名',text:'我的成绩和排名需要满足哪些条件？'},
  {icon:'folder',title:'梳理申请材料',text:'申请奖学金还缺哪些材料？'},
]
let alive=true, version=0
const json = body => ({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
function trackScroll() { const el=scroll.value; if(el) atBottom.value=el.scrollHeight-el.scrollTop-el.clientHeight < 70 }
async function scrollBottom(force=false) {
  const shouldFollow=force || atBottom.value
  await nextTick()
  if(shouldFollow && scroll.value) { scroll.value.scrollTop=scroll.value.scrollHeight; atBottom.value=true }
}
async function toggleSettings() {
  settingsOpen.value=!settingsOpen.value
  if(settingsOpen.value) { await nextTick(); scroll.value?.scrollTo({top:0}) }
}
async function load() { const result=await props.request('/assistant/sessions'); if(alive) sessions.value=result }
function applyState(result) {
  session.value=result
  context.value={...context.value,...result.payload.context}
  deepThink.value=!!result.payload.preferences?.deep_think
  webSearch.value=!!result.payload.preferences?.web_search
}
function parseEvent(block) {
  let name='message', data=''
  for(const line of block.split('\n')) {
    if(line.startsWith('event:')) name=line.slice(6).trim()
    else if(line.startsWith('data:')) data+=line.slice(5).trim()
  }
  return data ? {name,data:JSON.parse(data)} : null
}
async function stream(id, generation=version) {
  streamController.value?.abort()
  const controller=new AbortController(); streamController.value=controller
  try {
    const response=await props.request(`/assistant/sessions/${id}/events?after=${messages.value.length}`,{stream:true,signal:controller.signal,headers:{Accept:'text/event-stream'}})
    const reader=response.body.getReader(), decoder=new TextDecoder(); let buffer=''
    while(alive && generation===version) {
      const {value,done}=await reader.read(); if(done) break
      buffer+=decoder.decode(value,{stream:true}).replace(/\r/g,'')
      let boundary
      while((boundary=buffer.indexOf('\n\n'))>=0) {
        const raw=buffer.slice(0,boundary); buffer=buffer.slice(boundary+2)
        const event=parseEvent(raw); if(!event) continue
        if(event.name==='state') { applyState(event.data); await scrollBottom() }
        else if(event.name==='message') { session.value.payload.messages.push(event.data); await scrollBottom() }
        else if(event.name==='delta') { const last=session.value.payload.messages.at(-1); if(last) last.text=(last.text||'')+event.data.text; await scrollBottom() }
        else if(event.name==='done') { await refresh(id,generation); return }
      }
    }
  } catch(e) { if(e.name!=='AbortError' && alive && generation===version) error.value=e.message }
  finally { if(streamController.value===controller) streamController.value=null }
}
async function refresh(id, generation=version) {
  try {
    const result=await props.request(`/assistant/sessions/${id}`)
    if(!alive || generation!==version || session.value?.id!==id) return
    const report=result.status==='completed' && result.payload.assessment_id ? await props.request(`/assessments/${result.payload.assessment_id}`) : null
    if(!alive || generation!==version || session.value?.id!==id) return
    applyState(result); assessment.value=report
    for(const [key,fact] of Object.entries(result.payload.suggested_facts || {})) {
      if(inputs.value[key]===undefined) inputs.value[key]=typeof fact.value==='boolean'?String(fact.value):fact.value
    }
    if(result.status==='waiting' && result.payload.pending?.some(q=>q.kind==='context')) settingsOpen.value=true
    await scrollBottom()
    await load()
    if(['running','cancelling'].includes(result.status)) stream(id,generation)
  } catch(e) { if(alive && generation===version) error.value=e.message }
}
async function select(item) {
  if(busy.value) return
  streamController.value?.abort(); const generation=++version
  applyState(item); inputs.value={}; assessment.value=null; error.value=''; text.value=''
  context.value={...item.payload.context}; settingsOpen.value=false; atBottom.value=true
  if(window.innerWidth<=1100) historyOpen.value=false
  await refresh(item.id,generation)
}
function newSession() {
  if(busy.value) return
  streamController.value?.abort(); version++
  session.value=null; assessment.value=null; inputs.value={}; error.value=''; text.value=''
  context.value=initialContext(); settingsOpen.value=false; atBottom.value=true
  deepThink.value=false; webSearch.value=false
  if(window.innerWidth<=1100) historyOpen.value=false
  nextTick(()=>composer.value?.focus())
}
async function send(facts={}) {
  if(busy.value || running.value || (!text.value.trim() && !session.value)) return
  busy.value=true; error.value=''; const generation=version; const submitted=text.value.trim()
  try {
    if(!session.value) {
      const item=await props.request('/assistant/sessions',json({...context.value,academic_year:context.value.academic_year || null}))
      if(!alive || generation!==version) return
      session.value=item
    }
    const id=session.value.id
    const result=await props.request(`/assistant/sessions/${id}/messages`,json({text:submitted,facts,selection_year:Number(context.value.selection_year)||null,academic_year:context.value.academic_year || null,deep_think:deepThink.value,web_search:webSearch.value}))
    if(!alive || generation!==version) return
    applyState(result); text.value=''; inputs.value={}; atBottom.value=true
    await scrollBottom(true); stream(id,generation)
  } catch(e) { if(alive && generation===version) error.value=e.message }
  finally { if(alive && generation===version) busy.value=false }
}
async function stop() {
  if(!session.value || !running.value) return
  try { applyState(await props.request(`/assistant/sessions/${session.value.id}/cancel`,json({}))) }
  catch(e) { error.value=e.message }
}
async function regenerate() {
  if(!session.value || busy.value || running.value) return
  busy.value=true; error.value=''; const generation=version
  try { const result=await props.request(`/assistant/sessions/${session.value.id}/regenerate`,json({})); applyState(result); assessment.value=null; atBottom.value=true; await scrollBottom(true); stream(result.id,generation) }
  catch(e) { error.value=e.message } finally { busy.value=false }
}
async function renameSession(item) {
  const current=item.payload.title || item.payload.messages?.find(message=>message.role==='user')?.text || ''
  const title=window.prompt('输入新的会话名称',current.slice(0,80)); if(!title?.trim()) return
  try { const updated=await props.request(`/assistant/sessions/${item.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:title.trim()})}); if(session.value?.id===item.id) applyState(updated); await load() }
  catch(e) { error.value=e.message }
}
async function deleteSession(item) {
  if(!window.confirm(`确定删除“${item.payload.title || '这条会话'}”吗？删除后无法恢复。`)) return
  try { await props.request(`/assistant/sessions/${item.id}`,{method:'DELETE'}); if(session.value?.id===item.id) newSession(); await load() }
  catch(e) { error.value=e.message }
}
function submitFacts() {
  const facts={}
  for(const q of pending.value) {
    const value=inputs.value[q.field]
    if(value===undefined || value==='' || (q.kind==='rank' && !value.rank && !value.total)) continue
    facts[q.field]={value:q.kind==='rank'?{rank:Number(value.rank),total:Number(value.total),scope:value.scope,type:q.field}:q.kind==='boolean'?value==='true':q.kind==='number'?Number(value):value,academic_year:q.academic_year}
  }
  send(facts)
}
async function interpret() {
  if(busy.value || !session.value) return
  busy.value=true; error.value=''; const generation=version
  try {
    const result=await props.request(`/assistant/sessions/${session.value.id}/interpret`,json({text:text.value}))
    if(!alive || generation!==version) return
    for(const [key,fact] of Object.entries(result.suggestions)) inputs.value[key]=typeof fact.value==='boolean'?String(fact.value):fact.value
  } catch(e) { if(alive && generation===version) error.value=e.message }
  finally { if(alive && generation===version) busy.value=false }
}
function rankInput(field) { if(!inputs.value[field]) inputs.value[field]={rank:'',total:'',scope:''}; return inputs.value[field] }
function suggest(value) { text.value=value; nextTick(()=>composer.value?.focus()) }
onMounted(async()=>{try{await load()}catch(e){if(alive)error.value=e.message}finally{historyLoading.value=false}})
onUnmounted(()=>{alive=false;version++;streamController.value?.abort()})
</script>

<template>
  <section class="ai-chat" aria-label="教务助手聊天">
    <button v-if="historyOpen" class="chat-history-backdrop" aria-label="关闭历史记录" @click="historyOpen=false"></button>
    <ChatHistory :sessions="sessions" :selected="session?.id" :disabled="busy" :open="historyOpen" :loading="historyLoading" @select="select" @new="newSession" @close="historyOpen=false" @rename="renameSession" @delete="deleteSession" />
    <div class="chat-main">
      <header class="chat-header">
        <button class="chat-icon-button" :aria-expanded="historyOpen" aria-controls="chat-history" aria-label="切换历史记录" title="历史记录" @click="historyOpen=!historyOpen"><AppIcon name="panel" :size="20" /></button>
        <div class="chat-header-title"><h1>教务助手 <span>Campus AI</span></h1><p>{{session ? statuses[session.status] : '从政策到规划，陪你理清每一步'}}</p></div>
        <button class="chat-icon-button" :disabled="busy" aria-label="新建评估" title="新建评估" @click="newSession"><AppIcon name="plus" :size="21" /></button>
      </header>
      <div ref="scroll" class="chat-scroll" tabindex="0" aria-label="对话内容" @scroll="trackScroll">
        <div class="chat-content">
          <section v-if="settingsOpen" id="chat-context" class="chat-context academic-view" aria-label="评估设置">
            <div class="chat-context-heading"><div><h2>本次评估设置</h2><p>评选年度和成绩所属学年可能不同，请按通知确认。</p></div><button class="chat-icon-button" aria-label="关闭评估设置" @click="settingsOpen=false"><AppIcon name="close" :size="17" /></button></div>
            <div class="academic-form-row"><label>学校<input v-model="context.school" :disabled="!!session || busy || running"></label><label>奖学金<input v-model="context.scholarship" :disabled="!!session || busy || running"></label><label>评选年度<input v-model.number="context.selection_year" type="number" min="2000" max="2200" :disabled="busy || running"></label><label>考核学年<input v-model="context.academic_year" placeholder="例如 2025-2026" :disabled="busy || running"></label></div>
          </section>
          <div v-if="!messages.length" class="chat-welcome">
            <span class="chat-welcome-mark"><AppIcon name="spark" :size="35" /></span>
            <p class="chat-welcome-kicker">你好，我是你的教务助手</p>
            <h2>让每一步申请，都更有把握。</h2>
            <p>一起读懂政策、核对资格，整理属于你的申请计划。</p>
            <div class="chat-suggestions"><button v-for="item in suggestions" :key="item.title" :disabled="busy" @click="suggest(item.text)"><AppIcon :name="item.icon" :size="20" /><strong>{{item.title}}</strong><span>{{item.text}}</span></button></div>
          </div>
          <div v-else class="chat-thread"><ChatMessage v-for="(message,index) in messages" :key="`${session.id}-${index}`" :message="message" :can-regenerate="message.role!=='user' && index===messages.length-1 && !running" @regenerate="regenerate" /></div>
          <div v-if="running || busy" class="chat-thinking" role="status"><span class="chat-thinking-dots"><i></i><i></i><i></i></span><span>{{running ? progress : '正在提交，请稍候'}}</span></div>
          <section v-if="session?.status==='waiting'" ref="followup" class="chat-followup academic-view" aria-label="补充评估信息">
            <div class="chat-followup-heading"><span><AppIcon name="folder" :size="18" /></span><div><h2>还需要你补充一点信息</h2><p>确认后会保存到学业档案，再继续核对。</p></div></div>
            <p v-if="pending.some(q=>q.kind==='context')" class="chat-context-reminder">请在上方评估设置中补全评选年度和考核学年。</p>
            <template v-for="q in pending" :key="q.field"><div v-if="q.kind!=='context'" class="followup-field"><label>{{q.label}}<small>{{q.academic_year}} {{q.help}}</small></label>
              <div v-if="q.kind==='rank'" class="academic-form-row"><label>名次<input v-model.number="rankInput(q.field).rank" type="number" min="1" :disabled="busy"></label><label>总人数<input v-model.number="rankInput(q.field).total" type="number" min="1" :disabled="busy"></label><label>实际排名范围<input v-model="rankInput(q.field).scope" :placeholder="`政策要求：${q.scope}`" :disabled="busy"></label></div>
              <select v-else-if="q.kind==='boolean'" v-model="inputs[q.field]" :aria-label="q.label" :disabled="busy"><option value="">请选择</option><option value="true">是</option><option value="false">否</option></select>
              <p v-else-if="['courses','course_credits'].includes(q.field)">请在“学业档案”导入或核对成绩单，再返回继续评估。</p>
              <input v-else v-model="inputs[q.field]" :aria-label="q.label" :type="q.kind==='number'?'number':'text'" :disabled="busy">
            </div></template>
            <div class="chat-followup-actions"><button class="primary-button" :disabled="busy" @click="submitFacts">确认补充并继续</button><button v-if="text.trim()" :disabled="busy" @click="interpret">从回复提取待确认信息</button></div>
          </section>
          <details v-if="session?.payload.tools?.length" class="chat-execution"><summary><AppIcon name="check" :size="15" />查看执行记录 <span>{{session.payload.tools.length}} 个步骤</span></summary><ol><li v-for="(event,index) in session.payload.tools" :key="index"><span>{{event.summary}}</span><small>{{event.status==='done'?'完成':event.status==='blocked'?'待处理':event.status==='cancelled'?'已停止':'处理中'}}</small></li></ol></details>
          <section v-if="session?.payload.web_search_result" class="chat-search-results"><h2>校园资料检索</h2><p>{{session.payload.web_search_result.answer}}</p><ol v-if="session.payload.web_search_result.sources?.length"><li v-for="source in session.payload.web_search_result.sources" :key="source.chunk_id"><strong>{{source.title}}</strong><blockquote>{{source.snippet}}</blockquote><a v-if="source.source_url" :href="source.source_url" target="_blank" rel="noopener noreferrer">查看来源 ↗</a></li></ol></section>
          <div v-if="assessment" class="chat-report academic-view"><AssessmentReport :assessment="assessment" /></div>
        </div>
      </div>
      <div class="chat-bottom">
        <button v-if="!atBottom" class="chat-to-bottom" aria-label="回到最新消息" @click="scrollBottom(true)"><AppIcon name="down" :size="18" /></button>
        <p v-if="error" class="chat-error" role="alert">{{error}}<button v-if="session && !busy" @click="refresh(session.id)">重新同步</button></p>
        <div class="chat-context-strip"><button :aria-expanded="settingsOpen" @click="toggleSettings"><AppIcon name="shield" :size="13" /><span>{{context.scholarship}} · {{context.selection_year || '年度待定'}} 年</span><span class="chat-context-year">{{context.academic_year || '考核学年待确认'}}</span><AppIcon name="chevron" :size="12" /></button><span v-if="session?.payload.mode==='local-tools'" class="chat-local-label">本地规则模式</span></div>
        <ChatComposer ref="composer" v-model="text" :disabled="busy || running" :running="running" :can-continue="!!session" :settings-open="settingsOpen" :deep-think="deepThink" :web-search="webSearch" @send="send()" @stop="stop" @settings="toggleSettings" @toggle-deep="deepThink=!deepThink" @toggle-web="webSearch=!webSearch" />
      </div>
    </div>
  </section>
</template>
