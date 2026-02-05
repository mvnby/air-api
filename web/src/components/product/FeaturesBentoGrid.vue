<template>
  <div v-if="activeFeatures.length > 0" class="features-bento-grid mt-12 mb-16">
    <h2 class="text-2xl font-bold mb-6 text-slate-800">Ключевые особенности</h2>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div 
        v-for="feature in activeFeatures" 
        :key="feature.id"
        :class="[
          'feature-card group',
          feature.id === 'inverter' ? 'md:col-span-2 aspect-[2/1]' : 'aspect-square'
        ]"
      >
        <div class="card-inner">
          <div class="icon-wrapper">
            <img :src="feature.icon" :alt="feature.title" class="feature-icon" />
          </div>
          <div class="content">
            <h3 class="title">{{ feature.title }}</h3>
            <p class="subtitle">{{ feature.subtitle }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  product: {
    type: Object,
    required: true
  }
});

const specs = computed(() => props.product?.specs || {});

const activeFeatures = computed(() => {
  const features = [];

  // Inverter
  if (specs.value.inverter === true || specs.value.inverter === 'true' || specs.value.inverter === 'Да') {
    features.push({
      id: 'inverter',
      title: 'Инверторный мотор',
      subtitle: 'Тише, экономичнее и долговечнее обычных компрессоров',
      icon: '/img/features/inverter-3d.png'
    });
  }

  // WiFi
  const hasWifi = specs.value.wifi_ready === true || 
                 specs.value.wifi_ready === 'true' || 
                 specs.value.wifi_ready === 'Да' || 
                 specs.value.wifi_ready === 'да';
  if (hasWifi) {
    features.push({
      id: 'wifi',
      title: 'Wi-Fi Управление',
      subtitle: 'Управляйте климатом из любой точки мира через смартфон',
      icon: '/img/features/wifi-3d.png'
    });
  }

  // Silent Mode
  const noiseIndoor = parseInt(specs.value.noise_indoor);
  const isSilent = specs.value.silent_mode === true || 
                  specs.value.silent_mode === 'true' || 
                  (noiseIndoor && noiseIndoor < 22);
  if (isSilent) {
    features.push({
      id: 'silent',
      title: 'Бесшумный режим',
      subtitle: 'Минимальный уровень шума для комфортного сна и отдыха',
      icon: '/img/features/silent-3d.png'
    });
  }

  // Health / Cleaning
  const hasHealth = specs.value.self_cleaning === true || 
                   specs.value.self_cleaning === 'true' || 
                   specs.value.fresh_air === true || 
                   specs.value.fresh_air === 'true';
  if (hasHealth) {
    features.push({
      id: 'health',
      title: 'Здоровье и Чистота',
      subtitle: 'Система очистки воздуха и самоочистка внутреннего блока',
      icon: '/img/features/health-3d.png'
    });
  }

  return features;
});
</script>

<style scoped>
.features-bento-grid {
  width: 100%;
}

.feature-card {
  position: relative;
  background: white;
  border-radius: 1.5rem;
  padding: 2rem;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid rgba(0, 0, 0, 0.03);
}

.feature-card:hover {
  transform: translateY(-6px);
  box-shadow: 0 10px 25px rgba(0, 127, 128, 0.1);
  border-color: rgba(0, 127, 128, 0.1);
}

.card-inner {
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.icon-wrapper {
  width: 100%;
  display: flex;
  justify-content: flex-start;
  align-items: flex-start;
}

.feature-icon {
  width: 130px;
  height: 130px;
  object-fit: contain;
  filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.05));
  transition: transform 0.5s ease;
}

.feature-card:hover .feature-icon {
  transform: scale(1.1) rotate(5deg);
}

.content {
  margin-top: auto;
}

.title {
  font-size: 1.5rem;
  font-weight: 800;
  color: #0f172a;
  margin-bottom: 0.5rem;
}

.subtitle {
  font-size: 0.95rem;
  color: #64748b;
  line-height: 1.4;
  max-width: 90%;
}

@media (max-width: 768px) {
  .feature-card {
    aspect-ratio: auto !important;
    min-height: 200px;
  }
  .feature-icon {
    width: 80px;
    height: 80px;
  }
  .title {
    font-size: 1.25rem;
  }
}
</style>
