<script setup>
defineProps({ item: Object })
defineEmits(['action','open'])
const typeTone = type => ({竞赛:'blue',活动:'green',讲座:'violet',就业:'orange',考研:'indigo',通知:'slate'}[type] || 'slate')
const typeLabel = item => item.content_type_label || '校园信息'
</script>
<template>
  <article class="recommend-card"><div class="card-heading"><span :class="['category-tag', typeTone(typeLabel(item))]">{{ typeLabel(item) }}</span><span class="match-score" v-if="item.score != null" title="综合兴趣、身份、行为和时效的排序分，不代表匹配概率">推荐分 {{ Math.round(item.score * 100) }}</span></div><h3>{{ item.title }}</h3><p class="card-summary">{{ item.summary || item.body }}</p><div class="card-meta"><span>{{ item.deadline ? '截止 ' + new Date(item.deadline).toLocaleDateString('zh-CN') : '校园信息库' }}</span><span>·</span><span>{{ item.source_department || (item.publisher_id ? '校园部门' : '新疆工程学院') }}</span></div><div class="card-footer"><span class="reason-chip" :title="item.reason">✦ {{ item.reason || '为你筛选的内容' }}</span><div class="card-actions"><button title="减少类似推荐" @click="$emit('action', item, 'dismiss')">不感兴趣</button><button title="收藏" @click="$emit('action', item, 'favorite')">♡</button><button title="查看完整内容" @click="$emit('open', item);$emit('action', item, 'click')">查看全文</button><button v-if="item.content_type === 'activity'" class="action-primary" @click="$emit('action', item, 'register')">报名 →</button></div></div></article>
</template>
