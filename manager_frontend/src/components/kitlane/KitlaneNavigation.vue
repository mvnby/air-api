<script setup lang="ts">
import { ChevronDown } from 'lucide-vue-next';
import type { NavItem, NavSection, NavSectionId } from '../../manager-navigation';
defineProps<{
  items: NavItem[]; sections: NavSection[]; collapsed: boolean; leadsCount: number;
  expanded: Record<NavSectionId, boolean>;
  isNavItemActive: (item: NavItem) => boolean;
  isNavSectionActive: (section: NavSection) => boolean;
}>();
const emit = defineEmits<{ navigate: [path: string]; toggleSection: [id: NavSectionId] }>();
</script>
<template>
      <nav class="kitlane-navigation p-3 space-y-2" aria-label="Разделы кабинета">
        <div class="space-y-1">
          <button
            v-for="item in items"
            :key="item.path"
            class="kitlane-nav-item w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left relative"
            :class="[
              isNavItemActive(item)
                ? 'is-active'
                : '',
              collapsed ? 'md:justify-center md:px-0' : ''
            ]"
            @click="emit('navigate', item.path)"
            :title="collapsed ? item.label : ''"
            :aria-label="item.path === '/manager/leads' && leadsCount > 0 ? `${item.label}: ${leadsCount}` : item.label" :aria-current="isNavItemActive(item) ? 'page' : undefined"
          >
            <component :is="item.icon" class="w-5 h-5 shrink-0" />
            <span class="flex-1 truncate" :class="collapsed ? 'md:hidden' : ''">{{ item.label }}</span>
            <span
              v-if="item.path === '/manager/leads' && leadsCount > 0"
              data-testid="manager-leads-count"
              class="inline-flex items-center justify-center font-bold bg-red-500 text-white shrink-0"
              :class="collapsed ? 'md:absolute md:top-1 md:right-1 h-3 w-3 rounded-full text-[0px]' : 'min-w-[20px] h-5 px-1 rounded-full text-[11px]'"
            >
              {{ collapsed ? '' : leadsCount }}
            </span>
          </button>
        </div>

        <div
          v-for="section in sections"
          :key="section.id"
          class="border-t kitlane-nav-border pt-2"
        >
          <button
            class="kitlane-nav-section mb-1 flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-[11px] font-bold uppercase tracking-[0.16em] transition-colors"
            :class="[
              isNavSectionActive(section)
                ? 'is-current-section'
                : '',
              collapsed ? 'md:justify-center md:px-0' : ''
            ]"
            @click="emit('toggleSection', section.id)"
            :title="collapsed ? section.label : ''"
            :aria-expanded="expanded[section.id]" :aria-label="section.label"
          >
            <span class="min-w-0 flex-1 truncate" :class="collapsed ? 'md:hidden' : ''">{{ section.label }}</span>
            <ChevronDown
              class="h-3.5 w-3.5 shrink-0 transition-transform"
              :class="[
                expanded[section.id] ? 'rotate-0' : '-rotate-90',
                collapsed ? 'md:h-4 md:w-4' : ''
              ]"
            />
          </button>

          <div
            v-show="expanded[section.id]"
            class="space-y-1 border-l kitlane-nav-border pl-3 ml-3"
            :class="collapsed ? 'md:ml-0 md:border-l-0 md:pl-0' : ''"
          >
            <button
              v-for="item in section.items"
              :key="item.path"
              class="kitlane-nav-item w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors text-left relative"
              :class="[
                isNavItemActive(item)
                  ? 'is-active'
                  : '',
                collapsed ? 'md:justify-center md:px-0' : ''
              ]"
              @click="emit('navigate', item.path)"
              :title="collapsed ? item.label : ''"
            :aria-label="item.path === '/manager/leads' && leadsCount > 0 ? `${item.label}: ${leadsCount}` : item.label" :aria-current="isNavItemActive(item) ? 'page' : undefined"
            >
              <component :is="item.icon" class="w-5 h-5 shrink-0" />
              <span class="flex-1 truncate" :class="collapsed ? 'md:hidden' : ''">{{ item.label }}</span>
            </button>
          </div>
        </div>
      </nav>
</template>
<style scoped>
.kitlane-nav-item { color: var(--kitlane-sidebar-text); min-height: 42px; }
.kitlane-nav-item:hover, .kitlane-nav-section:hover { background: var(--kitlane-sidebar-hover); color: #fff; }
.kitlane-nav-item.is-active { background: var(--kitlane-sidebar-selected); color: #fff; box-shadow: inset 3px 0 #80b1ff; }
.kitlane-nav-section { color: var(--kitlane-sidebar-muted); }
.kitlane-nav-section.is-current-section { color: #b5d2ff; }
.kitlane-nav-border { border-color: var(--kitlane-sidebar-border); }
</style>
