<script setup>
defineProps({ active: String, roleLabel: String, role: String })
defineEmits(['navigate'])
</script>
<template>
  <aside class="sidebar"><div class="sidebar-label">工作台</div><button :class="{active: active === 'home'}" @click="$emit('navigate','home')"><span>⌂</span>为你推荐</button><button :class="{active: active === 'ask'}" @click="$emit('navigate','ask')"><span>✦</span>教务助手</button><button :class="{active: active === 'academic'}" @click="$emit('navigate','academic')"><span>▣</span>学业档案</button><button :class="{active: active === 'policies'}" @click="$emit('navigate','policies')"><span>▤</span>政策库</button><button v-if="role==='admin'||role==='counselor'" :class="{active: active === 'rankings'}" @click="$emit('navigate','rankings')"><span>↕</span>班级成绩排名</button><div class="sidebar-label">探索</div><button :class="{active: active === 'activities'}" @click="$emit('navigate','activities')"><span>◎</span>活动与竞赛</button><button :class="{active: active === 'info'}" @click="$emit('navigate','info')"><span>▤</span>通知与资讯</button><div class="sidebar-spacer"></div><div class="sidebar-role"><span class="status-dot"></span>{{ roleLabel }}</div><button @click="$emit('navigate','profile')"><span>◯</span>个人中心</button></aside>
</template>
