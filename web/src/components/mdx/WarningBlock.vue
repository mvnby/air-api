<template>
  <div class="my-8 p-6 bg-amber-50 dark:bg-amber-900/10 border-l-4 border-amber-500 rounded-r-2xl shadow-sm transition-all duration-300">
    <div class="flex items-start gap-4">
      <div class="text-amber-500 mt-1 shrink-0">
        <span class="material-icons-round text-2xl">error_outline</span>
      </div>
      <div>
        <h4 v-if="title" class="font-bold text-amber-900 dark:text-amber-200 mb-1 text-lg not-prose">{{ title }}</h4>
        <div class="text-amber-800 dark:text-amber-100/90 leading-relaxed font-medium">
          <slot />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: String
});
</script>