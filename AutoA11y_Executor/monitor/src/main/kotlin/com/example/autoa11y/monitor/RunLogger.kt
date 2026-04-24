package com.example.autoa11y.monitor

import android.content.Context
import android.util.Log
import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.shared.AppConfig
import com.example.autoa11y.shared.Time
import java.io.File
import java.io.FileWriter

private const val TAG = "RunLogger"

/**
 * 兼容版 RunLogger：
 * - 保留原有类名与公开方法签名，避免外部调用报错；
 * - 实现新策略：仅记录“完整结束”的循环；每轮结束一次性写入该轮起止；
 * - 至少完成一轮后才补写 RUN_START；若整个运行没有任何完整循环，则不写 RUN_END；
 * - 同步落盘，避免进程被杀后丢失已完成轮的时间点。
 */
class RunLogger(
    private val ctx: Context,
    private val runId: String,
    targetPackage: String
) {

    private val targetTag = targetPackage.ifBlank { "unknown" }
        .replace(Regex("[^A-Za-z0-9._-]"), "_")
    private val rootDir = File(ctx.filesDir, AppConfig.RUN_DIR_PREFIX)
    private val file = File(rootDir, "${runId}_${targetTag}.txt")

    /** 缓存：本次运行开始时间（首轮完成时再补写 RUN_START） */
    private var runStartTs: Long = 0L

    /** 标记：是否已完成过至少一轮 */
    private var anyLoopCompleted: Boolean = false

    /** 缓存：当前轮的 index + startTs，等 ok=true 的 LOOP_END 时与 endTs 一起写入 */
    private var pendingLoopIndex: Int? = null
    private var pendingLoopStartTs: Long? = null
    private var headerWritten: Boolean = false

    // ===================== 对外公开方法（保持签名不变） =====================

    /** 运行开始：仅缓存在内存，等首轮完成时才落盘 RUN_START */
    fun logRunStart(ts: Long = System.currentTimeMillis()) {
        runStartTs = ts
        if (!rootDir.exists()) rootDir.mkdirs()
        Log.i(TAG, "RUN_START buffered @ ${Time.iso(ts)}")
    }

    fun logHeader(headers: Map<String, String>) {
        if (headerWritten) return
        headerWritten = true
        appendLines(
            "RUN_HEADER ${Time.iso()}",
            *headers.entries
                .sortedBy { it.key }
                .map { "${it.key}=${it.value}" }
                .toTypedArray()
        )
    }

    /** 某轮开始：仅缓存在内存，不立即写文件 */
    fun logLoopStart(index: Int, startTs: Long) {
        pendingLoopIndex = index
        pendingLoopStartTs = startTs
        Log.i(TAG, "LOOP_START #$index buffered @ ${Time.iso(startTs)}")
    }

    /**
     * 某轮结束：只有 ok=true 且存在匹配的 LOOP_START 时才一次性写入【该轮起止】；
     * 首次完成时先补写 RUN_START。
     * 注意：startTs 参数保持兼容，但实际以内部缓存的 start 为准。
     */
    fun logLoopEnd(index: Int, @Suppress("UNUSED_PARAMETER") startTs: Long, endTs: Long, ok: Boolean) {
        if (!ok) {
            Log.w(TAG, "LOOP_END #$index skipped (ok=false)")
            // 清理本轮缓存
            pendingLoopIndex = null
            pendingLoopStartTs = null
            return
        }
        val sIdx = pendingLoopIndex
        val sTs = pendingLoopStartTs
        if (sIdx == null || sTs == null || sIdx != index) {
            Log.w(TAG, "LOOP_END #$index without matching LOOP_START -> ignore")
            return
        }

        // 首轮完成时补写 RUN_START
        if (!anyLoopCompleted) {
            appendLine("RUN_START ${Time.iso(runStartTs)}")
            anyLoopCompleted = true
        }

        // 一次性写入本轮起止
        appendLines(
            "LOOP_START #$index ${Time.iso(sTs)}",
            "LOOP_END   #$index ${Time.iso(endTs)}"
        )

        // 清理本轮缓存
        pendingLoopIndex = null
        pendingLoopStartTs = null
    }

    /** 运行结束：只有在出现过完整循环时才写 RUN_END */
    fun logRunEnd(ts: Long = System.currentTimeMillis()) {
        if (anyLoopCompleted) {
            appendLine("RUN_END ${Time.iso(ts)}")
        } else {
            Log.i(TAG, "RUN_END: no completed loops -> nothing to write")
        }
    }

    // ====== 兼容占位：如果历史代码里有调用这些方法，不会报错，但不做记录 ======

    /** 历史可能存在的摘要输出（保留签名，改为 no-op） */
    @Deprecated("No-op for compatibility")
    fun logSummary(@Suppress("UNUSED_PARAMETER") ok: Boolean,
                   @Suppress("UNUSED_PARAMETER") metrics: Map<String, Any>,
                   @Suppress("UNUSED_PARAMETER") startTsOpt: Long? = null) { /* no-op */ }

    /** 历史可能存在的动作明细（保留签名，改为 no-op） */
    @Deprecated("No-op for compatibility")
    fun logAction(@Suppress("UNUSED_PARAMETER") index: Int,
                  @Suppress("UNUSED_PARAMETER") action: Action,
                  @Suppress("UNUSED_PARAMETER") driver: Driver,
                  @Suppress("UNUSED_PARAMETER") ok: Boolean,
                  @Suppress("UNUSED_PARAMETER") elapsedMs: Long,
                  @Suppress("UNUSED_PARAMETER") evidencePath: String? = null,
                  @Suppress("UNUSED_PARAMETER") error: String? = null) { /* no-op */ }

    // ===================== 文件写入工具 =====================

    private fun appendLine(line: String) {
        try {
            if (!rootDir.exists()) rootDir.mkdirs()
            FileWriter(file, /*append=*/true).use { fw ->
                fw.append(line).append('\n')
                fw.flush()
            }
        } catch (t: Throwable) {
            Log.e(TAG, "appendLine error: ${t.message}", t)
        }
    }

    private fun appendLines(vararg lines: String) {
        try {
            if (!rootDir.exists()) rootDir.mkdirs()
            FileWriter(file, /*append=*/true).use { fw ->
                for (ln in lines) fw.append(ln).append('\n')
                fw.flush()
            }
        } catch (t: Throwable) {
            Log.e(TAG, "appendLines error: ${t.message}", t)
        }
    }
}
