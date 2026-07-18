import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import { i18n, i18nFallbackPlugin } from './i18n'

import './styles/tokens.css'
import './styles/base.css'
import './styles/animations.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(i18nFallbackPlugin)
app.mount('#app')
