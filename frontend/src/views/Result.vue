<template>
  <div v-if="plan">
    <a-page-header :title="plan.title" :sub-title="`${plan.destination} · ${plan.date_range}`">
      <template #extra>
        <a-button @click="$router.push({ name: 'home' })">再来一次</a-button>
      </template>
    </a-page-header>

    <!-- 行程总览 -->
    <a-card class="overview-card" :bordered="false">
      <div class="overview-title">📊 行程总览</div>
      <a-row :gutter="16">
        <a-col :xs="12" :sm="6">
          <div class="overview-item">
            <div class="overview-value">{{ plan.days.length }}</div>
            <div class="overview-label">行程天数</div>
          </div>
        </a-col>
        <a-col :xs="12" :sm="6">
          <div class="overview-item">
            <div class="overview-value">{{ totalAttractions }}</div>
            <div class="overview-label">景点总数</div>
          </div>
        </a-col>
        <a-col :xs="12" :sm="6">
          <div class="overview-item">
            <div class="overview-value">¥{{ totalCost }}</div>
            <div class="overview-label">门票总额</div>
          </div>
        </a-col>
        <a-col :xs="12" :sm="6">
          <div class="overview-item">
            <div class="overview-value">{{ totalDuration }} 分钟</div>
            <div class="overview-label">游玩总时长</div>
          </div>
        </a-col>
      </a-row>

      <div class="overview-map">
        <OverviewMap :plan="plan" />
      </div>
    </a-card>

    <!-- 每日行程 — 可折叠卡片 -->
    <a-card
      v-for="(day, idx) in plan.days"
      :key="day.date"
      style="margin-bottom: 16px"
    >
      <template #title>
        <a class="day-toggle" @click.prevent="toggleDay(idx)">
          <span class="day-caret">{{ expandedDays[idx] ? '▼' : '▶' }}</span>
          <span style="font-size: 16px; margin-left: 4px">
            Day {{ idx + 1 }} · {{ day.date }}
          </span>
          <a-tag v-if="day.theme" color="blue" style="margin-left: 8px">{{ day.theme }}</a-tag>
        </a>
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

      <div v-show="expandedDays[idx]">
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
      </div>
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
import { computed, reactive, ref, onMounted } from 'vue'
import type { TripPlan } from '../types'
import DayMap from '../components/DayMap.vue'
import OverviewMap from '../components/OverviewMap.vue'

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
// 每张卡是否展开(默认全部展开)
const expandedDays = reactive<boolean[]>([])

const totalAttractions = computed(() => {
  if (!plan.value) return 0
  return plan.value.days.reduce((sum, d) => sum + d.attractions.length, 0)
})

const totalCost = computed(() => {
  if (!plan.value) return 0
  return plan.value.days.reduce(
    (sum, d) => sum + d.attractions.reduce((s, a) => s + (a.cost || 0), 0),
    0,
  )
})

const totalDuration = computed(() => {
  if (!plan.value) return 0
  return plan.value.days.reduce(
    (sum, d) => sum + d.attractions.reduce((s, a) => s + (a.visit_duration || 0), 0),
    0,
  )
})

function toggleDay(idx: number) {
  expandedDays[idx] = !expandedDays[idx]
}

// 直接读 Home.vue 在 SSE done 时写入的 plan;刷新页面/直链 Result 时为 null,显示 empty
onMounted(() => {
  const raw = sessionStorage.getItem('trip_plan')
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as TripPlan
      plan.value = parsed
      // 默认全部展开
      expandedDays.length = 0
      for (let i = 0; i < parsed.days.length; i++) {
        expandedDays.push(true)
      }
    } catch {
      plan.value = null
    }
  }
})
</script>

<style scoped>
.overview-card {
  margin-bottom: 16px;
  background: linear-gradient(135deg, #f0f7ff 0%, #e6f4ff 100%);
}
.overview-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #333;
}
.overview-item {
  text-align: center;
  padding: 12px 8px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e6f4ff;
}
.overview-value {
  font-size: 22px;
  font-weight: 700;
  color: #1677ff;
  margin-bottom: 4px;
}
.overview-label {
  font-size: 12px;
  color: #888;
}
.overview-map {
  margin-top: 12px;
}

.day-toggle {
  color: inherit;
  cursor: pointer;
}
.day-toggle:hover {
  color: #1677ff;
}
.day-caret {
  font-size: 12px;
  color: #888;
  display: inline-block;
  width: 14px;
}

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