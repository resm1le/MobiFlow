package com.example.autoa11y.executor.app

import android.content.Context
import android.content.Intent
import com.example.autoa11y.env.NetworkIsolationManager
import com.example.autoa11y.executor.reporting.RuntimeSnapshotStore

object TaskExecutionStopper {
    fun cancelCurrent(context: Context) {
        NetworkIsolationManager.restore(context.applicationContext)
        val currentProfilePackage = RuntimeSnapshotStore(context).read().currentProfilePackage
        AutomationSafetyManager.disableKnownAutomation(context, currentProfilePackage)
        TaskExecutionService.stopExecutionLoop(context)
    }
}
