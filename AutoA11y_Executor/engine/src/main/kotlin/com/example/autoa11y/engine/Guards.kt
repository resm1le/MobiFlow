package com.example.autoa11y.engine

import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.Interceptor

/**
 * 前台守护拦截器：若前台组件不含目标包名，则尝试返回一次并短暂停顿。
 * 用于视频/长时间滚动等场景，降低被弹窗或切屏拉走的风险。
 */
fun foregroundGuardInterceptor(
    packageName: String,
    backPauseMs: Long = 400L
): Interceptor = object : Interceptor {
    override fun tryIntercept(driver: Driver): Boolean {
        val component = ForegroundActivityInspector.currentComponent() ?: return false
        if (!component.contains(packageName)) {
            val ok = driver.back()
            if (ok) Thread.sleep(backPauseMs)
            return ok
        }
        return false
    }
}
