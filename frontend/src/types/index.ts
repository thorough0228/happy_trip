// 前端类型,镜像后端 Pydantic schema
export interface Party {
  adults: number
  children: number
  elders: number
  companion_type: 'couple' | 'family' | 'friends' | 'solo'
  total?: number
}

export interface BudgetConstraint {
  amount: number
}

export interface TripRequest {
  destination: string
  start_date: string
  travel_days: number
  party: Party
  budget_constraint: BudgetConstraint
  transportation: 'flight' | 'train' | 'self_drive'
  accommodation: 'hotel' | 'hostel' | 'youth_hostel'
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

export interface Meal {
  name: string
  address: string
  location: [number, number] | null
  cost: number
}

export interface Hotel {
  name: string
  address: string
  location: [number, number] | null
  cost: number
  nights: number
}

export interface Day {
  date: string
  theme: string | null
  attractions: Attraction[]
  meals: {
    breakfast: Meal | null
    lunch: Meal | null
    dinner: Meal | null
  }
  hotel: Hotel | null
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface TripPlan {
  title: string
  destination: string
  date_range: string
  party: Party
  days: Day[]
  budget: Budget
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