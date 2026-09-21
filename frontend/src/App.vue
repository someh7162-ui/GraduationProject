<script setup>
import { computed, onMounted, ref } from 'vue'
import AppHeader from './components/AppHeader.vue'
import Sidebar from './components/Sidebar.vue'
import RecommendationCard from './components/RecommendationCard.vue'
import AIChat from './components/AIChat.vue'
import InterestSelector from './components/InterestSelector.vue'
import EmptyState from './components/EmptyState.vue'
import SkeletonCard from './components/SkeletonCard.vue'
import UserProfile from './components/UserProfile.vue'
import AcademicProfile from './components/AcademicProfile.vue'
import PolicyManager from './components/PolicyManager.vue'
import ClassRanking from './components/ClassRanking.vue'

const api = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const token = ref(localStorage.getItem('token') || '')
const page = ref(token.value ? 'loading' : 'login')
const authMode = ref('login')
const user = ref(null)
const modules = ref([])
const selected = ref([])
const items = ref([])
const selectedContent = ref(null)
const form = ref({ username: '', password: '', name: '', role: 'student', college: '', major: '', grade: '' })
const filter = ref('全部'); const search = ref(''); const error = ref(''); const toast = ref(''); const loading = ref(false)
const categories = [{name:'全部',icon:'⌘'},{name:'竞赛',icon:'◇'},{name:'活动',icon:'◎'},{name:'讲座',icon:'◌'},{name:'就业',icon:'↗'},{name:'考研',icon:'⌁'},{name:'通知',icon:'▤'}]
const roleLabel = computed(() => ({student:'学生',counselor:'辅导员',organizer:'活动组织者'}[user.value?.role] || '校园用户'))
const greeting = computed(() => user.value?.grade === '大一' ? '欢迎来到校园生活。' : user.value?.grade === '大四' ? '毕业季也要稳稳向前。' : '今天也为你准备了新内容。')
const visibleItems = computed(() => items.value.filter(item => (filter.value === '全部' || item.content_type === filter.value || (item.tags || []).some(tag => tag.includes(filter.value))) && (!search.value || `${item.title}${item.body}${(item.tags || []).join('')}`.toLowerCase().includes(search.value.toLowerCase()))))
async function request(path, options = {}) { const headers = {...(options.headers || {})}; if (token.value) headers.Authorization = `Bearer ${token.value}`; const r = await fetch(`${api}${path}`, {...options, headers}); const data = await r.json().catch(() => ({})); if (!r.ok) throw Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || '请求失败，请稍后重试')); return data }
function notify(text) { toast.value = text; clearTimeout(notify.timer); notify.timer = setTimeout(() => toast.value = '', 2600) }
function fail(text) { error.value = text; setTimeout(() => error.value = '', 4500) }
async function loadModules() { modules.value = await request('/onboarding/modules'); if (selected.value.length && typeof selected.value[0] === 'string') selected.value = modules.value.filter(module => selected.value.includes(module.name)).map(module => module.id) }
async function loadFeed() { loading.value = true; try { items.value = (await request('/recommendations?page_size=30')).items || [] } catch (e) { fail(e.message) } finally { loading.value = false } }
async function enter(data) { token.value = data.access_token; user.value = data.user; localStorage.setItem('token', token.value); page.value = 'ask'; await loadModules() }
async function login() { loading.value = true; try { await enter(await request('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:form.value.username,password:form.value.password})})); notify('登录成功，正在整理你的校园信息') } catch (e) { fail(e.message) } finally { loading.value = false } }
async function register() { loading.value = true; try { await request('/auth/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form.value)}); authMode.value='login'; form.value.password=''; notify('账号创建成功，请登录') } catch(e) { fail(e.message) } finally { loading.value=false } }
async function saveInterests(ids) { try { await request('/onboarding/interests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({module_ids:ids})}); selected.value=ids; user.value.interests=modules.value.filter(module => ids.includes(module.id)).map(module => module.name); user.value.onboarding_completed=true; page.value='home'; await loadFeed(); notify('兴趣已保存，你的专属信息流准备好了') } catch(e) { fail(e.message) } }
async function action(item,type) { try { await request('/events',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content_id:item.id,event_type:type,source:'vue-home'})}); notify(type==='register'?'报名成功，已加入你的行程':type==='favorite'?'已收藏到个人中心':'已记录你的兴趣') } catch(e) { fail(e.message) } }
function navigate(target) { if(target==='home' && !user.value.onboarding_completed){ page.value='onboarding';loadModules();return } page.value=target; if (target==='home') loadFeed() }
async function openContent(item) { try { selectedContent.value = await request(`/contents/${item.id}`) } catch (e) { fail(e.message) } }
function logout() { token.value=''; user.value=null; localStorage.removeItem('token'); page.value='login'; authMode.value='login' }
async function bootstrap() { if (!token.value) return; try { user.value=await request('/me'); page.value='ask'; await loadModules() } catch { logout() } }
onMounted(bootstrap)
</script>
<template>
<div class="app-shell">
  <section v-if="page==='login'" class="auth-layout"><div class="auth-intro"><div class="brand-lockup"><span class="brand-mark">C</span><span><strong>Campus AI</strong><small>教务服务</small></span></div><div class="intro-copy"><p class="eyebrow">YOUR CAMPUS, IN FOCUS</p><h1>让每一次教务咨询，<em>有据</em>可依。</h1><p>导入学业档案，按年度政策核验奖学金条件，获取材料清单和办理流程。</p></div><div class="intro-note">基于政策与个人材料，逐项核验</div></div><div class="auth-panel"><div class="auth-tabs"><button :class="{active:authMode==='login'}" @click="authMode='login'">登录</button><button :class="{active:authMode==='register'}" @click="authMode='register'">注册</button></div><div class="panel-heading"><p class="eyebrow blue">CAMPUS AI</p><h2>{{authMode==='login'?'欢迎回来':'创建你的校园账号'}}</h2><p>{{authMode==='login'?'登录后进入教务助手。':'填写基础资料，开始你的教务咨询。'}}</p></div><form @submit.prevent="authMode==='login'?login():register()"><template v-if="authMode==='register'"><label>姓名<input v-model="form.name" required placeholder="你的姓名"></label><label>身份<select v-model="form.role"><option value="student">学生</option><option value="counselor">辅导员</option><option value="organizer">活动组织者</option></select></label><div class="form-row"><label>学院<input v-model="form.college" required placeholder="例如：软件学院"></label><label>年级<select v-model="form.grade" :required="form.role==='student'"><option value="">选择年级</option><option>大一</option><option>大二</option><option>大三</option><option>大四</option></select></label></div></template><label>用户名<input v-model="form.username" required placeholder="用户名"></label><label>密码<input v-model="form.password" required minlength="8" type="password" placeholder="至少 8 位字符"></label><button class="submit-button" :disabled="loading">{{loading?'请稍候…':authMode==='login'?'登录 Campus AI':'创建账号'}}<span>→</span></button></form><p class="auth-switch">{{authMode==='login'?'还没有账号？':'已经有账号？'}}<button @click="authMode=authMode==='login'?'register':'login'">{{authMode==='login'?'立即注册':'返回登录'}}</button></p><p v-if="error" class="inline-error">{{error}}</p></div></section>
  <section v-else-if="page==='loading'" class="boot-screen"><div class="brand-lockup"><span class="brand-mark">C</span><span><strong>Campus AI</strong><small>教务服务</small></span></div><div class="loader-line"></div></section>
  <InterestSelector v-else-if="page==='onboarding'" :modules="modules" :selected="selected" :user="user" @submit="saveInterests" @logout="logout" />
  <template v-else><AppHeader :user="user" :active-page="page" @navigate="navigate" @logout="logout" /><div class="workspace"><Sidebar :active="page" :role-label="roleLabel" :role="user?.role" @navigate="navigate" /><main class="main-content"><section v-if="page==='home'" class="home-view"><div class="hero-row"><div><p class="eyebrow blue">PERSONALIZED CAMPUS FEED</p><h1>早上好，{{user?.name}} <span class="wave">✦</span></h1><p class="hero-subtitle">{{greeting}} 根据你的专业、年级和兴趣，为你精选了 <strong>{{items.length}} 条</strong>校园信息。</p><div class="interest-strip"><span v-for="tag in (user?.interests || []).slice(0,5)" :key="tag">#{{tag}}</span><button @click="navigate('profile')">编辑兴趣</button></div></div><div class="hero-stat"><span>今日匹配度</span><strong>{{items.length?'92%':'—'}}</strong><small>持续根据你的反馈优化</small></div></div><div class="feed-toolbar"><div class="category-tabs"><button v-for="cat in categories" :key="cat.name" :class="['category-tab',{active:filter===cat.name}]" @click="filter=cat.name"><span>{{cat.icon}}</span>{{cat.name}}</button></div><div class="search-wrap"><span>⌕</span><input v-model="search" placeholder="搜索活动、竞赛、通知…"></div></div><div v-if="loading" class="cards-grid"><SkeletonCard v-for="n in 6" :key="n" /></div><div v-else-if="visibleItems.length" class="cards-grid"><RecommendationCard v-for="item in visibleItems" :key="item.id" :item="item" @action="action" @open="openContent" /></div><EmptyState v-else title="还没有匹配的内容" description="换一个分类或关键词，我们再帮你找找。" action-label="查看全部" @action="filter='全部';search=''" /></section><AIChat v-else-if="page==='ask'" :request="request" :user="user" /><AcademicProfile v-else-if="page==='academic'" :request="request" /><PolicyManager v-else-if="page==='policies'" :request="request" :user="user" /><ClassRanking v-else-if="page==='rankings'" :request="request" /><UserProfile v-else-if="page==='profile'" :user="user" :items="items" :modules="modules" @edit-interests="page='onboarding';loadModules()" /><section v-else class="placeholder-view"><p class="eyebrow blue">CAMPUS DIRECTORY</p><h1>{{page==='activities'?'校园活动':'校园资讯'}}</h1><p>这里会聚合更完整的校园内容，你也可以从首页推荐开始浏览。</p><button class="primary-button" @click="navigate('home')">回到推荐</button></section></main></div></template>
  <div v-if="selectedContent" class="content-modal-backdrop" @click.self="selectedContent=null"><article class="content-modal"><button class="content-modal-close" @click="selectedContent=null">×</button><p class="eyebrow blue">{{selectedContent.source_department || '新疆工程学院公开信息'}}</p><h2>{{selectedContent.title}}</h2><div class="content-modal-meta">{{selectedContent.publish_time ? new Date(selectedContent.publish_time).toLocaleDateString('zh-CN') : ''}} <span v-if="selectedContent.content_type">· {{selectedContent.content_type}}</span></div><p class="content-modal-body">{{selectedContent.body || selectedContent.summary}}</p><a v-if="selectedContent.source_url" :href="selectedContent.source_url" target="_blank" rel="noopener">查看官网原文 ↗</a></article></div>
  <transition name="toast"><div v-if="toast" class="toast">{{toast}}</div></transition>
</div>
</template>

