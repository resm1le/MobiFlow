package com.example.autoa11y.engine

import android.util.Log
import java.io.BufferedReader

object ForegroundActivityInspector {

    private const val TAG = "ForegroundInspector"
    private val COMPONENT_REGEX = Regex("([A-Za-z0-9._]+/[A-Za-z0-9._$]+)")
    private val RESUMED_MARKERS = listOf(
        "mResumedActivity",
        "topResumedActivity",
        "mTopResumedActivity",
        "ResumedActivity",
        "mFocusedActivity"
    )

    fun isOnComponent(componentName: String): Boolean {
        val component = currentComponent() ?: return false
        return component == componentName
    }

    fun currentComponent(): String? {
        val resumedRaw = queryFirstLine("dumpsys activity activities", RESUMED_MARKERS, useSu = true)
        val resumed = resumedRaw?.let(::extractComponent)
        if (resumed != null) {
            Log.d(TAG, "resumed=$resumedRaw -> $resumed")
            return resumed
        }
        // 兜底：某些系统的 'dumpsys activity activities' 输出格式差异较大，尝试用 'dumpsys activity top'
        val topRaw = queryFirstLine("dumpsys activity top", RESUMED_MARKERS + "ACTIVITY", useSu = true)
        val top = topRaw?.let(::extractComponent)
        if (top != null) {
            Log.d(TAG, "top=$topRaw -> $top")
            return top
        }
        val focusRaw = queryLine("dumpsys window", "mCurrentFocus", useSu = true)
        val focus = focusRaw?.let { extractComponent(it) }
        if (focus != null) {
            Log.d(TAG, "mCurrentFocus=$focusRaw -> $focus")
        }
        return focus
    }

    private fun queryFirstLine(cmd: String, markers: List<String>, useSu: Boolean = false): String? = try {
        val shell = if (useSu) arrayOf("su", "-c", cmd) else arrayOf("sh", "-c", cmd)
        val proc = Runtime.getRuntime().exec(shell)
        val out = proc.inputStream.bufferedReader().use(BufferedReader::readText)
        proc.waitFor()
        out.lineSequence()
            .firstOrNull { line -> markers.any { marker -> line.contains(marker) } }
            ?.trim()
            ?.takeIf { it.isNotBlank() }
    } catch (t: Throwable) {
        Log.w(TAG, "queryFirstLine($cmd) failed: ${t.message}", t)
        null
    }

    private fun queryLine(cmd: String, marker: String, useSu: Boolean = false): String? = try {
        val shell = if (useSu) arrayOf("su", "-c", cmd) else arrayOf("sh", "-c", cmd)
        val proc = Runtime.getRuntime().exec(shell)
        val out = proc.inputStream.bufferedReader().use(BufferedReader::readText)
        proc.waitFor()
        out.lineSequence().firstOrNull { it.contains(marker) }?.trim()?.takeIf { it.isNotBlank() }
    } catch (t: Throwable) {
        Log.w(TAG, "queryLine($cmd) failed: ${t.message}", t)
        null
    }

    private fun extractComponent(raw: String): String? =
        COMPONENT_REGEX.find(raw)?.groupValues?.getOrNull(1)
}
