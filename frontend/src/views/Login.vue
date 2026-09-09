<template>
  <div class="login-container">
    <a-card class="login-card" :bordered="false">
      <template #title>
        <span class="card-title">{{ isLogin ? '登录' : '注册' }}</span>
      </template>

      <a-form :model="form" layout="vertical" @finish="handleSubmit">
        <a-form-item
          label="用户名"
          name="username"
          :rules="[{ required: true, message: '请输入用户名' }]"
        >
          <a-input v-model:value="form.username" placeholder="用户名" size="large" />
        </a-form-item>

        <a-form-item
          label="密码"
          name="password"
          :rules="[{ required: true, message: '请输入密码' }]"
        >
          <a-input-password v-model:value="form.password" placeholder="密码" size="large" />
        </a-form-item>

        <a-form-item v-if="!isLogin" :rules="[{ required: true, message: '请确认密码' }]">
          <a-input-password v-model:value="confirmPassword" placeholder="确认密码" size="large" />
        </a-form-item>

        <a-form-item>
          <a-button type="primary" html-type="submit" size="large" block :loading="loading">
            {{ isLogin ? '登录' : '注册' }}
          </a-button>
        </a-form-item>
      </a-form>

      <div class="switch-mode">
        <a-button type="link" @click="switchMode">
          {{ isLogin ? '没有账号？去注册' : '已有账号？去登录' }}
        </a-button>
      </div>

      <a-divider />

      <div class="back-home">
        <router-link to="/">返回首页</router-link>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { login as userLogin, register as userRegister, useAuth } from '../stores/user'

const router = useRouter()
const { isLoggedIn } = useAuth()

// 已登录用户访问登录页则重定向
if (isLoggedIn.value) {
  router.push('/')
}

const isLogin = ref(true)
const loading = ref(false)
const form = reactive({
  username: '',
  password: '',
})
const confirmPassword = ref('')

function switchMode() {
  isLogin.value = !isLogin.value
  form.username = ''
  form.password = ''
  confirmPassword.value = ''
}

async function handleSubmit() {
  if (!isLogin.value && form.password !== confirmPassword.value) {
    message.error('两次密码输入不一致')
    return
  }

  loading.value = true
  try {
    if (isLogin.value) {
      await userLogin(form.username, form.password)
      message.success('登录成功')
    } else {
      await userRegister(form.username, form.password)
      message.success('注册成功')
    }
    router.push('/')
  } catch (e: any) {
    const errMsg = e.response?.data?.detail || e.message || '操作失败'
    message.error(errMsg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  width: 400px;
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}

.card-title {
  font-size: 20px;
  font-weight: 600;
  text-align: center;
  display: block;
}

.switch-mode {
  text-align: center;
}

.back-home {
  text-align: center;
}
</style>
