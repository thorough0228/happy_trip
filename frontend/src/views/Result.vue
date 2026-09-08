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
                <a-tag v-if="item.dist_from_prev_km !== null && item.dist_from_prev_km !== undefined" color="cyan" style="margin-left: 8px">
                  距上一段 ~{{ item.dist_from_prev_km }}km
                </a-tag>
              </template>
              <template #description>
                <div>{{ item.address }}</div>
                <div v-if="item.notes" style="color: #888; font-size: 12px; margin-top: 4px">{{ item.notes }}</div>
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
import { ref } from 'vue'
import { onMounted } from 'vue'
import type { TripPlan } from '../types'
import DayMap from '../components/DayMap.vue'

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