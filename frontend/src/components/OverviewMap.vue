<template>
  <div>
    <div v-if="loadError" class="map-error">
      🗺️ 地图加载失败:{{ loadError }}
      <div style="font-size: 12px; margin-top: 4px">
        请检查 frontend/.env 中的 VITE_AMAP_WEB_KEY
      </div>
    </div>
    <div v-else :ref="el => mapDiv = el as HTMLElement" class="map-canvas"></div>
    <div class="legend">
      <span
        v-for="(c, idx) in legendColors"
        :key="idx"
        class="legend-item"
      >
        <span class="legend-dot" :style="{ background: c }"></span>
        Day {{ idx + 1 }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { loadAMap } from '../services/amapLoader'
import type { TripPlan } from '../types'

const props = defineProps<{ plan: TripPlan }>()

const mapDiv = ref<HTMLElement | null>(null)
const loadError = ref<string>('')

let mapInstance: any = null
const markers: any[] = []
const polylines: any[] = []

// 每天一种颜色,10 天以内都覆盖
const ROUTE_COLORS = [
  '#1677ff', // 蓝
  '#52c41a', // 绿
  '#fa541c', // 橙红
  '#722ed1', // 紫
  '#eb2f96', // 粉
  '#13c2c2', // 青
  '#faad14', // 琥珀
  '#f5222d', // 红
  '#2f54eb', // 钴蓝
  '#a0d911', // 青绿
]

const legendColors = computed(() =>
  props.plan.days.map((_, i) => ROUTE_COLORS[i % ROUTE_COLORS.length]),
)

async function renderMap() {
  if (!mapDiv.value) return
  try {
    const AMap = await loadAMap()
    initMap(AMap)
    await renderAllDayRoutes(AMap)
  } catch (e: any) {
    loadError.value = e.message || String(e)
  }
}

function initMap(AMap: any) {
  markers.forEach((m) => m.setMap(null))
  markers.length = 0
  polylines.forEach((p) => p.setMap(null))
  polylines.length = 0

  if (mapInstance) {
    mapInstance.destroy()
    mapInstance = null
  }

  // 计算所有景点的中心点
  const points: Array<[number, number]> = []
  for (const d of props.plan.days) {
    for (const a of d.attractions) {
      if (a.location) points.push(a.location)
    }
  }

  let center: [number, number] = [118.78, 32.04] // 默认南京
  if (points.length > 0) {
    const avgLng = points.reduce((s, p) => s + p[0], 0) / points.length
    const avgLat = points.reduce((s, p) => s + p[1], 0) / points.length
    center = [avgLng, avgLat]
  }

  mapInstance = new AMap.Map(mapDiv.value, {
    zoom: 11,
    center,
    mapStyle: 'amap://styles/light',
  })
}

async function renderAllDayRoutes(AMap: any) {
  /**
   * 每天画一条折线(直线兜底,无 walking route 真实路网),
   * 每个景点一个 marker,标记 (day_idx, attraction_idx)。
   * 每天用不同颜色区分。
   */
  props.plan.days.forEach((day, dayIdx) => {
    const color = ROUTE_COLORS[dayIdx % ROUTE_COLORS.length]
    const path: Array<[number, number]> = []
    day.attractions.forEach((a, aIdx) => {
      if (!a.location) return
      path.push(a.location)
      const marker = new AMap.Marker({
        position: a.location,
        title: a.name,
        label: {
          content: a.name,
          direction: 'top',
        },
      })
      marker.setMap(mapInstance)
      markers.push(marker)
    })
    if (path.length < 2) return
    const line = new AMap.Polyline({
      path,
      strokeColor: color,
      strokeWeight: 4,
      strokeOpacity: 0.85,
      strokeStyle: 'solid',
    })
    line.setMap(mapInstance)
    polylines.push(line)
  })

  // 自适应缩放:把所有 marker 框起来
  if (markers.length > 0) {
    mapInstance.setFitView(null, false, [40, 40, 40, 40])
  }
}

onMounted(renderMap)

watch(() => props.plan, renderMap, { deep: true })
</script>

<style scoped>
.map-canvas {
  width: 100%;
  height: 500px;
  border-radius: 4px;
}
.map-error {
  padding: 24px;
  color: #999;
  text-align: center;
  background: #fafafa;
  border-radius: 4px;
}
.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
  padding: 8px 4px;
  font-size: 12px;
  color: #555;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}
</style>