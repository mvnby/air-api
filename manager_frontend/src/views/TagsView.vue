<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { api } from '../api';
import type { ManagerTagGroupResponse, ManagerTagOptionResponse } from '../client';
import TagGroupModal from '../components/TagGroupModal.vue';
import TagModal from '../components/TagModal.vue';
import { confirmDialog, notify } from '../services/ui-feedback';

const groups = ref<ManagerTagGroupResponse[]>([]);
const selectedGroupId = ref<number | null>(null);
const loading = ref(true);

const isGroupModalOpen = ref(false);
const editingGroup = ref<ManagerTagGroupResponse | null>(null);

const isTagModalOpen = ref(false);
const editingTag = ref<ManagerTagOptionResponse | null>(null);

const fetchTags = async () => {
  loading.value = true;
  try {
    groups.value = await api.getManagerTagGroups();
    if (!selectedGroupId.value && groups.value.length > 0 && groups.value[0]) {
      selectedGroupId.value = groups.value[0].id;
    }
  } catch (err) {
    console.error('Failed to fetch tags', err);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchTags();
});

const selectedGroup = computed(() => {
  if (!selectedGroupId.value) return null;
  return groups.value.find(g => g.id === selectedGroupId.value) || null;
});

const selectGroup = (id: number) => {
  selectedGroupId.value = id;
};

// Group Actions
const openCreateGroup = () => {
  editingGroup.value = null;
  isGroupModalOpen.value = true;
};

const openEditGroup = (group: ManagerTagGroupResponse) => {
  editingGroup.value = group;
  isGroupModalOpen.value = true;
};

const deleteGroup = async (group: ManagerTagGroupResponse) => {
  if (!await confirmDialog({ title: 'Удалить группу тегов?', description: group.title, confirmText: 'Удалить', variant: 'danger' })) return;
  try {
    await api.deleteManagerTagGroup(group.id);
    if (selectedGroupId.value === group.id) selectedGroupId.value = null;
    await fetchTags();
  } catch (err: any) {
    notify(err?.body?.detail || 'Ошибка при удалении', 'error');
  }
};

// Tag Actions
const openCreateTag = () => {
  if (!selectedGroup.value) return;
  editingTag.value = null;
  isTagModalOpen.value = true;
};

const openEditTag = (tag: ManagerTagOptionResponse) => {
  editingTag.value = tag;
  isTagModalOpen.value = true;
};

const deleteTag = async (tag: ManagerTagOptionResponse) => {
  if (!await confirmDialog({ title: 'Удалить тег?', description: tag.title, confirmText: 'Удалить', variant: 'danger' })) return;
  try {
    await api.deleteManagerTag(tag.id);
    await fetchTags();
  } catch (err: any) {
    notify(err?.body?.detail || 'Ошибка при удалении', 'error');
  }
};

