package com.example.autoa11y.env

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.util.Log

/**
 * Network isolation manager: installs iptables/ip6tables guard chains to limit network access at runtime.
 *
 * Flow:
 * 1. enable() creates/refreshes the guard chain so that only the target UID, the host UID and core system UIDs keep access.
 * 2. restore()/clearGuard() remove the guard chain to bring networking back to its unrestricted state.
 * 3. clearGuard() stays available to forcibly delete guard chains even if enable() failed midway.
 */
object NetworkIsolationManager {

    const val ACTION_STATE_CHANGED = "com.example.autoa11y.env.NETWORK_ISOLATION_STATE_CHANGED"
    const val EXTRA_ACTIVE = "extra_active"
    const val EXTRA_TARGET_UID = "extra_target_uid"
    const val EXTRA_TARGET_PACKAGE = "extra_target_package"

    private const val TAG = "NetworkIsolation"
    private const val GUARD_CHAIN = "AUTOA11Y_GUARD"

    private val lock = Any()

    private var active = false
    private var targetUid: Int = -1
    private var targetPackageName: String? = null
    private var hostUid: Int = -1
    private var appContext: Context? = null
    private var extraPackages: Set<String> = emptySet()
    private var processUids: Set<Int> = emptySet()

    /**
     * Enable isolation so that [targetPackage] and [extraPackages] keep network access.
     * Returns true when the guard is active (no-op if already applied for the same UID).
     */
    @JvmOverloads
    fun enable(
        context: Context,
        targetPackage: String,
        extraPackages: List<String> = emptyList()
    ): Boolean = synchronized(lock) {
        val requestedExtras = extraPackages.map { it.trim() }.filter { it.isNotEmpty() }.toSet()
        // 通过包名解析目标 UID，后续 iptables 将按 UID 匹配。
        val resolvedUid = resolveUid(context, targetPackage) ?: run {
            Log.e(TAG, "Unable to resolve UID for package=$targetPackage")
            return@synchronized false
        }
        val extraUids = requestedExtras.mapNotNull { pkg ->
            val uid = resolveUid(context, pkg)
            if (uid == null) {
                Log.w(TAG, "Unable to resolve UID for extra package=$pkg")
            }
            uid
        }.toSet()
        val packageSet = requestedExtras + targetPackage
        val allowWebviewZygote = packageSet.any { it.contains("webview") || it.contains("chrome") }
        val extraProcessNames = if (allowWebviewZygote) {
            setOf("webview_zygote", "webview_zygote32", "webview_zygote64")
        } else {
            emptySet()
        }
        val resolvedProcessUids = resolveProcessUids(packageSet, extraProcessNames)
        val currentProcessUids = resolvedProcessUids ?: if (active) {
            this.processUids
        } else {
            emptySet()
        }
        if (currentProcessUids.isNotEmpty()) {
            Log.i(
                TAG,
                "Allowing process UIDs for packages=${packageSet.joinToString()} extras=${extraProcessNames.joinToString()} -> " +
                    currentProcessUids.joinToString()
            )
        }
        val guardExtraUids = extraUids + currentProcessUids

        if (active) {
            if (resolvedUid == targetUid &&
                requestedExtras == this.extraPackages &&
                currentProcessUids == this.processUids
            ) {
                Log.i(
                    TAG,
                    "Network isolation already active for uid=$resolvedUid extras=${requestedExtras.joinToString()}"
                )
                return@synchronized true
            }
            Log.w(
                TAG,
                "Switching network isolation target from uid=$targetUid to uid=$resolvedUid " +
                    "(extras changed=${requestedExtras != this.extraPackages})"
            )
            restoreInternal()
        }

        // Probe iptables/ip6tables availability before applying guard.
        if (captureTable("iptables-save") == null) {
            Log.e(TAG, "Failed to probe IPv4 rules, abort isolating")
            return@synchronized false
        }
        val includeIpv6 = captureTable("ip6tables-save") != null
        if (!includeIpv6) {
            Log.i(TAG, "IPv6 tables not detected, applying IPv4-only guard")
        }

        // Record host UID so the current process retains network access.
        hostUid = context.applicationInfo.uid

        if (!applyGuard(resolvedUid, hostUid, guardExtraUids, includeIpv6 = includeIpv6)) {
            Log.e(TAG, "Failed to apply guard rules, clearing guard chains")
            clearGuardLocked()
            return@synchronized false
        }

        appContext = context.applicationContext
        targetUid = resolvedUid
        targetPackageName = targetPackage
        this.extraPackages = requestedExtras
        processUids = currentProcessUids
        active = true

        Log.i(TAG, "Network isolation enabled for uid=$targetUid pkg=$targetPackage extras=${requestedExtras.joinToString()}")
        notifyStateChangedLocked()
        true
    }

