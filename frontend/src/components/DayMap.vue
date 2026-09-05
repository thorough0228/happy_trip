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

const COLORS = {
  attraction: '#1677ff',  // 蓝
  hotel: '#52c41a',       // 绿
  meal: '#fa8c16',        // 橙
}

async function renderMap() {
  if (!mapDiv.value) return

  try {
    const AMap = await loadAMap()
    initMap(AMap)
    addMarkers(AMap)
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

  // 收集所有 POI 的经纬度,确定地图中心
  const points: Array<[number, number]> = []

  for (const a of props.day.attractions) {
    if (a.location) points.push(a.location)
  }
  if (props.day.hotel?.location) points.push(props.day.hotel.location)
  for (const meal of Object.values(props.day.meals)) {
    if (meal?.location) points.push(meal.location)
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

function addMarkers(AMap: any) {
  // 景点 marker
  for (const a of props.day.attractions) {
    if (!a.location) continue
    const marker = new AMap.Marker({
      position: a.location,
      title: a.name,
      label: { content: `📍 ${a.name}`, direction: 'top' },
    })
    marker.setMap(mapInstance)
    markers.push(marker)

    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding: 8px; min-width: 180px">
          <strong>${a.name}</strong><br>
          <span style="color: #666; font-size: 12px">${a.address}</span><br>
          <span style="color: ${COLORS.attraction}">📍 景点 · ¥${a.cost}</span>
        </div>
      `,
    })
    marker.on('click', () => infoWindow.open(mapInstance, marker.getPosition()))
  }

  // 酒店 marker
  if (props.day.hotel?.location) {
    const marker = new AMap.Marker({
      position: props.day.hotel.location,
      title: props.day.hotel.name,
      label: { content: `🏨 ${props.day.hotel.name}`, direction: 'top' },
    })
    marker.setMap(mapInstance)
    markers.push(marker)

    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding: 8px; min-width: 180px">
          <strong>${props.day.hotel.name}</strong><br>
          <span style="color: #666; font-size: 12px">${props.day.hotel.address}</span><br>
          <span style="color: ${COLORS.hotel}">🏨 住宿 · ¥${props.day.hotel.cost}/晚 × ${props.day.hotel.nights}</span>
        </div>
      `,
    })
    marker.on('click', () => infoWindow.open(mapInstance, marker.getPosition()))
  }

  // 餐饮 marker
  for (const [mealType, meal] of Object.entries(props.day.meals)) {
    if (!meal?.location) continue
    const icon = mealType === 'breakfast' ? '☕' : mealType === 'lunch' ? '🍱' : '🍽️'
    const marker = new AMap.Marker({
      position: meal.location,
      title: meal.name,
      label: { content: `${icon} ${meal.name}`, direction: 'top' },
    })
    marker.setMap(mapInstance)
    markers.push(marker)

    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding: 8px; min-width: 180px">
          <strong>${meal.name}</strong><br>
          <span style="color: #666; font-size: 12px">${meal.address}</span><br>
          <span style="color: ${COLORS.meal}">${icon} ${mealType} · ¥${meal.cost}</span>
        </div>
      `,
    })
    marker.on('click', () => infoWindow.open(mapInstance, marker.getPosition()))
  }
}

async function renderRouteSegments(AMap: any) {
  // 景点顺序连线:默认画直线(蓝色),异步调 walking API 替换为真实路网(绿色)
  const atts = props.day.attractions.filter(a => a.location)
  if (atts.length < 2) return

  // 直线兜底(蓝色)
  const linePath = atts.map(a => a.location!)
  const fallback = new AMap.Polyline({
    path: linePath,
    strokeColor: '#1677ff',
    strokeWeight: 3,
    strokeOpacity: 0.8,
    strokeStyle: 'solid',
  })
  fallback.setMap(mapInstance)
  polylines.push(fallback)

  // 异步获取真实路网替换
  const realCoords: [number, number][][] = []
  for (let i = 1; i < atts.length; i++) {
    const result = await getWalkingRoute(atts[i - 1].location!, atts[i].location!)
    if (result && result.coords && result.coords.length > 0) {
      realCoords.push(result.coords as [number, number][])
    } else {
      realCoords.push([atts[i - 1].location!, atts[i].location!])  // fallback 到直线
    }
  }

  if (realCoords.length > 0) {
    const real = new AMap.Polyline({
      path: realCoords.flat(),
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

onMounted(renderMap)

// 监听 day 变化(切换 Day 时重新渲染)
watch(() => props.day, renderMap)
</script>