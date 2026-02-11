import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
    history: createWebHashHistory(),
    routes: [
        {
            path: '/',
            redirect: '/products'
        },
        {
            path: '/products',
            name: 'products',
            component: () => import('../views/ProductsView.vue')
        },
        {
            path: '/orders',
            name: 'orders',
            component: () => import('../views/OrdersView.vue')
        },
        {
            path: '/customers',
            name: 'customers',
            component: () => import('../views/CustomersView.vue')
        }
    ]
})

export default router
