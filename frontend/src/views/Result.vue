<template>
  <div v-if="plan">
    <a-page-header :title="plan.title" :sub-title="`${plan.destination} · ${plan.date_range}`">
      <template #extra>
        <a-button @click="$router.push({ name: 'home' })">再来一次</a-button>
      </template>
    </a-page-header>

    <!-- 每日行程 — 简化版:景点列表 + 酒店区域建议 -->
    <a-card
      v-for="(day, idx) in plan.days"
      :key="day.date"
      style="margin-bottom: 16px"
    >
      <template #title>
        <span style="font-size: 16px">Day {{ idx + 1 }} · {{ day.date }}</span>
        <a-tag v-if="day.theme" color="blue" style="margin-left: 8px">{{ day.theme }}</a-tag>
      </template>
      <template #extra>
        <a-tooltip v-if="day.weather" :title="weatherTooltip(day)">
          <div class="weather-chip">
            <span class="weather-icon">{{ weatherIcon(day.weather) }}</span>
            <span class="weather-text">{{ day.weather }}</span>
            <span v-if="day.temp_max != null && day.temp_min != null" class="weather-temp">
              {{ day.temp_min }}°~{{ day.temp_max }}°
            </span>
          </div>
        </a-tooltip>
      </template>

      <!-- 酒店区域建议(替代具体酒店预订) -->
      <a-alert
        v-if="day.hotel_area_hint"
        type="info"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #message>
          <strong>🏨 酒店区域建议:</strong>{{ day.hotel_area_hint }}
        </template>
      </a-alert>

      <h4 style="margin-top: 8px">景点(按最优路径排序)</h4>
      <a-list :data-source="day.attractions" size="small">
        <template #renderItem="{ item, index }">
          <a-list-item>
            <a-list-item-meta>
              <template #title>
                <a-tag color="blue" style="margin-right: 8px">{{ index + 1 }}</a-tag>
                <strong>{{ item.name }}</strong>
                <a-tag v-if="item.cost === 0" color="green" style="margin-left: 8px">免费</a-tag>
                <a-tag v-else color="orange" style="margin-left: 8px">¥{{ item.cost }}</a-tag>
                <a-tag
                  v-if="item.dist_from_prev_km !== null && item.dist_from_prev_km !== undefined"
                  color="cyan"
                  style="margin-left: 8px"
                >
                  距上一段 ~{{ item.dist_from_prev_km }}km
                </a-tag>
              </template>
              <template #description>
                <div>{{ item.address }}</div>
                <div v-if="item.notes" style="color: #888; font-size: 12px; margin-top: 4px">
                  {{ item.notes }}
                </div>
              </template>
            </a-list-item-meta>
          </a-list-item>
        </template>
      </a-list>

      <a-divider style="margin: 12px 0" />
      <h4>地图</h4>
      <DayMap :day="day" />
    </a-card>

    <!-- 贴士 -->
    <a-card title="实用贴士" v-if="plan.notes.length > 0">
      <a-list :data-source="plan.notes" size="small">
        <template #renderItem="{ item }">
          <a-list-item>{{ item }}</a-list-item>
        </template>
      </a-list>
    </a-card>
  </div>

  <a-empty v-else description="暂无行程数据">
    <a-button type="primary" @click="$router.push({ name: 'home' })">回到首页</a-button>
  </a-empty>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { TripPlan } from '../types'
import DayMap from '../components/DayMap.vue'

// 高德天气描述 → emoji 图标（覆盖常见情况，未匹配时显示云图）
function weatherIcon(desc: string): string {
  const d = desc || ''
  if (/晴/.test(d) && !/转/.test(d)) return '☀️'
  if (/多云/.test(d)) return '⛅'
  if (/阴/.test(d)) return '☁️'
  if (/雨/.test(d)) return /雷/.test(d) ? '⛈️' : '🌧️'
  if (/雪/.test(d)) return '❄️'
  if (/雾/.test(d) || /霾/.test(d)) return '🌫️'
  if (/沙|尘/.test(d)) return '🌪️'
  return '🌥️'
}

function weatherTooltip(day: TripPlan['days'][number]): string {
  if (!day.weather) return ''
  const temp = day.temp_min != null && day.temp_max != null ? `${day.temp_min}°C ~ ${day.temp_max}°C` : ''
  return [day.weather, temp].filter(Boolean).join(' · ')
}

const plan = ref<TripPlan | null>(null)

// 直接读 Home.vue 在 SSE done 时写入的 plan;刷新页面/直链 Result 时为 null,显示 empty
onMounted(() => {
  const raw = sessionStorage.getItem('trip_plan')
  if (raw) {
    try {
      plan.value = JSON.parse(raw)
    } catch {
      plan.value = null
    }
  }
})
</script>

<style scoped>
.weather-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #f0f7ff;
  border-radius: 14px;
  font-size: 13px;
  color: #1677ff;
  cursor: default;
}
.weather-icon {
  font-size: 16px;
  line-height: 1;
}
.weather-text {
  font-weight: 500;
}
.weather-temp {
  color: #888;
  font-size: 12px;
}
</style>