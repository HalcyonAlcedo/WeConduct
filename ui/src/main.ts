import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import { i18n, i18nFallbackPlugin } from './i18n'
import { initializeUiToken } from './services/api'

import './styles/tokens.css'
import './styles/base.css'
import './styles/animations.css'

async function bootstrap(): Promise<void> {
  try {
    await initializeUiToken()
  } catch (error) {
    const root = document.querySelector('#app')
    if (root) {
      root.textContent = `桌面安全会话初始化失败：${error instanceof Error ? error.message : String(error)}`
    }
    return
  }
  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.use(i18n)
  app.use(i18nFallbackPlugin)
  app.mount('#app')
}

void bootstrap()
