package com.example.autoa11y.core.api

/**
 * 全局拦截器：在每个 Step 执行前调用，用于清理弹窗等横切问题。
 * 返回 true 表示本次调用确实做了拦截（例如点掉了一个弹窗按钮）。
 */
interface Interceptor {
    fun tryIntercept(driver: Driver): Boolean
}
