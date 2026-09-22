<script setup>
import AppIcon from './AppIcon.vue'
defineProps({ user: Object, activePage: String })
defineEmits(['navigate','logout'])
</script>
<template>
  <header class="app-header">
    <button class="brand-button" aria-label="Campus AI 推荐首页" @click="$emit('navigate','home')"><span class="brand-mark"><AppIcon name="book" :size="23" /></span><span><strong>Campus <em>AI</em></strong><small>新疆工程学院 · 智慧校园</small></span></button>
    <div class="header-context"><span class="header-divider"></span><span>校园生活，有序发生。</span></div>
    <div class="header-actions"><button class="header-search" @click="$emit('navigate','campus-qa')"><AppIcon name="search" :size="17" /><span>搜索校园资料</span></button><button class="header-profile" aria-label="个人中心" @click="$emit('navigate','profile')"><span class="avatar-button">{{user?.name?.slice(0,1) || 'C'}}</span><span class="header-user-name">{{user?.name}}</span></button><button class="header-logout" title="退出登录" aria-label="退出登录" @click="$emit('logout')"><AppIcon name="logout" :size="18" /></button></div>
  </header>
</template>
