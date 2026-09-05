<template>
  <div>
    <!-- 进度面板:任务未完成时显示 -->
    <a-card v-if="!plan" style="margin-bottom: 16px">
      <template #title>
        <span style="font-size: 16px">正在规划行程...</span>
      </template>

      <a-progress
        :percent="progress / 100"
        :status="errorMsg ? 'exception' : 'active'"
        :stroke-color="errorMsg ? undefined : '#1677ff'"
      />
      <p style="margin-top: 16px; color: #666">
        <span v-if="errorMsg" style="color: #ff4d4f">{{ errorMsg }}</span>
        <span v-else>{{ stage || '等待后端开始...' }}</span></p>

      <a-button
        v-if="errorMsg || isDone"
        type="primary"
        @click="$router.push({ name: 'home' })"
        style="margin-top: 16px"
      >
        回到首页
      </a-button>
    </a-card>

    <!-- 结果面板 -->
    <div v-if="plan">
      <a-page-header :title="plan.title" :sub-title="`${plan.destination} · ${plan.date_range}`">
        <template #extra>
          <a-button @click="$router.push({ name: 'home' })">再来一次</a-button>
        </template>
      </a-page-header>

      <!-- 每日行程 -->
      <a-card
        v-for="(day, idx) in plan.days"
        :key="day.date"
        style="margin-bottom: 16px"
      >
        <template #title>
          <span style="font-size: 16px">Day {{ idx + 1 }} · {{ day.date }}</span>
          <a-tag v-if="day.theme" color="blue" style="margin-left: 8px">{{ day.theme }}</a-tag>
        </template>

        <h4>景点</h4>
        <a-list :data-source="day.attractions" size="small">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #title>
                  <strong>{{ item.name }}</strong>
                  <a-tag v-if="item.cost === 0" color="green" style="margin-left: 8px">免费</a-tag>
                  <a-tag v-else color="orange" style="margin-left: 8px">¥{{ item.cost }}</a-tag>
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

        <h4>餐饮</h4>
        <a-descriptions :column="1" size="small">
          <a-descriptions-item label="早餐">
            <span v-if="day.meals.breakfast">
              <strong>{{ day.meals.breakfast.name }}</strong> · {{ day.meals.breakfast.address }} · ¥{{ day.meals.breakfast.cost }}
            </span>
            <span v-else style="color: #999">无</span>
          </a-descriptions-item>
          <a-descriptions-item label="午餐">
            <span v-if="day.meals.lunch">
              <strong>{{ day.meals.lunch.name }}</strong> · {{ day.meals.lunch.address }} · ¥{{ day.meals.lunch.cost }}
            </span>
            <span v-else style="color: #999">无</span>
          </a-descriptions-item>
          <a-descriptions-item label="晚餐">
            <span v-if="day.meals.dinner">
              <strong>{{ day.meals.dinner.name }}</strong> · {{ day.meals.dinner.address }} · ¥{{ day.meals.dinner.cost }}
            </span>
            <span v-else style="color: #999">无</span>
          </a-descriptions-item>
        </a-descriptions>

        <template v-if="day.hotel">
          <a-divider style="margin: 12px 0" />
          <h4>住宿</h4>
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
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { streamTask } from '../services/api'
import type { TripPlan } from '../types'
import DayMap from '../components/DayMap.vue'

const route = useRoute()
const router = useRouter()

const plan = ref<TripPlan | null>(null)
const progress = ref(0)
const stage = ref('')
const errorMsg = ref('')
const isDone = ref(false)

// 用于主动停止 SSE 流(组件卸载或切页时,cancelled=true 让 for await 跳出)
let cancelled = false

onMounted(async () => {
  const task_id = route.query.task_id as string | undefined
  if (!task_id) {
    router.replace({ name: 'home' })
    return
  }

  try {
    for await (const ev of streamTask(task_id)) {
      if (cancelled) break
      progress.value = ev.progress
      stage.value = ev.stage
      if (ev.status === 'done' && ev.result) {
        plan.value = ev.result
        isDone.value = true
        return
      }
      if (ev.status === 'error') {
        errorMsg.value = ev.error || '任务失败'
        isDone.value = true
        return
      }
    }
  } catch (e: any) {
    errorMsg.value = '连接异常: ' + (e.message || String(e))
    isDone.value = true
  }
})

onBeforeUnmount(() => {
  cancelled = true
  // streamTask 内部 finally 会调用 source.close()
})
</script>