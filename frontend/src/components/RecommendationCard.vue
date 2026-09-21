<script setup>
defineProps({ item: Object })
defineEmits(['action','open'])
const typeTone = type => ({竞赛:'blue',活动:'green',讲座:'violet',就业:'orange',考研:'indigo',通知:'slate'}[type] || 'slate')
const typeLabel = item => item.content_type === 'activity' ? '活动' : item.content_type === 'lecture' ? '讲座' : item.content_type === 'scholarship' ? '通知' : item.tags?.find(t => ['就业','考研','竞赛'].some(k => t.includes(k))) || '资讯'
</script>
<template>
  <article class="recommend-card"><div class="card-heading"><span :class="['category-tag', typeTone(typeLabel(item))]">{{ typeLabel(item) }}</span><span class="match-score" v-if="item.score">{{ Math.round(item.score * 100) }}% 匹配</span></div><h3>{{ item.title }}</h3><p class="card-summary">{{ item.summary || item.body }}</p><div class="card-meta"><span>{{ item.deadline ? '截止 ' + new Date(item.deadline).toLocaleDateString('zh-CN') : '校园信息库' }}</span><span>·</span><span>{{ item.source_department || (item.publisher_id ? '校园部门' : '新疆工程学院') }}</span></div><div class="card-footer"><span class="reason-chip">✦ {{ item.reason || '为你筛选的内容' }}</span><div class="card-actions"><button title="收藏" @click="$emit('action', item, 'favorite')">♡</button><button title="查看完整内容" @click="$emit('open', item);$emit('action', item, 'click')">查看全文</button><button v-if="item.content_type === 'activity'" class="action-primary" @click="$emit('action', item, 'register')">报名 →</button></div></div></article>
</template>
