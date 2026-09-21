<script setup>
import { onMounted, ref } from 'vue'
const props = defineProps({ request: Function })
const profile = ref({courses: [], facts: {}}), documents = ref([]), preview = ref(null), error = ref(''), busy = ref(false), note = ref('')
const revision = ref(0), editing = ref(null), reason = ref('')
const years = ref([]), completeYears = ref([])
async function load() {
  const record = await props.request('/academic-profile'); profile.value = record.payload; revision.value = record.revision
  documents.value = await props.request('/documents')
  years.value = [...new Set(profile.value.courses.map(c => c.academic_year))]
}
async function upload(event) {
  const file = event.target.files[0]; if (!file) return
  error.value = ''; busy.value = true
  try { const body = new FormData(); body.append('file', file); preview.value = await props.request('/documents', { method:'POST', body }) }
  catch (e) { error.value = e.message } finally { busy.value = false; event.target.value = '' }
}
async function confirm() {
  error.value = ''; busy.value = true
  try {
    await props.request(`/documents/${preview.value.id}/confirm`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({courses:preview.value.payload.preview.courses, facts:preview.value.payload.preview.facts})})
    preview.value = null; await load(); note.value = '材料已确认并合并到档案。'
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function complete(year) {
  try {
    await props.request('/academic-profile', {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({facts:{transcript_complete:{value:true, academic_year:year}}})})
    note.value = `已确认 ${year} 学年课程完整。`; await load()
  } catch(e) { error.value = e.message }
}
async function correct() { try { await props.request('/academic-profile/courses',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({course:editing.value,reason:reason.value,revision:revision.value})});editing.value=null;reason.value='';await load();note.value='课程更正已记录，可返回助手重新评估。' } catch(e) {error.value=e.message} }
onMounted(() => load().catch(e => error.value = e.message))
</script>
<template>
  <section class="academic-view">
    <h1>我的学业档案</h1><p class="muted">导入成绩单，核对后用于奖学金资格初评。材料仅对你的账号可见。</p>
    <p v-if="error" role="alert" class="inline-error">{{error}}</p><p v-if="note" role="status">{{note}}</p>
    <label class="upload-button">{{busy ? '正在处理…' : '导入成绩单'}}<input type="file" accept=".pdf,.xls,.xlsx" :disabled="busy" @change="upload" /></label>
    <p class="muted">支持文字型 PDF、XLS、XLSX，单个文件不超过 10 MB。</p>
    <article v-if="preview" class="academic-card">
      <h2>核对导入内容 · {{preview.payload.filename}}</h2>
      <p v-for="warning in preview.payload.preview.warnings" :key="warning" class="academic-warning">{{warning}}</p>
      <div class="table-scroll"><table><thead><tr><th>学年</th><th>学期</th><th>课程</th><th>属性</th><th>学分</th><th>成绩</th><th></th></tr></thead>
      <tbody><tr v-for="(course,i) in preview.payload.preview.courses" :key="i">
        <td><input v-model="course.academic_year" aria-label="学年" /></td><td><input v-model.number="course.term" type="number" min="1" max="3" aria-label="学期" /></td>
        <td><input v-model="course.name" aria-label="课程" /></td><td><input v-model="course.category" aria-label="属性" /></td>
        <td><input v-model.number="course.credits" type="number" min="0" step="0.5" aria-label="学分" /></td><td><input v-model.number="course.score" type="number" min="0" max="100" step="0.1" aria-label="成绩" /></td>
        <td><button @click="preview.payload.preview.courses.splice(i,1)">移除</button></td></tr></tbody></table></div>
      <button @click="preview.payload.preview.courses.push({academic_year:preview.payload.preview.academic_year || '',term:1,name:'',category:'',credits:null,score:0,sources:[]})">补录课程</button>
      <dl v-for="(fact,key) in preview.payload.preview.facts" :key="key"><dt>{{({college:'学院',major:'专业',class_name:'班级',admission_year:'入学年份',unclassified_rank:'待确认口径的排名',awards_text:'获奖记录',moral_score:'思想品德',physical_education:'体育成绩'})[key] || key}}</dt><dd>{{typeof fact.value === 'object' ? `${fact.value.label}：${fact.value.rank}/${fact.value.total}` : fact.value}}</dd></dl>
      <p class="muted">确认表示你已核对以上内容。存在冲突时不会覆盖原档案。</p>
      <button class="primary-button" :disabled="busy || !preview.payload.preview.courses.length" @click="confirm">确认导入</button> <button @click="preview = null">取消</button>
    </article>
    <article class="academic-card"><h2>已确认课程 · {{profile.courses.length}} 门</h2>
      <div class="table-scroll"><table><thead><tr><th>学年 / 学期</th><th>课程</th><th>学分</th><th>成绩</th><th>来源</th><th>操作</th></tr></thead>
      <tbody><tr v-for="course in profile.courses" :key="`${course.academic_year}-${course.term}-${course.name}`"><td>{{course.academic_year}} / {{course.term}}</td><td>{{course.name}}</td><td>{{course.credits ?? '待补充'}}</td><td>{{course.score}}</td><td><small v-for="(source,i) in course.sources" :key="i" class="source-line">{{source.filename}} · {{source.locator}}</small></td><td><button @click="editing=JSON.parse(JSON.stringify(course))">更正</button></td></tr></tbody></table></div>
      <p v-if="!profile.courses.length" class="muted">尚未导入课程。</p>
      <div v-for="year in years" :key="year" class="completion-row"><label><input type="checkbox" :value="year" v-model="completeYears" /> 我已核对 {{year}} 学年课程全部导入</label><button :disabled="!completeYears.includes(year)" @click="complete(year)">确认完整性</button></div>
    </article>
    <article v-if="editing" class="academic-card"><h2>更正课程 · {{editing.name}}</h2><p>原值和更正原因会保留在档案中。</p><div class="academic-form-row"><label>成绩<input v-model.number="editing.score" type="number" min="0" max="100" /></label><label>学分<input v-model.number="editing.credits" type="number" min="0" step="0.5" /></label><label>属性<input v-model="editing.category" /></label><label>更正原因<input v-model="reason" /></label></div><button :disabled="reason.length<2" @click="correct">确认更正</button> <button @click="editing=null">取消</button></article>
    <article class="academic-card"><h2>材料记录</h2><p v-for="doc in documents" :key="doc.id">{{doc.payload.filename}} · {{doc.status === 'confirmed' ? '已确认' : '待确认'}} <button @click="preview = JSON.parse(JSON.stringify(doc))">核对</button></p></article>
  </section>
</template>
