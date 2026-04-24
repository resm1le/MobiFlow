package com.example.autoa11y.executor.app

import android.content.Context
import com.example.autoa11y.core.api.TargetAppProfile

object ExecutorProfileRegistry {
    data class Entry(
        val id: String,
        val label: String,
        val profile: TargetAppProfile
    )

    fun entries(@Suppress("UNUSED_PARAMETER") ctx: Context): List<Entry> {
        return GeneratedExecutorPluginEntries.entries
    }

    fun findByPackage(ctx: Context, packageName: String): TargetAppProfile? =
        entries(ctx).firstOrNull { it.profile.packageName == packageName }?.profile

    fun enabledPluginIds(raw: String = BuildConfig.ENABLED_PLUGINS): Set<String> {
        val normalized = raw.trim()
        if (normalized.isBlank() || normalized.equals("all", ignoreCase = true)) {
            return emptySet()
        }
        return normalized.split(",")
            .map { it.trim().lowercase() }
            .filter { it.isNotBlank() }
            .toSet()
    }
}
