package com.example.autoa11y.executor.app

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.autoa11y.executor.control.ExecutorClient
import com.example.autoa11y.executor.reporting.RuntimeSnapshotStore

class ExecutorMainActivity : AppCompatActivity() {
    companion object {
        private const val GOOGLE_MAPS_PKG = "com.google.android.apps.maps"
        private const val TIKTOK_PKG = "com.zhiliaoapp.musically"
        private const val SHEIN_PKG = "com.zzkko"
    }

    private lateinit var txtStatus: TextView
    private lateinit var editBackendUrl: EditText
    private lateinit var editDeviceToken: EditText
    private lateinit var snapshotStore: RuntimeSnapshotStore
    private lateinit var executorClient: ExecutorClient

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_executor_main)

        snapshotStore = RuntimeSnapshotStore(this)
        executorClient = ExecutorClient(this)
        txtStatus = findViewById(R.id.txtExecutorStatus)
        editBackendUrl = findViewById(R.id.editBackendUrl)
        editDeviceToken = findViewById(R.id.editDeviceToken)
        editBackendUrl.setText(executorClient.baseUrl)
        editDeviceToken.setText(executorClient.deviceToken)

        findViewById<Button>(R.id.btnSaveBackend).setOnClickListener {
            val backendUrl = editBackendUrl.text?.toString().orEmpty().trim()
            val deviceToken = editDeviceToken.text?.toString().orEmpty().trim()
            if (backendUrl.isNotEmpty()) {
                executorClient.baseUrl = backendUrl
                executorClient.deviceToken = deviceToken
                snapshotStore.updateBackend(executorClient.baseUrl, snapshotStore.read().deviceId)
                TaskExecutionService.requestHealthCheck(this)
                refreshStatus()
            }
        }
        findViewById<Button>(R.id.btnHealthCheck).setOnClickListener {
            TaskExecutionService.requestHealthCheck(this)
            refreshStatus()
        }
        findViewById<Button>(R.id.btnStartExecutor).setOnClickListener {
            TaskExecutionService.startExecutionLoop(this)
            refreshStatus()
        }
        findViewById<Button>(R.id.btnStopExecutor).setOnClickListener {
            TaskExecutionStopper.cancelCurrent(this)
            refreshStatus()
        }
        findViewById<Button>(R.id.btnFakeMaps).setOnClickListener {
            TaskExecutionService.runFakeTask(this, GOOGLE_MAPS_PKG)
            refreshStatus()
        }
        findViewById<Button>(R.id.btnFakeTiktok).setOnClickListener {
            TaskExecutionService.runFakeTask(this, TIKTOK_PKG)
            refreshStatus()
        }
        findViewById<Button>(R.id.btnFakeShein).setOnClickListener {
            TaskExecutionService.runFakeTask(this, SHEIN_PKG)
            refreshStatus()
        }
        findViewById<Button>(R.id.btnRefresh).setOnClickListener { refreshStatus() }

        TaskExecutionService.startExecutionLoop(this)
        refreshStatus()
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
    }

    private fun refreshStatus() {
        val snapshot = snapshotStore.read()
        val labels = ExecutorProfileRegistry.entries(this).joinToString { it.label }
        editBackendUrl.setText(executorClient.baseUrl)
        editDeviceToken.setText(executorClient.deviceToken)
        txtStatus.text = buildString {
            appendLine("Backend: ${snapshot.backendUrl.ifBlank { executorClient.baseUrl }}")
            appendLine("DeviceId: ${snapshot.deviceId.ifBlank { "unknown" }}")
            appendLine("Protocol: ${snapshot.protocolVersion}")
            appendLine("State: ${snapshot.state}")
            appendLine("Registered: ${snapshot.registered}")
            appendLine("Busy: ${snapshot.busy}")
            appendLine("A11y: ${snapshot.health.accessibilityEnabled}")
            appendLine("Root: ${snapshot.health.rootAvailable}")
            appendLine("Shell: ${snapshot.health.shellAvailable}")
            appendLine("NetIsolation: ${snapshot.health.networkIsolationAvailable}")
            appendLine("BackendReachable: ${snapshot.health.backendReachable}")
            appendLine("RegisterOk: ${snapshot.health.lastRegisterOk}")
            appendLine("HeartbeatOk: ${snapshot.health.lastHeartbeatOk}")
            appendLine("AuthConfigured: ${snapshot.health.authConfigured}")
            appendLine("BufferedDeliveries: ${snapshot.health.bufferedDeliveryCount}")
            appendLine("ConfigVersion: ${snapshot.configVersion ?: "-"}")
            appendLine("PollMs: ${snapshot.pollIntervalMs}")
            appendLine("HeartbeatMs: ${snapshot.heartbeatIntervalMs}")
            appendLine("LastHeartbeatAt: ${snapshot.lastHeartbeatAt}")
            appendLine("Attempt: ${snapshot.currentAttemptId ?: "idle"}")
            appendLine("TaskId: ${snapshot.currentTaskId ?: "-"}")
            appendLine("TaskType: ${snapshot.currentTaskType ?: "-"}")
            appendLine("Profile: ${snapshot.currentProfilePackage ?: "-"}")
            appendLine("RunId: ${snapshot.lastRunId ?: "-"}")
            appendLine("LeaseExpireAt: ${snapshot.leaseExpireAt ?: "-"}")
            appendLine("LastCommand: ${snapshot.lastCommand ?: "-"}")
            appendLine("Tags: ${snapshot.tags.joinToString().ifBlank { "-" }}")
            appendLine("Last: ${snapshot.lastMessage}")
            appendLine("Error: ${snapshot.lastError ?: "-"}")
            appendLine("Degraded: ${snapshot.health.degradedReason ?: "-"}")
            appendLine("Plugins: $labels")
        }
    }
}
