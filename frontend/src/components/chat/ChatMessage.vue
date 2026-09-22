<script setup>
import { computed, ref, onUnmounted } from 'vue'
import AppIcon from '../AppIcon.vue'
import { renderAssistantMarkdown } from './markdown.js'
const props = defineProps({message:Object, canRegenerate:Boolean})
const emit = defineEmits(['regenerate'])
const html = computed(()=>renderAssistantMarkdown(props.message.text))
const copyState = ref('')
let timer
async function copy() {
  try { await navigator.clipboard.writeText(props.message.text || ''); copyState.value='已复制' }
  catch { copyState.value='复制失败，请选择文本复制' }
  clearTimeout(timer); timer=setTimeout(()=>copyState.value='',2400)
}
async function contentClick(event) {
  const button=event.target.closest?.('.chat-code-copy'); if(!button) return
  const code=button.closest('.chat-code-block')?.querySelector('code')?.textContent || ''
  try { await navigator.clipboard.writeText(code); button.textContent='已复制' }
  catch { button.textContent='复制失败' }
  setTimeout(()=>{ if(button.isConnected) button.textContent='复制代码' },1800)
}
onUnmounted(()=>clearTimeout(timer))
</script>
<template>
  <article :class="['chat-message',message.role==='user'?'chat-message-user':'chat-message-assistant']" :aria-label="message.role==='user'?'你的消息':'助手回复'">
    <div v-if="message.role!=='user'" class="chat-assistant-identity"><span class="chat-assistant-avatar"><AppIcon name="spark" :size="18" /></span><strong>教务助手</strong></div>
    <p v-if="message.role==='user'" class="chat-user-bubble">{{message.text}}</p>
    <div v-else class="chat-markdown" v-html="html" @click="contentClick"></div>
    <div v-if="message.role!=='user'" class="chat-message-actions"><button class="chat-icon-button" title="复制回答" aria-label="复制回答" @click="copy"><AppIcon :name="copyState==='已复制'?'check':'copy'" :size="15" /></button><button v-if="canRegenerate" class="chat-icon-button" title="重新生成" aria-label="重新生成" @click="emit('regenerate')"><AppIcon name="refresh" :size="15" /></button><span role="status">{{copyState}}</span></div>
  </article>
</template>
