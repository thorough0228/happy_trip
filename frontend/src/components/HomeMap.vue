<template>
  <div>
    <div v-if="loadError" style="padding: 24px; color: #999; text-align: center; background: #fafafa; border-radius: 4px">
      🗺️ 地图加载失败:{{ loadError }}
      <div style="font-size: 12px; margin-top: 4px">请检查 frontend/.env 中的 VITE_AMAP_WEB_KEY</div>
    </div>
    <div v-else :ref="el => mapDiv = el as HTMLElement" :style="{ width: '100%', height: '100%', minHeight: '520px', borderRadius: '4px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { loadAMap } from '../services/amapLoader'

const props = defineProps<{ destination: string }>()

const mapDiv = ref<HTMLElement | null>(null)
const loadError = ref<string>('')

let mapInstance: any = null
let geocoder: any = null
let marker: any = null
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const DEFAULT_CENTER: [number, number] = [120.149, 30.246]  // 杭州

async function renderMap() {
  if (!mapDiv.value) return
  try {
    const AMap = await loadAMap()
    mapInstance = new AMap.Map(mapDiv.value, {
      zoom: 11,
      center: DEFAULT_CENTER,
      mapStyle: 'amap://styles/light',
    })
    geocoder = new AMap.Geocoder({ city: '全国' })
    // 初始根据默认目的地定位
    if (props.destination) locate(props.destination)
  } catch (e: any) {
    loadError.value = e.message || String(e)
  }
}

function locate(city: string) {
  if (!geocoder || !mapInstance) return
  geocoder.getLocation(city, (status: string, result: any) => {
    if (status === 'complete' && result?.geocodes?.length) {
      const { lng, lat } = result.geocodes[0].location
      mapInstance.setCenter([lng, lat])
      mapInstance.setZoom(11)

      // 更新/创建城市标记点
      if (marker) {
        marker.setPosition([lng, lat])
      } else if (window.AMap) {
        marker = new window.AMap.Marker({
          position: [lng, lat],
          label: { content: `📍 ${city}`, direction: 'top' },
        })
        marker.setMap(mapInstance)
      }
    }
  })
}

// 目的地输入变化 → 防抖 400ms 后重新定位
watch(
  () => props.destination,
  (val) => {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      const v = (val || '').trim()
      if (v) locate(v)
    }, 400)
  },
)

onMounted(renderMap)
</script>