package com.example.autoa11y.engine

import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.ActionLibrary
import com.example.autoa11y.core.api.ActionResult
import com.example.autoa11y.core.api.BehaviorProfile
import com.example.autoa11y.core.api.BehaviorSession
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.Interceptor
import com.example.autoa11y.core.api.PageSignature
import com.example.autoa11y.core.api.ResolveResult
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.Selector
import com.example.autoa11y.core.api.Step
import com.example.autoa11y.core.api.TargetAppProfile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ScenarioExecutorSmartClickTest {

    @Test
    fun `smart click success should click once and verify once`() {
        val trigger = Selector.ByText("trigger")
        val expected = Selector.ByText("expected")
        val driver = SmartClickDriver(clickOk = true, waitOk = true)
        val exec = newExecutor(driver)
        val scenario = oneStepScenario(
            Action.SmartClick(
                trigger = trigger,
                expectedMarker = expected,
                timeoutMs = 3_000L,
                settleDelayMs = 0L
            )
        )

        val ok = exec.run(scenario)

        assertTrue(ok)
        assertEquals(1, driver.clickResolvedCount)
        assertEquals(1, driver.waitResolvedCount)
    }

    @Test
    fun `smart click trigger failure should not run verify`() {
        val trigger = Selector.ByText("trigger")
        val expected = Selector.ByText("expected")
        val driver = SmartClickDriver(clickOk = false, waitOk = true)
        val exec = newExecutor(driver)
        val scenario = oneStepScenario(
            Action.SmartClick(
                trigger = trigger,
                expectedMarker = expected,
                timeoutMs = 3_000L,
                settleDelayMs = 0L
            )
        )

        val ok = exec.run(scenario)

        assertTrue(ok)
        assertEquals(1, driver.clickResolvedCount)
        assertEquals(0, driver.waitResolvedCount)
    }

    @Test
    fun `smart click verify failure should not retry`() {
        val trigger = Selector.ByText("trigger")
        val expected = Selector.ByText("expected")
        val driver = SmartClickDriver(clickOk = true, waitOk = false)
        val exec = newExecutor(driver)
        val scenario = oneStepScenario(
            Action.SmartClick(
                trigger = trigger,
                expectedMarker = expected,
                timeoutMs = 3_000L,
                settleDelayMs = 0L
            )
        )

        val ok = exec.run(scenario)

        assertTrue(ok)
        assertEquals(1, driver.clickResolvedCount)
        assertEquals(1, driver.waitResolvedCount)
    }

    private fun oneStepScenario(action: Action): Scenario =
        Scenario(
            id = "smart-click-one-step",
            steps = listOf(
                Step(require = null, actions = listOf(action))
            )
        )

    private fun newExecutor(driver: Driver): ScenarioExecutor =
        ScenarioExecutor(
            driver = driver,
            interceptors = emptyList(),
            profile = fakeProfile,
            homeComponentProvider = { null },
            foregroundGuard = { true },
            isAlive = { true }
        )

    private class SmartClickDriver(
        private val clickOk: Boolean,
        private val waitOk: Boolean
    ) : Driver {
        var clickResolvedCount: Int = 0
            private set
        var waitResolvedCount: Int = 0
            private set

        override fun clickResolved(sel: Selector): ActionResult {
            clickResolvedCount++
            return if (clickOk) {
                ActionResult.success()
            } else {
                ActionResult.failure(ResolveResult.notFound(sel))
            }
        }

        override fun waitVisibleResolved(sel: Selector, timeoutMs: Long): ActionResult {
            waitResolvedCount++
            return if (waitOk) {
                ActionResult.success()
            } else {
                ActionResult.failure(ResolveResult.notFound(sel))
            }
        }

        override fun waitVisible(sel: Selector, timeoutMs: Long): Boolean = waitOk
        override fun click(sel: Selector): Boolean = clickOk
        override fun input(sel: Selector, text: String, clearFirst: Boolean): Boolean = true
        override fun scroll(steps: Int, dir: Action.Direction): Boolean = true
        override fun swipe(
            fromXRatio: Float,
            fromYRatio: Float,
            toXRatio: Float,
            toYRatio: Float,
            durationMs: Int
        ): Boolean = true

        override fun back(): Boolean = true
    }

    private companion object {
        val fakeProfile: TargetAppProfile = object : TargetAppProfile {
            override val packageName: String = "pkg"
            override val homeSignature: PageSignature = PageSignature("pkg")
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
    }
}

