import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: () => (localStorage.getItem('token') ? '/generate' : '/auth'),
    },
    { path: '/auth', component: () => import('../views/AuthView.vue') },
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
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return '/auth'
  }
})

export default router
