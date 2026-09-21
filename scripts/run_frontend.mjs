import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const frontendDir = path.join(root, 'frontend')
const stopRequest = path.join(root, '.private', 'runtime', 'project-stop.request')
const viteModule = path.join(frontendDir, 'node_modules', 'vite', 'dist', 'node', 'index.js')
const { createServer } = await import(pathToFileURL(viteModule).href)

const server = await createServer({
  root: frontendDir,
  clearScreen: false,
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
})

await server.listen()

let closing = false
const timer = setInterval(async () => {
  if (closing || !existsSync(stopRequest)) return
  closing = true
  clearInterval(timer)
  await server.close()
  process.exit(0)
}, 250)
