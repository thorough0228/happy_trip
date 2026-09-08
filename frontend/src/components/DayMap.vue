<template>
  <div>
    <div v-if="loadError" style="padding: 16px; color: #999; text-align: center; background: #fafafa; border-radius: 4px">
      🗺️ 地图加载失败:{{ loadError }}
      <div style="font-size: 12px; margin-top: 4px">请检查 frontend/.env 中的 VITE_AMAP_WEB_KEY</div>
    </div>
    <div v-else :ref="el => mapDiv = el as HTMLElement" :style="{ width: '100%', height: '300px', borderRadius: '4px' }"></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { loadAMap } from '../services/amapLoader'
import { getWalkingRoute } from '../services/api'
import type { Day } from '../types'

const props = defineProps<{ day: Day }>()

const mapDiv = ref<HTMLElement | null>(null)
const loadError = ref<string>('')
let mapInstance: any = null
let markers: any[] = []
let polylines: any[] = []

const ATTRACTION_COLOR = '#1677ff'  // 景点 marker 蓝色

async function renderMap() {
  if (!mapDiv.value) return

  try {
    const AMap = await loadAMap()
    initMap(AMap)
    addAttractionMarkers(AMap)
    await renderRouteSegments(AMap)
  } catch (e: any) {
    loadError.value = e.message || String(e)
  }
}

function initMap(AMap: any) {
  // 清理旧 markers
  markers.forEach(m => m.setMap(null))
  markers = []
  polylines.forEach(p => p.setMap(null))
  polylines = []

  if (mapInstance) {
    mapInstance.destroy()
    mapInstance = null
  }

  // 收集景点经纬度,确定地图中心
  const points: Array<[number, number]> = []
  for (const a of props.day.attractions) {
    if (a.location) points.push(a.location)
  }

  // 默认中心:杭州西湖(如果没数据)
  let center: [number, number] = [120.149, 30.246]
  if (points.length > 0) {
    const avgLng = points.reduce((s, p) => s + p[0], 0) / points.length
    const avgLat = points.reduce((s, p) => s + p[1], 0) / points.length
    center = [avgLng, avgLat]
  }

  mapInstance = new AMap.Map(mapDiv.value, {
    zoom: 13,
    center: center,
    mapStyle: 'amap://styles/light',
  })
}

function addAttractionMarkers(AMap: any) {
  /**
   * 只画景点 marker,带序号(对应路径顺序)。
   * 序号让用户清楚"先逛 A,再去 B"的路径。
   */
  props.day.attractions.forEach((a, idx) => {
    if (!a.location) return
    const marker = new AMap.Marker({
      position: a.location,
      title: `${idx + 1}. ${a.name}`,
      label: { content: `${idx + 1}. ${a.name}`, direction: 'top' },
    })
    marker.setMap(mapInstance)
    markers.push(marker)

    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding: 8px; min-width: 180px">
          <strong>${idx + 1}. ${a.name}</strong><br>
          <span style="color: #666; font-size: 12px">${a.address}</span><br>
          <span style="color: ${ATTRACTION_COLOR}">📍 景点 · ¥${a.cost}</span>
          ${a.dist_from_prev_km !== null && a.dist_from_prev_km !== undefined
            ? `<br><span style="color: #999; font-size: 12px">距上一段 ~${a.dist_from_prev_km}km</span>`
            : ''}
        </div>
      `,
    })
    marker.on('click', () => infoWindow.open(mapInstance, marker.getPosition()))
  })
}

async function renderRouteSegments(AMap: any) {
  /**
   * 画景点顺序路径:A1 → A2 → ... → AN
   * 默认画直线(蓝色),异步调 walking API 段段获取真实路网(绿色实线)替换。
   * 无 hotel 起终点,无 meal 节点,纯景点连线。
   */
  const path = _buildPath()
  if (path.length < 2) return

  // 直线兜底(蓝色)
  const fallback = new AMap.Polyline({
    path,
    strokeColor: ATTRACTION_COLOR,
    strokeWeight: 3,
    strokeOpacity: 0.8,
    strokeStyle: 'solid',
  })
  fallback.setMap(mapInstance)
  polylines.push(fallback)

  // 逐段获取真实路网
  const realSegments: [number, number][][] = []
  for (let i = 0; i < path.length - 1; i++) {
    const result = await getWalkingRoute(path[i], path[i + 1])
    if (result && result.coords && result.coords.length > 0) {
      realSegments.push(result.coords as [number, number][])
    } else {
      realSegments.push([path[i], path[i + 1]])  // 单段 fallback
    }
  }

  if (realSegments.length > 0) {
    const real = new AMap.Polyline({
      path: realSegments.flat(),
      strokeColor: '#52c41a',
      strokeWeight: 4,
      strokeOpacity: 0.9,
      strokeStyle: 'solid',
    })
    real.setMap(mapInstance)
    fallback.setMap(null)
    polylines.push(real)
  }
}

function _buildPath(): [number, number][] {
  /** 景点顺序路径:第一个景点 → ... → 最后一个景点(无起终点)。 */
  const path: [number, number][] = []
  for (const a of props.day.attractions) {
    if (a.location) path.push(a.location)
  }
  return path
}

onMounted(renderMap)

// 监听 day 变化(切换 Day 时重新渲染)
watch(() => props.day, renderMap)
</script>