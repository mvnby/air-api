import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(viteConfig, defineConfig({
  test: {
    environment: 'jsdom',
    // ui-logic.test.ts uses the separate Node runner in test:ui-logic.
    include: ['tests/**/*.spec.ts'],
  },
}))
