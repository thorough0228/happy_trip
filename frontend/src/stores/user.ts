import axios from 'axios'
import { computed, reactive } from 'vue'

const TOKEN_KEY = 'happy_trip_token'
const USER_KEY = 'happy_trip_user'

export interface UserInfo {
  user_id: string
  username: string
}

export interface AuthState {
  user: UserInfo | null
  token: string | null
  isLoggedIn: boolean
}

const state = reactive<AuthState>({
  user: null,
  token: localStorage.getItem(TOKEN_KEY),
  isLoggedIn: false,
})

// 从 localStorage 恢复登录状态
if (state.token) {
  const saved = localStorage.getItem(USER_KEY)
  if (saved) {
    try {
      state.user = JSON.parse(saved)
      state.isLoggedIn = true
    } catch {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
      state.token = null
    }
  }
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:7000',
  timeout: 30000,
})

export async function login(username: string, password: string): Promise<void> {
  const resp = await api.post('/api/auth/login', null, {
    params: { username, password },
  })
  const data = resp.data as { user_id: string; token: string; username: string }
  state.user = { user_id: data.user_id, username: data.username }
  state.token = data.token
  state.isLoggedIn = true
  localStorage.setItem(TOKEN_KEY, data.token)
  localStorage.setItem(USER_KEY, JSON.stringify(state.user))
}

export async function register(username: string, password: string): Promise<void> {
  const resp = await api.post('/api/auth/register', null, {
    params: { username, password },
  })
  const data = resp.data as { user_id: string; token: string; username: string }
  state.user = { user_id: data.user_id, username: data.username }
  state.token = data.token
  state.isLoggedIn = true
  localStorage.setItem(TOKEN_KEY, data.token)
  localStorage.setItem(USER_KEY, JSON.stringify(state.user))
}

export function logout(): void {
  state.user = null
  state.token = null
  state.isLoggedIn = false
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function useAuth() {
  return {
    user: computed(() => state.user),
    token: computed(() => state.token),
    isLoggedIn: computed(() => state.isLoggedIn),
    login,
    register,
    logout,
  }
}
