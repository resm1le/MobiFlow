package com.example.autoa11y.engine

import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.ActionLibrary
import com.example.autoa11y.core.api.BehaviorProfile
import com.example.autoa11y.core.api.BehaviorSession
import com.example.autoa11y.core.api.Condition
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.Interceptor
import com.example.autoa11y.core.api.PageSignature
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.Selector
import com.example.autoa11y.core.api.Step
import com.example.autoa11y.core.api.TargetAppProfile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ScenarioExecutorPageSignatureTest {

    @Test
    fun `must+oneOf pass and mustNot miss should execute step`() {
        val mustSel = Selector.ByText("must")
        val oneA = Selector.ByText("oneA")
        val oneB = Selector.ByText("oneB")
        val blockSel = Selector.ByText("blocked")
        val actionSel = Selector.ByText("act")

        val driver = FakeDriver(
            visible = mapOf(
                mustSel to true,
                oneA to false,
                oneB to true,
                blockSel to false
            )
        )
        val exec = newExecutor(driver)
        val scenario = oneStepScenario(
            PageSignature(
                pkg = "pkg",
                must = listOf(mustSel),
                oneOf = listOf(oneA, oneB),
                mustNot = listOf(blockSel)
            ),
            actionSel
        )

        val ok = exec.run(scenario)

        assertTrue(ok)
        assertEquals(1, driver.clickCount)
    }

    @Test
    fun `oneOf all miss should skip step`() {
        val mustSel = Selector.ByText("must")
        val oneA = Selector.ByText("oneA")
        val oneB = Selector.ByText("oneB")
        val actionSel = Selector.ByText("act")

        val driver = FakeDriver(
            visible = mapOf(
                mustSel to true,
                oneA to false,
                oneB to false
            )
        )
        val exec = newExecutor(driver)
        val scenario = oneStepScenario(
            PageSignature(
                pkg = "pkg",
                must = listOf(mustSel),
                oneOf = listOf(oneA, oneB)
            ),
            actionSel
        )

        val ok = exec.run(scenario)

        assertTrue(ok)
        assertEquals(0, driver.clickCount)
    }

    @Test
    fun `mustNot hit should skip step`() {
        val mustSel = Selector.ByText("must")
        val blockSel = Selector.ByText("blocked")
        val actionSel = Selector.ByText("act")

        val driver = FakeDriver(
            visible = mapOf(
                mustSel to true,
                blockSel to true
            )
        )
        val exec = newExecutor(driver)
        val scenario = oneStepScenario(
            PageSignature(
                pkg = "pkg",
                must = listOf(mustSel),
                mustNot = listOf(blockSel)
            ),
            actionSel
        )

        val ok = exec.run(scenario)

        assertTrue(ok)
        assertEquals(0, driver.clickCount)
    }

    private fun oneStepScenario(sig: PageSignature, actionSel: Selector): Scenario =
        Scenario(
            id = "one-step",
            steps = listOf(
                Step(
                    require = Condition.OnPage(sig),
                    actions = listOf(Action.Click(actionSel))
                )
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

    private class FakeDriver(
        private val visible: Map<Selector, Boolean> = emptyMap()
    ) : Driver {
        var clickCount: Int = 0
            private set

        override fun waitVisible(sel: Selector, timeoutMs: Long): Boolean =
            visible[sel] == true

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

