<script setup>
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
const props = defineProps({ active: String, roleLabel: String, role: String })
defineEmits(['navigate'])
const groups = computed(() => [
  { title:'我的工作台', items:[{id:'home',label:'为你推荐',icon:'home'},{id:'ask',label:'教务助手',icon:'spark'},{id:'academic',label:'学业档案',icon:'folder'},{id:'policies',label:'政策库',icon:'shield'}] },
  { title:'发现校园', items:[{id:'campus-qa',label:'校园问答',icon:'chat'},{id:'activities',label:'活动与竞赛',icon:'calendar'},{id:'info',label:'通知与资讯',icon:'news'}] },
  ...(['admin','counselor','academic_admin'].includes(props.role) ? [{title:'管理服务',items:[{id:'rankings',label:'班级成绩排名',icon:'chart'},{id:'management',label:'账号与数据管理',icon:'settings'}]}] : [])
])
</script>
<template><aside class="sidebar"><nav aria-label="主导航" class="sidebar-nav"><div v-for="group in groups" :key="group.title" class="nav-group"><div class="sidebar-label">{{group.title}}</div><button v-for="item in group.items" :key="item.id" :class="['sidebar-link',{active:active===item.id}]" :aria-current="active===item.id?'page':undefined" :title="item.label" @click="$emit('navigate',item.id)"><AppIcon :name="item.icon" /><span class="nav-label">{{item.label}}</span><span v-if="active===item.id" class="nav-active-dot"></span></button></div><div class="nav-group profile-nav"><button :class="['sidebar-link',{active:active==='profile'}]" :aria-current="active==='profile'?'page':undefined" title="个人中心" @click="$emit('navigate','profile')"><AppIcon name="user" /><span class="nav-label">个人中心</span></button></div></nav><div class="sidebar-bottom"><span class="sidebar-emblem"><AppIcon name="compass" :size="25" /></span><strong>你的校园服务站</strong><p>信息、学业与每一步成长。</p><div class="sidebar-role"><span class="status-dot"></span>{{roleLabel}}</div></div></aside></template>
