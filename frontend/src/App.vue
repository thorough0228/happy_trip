<template>
  <a-config-provider>
    <a-layout style="min-height: 100vh">
      <a-layout-header style="background: #fff; padding: 0 24px; border-bottom: 1px solid #f0f0f0; text-align: center">
        <h2 style="margin: 16px 0; color: #1677ff">Happy Trip Planner</h2>
      </a-layout-header>
      <a-layout-content style="padding: 24px; max-width: 1200px; margin: 0 auto; width: 100%">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-config-provider>
</template>