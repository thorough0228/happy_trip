import axios from 'axios'
import type { TripRequest, TripPlan } from '../types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:7000',
  timeout: 600000, // LLM 生成可能耗时,这里给 10 分钟超时
})

export async function planTrip(req: TripRequest): Promise<TripPlan> {
  const resp = await api.post<TripPlan>('/api/trip/plan', req)
  return resp.data
}

export async function healthCheck(): Promise<string> {
  const resp = await api.get<{ status: string }>('/health')
  return resp.data.status
}