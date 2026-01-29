<template>
  <div class="my-10 p-8 bg-teal-600 rounded-2xl text-center shadow-lg text-white not-prose relative overflow-hidden group">
    <div class="absolute top-0 left-0 w-full h-full opacity-10 bg-[radial-gradient(circle_at_top_right,_var(--tw-gradient-stops))] from-white to-transparent pointer-events-none"></div>
    
    <h3 class="text-2xl font-bold mb-3 relative z-10">{{ text }}</h3>
    <p v-if="subtext" class="mb-6 opacity-90 relative z-10">{{ subtext }}</p>
    
    <a :href="link" class="inline-block px-8 py-3 bg-white text-teal-700 font-bold rounded-full hover:bg-teal-50 transition-colors shadow-md relative z-10 no-underline">
      {{ btnText }} →
    </a>
  </div>
</template>

<script setup>
defineProps({
  text: String,
  subtext: String,
  link: String,
  btnText: { type: String, default: "Подробнее" }
});
</script>