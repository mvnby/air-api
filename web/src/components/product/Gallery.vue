<template>
  <div class="gallery-component">
    <div class="main-image-wrapper">
      <img
        v-if="activeImage && !brokenImages.has(activeImage)"
        :src="activeImage"
        alt="Product Image"
        class="main-img"
        @click="zoomImage"
      />
      <div v-else class="image-placeholder">
          <span class="material-icons-round placeholder-icon">image_not_supported</span>
      </div>
    </div>
    
    <div v-if="images && images.length > 1" class="thumbnails-track">
      <template v-for="(img, idx) in images" :key="idx">
        <div 
          v-if="!brokenImages.has(img)"
          class="thumb-item"
          :class="{ active: img === activeImage }"
          @click="activeImage = img"
        >
          <img 
            :src="img" 
            loading="lazy" 
            alt="Thumbnail"
            @error="handleImageError(img)"
          />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, reactive, onMounted } from 'vue';

const props = defineProps({
  images: {
    type: Array,
    default: () => []
  },
  initialImage: {
    type: String,
    default: ''
  }
});

const activeImage = ref(props.initialImage || props.images[0]);
const brokenImages = ref(new Set());

watch(() => props.initialImage, (newVal) => {
  if (newVal) activeImage.value = newVal;
});

const handleImageError = (url) => {
  if (!brokenImages.value.has(url)) {
    brokenImages.value.add(url);
    // Trigger reactivity by creating a new Set
    brokenImages.value = new Set(brokenImages.value);
  }
  
  // If the currently active image is broken, try to switch to the first working one
  if (activeImage.value === url) {
    const firstWorking = props.images.find(img => !brokenImages.value.has(img));
    if (firstWorking) {
      activeImage.value = firstWorking;
    } else {
        activeImage.value = null;
    }
  }
};

const zoomImage = () => {
    if (!activeImage.value) return;
    console.log('Zoom functionality to be implemented');
};
</script>

<style scoped>
.gallery-component {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
  min-width: 0; /* Important for flex/grid children to shrink */
}

.main-image-wrapper {
  position: relative;
  width: 100%;
  aspect-ratio: 4/3.5; /* Keeping it slightly rectangular */
  background: var(--surface, #fff);
  border-radius: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,0.03);
  border: 1px solid var(--border);
}

:global(.dark) .main-image-wrapper {
    background: rgba(255,255,255,0.02);
}

.main-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  transition: transform 0.3s ease;
  cursor: zoom-in;
  padding: 1.5rem;
}

.main-img:hover {
    transform: scale(1.03);
}

.image-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    opacity: 0.3;
}
.placeholder-icon {
    font-size: 4rem;
}

.thumbnails-track {
  display: flex;
  gap: 1rem;
  overflow-x: auto;
  padding: 4px; /* Space for focus rings */
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none; /* Firefox */
  width: 100%;
  max-width: 100%;
}
.thumbnails-track::-webkit-scrollbar {
    display: none; /* Chrome/Safari */
}

.thumb-item {
  flex: 0 0 70px;
  height: 70px;
  border-radius: 12px;
  overflow: hidden;
  border: 2px solid transparent;
  cursor: pointer;
  background: var(--surface, white);
  transition: all 0.2s ease;
  border: 1px solid var(--border);
  user-select: none;
  -webkit-user-drag: none;
}

.thumb-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.thumb-item.active {
  border-color: #007f80; /* Teal Brand Color */
  transform: translateY(-2px);
  box-shadow: 0 4px 10px rgba(0, 127, 128, 0.2);
}

@media (max-width: 768px) {
    .main-image-wrapper {
        border-radius: 1.5rem;
        aspect-ratio: 1/1;
    }
    .gallery-component {
        width: 100%;
    }
}
</style>
