package com.example.autoa11y.executor.app

import org.junit.Assert.assertEquals
import org.junit.Test

class AutomationSafetyManagerTest {
    @Test
    fun enableCurrentAutomationRemovesLegacyAndPreservesOthers() {
        val result = AutomationSafetyManager.enabledServicesAfterEnable(
            raw = listOf(
                "com.reader/.ReaderService",
                AutomationSafetyManager.legacyServiceComponent,
                "com.tools/.ToolService"
            ).joinToString(":"),
            currentComponent = AutomationSafetyManager.currentServiceComponent
        )

        assertEquals(
            listOf(
                AutomationSafetyManager.currentServiceComponent,
                "com.reader/.ReaderService",
                "com.tools/.ToolService"
            ),
            result
        )
    }

    @Test
    fun disableKnownAutomationOnlyRemovesAutoA11yServices() {
        val result = AutomationSafetyManager.enabledServicesAfterDisable(
            raw = listOf(
                "com.reader/.ReaderService",
                AutomationSafetyManager.currentServiceComponent,
                AutomationSafetyManager.legacyServiceComponent,
                "com.tools/.ToolService"
            ).joinToString(":"),
            currentComponent = AutomationSafetyManager.currentServiceComponent
        )

        assertEquals(
            listOf(
                "com.reader/.ReaderService",
                "com.tools/.ToolService"
            ),
            result
        )
    }
}
