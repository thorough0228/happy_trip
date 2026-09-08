<template>
  <div v-if="plan">
    <a-page-header :title="plan.title" :sub-title="`${plan.destination} · ${plan.date_range}`">
      <template #extra>
        <a-button @click="$router.push({ name: 'home' })">再来一次</a-button>
      </template>
    </a-page-header>

    <!-- 每日行程 — 按时间段分组渲染 -->
    <a-card
      v-for="(day, idx) in plan.days"
      :key="day.date"
      style="margin-bottom: 16px"
    >
      <template #title>
        <span style="font-size: 16px">Day {{ idx + 1 }} · {{ day.date }}</span>
        <a-tag v-if="day.theme" color="blue" style="margin-left: 8px">{{ day.theme }}</a-tag>
      </template>

      <!-- 上午段:早餐 + 上午景点 -->
      <div class="time-segment">
        <h4 class="segment-title">🌅 上午</h4>
        <div v-if="day.meals.breakfast" class="meal-row">
          <a-tag color="orange">🍳 早餐</a-tag>
          <span><strong>{{ day.meals.breakfast.name }}</strong> · {{ day.meals.breakfast.address }} · ¥{{ day.meals.breakfast.cost }}</span>
        </div>
        <a-list :data-source="day.attractions.slice(0, day.split1)" size="small" :locale="{emptyText: '该时段无景点'}">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>
                  <strong>{{ item.name }}</strong>
                  <a-tag v-if="item.cost === 0" color="green" style="margin-left: 8px">免费</a-tag>
                  <a-tag v-else color="orange" style="margin-left: 8px">¥{{ item.cost }}</a-tag>
                  <a-tag v-if="item.dist_from_prev_km !== null && item.dist_from_prev_km !== undefined" color="blue" style="margin-left: 8px">
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
      </div>

      <!-- 中午/下午段:午餐 + 下午景点 -->
      <div class="time-segment">
        <h4 class="segment-title">☀️ 中午/下午</h4>
        <div v-if="day.meals.lunch" class="meal-row">
          <a-tag color="orange">🍱 午餐</a-tag>
          <span><strong>{{ day.meals.lunch.name }}</strong> · {{ day.meals.lunch.address }} · ¥{{ day.meals.lunch.cost }}</span>
        </div>
        <a-list :data-source="day.attractions.slice(day.split1, day.split2)" size="small" :locale="{emptyText: '该时段无景点'}">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>
                  <strong>{{ item.name }}</strong>
                  <a-tag v-if="item.cost === 0" color="green" style="margin-left: 8px">免费</a-tag>
                  <a-tag v-else color="orange" style="margin-left: 8px">¥{{ item.cost }}</a-tag>
                  <a-tag v-if="item.dist_from_prev_km !== null && item.dist_from_prev_km !== undefined" color="blue" style="margin-left: 8px">
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
      </div>

      <!-- 晚上段:晚餐 + 晚上景点(可选) -->
      <div v-if="day.split2 < day.attractions.length || day.meals.dinner" class="time-segment">
        <h4 class="segment-title">🌃 晚上</h4>
        <div v-if="day.meals.dinner" class="meal-row">
          <a-tag color="orange">🍽️ 晚餐</a-tag>
          <span><strong>{{ day.meals.dinner.name }}</strong> · {{ day.meals.dinner.address }} · ¥{{ day.meals.dinner.cost }}</span>
        </div>
        <a-list :data-source="day.attractions.slice(day.split2)" size="small" :locale="{emptyText: '该时段无景点'}">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>
                  <strong>{{ item.name }}</strong>
                  <a-tag v-if="item.cost === 0" color="green" style="margin-left: 8px">免费</a-tag>
                  <a-tag v-else color="orange" style="margin-left: 8px">¥{{ item.cost }}</a-tag>
                  <a-tag v-if="item.dist_from_prev_km !== null && item.dist_from_prev_km !== undefined" color="blue" style="margin-left: 8px">
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
      </div>

      <template v-if="day.hotel">
        <a-divider style="margin: 12px 0" />
        <h4>🏨 住宿</h4>
        <p>
          <strong>{{ day.hotel.name }}</strong> · {{ day.hotel.address }}<br>
          ¥{{ day.hotel.cost }}/晚 × {{ day.hotel.nights }}晚 = <strong>¥{{ day.hotel.cost * day.hotel.nights }}</strong>
        </p>
      </template>

      <a-divider style="margin: 12px 0" />
      <h4>地图</h4>
      <DayMap :day="day" />
    </a-card>

    <!-- 预算 -->
    <a-card title="预算总览" style="margin-bottom: 16px">
      <a-row :gutter="16">
        <a-col :span="6"><a-statistic title="景点" :value="plan.budget.total_attractions" prefix="¥" /></a-col>
        <a-col :span="6"><a-statistic title="酒店" :value="plan.budget.total_hotels" prefix="¥" /></a-col>
        <a-col :span="6"><a-statistic title="餐饮" :value="plan.budget.total_meals" prefix="¥" /></a-col>
        <a-col :span="6"><a-statistic title="交通" :value="plan.budget.total_transportation" prefix="¥" /></a-col>
      </a-row>
      <a-divider />
      <a-statistic title="总计" :value="plan.budget.total" prefix="¥" :value-style="{ color: '#1677ff', fontSize: '24px' }" />
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

<style scoped>
.time-segment {
  margin-bottom: 16px;
}
.time-segment .segment-title {
  margin-bottom: 8px;
  color: #333;
}
.meal-row {
  margin: 8px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>