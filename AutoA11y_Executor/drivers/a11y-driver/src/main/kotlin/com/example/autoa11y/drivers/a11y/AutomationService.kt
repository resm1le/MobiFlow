package com.example.autoa11y.drivers.a11y
import android.accessibilityservice.AccessibilityService
import android.util.Log
object A11yServiceHolder { @Volatile var service: AutomationService? = null }
class AutomationService : AccessibilityService() {
    override fun onServiceConnected() { super.onServiceConnected(); A11yServiceHolder.service = this; Log.i("AutomationService","Connected") }
    override fun onAccessibilityEvent(event: android.view.accessibility.AccessibilityEvent?) {}
    override fun onInterrupt() { A11yServiceHolder.service = null }
    override fun onDestroy() { A11yServiceHolder.service = null; super.onDestroy() }
    override fun onUnbind(intent: android.content.Intent?): Boolean { A11yServiceHolder.service = null; return super.onUnbind(intent) }
}
