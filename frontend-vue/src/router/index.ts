import { createRouter, createWebHistory } from 'vue-router'
import { authMode } from '../auth/config'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: () => authMode === 'cognito' && !localStorage.getItem('token') ? '/auth' : '/jobs',
    },
    { path: '/auth', component: () => import('../views/AuthView.vue') },
    { path: '/auth/callback', component: () => import('../views/AuthCallbackView.vue') },
    {
      path: '/jobs',
      component: () => import('../views/JobsView.vue'),
      meta: { requiresCloudAuth: true },
    },
    {
      path: '/job-settings',
      component: () => import('../views/JobSettingsView.vue'),
      meta: { requiresCloudAuth: true },
    },
    {
      path: '/profile',
      component: () => import('../views/ProfileView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/generate',
      component: () => import('../views/GenerateView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/templates',
      component: () => import('../views/TemplatesView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/sessions',
      component: () => import('../views/SessionsView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresCloudAuth && authMode === 'cognito' && !auth.isAuthenticated) {
    return '/auth'
  }
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return '/auth'
  }
})

export default router
