package com.example.autoa11y.executor.app

import android.content.Context
import com.example.autoa11y.executor.control.ExecutorCapabilities
import com.example.autoa11y.executor.control.ExecutorClient
import com.example.autoa11y.executor.reporting.ExecutorHealthSnapshot
import com.example.autoa11y.executor.reporting.LocalDeliveryStore
import com.example.autoa11y.drivers.shell.ShellBridge
import com.example.autoa11y.env.DeviceEnv
import com.example.autoa11y.env.RootDeviceEnv
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService

interface ExecutorRuntimeDependencies {
    fun createExecutorClient(context: Context): ExecutorClient
    fun createDeliveryStore(context: Context): LocalDeliveryStore
    fun createShellBridge(context: Context): ShellBridge
    fun createDeviceEnv(context: Context, shell: ShellBridge): DeviceEnv
    fun createTaskExecutor(): ExecutorService
    fun createControlExecutor(): ScheduledExecutorService
    fun collectCapabilities(context: Context, forceRefresh: Boolean): ExecutorCapabilities
    fun collectHealth(
        context: Context,
        backendReachable: Boolean,
        lastRegisterOk: Boolean,
        lastHeartbeatOk: Boolean,
        degradedReason: String?,
        forceRefresh: Boolean
    ): ExecutorHealthSnapshot
    fun isPackageInstalled(context: Context, packageName: String): Boolean
    fun nowMs(): Long = System.currentTimeMillis()
    fun shouldAutoStartLoop(): Boolean = true
}

object DefaultExecutorRuntimeDependencies : ExecutorRuntimeDependencies {
    override fun createExecutorClient(context: Context): ExecutorClient = ExecutorClient(context)

    override fun createDeliveryStore(context: Context): LocalDeliveryStore =
        LocalDeliveryStore.fromContext(context)

    override fun createShellBridge(context: Context): ShellBridge = ShellBridge(context)

    override fun createDeviceEnv(context: Context, shell: ShellBridge): DeviceEnv =
        RootDeviceEnv(context.applicationContext, shell)

    override fun createTaskExecutor(): ExecutorService = Executors.newSingleThreadExecutor()

    override fun createControlExecutor(): ScheduledExecutorService =
        Executors.newSingleThreadScheduledExecutor()

    override fun collectCapabilities(context: Context, forceRefresh: Boolean): ExecutorCapabilities =
        CapabilityProbe.collect(context, forceRefresh)

    override fun collectHealth(
        context: Context,
        backendReachable: Boolean,
        lastRegisterOk: Boolean,
        lastHeartbeatOk: Boolean,
        degradedReason: String?,
        forceRefresh: Boolean
    ): ExecutorHealthSnapshot = CapabilityProbe.healthSnapshot(
        context = context,
        backendReachable = backendReachable,
        lastRegisterOk = lastRegisterOk,
        lastHeartbeatOk = lastHeartbeatOk,
        degradedReason = degradedReason,
        forceRefresh = forceRefresh
    )

    override fun isPackageInstalled(context: Context, packageName: String): Boolean = runCatching {
        context.packageManager.getLaunchIntentForPackage(packageName) != null ||
            context.packageManager.getPackageInfo(packageName, 0) != null
    }.getOrDefault(false)
}

object ExecutorRuntimeDependenciesHolder {
    @Volatile
    var current: ExecutorRuntimeDependencies = DefaultExecutorRuntimeDependencies

    fun reset() {
        current = DefaultExecutorRuntimeDependencies
    }
}