    /** 恢复防火墙至启用前状态，若未启用过则仅清理缓存引用。 */
    fun restore(context: Context? = null) = synchronized(lock) {
        context?.applicationContext?.let { appContext = it }
        clearGuardLocked()
        notifyStateChangedLocked()
    }

    /**
     * 在没有快照时强制移除守卫链，确保 iptables/ip6tables 不再残留限制。
     * 适用于用户主动“恢复网络”的场景，即使之前启用失败也能清扫规则。
     */
    fun clearGuard(context: Context? = null): Boolean = synchronized(lock) {
        context?.applicationContext?.let { appContext = it }
        val wasActive = active
        val cleared = clearGuardLocked()
        notifyStateChangedLocked()
        if (wasActive) true else cleared
    }

    /** Visible for tests/diagnostics. */
    fun isActive(): Boolean = synchronized(lock) { active }

    // 回滚到启用前的网络状态：优先使用快照，若无快照则尝试直接清空守卫链。
    private fun restoreInternal() {
        clearGuardLocked()
    }

    private fun clearGuardLocked(): Boolean {
        val removed4 = tearDownGuard("iptables")
        val removed6 = tearDownGuard("ip6tables")
        if (removed4 || removed6) {
            Log.i(TAG, "Cleared guard chains (ipv4=$removed4 ipv6=$removed6)")
        } else if (active) {
            Log.w(TAG, "Guard marked active but clearing chains reported false")
        } else {
            Log.i(TAG, "No guard chains found to clear")
        }
        targetUid = -1
        targetPackageName = null
        extraPackages = emptySet()
        processUids = emptySet()
        hostUid = -1
        active = false
        return removed4 || removed6
    }

    // 发送内部广播，让 UI 与其他组件感知隔离状态变化。
    private fun notifyStateChangedLocked() {
        val ctx = appContext ?: return
        try {
            val intent = Intent(ACTION_STATE_CHANGED).apply {
                putExtra(EXTRA_ACTIVE, active)
                putExtra(EXTRA_TARGET_UID, targetUid)
                putExtra(EXTRA_TARGET_PACKAGE, targetPackageName)
            }
            ctx.sendBroadcast(intent)
        } catch (t: Throwable) {
            Log.w(TAG, "Failed to broadcast network isolation state: ${t.message}", t)
        }
    }

    // 优先通过系统 API 解析 UID，失败时降级到 shell 查询。
    private fun resolveUid(context: Context, pkg: String): Int? {
        return try {
            context.packageManager.getApplicationInfo(pkg, PackageManager.ApplicationInfoFlags.of(0)).uid
        } catch (primary: Throwable) {
            Log.w(TAG, "PackageManager lookup failed for pkg=$pkg: ${primary.message}")
            resolveUidViaShell(pkg)
        }
    }

    private fun resolveUidViaShell(pkg: String): Int? {
        // 先尝试 pm list packages -U，可直接拿到 uid 字段。
        val pmCmd = "pm list packages -U $pkg"
        val listOut = runShellForOutput(pmCmd)
        val uid = listOut?.lineSequence()
            ?.firstOrNull { it.contains("uid:") && it.contains(pkg) }
            ?.let { line -> Regex("uid:(\\d+)").find(line)?.groupValues?.getOrNull(1)?.toIntOrNull() }
        if (uid != null) {
            Log.i(TAG, "resolveUidViaShell using '$pmCmd' -> $uid")
            return uid
        }

        // 如果 pm 命令不可用，再查询 dumpsys package 结果。
        val dumpOut = runShellForOutput("dumpsys package $pkg")
        val dumpUid = dumpOut?.lineSequence()
            ?.firstOrNull { it.contains("userId=") }
            ?.let { line -> Regex("userId=(\\d+)").find(line)?.groupValues?.getOrNull(1)?.toIntOrNull() }
        if (dumpUid != null) {
            Log.i(TAG, "resolveUidViaShell using dumpsys -> $dumpUid")
            return dumpUid
        }

        Log.e(TAG, "resolveUidViaShell failed for pkg=$pkg (pm=$listOut dump=${dumpOut?.take(80)})")
        return null
    }

    private fun resolveProcessUids(
        packagePrefixes: Set<String>,
        extraProcessNames: Set<String>
    ): Set<Int>? {
        if (packagePrefixes.isEmpty() && extraProcessNames.isEmpty()) return emptySet()
        val output = runShellForOutput("ps -A -o UID,NAME") ?: return null
        val colonPrefixes = packagePrefixes.map { "$it:" }.toSet()
        val dotPrefixes = packagePrefixes.map { "$it." }.toSet()
        return output.lineSequence()
            .mapNotNull { line ->
                val trimmed = line.trim()
                if (trimmed.isEmpty() || trimmed.startsWith("UID")) return@mapNotNull null
                val parts = trimmed.split(Regex("\\s+"), limit = 2)
                if (parts.size < 2) return@mapNotNull null
                val uid = parts[0].toIntOrNull() ?: return@mapNotNull null
                val name = parts[1]
                val matchPrefix = packagePrefixes.any { name == it } ||
                    colonPrefixes.any { name.startsWith(it) } ||
                    dotPrefixes.any { name.startsWith(it) }
                val matchExtra = extraProcessNames.contains(name)
                if (matchPrefix || matchExtra) uid else null
            }
            .toSet()
    }

