<template>
  <div class="mobile-menu-wrapper">
    <!-- Hamburger Button -->
    <button
      class="icon-btn menu-toggle"
      @click="isOpen = true"
      aria-label="Open Menu"
    >
      <span class="material-icons-round">menu</span>
    </button>

    <!-- Fullscreen Overlay -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="isOpen" class="menu-overlay" @click.self="isOpen = false">
          <div class="menu-content">
            <div class="menu-header">
              <span class="menu-title">Меню</span>
              <button class="icon-btn close-btn" @click="isOpen = false">
                <span class="material-icons-round">close</span>
              </button>
            </div>

            <nav class="mobile-nav">
              <div class="nav-item-group">
                <div class="nav-item nav-item-title">
                  <span class="material-icons-round icon">grid_view</span>
                  Каталог
                </div>
                <a
                  href="/catalog?tag_slugs=cat-household"
                  class="nav-subitem"
                  @click="isOpen = false"
                >
                  Бытовые
                </a>
                <a
                  href="/catalog?tag_slugs=cat-multi"
                  class="nav-subitem"
                  @click="isOpen = false"
                >
                  Мультисплит
                </a>
                <a
                  href="/catalog?tag_slugs=cat-industrial"
                  class="nav-subitem"
                  @click="isOpen = false"
                >
                  Полупром
                </a>
              </div>
              <a href="/services" class="nav-item" @click="isOpen = false">
                <span class="material-icons-round icon">handyman</span>
                Услуги
              </a>
              <a href="/blog" class="nav-item" @click="isOpen = false">
                <span class="material-icons-round icon">article</span>
                Статьи
              </a>
              <a href="/contacts" class="nav-item" @click="isOpen = false">
                <span class="material-icons-round icon">contacts</span>
                Контакты
              </a>
            </nav>

            <div class="menu-footer">
              <a :href="`tel:${phoneClean}`" class="btn btn-primary w-full">
                <span class="material-icons-round">call</span>
                Позвонить
              </a>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';

defineProps({
  phoneClean: {
    type: String,
    required: true,
  },
});

const isOpen = ref(false);

// Lock body scroll when menu is open
watch(isOpen, (val) => {
  if (val) {
    document.body.style.overflow = 'hidden';
  } else {
    document.body.style.overflow = '';
  }
});
</script>

<style scoped>
.mobile-menu-wrapper {
  display: none;
}

@media (max-width: 980px) {
  .mobile-menu-wrapper {
    display: block;
  }
}

.menu-toggle {
  width: 44px;
  height: 44px;
  background: var(--surface);
  border-radius: 12px;
  border: 1px solid var(--border);
  color: var(--text);
}

.menu-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  z-index: 9999;
  display: flex;
  justify-content: flex-end;
}

.menu-content {
  width: 85%;
  max-width: 320px;
  height: 100%;
  background: var(--surface);
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  box-shadow: -5px 0 25px rgba(0, 0, 0, 0.1);
  overflow-y: auto;
}

.menu-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
}

.menu-title {
  font-size: 1.25rem;
  font-weight: 700;
  font-family: 'Space Grotesk', sans-serif;
}

.close-btn {
  background: var(--bg);
}

.mobile-nav {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex: 1;
}

.nav-item-group {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  padding-bottom: 0.2rem;
}

.nav-item-title {
  cursor: default;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  border-radius: 1rem;
  font-weight: 600;
  color: var(--text);
  transition: all 0.2s;
}

.nav-item:hover, .nav-item:active {
  background: var(--bg);
  color: var(--primary);
}

.nav-item .icon {
  color: var(--text-muted);
}
.nav-item:hover .icon {
  color: var(--primary);
}

.nav-subitem {
  padding: 0.65rem 1rem 0.65rem 2.85rem;
  border-radius: 0.8rem;
  color: var(--text-muted);
  font-weight: 600;
  transition: all 0.2s;
}

.nav-subitem:hover,
.nav-subitem:active {
  background: var(--bg);
  color: var(--primary);
}

.menu-footer {
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border);
}

.w-full {
  width: 100%;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.fade-enter-active .menu-content,
.fade-leave-active .menu-content {
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.fade-enter-from .menu-content,
.fade-leave-to .menu-content {
  transform: translateX(100%);
}
</style>
