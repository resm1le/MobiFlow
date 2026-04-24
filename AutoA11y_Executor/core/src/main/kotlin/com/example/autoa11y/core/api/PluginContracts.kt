package com.example.autoa11y.core.api

data class KnownPage(val id: String, val sig: PageSignature)
data class UnknownStateRecoveryPolicy(
    val enabled: Boolean = true,
    val maxBacks: Int = 2,
    val settleDelayMs: Long = 500L
)

interface ActionLibrary { fun snippets(): Map<String, Scenario> }
interface BehaviorProfile { fun beginSession(): BehaviorSession }
interface BehaviorSession {
    fun nextSnippet(timeLeftMs: Long): Scenario?
    fun metrics(): Map<String, Any>
    /**
     * Optional recovery flow when a scenario requests a restart/recovery.
     * Return null to skip recovery.
     */
    fun recoverySnippet(reason: String, timeLeftMs: Long): Scenario? = null
}
interface TargetAppProfile {
    val packageName: String
    val homeSignature: PageSignature
    val knownPages: List<KnownPage> get() = emptyList()
    val unknownStateRecoveryPolicy: UnknownStateRecoveryPolicy get() = UnknownStateRecoveryPolicy()
    val globalInterceptors: List<Interceptor>
    val actionLibrary: ActionLibrary
    val behavior: BehaviorProfile
    val homeActivityComponent: String? get() = null
    val extraNetworkPackages: List<String> get() = emptyList()
}
