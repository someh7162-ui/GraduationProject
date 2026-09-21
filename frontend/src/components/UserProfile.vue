<script setup>
import { computed } from 'vue'
const props = defineProps({ user: Object, items: Array, modules: Array })
defineEmits(['edit-interests'])
const coverage = computed(() => (props.user?.interests || []).map(name => ({name, count:(props.items || []).filter(item=>(item.tags || []).includes(name)).length, total:props.items?.length || 0})))
</script>
<template><section class="profile-view"><div class="profile-hero"><div class="profile-avatar">{{ user?.name?.slice(0,1) }}</div><div><p class="eyebrow blue">MY CAMPUS PROFILE</p><h1>{{ user?.name }}</h1><p>{{ user?.college }} · {{ user?.major }} · {{ user?.grade || '校园工作者' }}</p></div><button class="secondary-button" @click="$emit('edit-interests')">编辑兴趣</button></div><div class="profile-grid"><div class="profile-panel"><div class="panel-title"><h2>我的兴趣</h2><span>{{ user?.interests?.length || 0 }} 个模块</span></div><div class="profile-tags"><span v-for="interest in user?.interests" :key="interest"># {{ interest }}</span></div></div><div class="profile-panel"><div class="panel-title"><h2>推荐画像</h2><span>当前推荐列表的兴趣覆盖</span></div><div class="profile-bars"><div v-for="item in coverage" :key="item.name"><span>{{item.name}} · {{item.count}}/{{item.total}}</span><div><i :style="{width: `${item.total ? item.count/item.total*100 : 0}%`}"></i></div></div></div></div></div></section></template>
