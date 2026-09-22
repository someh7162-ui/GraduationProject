<script setup>
import { ref } from 'vue'
const props = defineProps({ request: Function })
const emit = defineEmits(['navigate'])
const autoRoute = ref(true), routing = ref(null), submittedQuestion = ref('')
const routeLabels = {campus_qa:'校园资料',scholarship:'奖学金咨询',recommendation:'校园推荐',academic:'学业档案',other:'待明确需求'}
const destinations = {ask:'进入教务助手',academic:'查看学业档案',home:'查看校园推荐'}
const question = ref(''), result = ref(null), busy = ref(false), error = ref('')
const sourceTypes = { official_website: '官网资料（导入标注）', official_document: '正式文档（导入标注）', manual: '人工整理', other: '其他来源', unknown: '来源类型未标注' }
const displayDate = value => value ? new Date(value).toLocaleString('zh-CN') : '未记录'
const safeLink = value => { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) && !url.username ? url.href : null } catch { return null } }
async function ask() {
  if (question.value.trim().length < 2 || busy.value) return
  busy.value = true; error.value = ''; result.value = null; routing.value = null; submittedQuestion.value = question.value.trim()
  try {
    const data = await props.request(autoRoute.value ? '/assistant/ask' : '/rag/ask', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ question: submittedQuestion.value }) })
    if(autoRoute.value) { routing.value = data; result.value = data.result }
    else result.value = data
  }
  catch (e) { error.value = e.message } finally { busy.value = false }
}
async function refreshSources() {
  if (!result.value?.answer_id || busy.value) return
  busy.value = true; error.value = ''
  try { result.value = await props.request(`/rag/sources/${result.value.answer_id}`) }
  catch (e) { result.value = null; error.value = e.message } finally { busy.value = false }
}
</script>
<template>
  <section class="academic-view campus-qa">
    <div class="assistant-heading"><div><p class="eyebrow blue">校园资料问答</p><h1>查找校园通知与办事信息</h1><p class="muted">描述你的需求，帮助你找到合适的服务；资料回答附原文摘录和来源。</p></div></div>
    <label class="route-toggle"><input v-model="autoRoute" type="checkbox" :disabled="busy"> 自动识别服务入口</label>
    <form class="academic-card academic-message-form" @submit.prevent="ask"><label for="campus-question">你的问题</label><textarea id="campus-question" v-model="question" rows="3" minlength="2" maxlength="500" required placeholder="例如：新生报到需要办理哪些手续？"></textarea><button class="primary-button" :disabled="busy || question.trim().length < 2">{{busy ? '正在查询…' : '查询校园资料'}}</button></form>
    <p v-if="error" class="inline-error" role="alert">{{error}}</p>
    <article v-if="routing" class="academic-card" aria-live="polite"><h2>{{routing.decision.source==='jev' ? `建议入口：${routeLabels[routing.decision.route]}` : '已使用校园资料查询'}}</h2><p>{{routing.message}}</p><p v-if="routing.decision.source==='fallback'" class="muted">{{routing.decision.reason==='low_confidence' ? '服务意图暂不明确，先查询相关资料。也可以从导航选择所需服务。' : '当前使用本地资料查询。你也可以从导航选择教务助手或其他服务。'}}</p><button v-if="destinations[routing.target_page]" class="primary-button" @click="emit('navigate',routing.target_page,submittedQuestion)">{{destinations[routing.target_page]}}</button></article>
    <article v-if="result" class="academic-card" aria-live="polite"><h2>{{result.grounded ? '资料回答' : '暂无可靠匹配'}}</h2><p class="qa-answer">{{result.answer}}</p>
      <p v-if="result.evidence?.status==='unchecked'" class="muted">以下为本地检索摘录，未完成语义证据检查，请核对原文。</p>
      <p v-else-if="result.evidence?.status==='sufficient'" class="muted">摘录通过语义证据检查，仍请以适用的正式原文为准。</p>
      <template v-if="result.sources.length"><div class="assistant-heading"><h3>引用来源</h3><button :disabled="busy" @click="refreshSources">重新检查来源</button></div>
        <ol class="qa-sources"><li v-for="source in result.sources" :key="source.chunk_id"><strong>{{source.title}}</strong><p>{{source.source_authority || source.source_department || '发布单位未记录'}} · {{sourceTypes[source.source_type] || sourceTypes.unknown}}</p>
          <p>{{source.verification_status === 'recorded' ? `核验记录：${displayDate(source.last_verified_at)}（由资料维护者填写）` : '未核验：暂无人工核验记录'}}</p>
          <p>资料更新：{{displayDate(source.updated_at || source.publish_time)}}</p><p v-if="source.effective_from || source.effective_to">有效期：{{source.effective_from ? displayDate(source.effective_from) : '未设置起始时间'}} 至 {{source.effective_to ? displayDate(source.effective_to) : '未设置截止时间'}}</p>
          <blockquote>{{source.snippet}}</blockquote>
          <a v-if="safeLink(source.source_url)" :href="safeLink(source.source_url)" target="_blank" rel="noopener noreferrer">打开原始来源 ↗</a><span v-else class="muted">未提供可打开的原始链接</span>
        </li></ol>
      </template>
    </article>
  </section>
</template>
<style scoped>
.qa-answer{white-space:pre-wrap;line-height:1.8;overflow-wrap:anywhere}.qa-sources{padding-left:24px}.qa-sources li{padding:14px 0;border-top:1px solid #e8ebf0}.qa-sources p{color:#667085;font-size:13px;line-height:1.6}.campus-qa>.academic-card{margin-top:20px}.qa-sources a{color:#4258b5}
.route-toggle{display:flex;align-items:center;gap:8px;margin-top:20px}.qa-sources blockquote{margin:12px 0;padding:12px;border-left:3px solid #bac6e7;background:#f5f7fc;color:#52627c;font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}
</style>
