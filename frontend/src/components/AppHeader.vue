<script setup>
defineProps({ user: Object, activePage: String })
defineEmits(['navigate','logout'])
</script>
<template>
  <header class="app-header">
    <button class="brand-button" @click="$emit('navigate', 'ask')"><span class="brand-mark">C</span><span><strong>Campus AI</strong><small>教务服务</small></span></button>
    <nav class="top-nav" aria-label="主导航"><button :class="{active: activePage === 'home'}" @click="$emit('navigate','home')">校园推荐</button><button :class="{active: activePage === 'activities'}" @click="$emit('navigate','activities')">活动</button><button :class="{active: activePage === 'info'}" @click="$emit('navigate','info')">校园资讯</button><button :class="{active: activePage === 'ask'}" @click="$emit('navigate','ask')">教务助手</button></nav>
    <div class="header-actions"><span class="header-search">⌕<span>搜索校园信息</span></span><button class="avatar-button" @click="$emit('navigate','profile')">{{ user?.name?.slice(0, 1) || 'C' }}</button></div>
  </header>
</template>
