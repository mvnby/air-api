import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import {
  installManagerStorefrontFetchScope,
  installManagerStorefrontHeaderResolver,
} from './services/manager-storefront-selection'
import { recoverManagerSessionFromUnauthorized } from './services/manager-session'

installManagerStorefrontHeaderResolver()
installManagerStorefrontFetchScope(window, () => {
  recoverManagerSessionFromUnauthorized()
})
const app = createApp(App)
app.mount('#app')
