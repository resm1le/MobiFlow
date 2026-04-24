package com.example.autoa11y.plugins.googlemaps

import android.util.Log
import com.example.autoa11y.core.api.ActionLibrary
import com.example.autoa11y.core.api.BehaviorProfile
import com.example.autoa11y.core.api.BehaviorSession
import com.example.autoa11y.core.api.Interceptor
import com.example.autoa11y.core.api.KnownPage
import com.example.autoa11y.core.api.PageSignature
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.TargetAppProfile
import kotlin.random.Random

object GooglemapsProfile : TargetAppProfile {
    override val packageName: String = TARGET_PKG
    override val homeSignature: PageSignature = GooglemapsPages.home
    override val knownPages: List<KnownPage> = GooglemapsPages.knownPages
    override val homeActivityComponent: String? = null
    override val globalInterceptors: List<Interceptor> = emptyList()
    override val actionLibrary: ActionLibrary = object : ActionLibrary {
        override fun snippets(): Map<String, Scenario> = emptyMap()
    }
    override val extraNetworkPackages: List<String> = listOf(
        "com.google.android.gms"
    )
    override val behavior: BehaviorProfile = GooglemapsBehavior
}

private object GooglemapsBehavior : BehaviorProfile {
    override fun beginSession(): BehaviorSession = GooglemapsSession()
}

private class GooglemapsSession : BehaviorSession {
    private var didStartup = false
    private val random = Random(System.currentTimeMillis())
    private var rounds = 0

    private val uniqueDestinations = SEARCH_DESTINATIONS_UNIQUE.shuffled(random).toMutableList()
    private var uniqueDestIndex = 0

    private val genericDestinations = SEARCH_DESTINATIONS_GENERIC.shuffled(random).toMutableList()
    private var genericDestIndex = 0

    private val categories = NEARBY_CATEGORIES.shuffled(random).toMutableList()
    private var catIndex = 0

    companion object {
        private const val ENABLE_MAIN_FLOW = true
    }

    override fun nextSnippet(timeLeftMs: Long): Scenario? {
        if (timeLeftMs < 15_000L) return null

        if (!didStartup) {
            didStartup = true
            Log.i(TAG, "startup: timeLeft=$timeLeftMs")
            return GooglemapsFlows.startup()
        }

        if (!ENABLE_MAIN_FLOW) return null

        rounds++

        return if (random.nextFloat() < 0.70f) {
            val isUnique = random.nextBoolean()
            val dest = if (isUnique) {
                val d = uniqueDestinations[uniqueDestIndex % uniqueDestinations.size]
                uniqueDestIndex++
                d
            } else {
                val d = genericDestinations[genericDestIndex % genericDestinations.size]
                genericDestIndex++
                d
            }
            Log.i(TAG, "searchAndRoute round=$rounds dest='$dest' isUnique=$isUnique timeLeft=$timeLeftMs")
            GooglemapsFlows.searchAndRoute(dest, isUnique)
        } else {
            val cat = categories[catIndex % categories.size]
            catIndex++
            Log.i(TAG, "browseNearby round=$rounds cat='$cat' timeLeft=$timeLeftMs")
            GooglemapsFlows.browseNearby(cat)
        }
    }

    override fun recoverySnippet(reason: String, timeLeftMs: Long): Scenario? {
        if (timeLeftMs < 8_000L) return null
        Log.w(TAG, "recovery: reason=$reason timeLeft=$timeLeftMs")
        return GooglemapsFlows.recoveryFlow(reason)
    }

    override fun metrics(): Map<String, Any> = mapOf(
        "seed" to random.nextInt(),
        "rounds" to rounds,
        "uniqueDestIndex" to uniqueDestIndex,
        "genericDestIndex" to genericDestIndex,
        "catIndex" to catIndex
    )
}
