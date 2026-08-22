<template>
  <div class="animate-pulse space-y-4" aria-label="Загрузка дашборда">
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"><div v-for="index in 6" :key="index" class="h-28 rounded-xl bg-slate-200 dark:bg-slate-700" /></div>
    <div class="grid gap-4 lg:grid-cols-2"><div class="h-72 rounded-xl bg-slate-200 dark:bg-slate-700" /><div class="h-72 rounded-xl bg-slate-200 dark:bg-slate-700" /></div>
  </div>
</template>
