<template>
  <div class="trip-form">
    <h2 style="margin-bottom: 24px">行程需求</h2>

    <a-form :model="form" layout="vertical" @finish="handleSubmit">
      <!-- 分组 1:目的地与日期 -->
      <section class="form-section">
        <h3 class="section-title">📍 目的地与日期</h3>
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="目的地城市" :rules="[{ required: true, message: '请输入目的地' }]">
              <a-input v-model:value="form.destination" placeholder="例如:北京" />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="开始日期" :rules="[{ required: true, validator: validateStartDate }]">
              <a-date-picker
                v-model:value="startDate"
                :disabled-date="disabledStartDate"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                placeholder="选择日期"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="结束日期" :rules="[{ required: true, validator: validateEndDate }]">
              <a-date-picker
                v-model:value="endDate"
                :disabled-date="disabledEndDate"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                placeholder="选择日期"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </section>

      <!-- 分组 2:同行与预算 -->
      <section class="form-section">
        <h3 class="section-title">👥 同行与预算</h3>
        <a-row :gutter="16">
          <a-col :span="4">
            <a-form-item label="成人">
              <a-input-number v-model:value="form.party.adults" :min="1" :max="20" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="4">
            <a-form-item label="儿童">
              <a-input-number v-model:value="form.party.children" :min="0" :max="10" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="4">
            <a-form-item label="老人">
              <a-input-number v-model:value="form.party.elders" :min="0" :max="10" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="4">
            <a-form-item label="同行类型">
              <a-select v-model:value="form.party.companion_type">
                <a-select-option value="solo">独行</a-select-option>
                <a-select-option value="couple">情侣</a-select-option>
                <a-select-option value="family">家庭</a-select-option>
                <a-select-option value="friends">朋友</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="4">
            <a-form-item label="总预算(元)">
              <a-input-number v-model:value="form.budget_constraint.amount" :min="0" placeholder="可不填" style="width: 100%" />
            </a-form-item>
          </a-col>
          <a-col :span="4">
            <a-form-item label="预算档位">
              <a-select v-model:value="form.budget_constraint.level">
                <a-select-option value="economy">经济</a-select-option>
                <a-select-option value="standard">标准</a-select-option>
                <a-select-option value="premium">豪华</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
      </section>

      <!-- 分组 3:偏好设置 -->
      <section class="form-section">
        <h3 class="section-title">🛏 偏好设置</h3>
        <a-row :gutter="16" align="top">
          <a-col :span="8">
            <a-form-item label="交通方式">
              <a-select v-model:value="form.transportation">
                <a-select-option value="train">公共交通</a-select-option>
                <a-select-option value="flight">飞机</a-select-option>
                <a-select-option value="self_drive">自驾</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="住宿偏好">
              <a-select v-model:value="form.accommodation">
                <a-select-option value="youth_hostel">青旅</a-select-option>
                <a-select-option value="hostel">经济型酒店</a-select-option>
                <a-select-option value="hotel">舒适型酒店</a-select-option>
                <a-select-option value="hotel">豪华型酒店</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="旅行偏好">
              <a-checkbox-group v-model:value="form.preferences" style="width: 100%">
                <a-row>
                  <a-col :span="8" v-for="opt in preferenceOptions" :key="opt" style="margin-bottom: 4px">
                    <a-checkbox :value="opt">{{ opt }}</a-checkbox>
                  </a-col>
                </a-row>
              </a-checkbox-group>
            </a-form-item>
          </a-col>
        </a-row>
      </section>

      <!-- 分组 4:额外要求 -->
      <section class="form-section">
        <h3 class="section-title">📝 额外要求</h3>
        <a-form-item label="负面约束(逗号分隔)">
          <a-input v-model:value="negativeText" placeholder="如:不吃辣,不去网红店,避开人多的景点" />
        </a-form-item>
      </section>

      <a-form-item>
        <a-button type="primary" html-type="submit" :loading="loading" size="large" block>
          生成行程
        </a-button>
      </a-form-item>
    </a-form>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import dayjs, { Dayjs } from 'dayjs'
import { useRouter } from 'vue-router'
import { planTrip } from '../services/api'
import type { TripRequest } from '../types'

const router = useRouter()
const loading = ref(false)

// ---- 日期:开始 + 结束(独立 picker,联动禁用)----
const startDate = ref<string | null>(dayjs().add(1, 'day').format('YYYY-MM-DD'))
const endDate = ref<string | null>(dayjs().add(3, 'day').format('YYYY-MM-DD'))

function disabledStartDate(current: Dayjs) {
  // 不能选今天之前
  return current && current < dayjs().startOf('day')
}

function disabledEndDate(current: Dayjs) {
  // 不能选今天之前,也不能早于开始日期
  const today = dayjs().startOf('day')
  if (current && current < today) return true
  if (startDate.value) {
    const start = dayjs(startDate.value)
    if (current && current < start) return true
  }
  return false
}

function validateStartDate() {
  if (!startDate.value) return Promise.reject(new Error('请选择开始日期'))
  return Promise.resolve()
}

function validateEndDate() {
  if (!endDate.value) return Promise.reject(new Error('请选择结束日期'))
  if (startDate.value && dayjs(endDate.value).isBefore(dayjs(startDate.value))) {
    return Promise.reject(new Error('结束日期不能早于开始日期'))
  }
  return Promise.resolve()
}

// ---- 旅行偏好候选(checkbox grid)----
const preferenceOptions = [
  '历史文化', '自然风光', '美食探店',
  '购物商圈', '艺术展览', '休闲放松',
  '亲子友好', '老人友好', '小众路线',
  '夜游体验', '摄影打卡', '博物馆',
  '城市漫步', '户外徒步', '主题乐园',
  '避开人群',
]

const form = reactive<Omit<TripRequest, 'travel_days'> & { travel_days: number }>({
  destination: '北京',
  start_date: '',
  travel_days: 0,
  party: {
    adults: 1,
    children: 0,
    elders: 0,
    companion_type: 'solo',
  },
  budget_constraint: {
    amount: 3000,
    level: 'standard',
  },
  transportation: 'train',
  accommodation: 'hostel',
  preferences: [],
  negative_constraints: [],
})

const negativeText = ref('')

const handleSubmit = async () => {
  if (!startDate.value || !endDate.value) {
    alert('请选择开始日期和结束日期')
    return
  }
  loading.value = true
  try {
    form.start_date = startDate.value
    form.travel_days = dayjs(endDate.value).diff(dayjs(startDate.value), 'day') + 1

    form.negative_constraints = negativeText.value
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
    // preferences 来自 checkbox group,已是 array

    const { task_id } = await planTrip(form as TripRequest)
    router.push({ name: 'result', query: { task_id } })
  } catch (e: any) {
    alert('创建任务失败: ' + (e.response?.data?.detail || e.message || JSON.stringify(e)))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.trip-form {
  max-width: 1200px;
  margin: 0 auto;
}
.form-section {
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
}
.form-section:last-of-type {
  border-bottom: none;
}
.section-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
  color: #333;
}
</style>