    // 调用 su -c 执行命令并返回标准输出，失败时打印错误日志。
    private fun runShellForOutput(cmd: String): String? = try {
        val proc = Runtime.getRuntime().exec(arrayOf("su", "-c", cmd))
        val out = proc.inputStream.bufferedReader().use { it.readText() }
        val err = proc.errorStream.bufferedReader().use { it.readText() }
        val rc = proc.waitFor()
        if (rc == 0) {
            out
        } else {
            Log.w(TAG, "runShellForOutput cmd='$cmd' rc=$rc err=$err")
            null
        }
    } catch (t: Throwable) {
        Log.e(TAG, "runShellForOutput cmd='$cmd' error: ${t.message}", t)
        null
    }

    private fun captureTable(cmd: String): String? = try {
        val proc = Runtime.getRuntime().exec(arrayOf("su", "-c", cmd))
        val out = proc.inputStream.bufferedReader().use { it.readText() }
        val rc = proc.waitFor()
        if (rc == 0) out else {
            val err = proc.errorStream.bufferedReader().use { it.readText() }
            Log.e(TAG, "Command $cmd failed rc=$rc err=$err")
            null
        }
    } catch (t: Throwable) {
        Log.e(TAG, "captureTable($cmd) error: ${t.message}", t)
        null
    }

    private fun applyGuard(target: Int, host: Int, extraUids: Set<Int>, includeIpv6: Boolean): Boolean {
        // 允许列表：目标应用 + 当前 App + root/system UID。
        val allowedUids = buildSet {
            add(target)
            add(host)
            add(0)      // root
            add(1000)   // system
            addAll(extraUids)
        }

        // 拼接 shell 命令，逐步创建/附加守卫链。
        val script = buildList {
            add("iptables -w -N $GUARD_CHAIN >/dev/null 2>&1 || true")
            add("iptables -w -F $GUARD_CHAIN >/dev/null 2>&1 || true")
            add("iptables -w -C OUTPUT -j $GUARD_CHAIN >/dev/null 2>&1 || iptables -w -I OUTPUT 1 -j $GUARD_CHAIN")
            allowedUids.forEach { uid ->
                add("iptables -w -A $GUARD_CHAIN -m owner --uid-owner $uid -j RETURN")
            }
            add("iptables -w -A $GUARD_CHAIN -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN >/dev/null 2>&1 || true")
            add("iptables -w -A $GUARD_CHAIN -j REJECT")

            if (includeIpv6) {
                add("ip6tables -w -N $GUARD_CHAIN >/dev/null 2>&1 || true")
                add("ip6tables -w -F $GUARD_CHAIN >/dev/null 2>&1 || true")
                add("ip6tables -w -C OUTPUT -j $GUARD_CHAIN >/dev/null 2>&1 || ip6tables -w -I OUTPUT 1 -j $GUARD_CHAIN >/dev/null 2>&1 || true")
                allowedUids.forEach { uid ->
                    add("ip6tables -w -A $GUARD_CHAIN -m owner --uid-owner $uid -j RETURN >/dev/null 2>&1 || true")
                }
                add("ip6tables -w -A $GUARD_CHAIN -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN >/dev/null 2>&1 || true")
                add("ip6tables -w -A $GUARD_CHAIN -j REJECT >/dev/null 2>&1 || true")
            }
        }

        return runScript(script)
    }

    private fun tearDownGuard(prefix: String): Boolean {
        // 无论链是否存在，都尝试删除相关规则，确保清理干净。
        val script = listOf(
            "$prefix -w -D OUTPUT -j $GUARD_CHAIN >/dev/null 2>&1 || true",
            "$prefix -w -F $GUARD_CHAIN >/dev/null 2>&1 || true",
            "$prefix -w -X $GUARD_CHAIN >/dev/null 2>&1 || true"
        )
        return runScript(script)
    }

    // 将多条命令串联成一条 shell 调用，执行成功返回 true。
    private fun runScript(lines: List<String>): Boolean {
        val script = lines.joinToString(" ; ")
        return try {
            val proc = Runtime.getRuntime().exec(arrayOf("su", "-c", script))
            val rc = proc.waitFor()
            if (rc != 0) {
                val err = proc.errorStream.bufferedReader().use { it.readText() }
                Log.e(TAG, "runScript failed rc=$rc err=$err script=$script")
            }
            rc == 0
        } catch (t: Throwable) {
            Log.e(TAG, "runScript error: ${t.message}", t)
            false
        }
    }
}
