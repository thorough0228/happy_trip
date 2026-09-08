// 前端类型,镜像后端 Pydantic schema(简化版:无 meal/hotel/transportation)
export interface Party {
  adults: number
  children: number
  elders: number
  companion_type: 'couple' | 'family' | 'friends' | 'solo'
  total?: number
}

export interface TripRequest {
  destination: string
  start_date: string
  travel_days: number
  party: Party
  preferences: string[]
  negative_constraints: string[]
}

export interface Attraction {
  name: string
  address: string
  location: [number, number] | null
  cost: number
  notes: string | null
  dist_from_prev_km: number | null
}

export interface Day {
  date: string
  theme: string | null
  attractions: Attraction[]
  hotel_area_hint: string | null  // 酒店区域建议(LLM 生成,自然语言)
}

export interface TripPlan {
  title: string
  destination: string
  date_range: string
  party: Party
  days: Day[]
  notes: string[]
}

// ---------- 异步任务 / SSE 相关 ----------

export type TaskStatus = 'pending' | 'running' | 'done' | 'error'

export interface TaskProgress {
  task_id: string
  status: TaskStatus
  stage: string
  progress: number  // 0-100
  result?: TripPlan
  error?: string
}

export interface PlanTaskResponse {
  task_id: string
}

// SSE 流事件载荷(对应后端 _event_generator 推送的 event 名)
export interface StreamProgressEvent {
  status: TaskStatus
  stage: string
  progress: number
}
export interface StreamErrorEvent {
  error: string
}