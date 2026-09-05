import axios from 'axios'
import type {
  TripRequest,
  TripPlan,
  PlanTaskResponse,
  TaskProgress,
  StreamProgressEvent,
} from '../types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:7000',
  timeout: 30000, // 提交后端只做"创建任务",用不上 10 分钟,30s 足够
})

/**
 * 创建异步规划任务。
 *
 * 后端立即返回 task_id,实际规划在 BackgroundTasks 里跑。
 * 客户端拿 task_id 去订阅 SSE 流拿进度和结果。
 */
export async function planTrip(req: TripRequest): Promise<PlanTaskResponse> {
  const resp = await api.post<PlanTaskResponse>('/api/trip/plan', req)
  return resp.data
}

export async function healthCheck(): Promise<string> {
  const resp = await api.get<{ status: string }>('/health')
  return resp.data.status
}

/**
 * 调后端拿两 POI 间的步行路线 polyline。
 * 返回 {coords, distance, duration};后端失败或网络错误返回 null。
 */
export async function getWalkingRoute(
  origin: [number, number],
  dest: [number, number],
): Promise<{ coords: [number, number][]; distance: number; duration: number } | null> {
  try {
    const resp = await api.get('/api/trip/route/walking', {
      params: {
        origin_lng: origin[0],
        origin_lat: origin[1],
        dest_lng: dest[0],
        dest_lat: dest[1],
      },
    })
    return resp.data
  } catch {
    return null
  }
}

/**
 * SSE 流客户端:把 EventSource 包装成 AsyncIterable<TaskProgress>。
 *
 * 后端推送三种 event:
 * - "progress": 阶段性进度(可多次)
 * - "done":     任务完成,data 是完整 TripPlan
 * - "failed":   任务失败或 task 不存在(避开 EventSource 原生 'error' 事件名冲突)
 *
 * 'error' 监听器只用于检测连接中断(native error,无 data)。
 * 终态后服务端关闭流,客户端也主动 source.close(),浏览器停止自动重连。
 */
export async function* streamTask(task_id: string): AsyncGenerator<TaskProgress, void, void> {
  const baseURL = api.defaults.baseURL || window.location.origin
  const url = `${baseURL}/api/trip/stream/${task_id}`

  const source = new EventSource(url)

  try {
    while (true) {
      const ev: { type: string; data: string } = await new Promise((resolve) => {
        const cleanup = () => {
          source.removeEventListener('progress', onProgress)
          source.removeEventListener('done', onDone)
          source.removeEventListener('failed', onFailed)
          source.removeEventListener('error', onNativeError)
        }
        const onProgress = (e: MessageEvent) => {
          cleanup()
          resolve({ type: 'progress', data: e.data })
        }
        const onDone = (e: MessageEvent) => {
          cleanup()
          resolve({ type: 'done', data: e.data })
        }
        const onFailed = (e: MessageEvent) => {
          cleanup()
          resolve({ type: 'failed', data: e.data })
        }
        const onNativeError = () => {
          cleanup()
          resolve({ type: 'failed', data: 'connection lost' })
        }
        source.addEventListener('progress', onProgress)
        source.addEventListener('done', onDone)
        source.addEventListener('failed', onFailed)
        source.addEventListener('error', onNativeError)
      })

      if (ev.type === 'progress') {
        const p: StreamProgressEvent = JSON.parse(ev.data)
        yield { task_id, ...p }
      } else if (ev.type === 'done') {
        const plan: TripPlan = JSON.parse(ev.data)
        yield { task_id, status: 'done', stage: '完成', progress: 100, result: plan }
        return
      } else {
        // failed
        let msg = ev.data
        try {
          msg = JSON.parse(ev.data).error || msg
        } catch {
          /* keep raw */
        }
        yield { task_id, status: 'error', stage: '', progress: 0, error: msg }
        return
      }
    }
  } finally {
    source.close()
  }
}