<template>
  <div class="my-8 p-6 bg-amber-50 border-l-4 border-amber-500 rounded-r-lg">
    <div class="flex items-start gap-4">
      <div class="text-amber-500 mt-1">
        <svg xmlns="http://www.w3.org/2000/svg" class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      </div>
      <div>
        <h4 v-if="title" class="font-bold text-amber-900 mb-1 text-lg not-prose">{{ title }}</h4>
        <div class="text-amber-800 leading-relaxed">
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