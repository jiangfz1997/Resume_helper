import naive from 'naive-ui'
import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'


createApp(App).use(createPinia()).use(router).use(naive).mount('#app')
