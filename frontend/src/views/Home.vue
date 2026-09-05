<template>
  <div>
    <h2 style="margin-bottom: 24px">规划你的下一次旅行</h2>

    <a-form :model="form" layout="vertical" @finish="handleSubmit">
      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="目的地" :rules="[{ required: true }]">
            <a-input v-model:value="form.destination" placeholder="如:杭州" />
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="出发日期">
            <a-input v-model:value="form.start_date" placeholder="YYYY-MM-DD" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="8">
          <a-form-item label="旅行天数">
            <a-input-number v-model:value="form.travel_days" :min="1" :max="30" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="出行类型">
            <a-select v-model:value="form.party.companion_type">
              <a-select-option value="solo">独自</a-select-option>
              <a-select-option value="couple">情侣</a-select-option>
              <a-select-option value="family">家庭</a-select-option>
              <a-select-option value="friends">朋友</a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="总预算(元)">
            <a-input-number v-model:value="form.budget_constraint.amount" :min="100" :step="500" style="width: 100%" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="8">
          <a-form-item label="成人">
            <a-input-number v-model:value="form.party.adults" :min="1" :max="20" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="儿童">
            <a-input-number v-model:value="form.party.children" :min="0" :max="10" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :span="8">
          <a-form-item label="老人">
            <a-input-number v-model:value="form.party.elders" :min="0" :max="10" style="width: 100%" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="16">
        <a-col :span="12">
          <a-form-item label="交通方式">
            <a-select v-model:value="form.transportation">
              <a-select-option value="flight">飞机</a-select-option>
              <a-select-option value="train">火车</a-select-option>
              <a-select-option value="self_drive">自驾</a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
        <a-col :span="12">
          <a-form-item label="住宿类型">
            <a-select v-model:value="form.accommodation">
              <a-select-option value="hotel">酒店</a-select-option>
              <a-select-option value="hostel">民宿</a-select-option>
              <a-select-option value="youth_hostel">青旅</a-select-option>
            </a-select>
          </a-form-item>
        </a-col>
      </a-row>

      <a-form-item label="预算档位">
        <a-radio-group v-model:value="form.budget_constraint.level">
          <a-radio-button value="economy">经济</a-radio-button>
          <a-radio-button value="standard">标准</a-radio-button>
          <a-radio-button value="premium">豪华</a-radio-button>
        </a-radio-group>
      </a-form-item>

      <a-form-item label="偏好(逗号分隔)">
        <a-input v-model:value="preferencesText" placeholder="如:西湖,博物馆,本地美食" />
      </a-form-item>

      <a-form-item label="负面约束(逗号分隔)">
        <a-input v-model:value="negativeText" placeholder="如:不吃辣,不去网红店" />
      </a-form-item>

      <a-form-item>
        <a-button type="primary" html-type="submit" :loading="loading" size="large">
          生成行程
        </a-button>
      </a-form-item>
    </a-form>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { planTrip } from '../services/api'
import type { TripRequest } from '../types'

const router = useRouter()
const loading = ref(false)

const form = reactive<TripRequest>({
  destination: '杭州',
  start_date: '2026-09-03',
  travel_days: 3,
  party: {
    adults: 2,
    children: 0,
    elders: 0,
    companion_type: 'friends',
  },
  budget_constraint: {
    amount: 3000,
    level: 'standard',
  },
  transportation: 'train',
  accommodation: 'hotel',
  preferences: [],
  negative_constraints: [],
})

const preferencesText = ref('')
const negativeText = ref('')

const handleSubmit = async () => {
  loading.value = true
  try {
    form.preferences = preferencesText.value
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
    form.negative_constraints = negativeText.value
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0)

    // 后端立即返回 task_id,实际规划在后台跑
    const { task_id } = await planTrip(form)
    router.push({ name: 'result', query: { task_id } })
  } catch (e: any) {
    alert('创建任务失败: ' + (e.response?.data?.detail || e.message || JSON.stringify(e)))
  } finally {
    loading.value = false
  }
}
</script>