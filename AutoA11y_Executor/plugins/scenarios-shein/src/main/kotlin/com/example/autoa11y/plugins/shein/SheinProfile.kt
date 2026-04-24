package com.example.autoa11y.plugins.shein

import android.util.Log
import com.example.autoa11y.core.api.ActionLibrary
import com.example.autoa11y.core.api.BehaviorProfile
import com.example.autoa11y.core.api.BehaviorSession
import com.example.autoa11y.core.api.Interceptor
import com.example.autoa11y.core.api.KnownPage
import com.example.autoa11y.core.api.PageSignature
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.TargetAppProfile
import com.example.autoa11y.core.common.keywords.KeywordPool
import kotlin.random.Random

object SheinProfile : TargetAppProfile {
    override val packageName: String = TARGET_PKG
    override val homeSignature: PageSignature = SheinPages.home
    override val knownPages: List<KnownPage> = SheinPages.allKnownPages
    override val homeActivityComponent: String? = null
    override val globalInterceptors: List<Interceptor> = emptyList()
    override val actionLibrary: ActionLibrary = object : ActionLibrary {
        override fun snippets(): Map<String, Scenario> = emptyMap()
    }
    override val behavior: BehaviorProfile = SheinBehavior
}

private object SheinBehavior : BehaviorProfile {
    override fun beginSession(): BehaviorSession = SheinSession()
}

private class SheinSession : BehaviorSession {
    private var didStartup = false
    private val random = Random(System.currentTimeMillis())
    private val keywords = KeywordPool(SheinData.keywordSearches, random)
    private var rounds = 0

    override fun nextSnippet(timeLeftMs: Long): Scenario? {
        if (timeLeftMs < 18_000L) return null

        if (!didStartup) {
            didStartup = true
            Log.i(TAG, "startup timeLeft=$timeLeftMs")
            return SheinFlows.startup()
        }

        rounds++
        val choice = random.nextFloat()
        return when {
            choice < 0.30f -> {
                Log.i(TAG, "round=$rounds flow=homeDiscovery timeLeft=$timeLeftMs")
                SheinFlows.homeDiscovery()
            }
            choice < 0.58f -> {
                val keyword = keywords.next()
                Log.i(TAG, "round=$rounds flow=keywordSearch keyword=$keyword refine=false timeLeft=$timeLeftMs")
                SheinFlows.keywordSearch(keyword = keyword, allowRefine = false)
            }
            choice < 0.82f -> {
                val keyword = keywords.next()
                Log.i(TAG, "round=$rounds flow=keywordSearch keyword=$keyword refine=true timeLeft=$timeLeftMs")
                SheinFlows.keywordSearch(keyword = keyword, allowRefine = true)
            }
            else -> {
                val source = SheinFlows.SuggestionSource.entries.random(random)
                Log.i(TAG, "round=$rounds flow=suggestionSearch source=$source timeLeft=$timeLeftMs")
                SheinFlows.suggestionSearch(source)
            }
        }
    }

    override fun recoverySnippet(reason: String, timeLeftMs: Long): Scenario? {
        if (timeLeftMs < 8_000L) return null
        Log.w(TAG, "recovery reason=$reason timeLeft=$timeLeftMs")
        return SheinFlows.recoveryFlow(reason)
    }

    override fun metrics(): Map<String, Any> = mapOf(
        "rounds" to rounds,
        "seed" to random.nextInt()
    )
}
