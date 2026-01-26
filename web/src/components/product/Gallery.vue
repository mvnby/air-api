<template>
  <div class="gallery-component">
    <div class="main-image-wrapper">
      <img
        :src="activeImage"
        alt="Product Image"
        class="main-img"
        @click="zoomImage"
      />
    </div>
    
    <div v-if="images && images.length > 1" class="thumbnails-track">
      <div 
        v-for="(img, idx) in images" 
        :key="idx"
        class="thumb-item"
        :class="{ active: img === activeImage }"
        @click="activeImage = img"
      >
        <img :src="img" loading="lazy" alt="Thumbnail" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';

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

watch(() => props.initialImage, (newVal) => {
  if (newVal) activeImage.value = newVal;
});

const zoomImage = () => {
    // Optional: Implement lightbox or zoom logic here
    console.log('Zoom functionality to be implemented');
};
</script>

<style scoped>
.gallery-component {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
}

.main-image-wrapper {
  position: relative;
  width: 100%;
  aspect-ratio: 4/3.5; /* Keeping it slightly rectangular */
  background: #fff;
  border-radius: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,0.03);
}

.main-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  transition: transform 0.3s ease;
  cursor: zoom-in;
  padding: 1rem;
}

.main-img:hover {
    transform: scale(1.03);
}

.thumbnails-track {
  display: flex;
  gap: 1rem;
  overflow-x: auto;
  padding: 4px; /* Space for focus rings */
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none; /* Firefox */
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
  background: white;
  transition: all 0.2s ease;
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
        width: 93dvw;
    }
}
</style>
