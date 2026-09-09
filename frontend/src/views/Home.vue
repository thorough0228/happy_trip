<template>
  <div class="trip-form">
    <div class="user-header">
      <span v-if="isLoggedIn" class="user-info">
        欢迎，{{ user?.username }}
        <a-button type="link" size="small" @click="handleLogout">退出</a-button>
        <a-button type="link" size="small" @click="showHistory = true">历史行程</a-button>
      </span>
      <router-link v-else to="/login">登录</router-link>
    </div>

    <h2 style="margin-bottom: 24px">行程需求</h2>

    <a-row :gutter="24">
      <!-- 左栏:选择表单 -->
      <a-col :xs="24" :md="14" :lg="13">
        <a-form :model="form" layout="vertical" @finish="handleSubmit">
          <!-- 分组 1:目的地与日期 -->
          <section class="form-section">
            <h3 class="section-title">📍 目的地与日期</h3>
            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="目的地城市" :rules="[{ required: true, message: '请输入目的地' }]">
                  <div v-if="!editingDestination" class="destination-tag-row">
                    <a-tag color="blue" class="destination-tag">
                      📍 {{ form.destination }}
                    </a-tag>
                    <a-button type="link" size="small" @click="editingDestination = true">
                      修改
                    </a-button>
                  </div>
                  <DestinationInput
                    v-else
                    v-model:value="form.destination"
                    @destination-confirmed="onDestinationChosen"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
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
              <a-col :span="12">
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

          <!-- 分组 2:偏好设置 -->
          <section class="form-section">
            <h3 class="section-title">🛏 偏好设置</h3>
            <a-form-item label="旅行偏好">
              <a-checkbox-group v-model:value="form.preferences" style="width: 100%">
                <a-row>
                  <a-col :span="8" v-for="opt in preferenceOptions" :key="opt" style="margin-bottom: 2px">
                    <a-checkbox :value="opt">
                      <span class="pref-icon">{{ PREF_ICONS[opt] }}</span>
                      {{ opt }}
                    </a-checkbox>
                  </a-col>
                </a-row>
              </a-checkbox-group>
            </a-form-item>
          </section>

          <!-- 分组 3:额外要求 -->
          <section class="form-section">
            <h3 class="section-title">📝 额外要求</h3>
            <a-form-item label="负面约束(逗号分隔)">
              <a-input v-model:value="negativeText" placeholder="如:不吃辣,不去网红店,避开人多的景点" />
            </a-form-item>
          </section>

          <a-form-item>
            <a-button type="primary" html-type="submit" :loading="loading" :disabled="loading" size="large" block>
              生成行程
            </a-button>
          </a-form-item>
        </a-form>

        <!-- 进度区:贴在"生成行程"按钮下方,留在 Home 页,完成后再跳 Result -->
        <div v-if="showProgress" class="progress-section">
          <a-progress
            :percent="progressPct"
            :status="errorMsg ? 'exception' : 'active'"
            :stroke-color="errorMsg ? undefined : '#1677ff'"
          />
          <div class="progress-stage">
            <span v-if="errorMsg" style="color: #ff4d4f">❌ {{ errorMsg }}</span>
            <span v-else style="color: #555">⏳ {{ progressStage || '准备中...' }}</span>
          </div>
          <a-button v-if="errorMsg" type="primary" size="small" @click="resetProgress" style="margin-top: 8px">
            重试
          </a-button>
        </div>
      </a-col>

      <!-- 右栏:目的地地图 -->
      <a-col :xs="24" :md="10" :lg="11">
        <a-card title="📍 目的地预览" style="position: sticky; top: 24px">
          <HomeMap :destination="mapDestination" />
        </a-card>
      </a-col>
    </a-row>

    <!-- 历史行程侧边栏 -->
    <a-drawer
      v-model:open="showHistory"
      :header-style="{ display: 'none' }"
      placement="right"
      :width="320"
    >
      <HistorySidebar v-if="showHistory" @close="showHistory = false" />
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import dayjs, { Dayjs } from 'dayjs'
import { useRouter } from 'vue-router'
import { planTrip, streamTask } from '../services/api'
import { useAuth } from '../stores/user'
import HomeMap from '../components/HomeMap.vue'
import HistorySidebar from '../components/HistorySidebar.vue'
import DestinationInput from '../components/DestinationInput.vue'
import type { TripRequest } from '../types'

const router = useRouter()
const { user, isLoggedIn, logout } = useAuth()
const loading = ref(false)
const showHistory = ref(false)

