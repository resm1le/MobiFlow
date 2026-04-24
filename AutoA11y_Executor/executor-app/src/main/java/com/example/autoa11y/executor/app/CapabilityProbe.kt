package com.example.autoa11y.executor.app

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.PowerManager
import com.example.autoa11y.executor.control.ExecutorCapabilities
import com.example.autoa11y.executor.reporting.ExecutorHealthSnapshot
import com.example.autoa11y.drivers.a11y.A11yServiceHolder

object CapabilityProbe {
    private const val CACHE_TTL_MS = 60_000L

    private data class CachedProbe(
        val checkedAt: Long,
        val capabilities: ExecutorCapabilities,
        val shellAvailable: Boolean
    )

    @Volatile
    private var cached: CachedProbe? = null

    fun invalidate() {
        cached = null
    }

    fun collect(context: Context, forceRefresh: Boolean = false): ExecutorCapabilities =
        diagnose(context, forceRefresh).capabilities

    fun healthSnapshot(
        context: Context,
        backendReachable: Boolean,
        lastRegisterOk: Boolean,
        lastHeartbeatOk: Boolean,
        degradedReason: String?,
        forceRefresh: Boolean = false
    ): ExecutorHealthSnapshot {
        val diagnosis = diagnose(context, forceRefresh)
        return ExecutorHealthSnapshot(
            accessibilityEnabled = diagnosis.capabilities.accessibilityEnabled,
            rootAvailable = diagnosis.capabilities.rootAvailable,
            shellAvailable = diagnosis.shellAvailable,
            networkIsolationAvailable = diagnosis.capabilities.networkIsolationAvailable,
            backendReachable = backendReachable,
            lastRegisterOk = lastRegisterOk,
            lastHeartbeatOk = lastHeartbeatOk,
            degradedReason = degradedReason,
            authConfigured = false,
            bufferedDeliveryCount = 0,
            lastCheckedAt = System.currentTimeMillis(),
            foregroundPackage = A11yServiceHolder.service?.rootInActiveWindow?.packageName?.toString(),
            batteryLevel = batteryLevel(context),
            thermalStatus = thermalStatus(context)
        )
    }

    private fun diagnose(@Suppress("UNUSED_PARAMETER") context: Context, forceRefresh: Boolean): CachedProbe {
        val existing = cached
        val now = System.currentTimeMillis()
        if (!forceRefresh && existing != null && now - existing.checkedAt < CACHE_TTL_MS) {
            return existing.copy(
                capabilities = existing.capabilities.copy(
                    accessibilityEnabled = A11yServiceHolder.service != null,
                    screenshotCapable = existing.capabilities.shellAvailable,
                    uiDumpCapable = existing.capabilities.shellAvailable
                )
            )
        }

        val shellAvailable = canExec(arrayOf("sh", "-c", "id"))
        val rootAvailable = canExec(arrayOf("su", "-c", "id"))
        val iptablesAvailable = if (rootAvailable) {
            canExec(arrayOf("su", "-c", "iptables -L -n >/dev/null 2>&1"))
        } else {
            false
        }
        return CachedProbe(
            checkedAt = now,
            capabilities = ExecutorCapabilities(
                accessibilityEnabled = A11yServiceHolder.service != null,
                rootAvailable = rootAvailable,
                shellAvailable = shellAvailable,
                networkIsolationAvailable = rootAvailable && iptablesAvailable,
                screenshotCapable = shellAvailable,
                uiDumpCapable = shellAvailable
            ),
            shellAvailable = shellAvailable
        ).also { cached = it }
    }

    private fun batteryLevel(context: Context): Int? {
        val intent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return null
        val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
        val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
        if (level < 0 || scale <= 0) return null
        return ((level * 100f) / scale.toFloat()).toInt()
    }

    private fun thermalStatus(context: Context): String? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return null
        val powerManager = context.getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return null
        return when (powerManager.currentThermalStatus) {
            PowerManager.THERMAL_STATUS_NONE -> "NONE"
            PowerManager.THERMAL_STATUS_LIGHT -> "LIGHT"
            PowerManager.THERMAL_STATUS_MODERATE -> "MODERATE"
            PowerManager.THERMAL_STATUS_SEVERE -> "SEVERE"
            PowerManager.THERMAL_STATUS_CRITICAL -> "CRITICAL"
            PowerManager.THERMAL_STATUS_EMERGENCY -> "EMERGENCY"
            PowerManager.THERMAL_STATUS_SHUTDOWN -> "SHUTDOWN"
            else -> "UNKNOWN"
        }
    }

    private fun canExec(cmd: Array<String>): Boolean = runCatching {
        val process = Runtime.getRuntime().exec(cmd)
        process.waitFor() == 0
    }.getOrDefault(false)
}
