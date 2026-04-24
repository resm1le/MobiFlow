package com.example.autoa11y.engine

import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.ActionLibrary
import com.example.autoa11y.core.api.BehaviorProfile
import com.example.autoa11y.core.api.BehaviorSession
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.Interceptor
import com.example.autoa11y.core.api.KnownPage
import com.example.autoa11y.core.api.PageSignature
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.Selector
import com.example.autoa11y.core.api.Step
import com.example.autoa11y.core.api.TargetAppProfile
import com.example.autoa11y.core.api.UnknownStateRecoveryPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ScenarioExecutorUnknownStateRecoveryTest {

    @Test
    fun `unknown state in target app should back to known page before step`() {
        val homeSel = Selector.ByText("home")
        val actionSel = Selector.ByText("act")
        val driver = RecoveringDriver(
            visibilityByState = listOf(
                mapOf(homeSel to false),
                mapOf(homeSel to true)
            )
        )
        val exec = newExecutor(driver, homeSel)

        val ok = exec.run(oneStepScenario(actionSel))

        assertTrue(ok)
        assertEquals(1, driver.backCount)
        assertEquals(1, driver.clickCount)
    }

    @Test
    fun `known page should not trigger unknown state recovery`() {
        val homeSel = Selector.ByText("home")
        val actionSel = Selector.ByText("act")
        val driver = RecoveringDriver(
            visibilityByState = listOf(
                mapOf(homeSel to true)
            )
        )
        val exec = newExecutor(driver, homeSel)

        val ok = exec.run(oneStepScenario(actionSel))

        assertTrue(ok)
        assertEquals(0, driver.backCount)
        assertEquals(1, driver.clickCount)
    }

    @Test
    fun `unknown state unresolved should request restart`() {
        val homeSel = Selector.ByText("home")
        val actionSel = Selector.ByText("act")
        val driver = RecoveringDriver(
            visibilityByState = listOf(
                mapOf(homeSel to false),
                mapOf(homeSel to false)
            )
        )
        val exec = newExecutor(driver, homeSel)

        val ok = exec.run(oneStepScenario(actionSel))

        assertFalse(ok)
        assertEquals(1, driver.backCount)
        assertEquals(0, driver.clickCount)
        assertEquals("unknown_state_unresolved", exec.consumeRestartRequest())
    }

    private fun oneStepScenario(actionSel: Selector): Scenario =
        Scenario(
            id = "unknown-state-one-step",
            steps = listOf(
                Step(require = null, actions = listOf(Action.Click(actionSel)))
            )
        )

    private fun newExecutor(driver: Driver, homeSel: Selector): ScenarioExecutor =
        ScenarioExecutor(
            driver = driver,
            interceptors = emptyList(),
            profile = fakeProfile(homeSel),
            homeComponentProvider = { null },
            foregroundGuard = { true },
            isAlive = { true },
            currentComponentProvider = { "pkg/.MainActivity" }
        )

    private fun fakeProfile(homeSel: Selector): TargetAppProfile = object : TargetAppProfile {
        override val packageName: String = "pkg"
        override val homeSignature: PageSignature = PageSignature("pkg", must = listOf(homeSel))
        override val knownPages: List<KnownPage> =
            listOf(KnownPage("home", PageSignature("pkg", must = listOf(homeSel))))
        override val unknownStateRecoveryPolicy: UnknownStateRecoveryPolicy =
            UnknownStateRecoveryPolicy(enabled = true, maxBacks = 1, settleDelayMs = 0L)
        override val globalInterceptors: List<Interceptor> = emptyList()
        override val actionLibrary: ActionLibrary = object : ActionLibrary {
            override fun snippets(): Map<String, Scenario> = emptyMap()
        }
        override val behavior: BehaviorProfile = object : BehaviorProfile {
            override fun beginSession(): BehaviorSession = object : BehaviorSession {
                override fun nextSnippet(timeLeftMs: Long): Scenario? = null
                override fun metrics(): Map<String, Any> = emptyMap()
            }
        }
    }

    private class RecoveringDriver(
        private val visibilityByState: List<Map<Selector, Boolean>>
    ) : Driver {
        private var stateIndex: Int = 0
        var clickCount: Int = 0
            private set
        var backCount: Int = 0
            private set

        override fun waitVisible(sel: Selector, timeoutMs: Long): Boolean =
            visibilityByState[stateIndex.coerceAtMost(visibilityByState.lastIndex)][sel] == true

        override fun click(sel: Selector): Boolean {
            clickCount++
            return true
        }

        override fun input(sel: Selector, text: String, clearFirst: Boolean): Boolean = true

        override fun scroll(steps: Int, dir: Action.Direction): Boolean = true

        override fun swipe(
            fromXRatio: Float,
            fromYRatio: Float,
            toXRatio: Float,
            toYRatio: Float,
            durationMs: Int
        ): Boolean = true

        override fun back(): Boolean {
            backCount++
            if (stateIndex < visibilityByState.lastIndex) {
                stateIndex++
            }
            return true
        }
    }
}
