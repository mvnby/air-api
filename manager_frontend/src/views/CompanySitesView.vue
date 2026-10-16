<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { managerCompaniesApi, type CompanySite } from '../services/manager-companies';
import CompanySitesList from '../components/manager/CompanySitesList.vue';
import { getApiErrorMessage } from '../utils/api-errors';
const sites = ref<CompanySite[]>([]), error = ref(''), loading = ref(true);
onMounted(async () => { try { sites.value = (await managerCompaniesApi.sites()).items; } catch (e) { error.value = getApiErrorMessage(e); } finally { loading.value = false; } });
</script>
<template><section class="mx-auto max-w-5xl space-y-5 p-4 sm:p-8"><h1 class="text-2xl font-bold">Сайты компании</h1><p class="text-sm text-gray-500">Площадки и домены выбранной компании. Для изменения обратитесь к поддержке платформы.</p><p v-if="loading" role="status">Загрузка…</p><p v-if="error" role="alert" class="text-red-600">{{ error }}</p><CompanySitesList v-if="!loading" :sites="sites" /></section></template>
