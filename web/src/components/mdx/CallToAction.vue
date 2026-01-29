<template>
  <div class="my-12 p-8 md:p-12 glass border-teal-500/20 rounded-[2rem] text-center shadow-xl not-prose relative overflow-hidden group transition-all duration-500 hover:shadow-2xl hover:translate-y-[-4px]">
    <!-- Animated Gradient Background -->
    <div class="absolute inset-0 bg-gradient-to-br from-teal-600/10 via-transparent to-teal-500/5 dark:from-teal-400/5 dark:to-transparent pointer-events-none"></div>
    <div class="absolute -top-24 -right-24 w-48 h-48 bg-teal-500/20 rounded-full blur-3xl group-hover:bg-teal-400/30 transition-colors duration-500"></div>
    
    <div class="relative z-10">
      <h3 class="text-2xl md:text-3xl font-display font-extrabold mb-4 bg-gradient-to-r from-teal-600 to-teal-400 dark:from-teal-400 dark:to-teal-200 bg-clip-text text-transparent italic">
        {{ text }}
      </h3>
      <p v-if="subtext" class="mb-8 text-lg text-slate-600 dark:text-slate-300/90 max-w-2xl mx-auto leading-relaxed">
        {{ subtext }}
      </p>
      
      <a :href="link" class="btn btn-primary btn-large px-10 py-4 text-lg inline-flex items-center group/btn">
        {{ btnText }}
        <span class="material-icons-round ml-2 transition-transform duration-300 group-hover/btn:translate-x-1">arrow_forward</span>
      </a>
    </div>
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