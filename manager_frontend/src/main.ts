import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import {
  installManagerStorefrontFetchScope,
  installManagerStorefrontHeaderResolver,
} from './services/manager-storefront-selection'

installManagerStorefrontHeaderResolver()
installManagerStorefrontFetchScope()
const app = createApp(App)
app.mount('#app')
