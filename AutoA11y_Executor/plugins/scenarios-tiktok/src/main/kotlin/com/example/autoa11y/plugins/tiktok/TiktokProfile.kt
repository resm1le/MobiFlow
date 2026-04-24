package com.example.autoa11y.plugins.tiktok

import android.util.Log
import com.example.autoa11y.core.api.ActionLibrary
import com.example.autoa11y.core.api.BehaviorProfile
import com.example.autoa11y.core.api.BehaviorSession
import com.example.autoa11y.core.api.Interceptor
import com.example.autoa11y.core.api.PageSignature
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.TargetAppProfile
import kotlin.random.Random

/**
 * TikTok 插件入口 / Profile。
 */
object TiktokProfile : TargetAppProfile {
    override val packageName: String = TARGET_PKG
    override val homeSignature: PageSignature = TiktokPages.home
    override val homeActivityComponent: String? = null
    override val globalInterceptors: List<Interceptor> = emptyList()
    override val actionLibrary: ActionLibrary = object : ActionLibrary {
        override fun snippets(): Map<String, Scenario> = emptyMap()
    }
    override val extraNetworkPackages: List<String> = listOf(
        "com.google.android.gms"  // TikTok 依赖 GMS 进行网络调度
    )
    override val behavior: BehaviorProfile = TiktokBehavior
}

private object TiktokBehavior : BehaviorProfile {
    override fun beginSession(): BehaviorSession = TiktokSession()
}

private class TiktokSession : BehaviorSession {
    private var didStartup = false
    private val random = Random(System.currentTimeMillis())
    private var rounds = 0

    companion object {
        /** 主流程已开发完成，设为 true 启用。 */
        private const val ENABLE_MAIN_FLOW = true
    }

    override fun nextSnippet(timeLeftMs: Long): Scenario? {
        // 每轮约消耗 30-60s, 留出 10s 余量
        if (timeLeftMs < 10_000L) return null

        if (!didStartup) {
            didStartup = true
            Log.i(TAG, "startup: timeLeft=$timeLeftMs")
            return TiktokFlows.startup()
        }

        if (!ENABLE_MAIN_FLOW) return null

        rounds++
        Log.i(TAG, "mainFlow round=$rounds timeLeft=$timeLeftMs")
        return TiktokFlows.mainFlow()
    }

    override fun recoverySnippet(reason: String, timeLeftMs: Long): Scenario? {
        if (timeLeftMs < 6_000L) return null
        Log.w(TAG, "recovery: reason=$reason timeLeft=$timeLeftMs")
        return TiktokFlows.recoveryFlow(reason)
    }

    override fun metrics(): Map<String, Any> = mapOf(
        "seed" to random.nextInt(),
        "rounds" to rounds
    )
}
