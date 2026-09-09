<template>
  <div class="history-sidebar">
    <div class="sidebar-header">
      <span>历史行程</span>
      <a-button type="text" size="small" @click="$emit('close')">
        <template #icon><CloseOutlined /></template>
      </a-button>
    </div>

    <div class="sidebar-content">
      <div v-if="loading" class="loading">
        <a-spin size="small" />
      </div>
      <div v-else-if="trips.length === 0" class="empty">
        暂无历史行程
      </div>
      <div v-else class="trip-list">
        <div
          v-for="trip in trips"
          :key="trip.id"
          class="trip-item"
          :class="{ active: selectedId === trip.id }"
          @click="selectTrip(trip)"
        >
          <div class="trip-title">{{ getTripName(trip) }}</div>
          <div class="trip-meta">
            <span>{{ trip.date_range }}</span>
          </div>
          <a-popconfirm
            title="确定删除此行程？"
            @confirm.stop="handleDelete(trip.id)"
          >
            <a-button type="text" size="small" class="delete-btn" @click.stop>
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </a-popconfirm>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { CloseOutlined, DeleteOutlined } from '@ant-design/icons-vue'
import { getTripHistory, deleteTrip, getTripDetail, type TripSummary } from '../services/api'
import type { TripPlan } from '../types'

defineEmits<{
  close: []
  viewTrip: [plan: TripPlan]
}>()

const loading = ref(false)
const trips = ref<TripSummary[]>([])
const selectedId = ref<string | null>(null)

async function loadHistory() {
  loading.value = true
  try {
    trips.value = await getTripHistory()
  } catch {
    // 未登录或无历史
  } finally {
    loading.value = false
  }
}

async function selectTrip(trip: TripSummary) {
  selectedId.value = trip.id
  try {
    const detail = await getTripDetail(trip.id)
    const plan = JSON.parse(detail.plan_json) as TripPlan
    // 存储到 sessionStorage 并跳转
    sessionStorage.setItem('trip_plan', JSON.stringify(plan))
    window.location.href = '/result'
  } catch (e: any) {
    message.error('加载行程详情失败')
  }
}

async function handleDelete(tripId: string) {
  try {
    await deleteTrip(tripId)
    trips.value = trips.value.filter((t) => t.id !== tripId)
    if (selectedId.value === tripId) {
      selectedId.value = null
    }
    message.success('已删除')
  } catch {
    message.error('删除失败')
  }
}

function getTripName(trip: TripSummary): string {
  // date_range 格式: "2026-10-01 ~ 2026-10-03"
  const match = trip.date_range.match(/(\d+-\d+-\d+) ~\s*(\d+-\d+-\d+)/)
  if (match) {
    const start = new Date(match[1])
    const end = new Date(match[2])
    const days = Math.round((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1
    return `${trip.destination}-${days}天`
  }
  return `${trip.destination}`
}

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.history-sidebar {
  width: 280px;
  border-left: 1px solid #f0f0f0;
  background: #fff;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 600;
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.loading,
.empty {
  text-align: center;
  padding: 24px;
  color: #999;
}

.trip-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trip-item {
  padding: 12px;
  border-radius: 6px;
  cursor: pointer;
  position: relative;
  border: 1px solid transparent;
  transition: all 0.2s;
}

.trip-item:hover {
  background: #f5f5f5;
}

.trip-item.active {
  background: #e6f4ff;
  border-color: #1677ff;
}

.trip-title {
  font-weight: 500;
  margin-bottom: 4px;
  padding-right: 24px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trip-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #888;
}

.delete-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  color: #ff4d4f;
}

.trip-item:hover .delete-btn {
  opacity: 1;
}
</style>
