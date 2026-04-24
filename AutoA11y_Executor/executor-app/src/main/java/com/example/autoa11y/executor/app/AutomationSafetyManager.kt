package com.example.autoa11y.executor.app

import android.content.Context
import com.example.autoa11y.drivers.shell.ShellBridge

object AutomationSafetyManager {
    internal const val LEGACY_APP_PACKAGE = "com.example.autoa11y.app"
    private const val DRIVER_SERVICE_CLASS = "com.example.autoa11y.drivers.a11y.AutomationService"

    internal val currentServiceComponent: String
        get() = "${BuildConfig.APPLICATION_ID}/$DRIVER_SERVICE_CLASS"

    internal val legacyServiceComponent: String
        get() = "$LEGACY_APP_PACKAGE/$DRIVER_SERVICE_CLASS"

    fun enforceExclusiveOwner(context: Context) {
        val shell = ShellBridge(context)
        val enabled = enabledServicesAfterEnable(readEnabledServices(shell), currentServiceComponent)
        writeEnabledServices(shell, enabled)
        shell.amForceStop(LEGACY_APP_PACKAGE)
    }

    fun enableCurrentAutomation(context: Context) {
        val shell = ShellBridge(context)
        val enabled = enabledServicesAfterEnable(readEnabledServices(shell), currentServiceComponent)
        writeEnabledServices(shell, enabled)
    }

    fun disableKnownAutomation(context: Context, stopProfilePackage: String? = null) {
        val shell = ShellBridge(context)
        val remaining = enabledServicesAfterDisable(readEnabledServices(shell), currentServiceComponent)
        writeEnabledServices(shell, remaining)
        stopProfilePackage?.takeIf { it.isNotBlank() }?.let(shell::amForceStop)
        shell.amForceStop(LEGACY_APP_PACKAGE)
    }

    internal fun enabledServicesAfterEnable(raw: String?, currentComponent: String): List<String> {
        val preserved = parseEnabledServices(raw)
            .filterNot { it == legacyServiceComponent || it == currentComponent }
            .toMutableList()
        preserved.add(0, currentComponent)
        return preserved
    }

    internal fun enabledServicesAfterDisable(raw: String?, currentComponent: String): List<String> =
        parseEnabledServices(raw)
            .filterNot { it == legacyServiceComponent || it == currentComponent }

    internal fun parseEnabledServices(raw: String?): List<String> =
        raw.orEmpty()
            .trim()
            .takeIf { it.isNotEmpty() && !it.equals("null", ignoreCase = true) }
            ?.split(':')
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?.distinct()
            ?: emptyList()

    private fun readEnabledServices(shell: ShellBridge): String =
        shell.runCommand("settings get secure enabled_accessibility_services").out.trim()

    private fun writeEnabledServices(shell: ShellBridge, services: List<String>) {
        if (services.isEmpty()) {
            shell.runCommand("settings delete secure enabled_accessibility_services")
            shell.runCommand("settings put secure accessibility_enabled 0")
            return
        }

        val joined = services.joinToString(":")
        shell.runCommand("settings put secure enabled_accessibility_services '$joined'")
        shell.runCommand("settings put secure accessibility_enabled 1")
    }
}
