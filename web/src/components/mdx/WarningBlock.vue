<template>
  <div class="my-8 p-6 bg-amber-50 dark:bg-amber-900/10 border-l-4 border-amber-500 rounded-r-2xl shadow-sm transition-all duration-300">
    <div class="flex flex-col gap-3">
      <h4 v-if="title" class="flex items-center gap-2 font-bold text-amber-900 dark:text-amber-200 text-xl not-prose">
        <span class="material-icons-round text-2xl text-amber-600">error_outline</span>
        {{ title }}
      </h4>
      <div class="text-amber-800 dark:text-amber-100/90 leading-relaxed font-medium pl-1">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: String
});
</script>