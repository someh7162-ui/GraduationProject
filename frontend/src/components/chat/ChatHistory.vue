<script setup>
import { computed, ref } from 'vue'
import AppIcon from '../AppIcon.vue'
const props = defineProps({sessions:Array,selected:String,disabled:Boolean,open:Boolean,loading:Boolean})
const emit = defineEmits(['select','new','close','rename','delete'])
const search = ref('')
const title = item => item.payload.title || item.payload.messages?.find(m=>m.role==='user' && m.text)?.text || `${item.payload.context.scholarship} · 新评估`
const filtered = computed(()=>props.sessions.filter(item=>`${title(item)} ${item.payload.context.academic_year || ''} ${item.payload.context.selection_year || ''}`.toLowerCase().includes(search.value.trim().toLowerCase())))
const statuses = {ready:'等待提问',running:'评估中',cancelling:'正在停止',cancelled:'已停止',waiting:'待补充',policy_missing:'待导入政策',retryable:'可继续',completed:'已完成'}
</script>
<template>
  <aside v-if="open" id="chat-history" class="chat-history" aria-label="评估历史">
    <div class="chat-history-top"><span>我的对话</span><button class="chat-icon-button" aria-label="收起历史记录" @click="$emit('close')"><AppIcon name="panel" :size="18" /></button></div>
    <button class="chat-new" :disabled="disabled" @click="$emit('new')"><AppIcon name="plus" :size="18" />开启新评估</button>
    <label class="chat-history-search"><AppIcon name="search" :size="15" /><input v-model="search" aria-label="搜索评估记录" placeholder="搜索历史记录"></label>
    <p class="chat-history-label">评估记录 <span>{{sessions.length}}</span></p>
    <div class="chat-history-list"><div v-if="loading" class="chat-history-skeleton" aria-label="正在加载记录"><i v-for="n in 4" :key="n"></i></div><p v-else-if="!filtered.length" class="chat-history-empty">{{search ? '没有找到匹配的对话' : '从一个问题开始，评估记录会保存在这里。'}}</p>
      <div v-for="item in filtered" :key="item.id" :class="['chat-history-row',{selected:selected===item.id}]"><button class="chat-history-item" :aria-current="selected===item.id?'true':undefined" :disabled="disabled" :title="title(item)" @click="emit('select',item)"><span class="chat-history-title">{{title(item)}}</span><small><span>{{item.payload.context.selection_year || '待确认'}} 年 · {{item.payload.context.scholarship}}</span><i :class="{running:item.status==='running'}">{{statuses[item.status] || item.status}}</i></small></button><details class="chat-history-menu"><summary aria-label="会话操作">···</summary><div><button @click.stop="emit('rename',item)">重命名</button><button @click.stop="emit('delete',item)">删除</button></div></details></div>
    </div>
    <div class="chat-history-footer"><AppIcon name="shield" :size="17" /><span>政策有据，成长有方向<small>仅展示你的个人评估记录</small></span></div>
  </aside>
</template>
