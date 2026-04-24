package com.example.autoa11y.executor.app

import android.app.Application

class ExecutorApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        runCatching {
            AutomationSafetyManager.enforceExclusiveOwner(this)
        }
    }
}