</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold flex items-center gap-3 text-gray-900 dark:text-white tracking-tight">
        <span class="material-icons-round text-teal-600 dark:text-teal-400">label</span>
        Управление тегами
      </h1>
      <button 
        @click="openCreateGroup"
        class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500/50 transition-all shadow-sm shadow-teal-600/20"
      >
        <span class="material-icons-round text-[18px]">add</span>
        Новая группа
      </button>
    </div>

    <!-- Main Content -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-6 h-[calc(100vh-12rem)] min-h-[500px]">
      
      <!-- Left Column: Tag Groups -->
      <div class="md:col-span-1 bg-white dark:bg-[#1e293b] rounded-xl border border-gray-200 dark:border-slate-700/50 overflow-hidden flex flex-col shadow-sm">
        <div class="p-4 border-b border-gray-100 dark:border-slate-700/50 flex justify-between items-center bg-gray-50/50 dark:bg-slate-800/20">
          <h2 class="font-semibold text-gray-800 dark:text-gray-200">Группы тегов</h2>
        </div>
        
        <div class="flex-1 overflow-y-auto p-2" v-if="!loading">
          <div v-if="groups.length === 0" class="p-4 text-center text-gray-500 dark:text-slate-400 text-sm">
            Нет групп тегов
          </div>
          <div 
            v-for="group in groups" 
            :key="group.id"
            @click="selectGroup(group.id)"
            class="group flex items-center justify-between p-3 mb-1 rounded-lg cursor-pointer transition-colors"
            :class="[
              selectedGroupId === group.id 
                ? 'bg-teal-50 dark:bg-teal-500/10 border-l-2 border-teal-500' 
                : 'hover:bg-gray-50 dark:hover:bg-slate-800/50 border-l-2 border-transparent'
            ]"
          >
            <div class="flex items-center gap-3 truncate">
              <!-- Color Dot -->
              <div class="w-3 h-3 rounded-full flex-shrink-0" :class="[group.color.startsWith('#') || group.color.startsWith('rgb') ? '' : `bg-${group.color}-500/80`]" :style="group.color.startsWith('#') || group.color.startsWith('rgb') ? { backgroundColor: group.color } : {}"></div>
              <div class="truncate">
                <div class="font-medium text-sm truncate" :class="selectedGroupId === group.id ? 'text-teal-800 dark:text-teal-300' : 'text-gray-700 dark:text-gray-300'">
                  {{ group.title }}
                </div>
                <div class="text-xs text-gray-500 dark:text-slate-500" v-if="group.tags">
                  {{ group.tags.length }} тегов
                </div>
              </div>
            </div>
            
            <div class="flex items-center opacity-0 group-hover:opacity-100 transition-opacity gap-1">
              <button @click.stop="openEditGroup(group)" class="p-1.5 text-gray-400 hover:text-teal-600 dark:hover:text-teal-400 rounded-md hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors" title="Редактировать">
                <span class="material-icons-round text-[16px]">edit</span>
              </button>
            </div>
          </div>
        </div>
        <div class="flex-1 flex items-center justify-center" v-else>
          <span class="material-icons-round animate-spin text-teal-600">refresh</span>
        </div>
      </div>

      <!-- Right Column: Tags list -->
      <div class="md:col-span-3 bg-white dark:bg-[#1e293b] rounded-xl border border-gray-200 dark:border-slate-700/50 overflow-hidden flex flex-col shadow-sm">
        <div v-if="selectedGroup" class="flex flex-col h-full">
          <!-- Header -->
          <div class="p-5 border-b border-gray-100 dark:border-slate-700/50 flex justify-between items-start bg-gray-50/50 dark:bg-slate-800/20">
            <div>
              <div class="flex items-center gap-2 mb-1">
                 <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ selectedGroup.title }}</h2>
                 <span v-if="selectedGroup.is_public" class="px-2 py-0.5 bg-green-100 dark:bg-green-500/20 text-green-700 dark:text-green-400 text-xs font-medium rounded-full border border-green-200 dark:border-green-500/20">Публичная</span>
                 <span v-if="!selectedGroup.is_public" class="px-2 py-0.5 bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-gray-400 text-xs font-medium rounded-full border border-gray-200 dark:border-slate-600">Системная</span>
              </div>
              <div class="text-sm text-gray-500 dark:text-slate-400 flex items-center gap-2">
                <span>Slug: {{ selectedGroup.slug }}</span>
                <span>•</span>
                <span>Множественный выбор: {{ selectedGroup.allow_multiple ? 'Да' : 'Нет' }}</span>
              </div>
            </div>
            
            <div class="flex items-center gap-2">
              <button 
                @click="deleteGroup(selectedGroup)"
                class="inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors"
              >
                <span class="material-icons-round text-[18px]">delete</span>
                Удалить группу
              </button>

              <button 
                @click="openCreateTag"
                class="inline-flex items-center justify-center gap-1.5 rounded-lg bg-teal-50 dark:bg-teal-500/10 border border-teal-200 dark:border-teal-500/20 px-3 py-1.5 text-sm font-medium text-teal-700 dark:text-teal-400 hover:bg-teal-100 dark:hover:bg-teal-500/20 transition-colors"
              >
                <span class="material-icons-round text-[18px]">add</span>
                Добавить тег
              </button>
            </div>
          </div>
          
          <!-- Tags Table/List -->
          <div class="flex-1 overflow-y-auto p-5">
            <div v-if="!selectedGroup.tags || selectedGroup.tags.length === 0" class="h-full flex flex-col items-center justify-center text-gray-400 dark:text-slate-500">
              <span class="material-icons-round text-4xl mb-2 opacity-50">sell</span>
              <p>В этой группе пока нет тегов</p>
              <button @click="openCreateTag" class="mt-4 text-teal-600 hover:text-teal-700 font-medium text-sm">Создать первый тег</button>
            </div>

            <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
               <!-- Tag Card -->
               <div 
                 v-for="tag in selectedGroup.tags" 
                 :key="tag.id"
                 class="group border border-gray-200 dark:border-slate-700/60 rounded-lg p-3 flex flex-col hover:border-teal-300 dark:hover:border-teal-500/50 hover:shadow-sm transition-all bg-white dark:bg-slate-800/50"
               >
                 <div class="flex justify-between items-start mb-2">
                   <h4 class="font-medium text-gray-800 dark:text-gray-200 truncate pr-2" :title="tag.title">{{ tag.title }}</h4>
                   <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                     <button @click="openEditTag(tag)" class="text-gray-400 hover:text-teal-600 dark:hover:text-teal-400"><span class="material-icons-round text-[16px]">edit</span></button>
                     <button @click="deleteTag(tag)" class="text-gray-400 hover:text-red-500"><span class="material-icons-round text-[16px]">close</span></button>
                   </div>
                 </div>
                 <div class="text-xs text-gray-500 dark:text-slate-400 font-mono mb-3 truncate">
                    {{ tag.slug }}
                 </div>
                 
                 <div class="flex flex-wrap gap-1 mt-auto">
                    <span v-if="tag.is_public" class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300">
                      Public
                    </span>
                    <span v-if="tag.is_filter" class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                      Filter
                    </span>
                 </div>
               </div>
            </div>
          </div>
        </div>

        <div v-else class="flex-1 flex flex-col items-center justify-center text-gray-400 dark:text-slate-500 p-8 text-center">
            <span class="material-icons-round text-5xl mb-4 opacity-30">view_sidebar</span>
            <p class="text-lg font-medium text-gray-500 dark:text-slate-400">Выберите группу слева</p>
            <p class="text-sm mt-1 max-w-sm">Или создайте новую группу тегов для классификации товаров</p>
        </div>
      </div>
    </div>

    <!-- Modals -->
    <TagGroupModal 
      v-model="isGroupModalOpen" 
      :tagGroup="editingGroup" 
      @success="fetchTags" 
    />
    
    <TagModal 
      v-model="isTagModalOpen" 
      :tag="editingTag" 
      :groupId="selectedGroupId"
      @success="fetchTags" 
    />

  </div>
</template>
