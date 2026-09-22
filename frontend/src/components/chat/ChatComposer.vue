<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import AppIcon from '../AppIcon.vue'
const props = defineProps({modelValue:String,disabled:Boolean,running:Boolean,canContinue:Boolean,settingsOpen:Boolean,deepThink:Boolean,webSearch:Boolean})
const emit = defineEmits(['update:modelValue','send','settings','stop','toggle-deep','toggle-web'])
const textarea = ref(null)
function resize() {
  if (!textarea.value) return
  textarea.value.style.height = 'auto'
  textarea.value.style.height = Math.min(textarea.value.scrollHeight, 180) + 'px'
}
function keydown(event) {
  if(event.key==='Enter' && !event.shiftKey && !event.isComposing && event.keyCode!==229) {
    event.preventDefault()
    if(!props.disabled && (props.modelValue.trim() || props.canContinue)) emit('send')
  }
}
function focus() { textarea.value?.focus() }
watch(()=>props.modelValue, async()=>{ await nextTick(); resize() })
onMounted(resize)
defineExpose({focus})
</script>
<template>
  <div class="chat-composer-wrap">
    <form class="chat-composer" @submit.prevent="props.running ? emit('stop') : emit('send')">
      <textarea ref="textarea" :value="modelValue" :disabled="disabled" aria-label="你的问题" rows="2" maxlength="4000" placeholder="向教务助手提问，或继续补充你的情况…" @input="emit('update:modelValue',$event.target.value)" @keydown="keydown"></textarea>
      <div class="chat-composer-tools">
        <button type="button" :class="['chat-mode-button',{active:deepThink}]" :aria-pressed="deepThink" @click="emit('toggle-deep')"><AppIcon name="spark" :size="15" />深度思考</button>
        <button type="button" :class="['chat-mode-button',{active:webSearch}]" :aria-pressed="webSearch" @click="emit('toggle-web')"><AppIcon name="search" :size="15" />资料检索</button>
        <button type="button" class="chat-mode-button" :aria-expanded="settingsOpen" aria-controls="chat-context" @click="emit('settings')"><AppIcon name="settings" :size="15" />评估设置</button>
        <span class="chat-enter-hint">Shift + Enter 换行</span>
        <button class="chat-send" :class="{stop:running}" :disabled="running ? false : disabled || (!modelValue.trim() && !canContinue)" :aria-label="running ? '停止生成' : modelValue.trim() ? '发送问题' : '继续评估'" :title="running ? '停止生成' : modelValue.trim() ? '发送问题' : '继续评估'"><span v-if="running" class="chat-stop-icon"></span><span v-else-if="disabled" class="chat-spinner"></span><AppIcon v-else name="send" :size="21" /></button>
      </div>
    </form>
    <p class="chat-composer-note">依据已确认的政策与资料进行初评，最终结果以学校审核为准。</p>
  </div>
</template>
