import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Result from '../views/Result.vue'
import Login from '../views/Login.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/result', name: 'result', component: Result },
    { path: '/login', name: 'login', component: Login },
  ],
})

// 路由守卫：已登录用户访问 /login 则重定向首页；未登录用户访问其他页面则重定向登录页
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('happy_trip_token')
  const isLoggedIn = !!token

  if (to.name === 'login') {
    if (isLoggedIn) {
      next({ name: 'home' })
    } else {
      next()
    }
  } else if (isLoggedIn) {
    next()
  } else {
    next({ name: 'login' })
  }
})

export default router