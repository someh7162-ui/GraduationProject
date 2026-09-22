import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js/lib/common'
import 'highlight.js/styles/github.css'

// Raw HTML and remote images stay disabled; markdown-it rejects unsafe link schemes.
const markdown = new MarkdownIt({html:false,linkify:true,breaks:true}).disable('image')
markdown.renderer.rules.fence = (tokens, index) => {
  const token=tokens[index], language=(token.info || '').trim().split(/\s+/)[0]
  let code=markdown.utils.escapeHtml(token.content)
  if(language && hljs.getLanguage(language)) {
    try { code=hljs.highlight(token.content,{language,ignoreIllegals:true}).value } catch {}
  }
  const label=markdown.utils.escapeHtml(language || '代码')
  return `<div class="chat-code-block"><div class="chat-code-head"><span>${label}</span><button type="button" class="chat-code-copy">复制代码</button></div><pre class="hljs"><code>${code}</code></pre></div>`
}
const openLink = markdown.renderer.rules.link_open || ((tokens, index, options, env, self)=>self.renderToken(tokens,index,options))
markdown.renderer.rules.link_open = (tokens,index,options,env,self) => {
  tokens[index].attrSet('target','_blank')
  tokens[index].attrSet('rel','noopener noreferrer')
  return openLink(tokens,index,options,env,self)
}
export const renderAssistantMarkdown = text => markdown.render(String(text || ''))
