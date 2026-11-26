<script setup lang="ts">
import { computed, ref } from 'vue';
import { Bell, Pin, Search, X } from 'lucide-vue-next';
import { useDialogA11y } from '../../composables/useDialogA11y';
import { useDialogViewport } from '../../composables/useDialogViewport';
import { searchNavSections, type NavSection } from '../../manager-navigation';

const props = defineProps<{
  personal: boolean; groups: NavSection[]; pins: string[]; active?: string; reminders: number;
}>();
const emit = defineEmits<{ close: []; navigate: [path: string]; pin: [path: string] }>();
const query = ref('');
const dialog = ref<HTMLElement | null>(null);
const search = ref<HTMLInputElement | null>(null);
const visible = computed(() => {
  if (props.personal) return props.groups.filter(group => group.id === 'personal');
  if (query.value.trim()) return searchNavSections(props.groups, query.value);
  const pinned = props.groups.flatMap(group => group.items).filter(item => props.pins.includes(item.path));
  return [
    ...(pinned.length ? [{ id: 'pinned', label: 'Закреплённые', items: pinned }] : []),
    ...props.groups.filter(group => group.id !== 'daily'),
  ];
});
const open = computed(() => true);
const initialFocus = computed(() => window.matchMedia?.('(max-width: 767px)')?.matches ? dialog.value : search.value);
const viewportStyle = useDialogViewport(open);
useDialogA11y({ open, dialogRef: dialog, initialFocusRef: initialFocus, close: () => emit('close') });
</script>

<template>
  <Teleport to="body">
    <div class="directory-backdrop" :style="viewportStyle" @click.self="emit('close')">
      <section ref="dialog" class="section-directory" role="dialog" aria-modal="true" aria-labelledby="section-directory-title" tabindex="-1">
        <header><h2 id="section-directory-title">{{ personal ? 'Моя работа' : 'Все разделы' }}</h2>
          <button class="icon-control" type="button" aria-label="Закрыть список разделов" @click="emit('close')"><X :size="20" /></button>
        </header>
        <label v-if="!personal" class="directory-search"><Search :size="18" aria-hidden="true" /><input ref="search" v-model="query" type="search" aria-label="Найти раздел" placeholder="Найти раздел" /></label>
        <div class="directory-scroll">
          <button v-if="reminders && !query.trim()" type="button" class="due-reminders" @click="emit('navigate', '/manager/tasks?filter=reminders')"><Bell :size="17" /> Напоминания к этому моменту · {{ reminders }}</button>
          <p v-if="!visible.length" role="status">По этому запросу разделов нет</p>
          <div class="directory-groups" :class="{ single: personal }">
            <section v-for="group in visible" :key="group.id">
              <h3 v-if="!personal">{{ group.label }}</h3>
              <div v-for="item in group.items" :key="item.path" class="directory-row">
                <a :href="item.path" :aria-current="active === item.path ? 'page' : undefined" @click.exact.prevent="emit('navigate', item.path)">
                  <component :is="item.icon" :size="17" aria-hidden="true" />{{ item.label }}
                </a>
                <button v-if="group.id !== 'daily'" class="icon-control pin" type="button" :aria-pressed="pins.includes(item.path)" :aria-label="(pins.includes(item.path) ? 'Открепить ' : 'Закрепить ') + item.label" :title="pins.includes(item.path) ? 'Открепить' : 'Закрепить'" @click="emit('pin', item.path)"><Pin :size="15" /></button>
              </div>
            </section>
          </div>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.directory-backdrop { position:fixed; inset:0; z-index:85; display:grid; place-items:center; padding:1rem; background:rgb(9 21 38 / .48); }
.section-directory { display:flex; flex-direction:column; width:min(46rem,100%); max-height:min(84dvh,48rem); background:var(--kitlane-surface); color:var(--kitlane-text); border:1px solid var(--kitlane-border); border-radius:1rem; box-shadow:0 16px 52px rgb(0 0 0 / .18); overflow:hidden; }
.section-directory:has(.single) { max-width:26rem; }
.section-directory header { display:flex; align-items:center; justify-content:space-between; padding:.7rem 1.1rem .25rem; }
.section-directory h2 { font-weight:700; font-size:1.2rem; }
.directory-search { display:flex; align-items:center; gap:.6rem; margin:.5rem 1.1rem; border:1px solid var(--kitlane-border); border-radius:.6rem; padding:0 .7rem; color:var(--kitlane-muted); }
.directory-search input { background:transparent; color:var(--kitlane-text); width:100%; min-width:0; height:2.7rem; }
.directory-scroll { overflow:auto; overscroll-behavior:contain; padding:.5rem 1.1rem 1rem; }
.directory-groups { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1.15rem 1.5rem; align-items:start; }
.directory-groups.single { grid-template-columns:1fr; }
.directory-groups h3 { color:var(--kitlane-muted); font-size:.78rem; font-weight:700; margin:0 0 .25rem; }
.directory-row { display:flex; min-width:0; align-items:center; }
.directory-row a,.due-reminders { display:flex; align-items:center; gap:.55rem; flex:1; min-width:0; min-height:42px; padding:.35rem; border-radius:.4rem; font-size:.9rem; }
.directory-row a svg { flex-shrink:0; }
.directory-row a:hover,.directory-row a[aria-current],.icon-control:hover,.due-reminders:hover { background:var(--kitlane-accent-soft); }
.icon-control { display:grid; place-items:center; width:36px; height:36px; flex:none; border-radius:.4rem; }
.pin { color:var(--kitlane-muted); } .pin[aria-pressed=true],.due-reminders { color:var(--kitlane-accent-text); }
@media (max-width:600px){ .directory-backdrop {padding:0;align-items:end;} .section-directory,.section-directory:has(.single){width:100%;max-width:none;max-height:88dvh;border-radius:1rem 1rem 0 0;padding-bottom:env(safe-area-inset-bottom);} .directory-groups{grid-template-columns:1fr;} .directory-row a,.icon-control{min-height:44px;} .icon-control{width:44px;} }
@media (prefers-reduced-motion:no-preference){.section-directory{animation:directory-in 140ms ease-out;} @keyframes directory-in{from{opacity:0;transform:translateY(5px)} to{opacity:1;transform:translateY(0)}}}
@media(max-width:767px){
  .directory-backdrop { top:var(--kitlane-dialog-top,0); bottom:auto; height:var(--kitlane-dialog-height,100dvh); grid-template-rows:minmax(0,1fr); }
  .section-directory { max-height:min(88dvh,100%); }
}
</style>
