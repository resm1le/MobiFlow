package com.example.autoa11y.engine

import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.ActionResult
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.NodeSummary
import com.example.autoa11y.core.api.ResolveResult
import com.example.autoa11y.core.api.Selector
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class DriverChainTest {

    @Test
    fun `coord selector should bypass primary and use fallback`() {
        val primary = RecordingDriver(clickResult = true)
        val fallback = RecordingDriver(clickResult = true)
        val chain = DriverChain(primary, fallback)

        val ok = chain.click(Selector.CoordRatio(0.5f, 0.5f))

        assertTrue(ok)
        assertEquals(0, primary.clickCount)
        assertEquals(1, fallback.clickCount)
    }

    @Test
    fun `semantic selector should try primary then fallback when primary fails`() {
        val primary = RecordingDriver(clickResult = false)
        val fallback = RecordingDriver(clickResult = true)
        val chain = DriverChain(primary, fallback)

        val ok = chain.click(Selector.ByText("搜索"))

        assertTrue(ok)
        assertEquals(1, primary.clickCount)
        assertEquals(1, fallback.clickCount)
    }

    @Test
    fun `semantic selector should not call fallback when primary succeeds`() {
        val primary = RecordingDriver(clickResult = true)
        val fallback = RecordingDriver(clickResult = true)
        val chain = DriverChain(primary, fallback)

        val ok = chain.click(Selector.ByText("搜索"))

        assertTrue(ok)
        assertEquals(1, primary.clickCount)
        assertEquals(0, fallback.clickCount)
    }

    @Test
    fun `not clickable with coord fallback in AnyOf should call fallback`() {
        val primary = object : Driver by RecordingDriver(clickResult = false) {
            override fun clickResolved(sel: Selector): ActionResult =
                ActionResult.failure(
                    ResolveResult.notClickable(
                        NodeSummary(
                            text = "路线",
                            desc = "",
                            bounds = "[0,0][10,10]",
                            clickable = false
                        )
                    )
                )
        }
        val fallback = RecordingDriver(clickResult = true)
        val chain = DriverChain(primary, fallback)

        val ok = chain.click(
            Selector.AnyOf(
                listOf(
                    Selector.ByText("路线"),
                    Selector.CoordRatio(0.85f, 0.91f)
                )
            )
        )

        assertTrue(ok)
        assertEquals(1, fallback.clickCount)
    }

    @Test
    fun `action failed without coord fallback should not call fallback`() {
        val primary = object : Driver by RecordingDriver(clickResult = false) {
            override fun clickResolved(sel: Selector): ActionResult =
                ActionResult.failure(
                    ResolveResult.actionFailed(
                        NodeSummary(
                            text = "路线",
                            desc = "",
                            bounds = "[0,0][10,10]",
                            clickable = true
                        )
                    )
                )
        }
        val fallback = RecordingDriver(clickResult = true)
        val chain = DriverChain(primary, fallback)

        val ok = chain.click(Selector.ByText("路线"))

        assertFalse(ok)
        assertEquals(0, fallback.clickCount)
    }

    @Test
    fun `action failed with coord fallback in AnyOf should call fallback`() {
        val primary = object : Driver by RecordingDriver(clickResult = false) {
            override fun clickResolved(sel: Selector): ActionResult =
                ActionResult.failure(
                    ResolveResult.actionFailed(
                        NodeSummary(
                            text = "路线",
                            desc = "",
                            bounds = "[0,0][10,10]",
                            clickable = true
                        )
                    )
                )
        }
        val fallback = RecordingDriver(clickResult = true)
        val chain = DriverChain(primary, fallback)

        val ok = chain.click(
            Selector.AnyOf(
                listOf(
                    Selector.ByText("路线"),
                    Selector.CoordRatio(0.85f, 0.91f)
                )
            )
        )

        assertTrue(ok)
        assertEquals(1, fallback.clickCount)
    }

    private class RecordingDriver(
        private val clickResult: Boolean = true,
        private val waitResult: Boolean = false
    ) : Driver {
        var clickCount: Int = 0
            private set
        var waitCount: Int = 0
            private set

        override fun waitVisible(sel: Selector, timeoutMs: Long): Boolean {
            waitCount++
            return waitResult
        }

        override fun click(sel: Selector): Boolean {
            clickCount++
            return clickResult
        }

        override fun input(sel: Selector, text: String, clearFirst: Boolean): Boolean = false

        override fun scroll(steps: Int, dir: Action.Direction): Boolean = false

        override fun swipe(
            fromXRatio: Float,
            fromYRatio: Float,
            toXRatio: Float,
            toYRatio: Float,
            durationMs: Int
        ): Boolean = false

        override fun back(): Boolean = false
    }
}