function handleLogout() {
  logout()
  router.push('/login')
}

const form = reactive<Omit<TripRequest, 'travel_days'> & { travel_days: number }>({
  destination: '南京',
  start_date: '',
  travel_days: 0,
  preferences: [],
  negative_constraints: [],
})

// 地图预览：仅在用户确认（选中下拉/回车）后才更新，避免输入过程中频繁请求
const mapDestination = ref('南京')
const editingDestination = ref(true)
function handleDestinationConfirmed(v: string) {
  const city = (v || '').trim()
  if (city) mapDestination.value = city
}
function onDestinationChosen(v: string) {
  // 1. 先把表单值更新成选择的城市(确保 v-model 同步)
  form.destination = v
  // 2. 触发地图更新
  handleDestinationConfirmed(v)
  // 3. 关闭编辑态
  editingDestination.value = false
}

// 进度状态
const progressStage = ref('')
const progressPct = ref(0)
const errorMsg = ref('')

const showProgress = computed(() => loading.value || !!errorMsg.value)

function resetProgress() {
  progressStage.value = ''
  progressPct.value = 0
  errorMsg.value = ''
  loading.value = false
}

// ---- 日期:开始 + 结束(独立 picker,联动禁用)----
const startDate = ref<string | null>(dayjs().add(1, 'day').format('YYYY-MM-DD'))
const endDate = ref<string | null>(dayjs().add(3, 'day').format('YYYY-MM-DD'))

function disabledStartDate(current: Dayjs) {
  return current && current < dayjs().startOf('day')
}

function disabledEndDate(current: Dayjs) {
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

const preferenceOptions = [
  '历史文化', '自然风光',
  '购物商圈', '艺术展览',
  '亲子友好', '老人友好', '小众路线',
  '夜游体验', '摄影打卡', '博物馆',
  '城市漫步', '户外徒步',
]

// 每个偏好对应的小图标
const PREF_ICONS: Record<string, string> = {
  历史文化: '🏯',
  自然风光: '🌄',
  购物商圈: '🛍️',
  艺术展览: '🎨',
  亲子友好: '🎠',
  老人友好: '🧓',
  小众路线: '🗺️',
  夜游体验: '🌃',
  摄影打卡: '📸',
  博物馆: '🏛️',
  城市漫步: '🚶',
  户外徒步: '🥾',
}

const negativeText = ref('')

const handleSubmit = async () => {
  if (!startDate.value || !endDate.value) {
    alert('请选择开始日期和结束日期')
    return
  }
  loading.value = true
  errorMsg.value = ''
  progressStage.value = ''
  progressPct.value = 0

  try {
    form.start_date = startDate.value
    form.travel_days = dayjs(endDate.value).diff(dayjs(startDate.value), 'day') + 1
    form.negative_constraints = negativeText.value
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0)

    // 创建任务
    const { task_id } = await planTrip(form as TripRequest)

    // 订阅 SSE 流,进度保持在 Home 页
    for await (const ev of streamTask(task_id)) {
      progressPct.value = ev.progress
      progressStage.value = ev.stage

      if (ev.status === 'done' && ev.result) {
        sessionStorage.setItem('trip_plan', JSON.stringify(ev.result))
        loading.value = false
        router.push({ name: 'result' })
        return
      }
      if (ev.status === 'error') {
        errorMsg.value = ev.error || '任务失败'
        loading.value = false
        return
      }
    }
  } catch (e: any) {
    errorMsg.value = '创建任务失败: ' + (e.response?.data?.detail || e.message || String(e))
    loading.value = false
  }
}
</script>

<style scoped>
.trip-form {
  max-width: 1200px;
  margin: 0 auto;
}
.user-header {
  text-align: right;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0f0f0;
}
.user-info {
  color: #666;
}
.form-section {
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f0f0;
}
.form-section:last-of-type {
  border-bottom: none;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 8px;
  color: #333;
}
:deep(.ant-form-item) {
  margin-bottom: 12px;
}
:deep(.ant-form-item-with-help .ant-form-item-explain) {
  min-height: 0;
}

.destination-tag-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.destination-tag {
  font-size: 14px;
  padding: 4px 12px;
  border-radius: 16px;
}

.pref-icon {
  margin-right: 4px;
  font-size: 14px;
}
.progress-section {
  margin-top: 24px;
  padding: 16px;
  background: #fafafa;
  border-radius: 6px;
}
.progress-stage {
  margin-top: 8px;
  font-size: 14px;
}
</style>