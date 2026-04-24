package com.example.autoa11y.engine

import android.util.Log
import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.Condition
import com.example.autoa11y.core.api.Driver
import com.example.autoa11y.core.api.Interceptor
import com.example.autoa11y.core.api.ResolveCode
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.TargetAppProfile
import com.example.autoa11y.drivers.shell.ShellBridge
import com.example.autoa11y.monitor.RunLogger

/**
 * 按时间预算执行自动化循环，完成启动、调度与日志记录。
 */
class TimeBoxedRunner(
    private val driver: Driver,
    private val fallback: Driver,
    private val profile: TargetAppProfile,
    private val logger: RunLogger,
    private val appStarter: () -> Unit,
    private val appKiller: () -> Unit,
    private val isAlive: () -> Boolean = { true },
    private val observer: ExecutionObserver? = null
) {
    private var lastForegroundCheck: Long = 0L
    private var homeComponentOverride: String? = null
    private var lastKnownComponent: String? = null

    /**
     * 执行单次循环，限制总用时不超过 [budgetMs] 毫秒。
     */
    fun runLoop(index: Int, budgetMs: Long) {
        val begin = System.currentTimeMillis()
        val deadline = begin + budgetMs
        logger.logLoopStart(index, begin)

        var completed = false
        var okHome = false
        val baseAlive: () -> Boolean = { isAlive() }
        val withinBudget: () -> Boolean = { System.currentTimeMillis() < deadline }
        val execAlive: () -> Boolean = { baseAlive() && withinBudget() }
        val idleSleepMs = 450L
        try {
            appStarter.invoke()
            resolveHomeComponent()
            // 启动后先做一次前台收敛，避免“目标 App 尚未置前/被覆盖”时误判并直接中止 scenario。
            ensureForegroundActive()

            val driverChain = DriverChain(driver, fallback)
            val exec = ScenarioExecutor(
                driver = driverChain,
                interceptors = profile.globalInterceptors,
                profile = profile,
                homeComponentProvider = { homeComponentOverride ?: profile.homeActivityComponent ?: lastKnownComponent },
                foregroundGuard = ::ensureForegroundActive,
                isAlive = { execAlive() },
                observer = observer
            )
            val session = profile.behavior.beginSession()

            scenarioLoop@while (baseAlive()) {
                if (!withinBudget()) {
                    completed = true
                    break
                }
                val elapsed = System.currentTimeMillis() - begin
                val timeLeft = budgetMs - elapsed
                if (timeLeft <= 0) {
                    completed = true
                    break
                }

                // 持续校验/恢复前台与 Home，不满足时只 idle，不提前结束 loop
                ensureForegroundActive()
                if (!okHome) {
                    okHome = profile.homeSignature.must.firstOrNull()?.let {
                        driver.waitVisible(it, 1_500)
                    } ?: true
                    if (!okHome) {
                        Thread.sleep(if (timeLeft < idleSleepMs) timeLeft else idleSleepMs)
                        continue@scenarioLoop
                    }
                }

                val scenario = session.nextSnippet(timeLeft)
                if (scenario == null) {
                    Thread.sleep(if (timeLeft < idleSleepMs) timeLeft else idleSleepMs)
                    continue@scenarioLoop
                }

                Log.d("TimeBoxedRunner", "loop index=$index executing scenario=${scenario.id} timeLeft=$timeLeft")
                val finished = exec.run(scenario)
                if (!finished) {
                    val elapsedAfter = System.currentTimeMillis() - begin
                    val timeLeftAfter = budgetMs - elapsedAfter
                    if (timeLeftAfter <= 0 || !withinBudget()) {
                        completed = true
                        break
                    }
                    val recoveryReason = exec.consumeRestartRequest()
                    val reason = recoveryReason ?: "scenario_aborted"
                    Log.i(
                        "TimeBoxedRunner",
                        "recovery requested scenario=${scenario.id} reason=$reason"
                    )
                    val recovery = session.recoverySnippet(reason, timeLeftAfter)
                    if (recovery != null) {
                        exec.run(recovery)
                    }
                    Thread.sleep(if (timeLeftAfter < idleSleepMs) timeLeftAfter else idleSleepMs)
                    continue@scenarioLoop
                }
            }
        } finally {
            if (!completed) {
                val elapsed = System.currentTimeMillis() - begin
                Log.w(
                    "TimeBoxedRunner",
                    "loop incomplete index=$index okHome=$okHome alive=${isAlive()} elapsed=$elapsed budget=$budgetMs"
                )
            }
            val end = System.currentTimeMillis()
            logger.logLoopEnd(index, begin, end, ok = completed)

            try {
                appKiller.invoke()
            } catch (t: Throwable) {
                Log.w("TimeBoxedRunner", "appKiller invoke failed: ${t.message}", t)
            }
        }
    }

    private fun resolveHomeComponent() {
        if (homeComponentOverride != null) return
        try {
            // 不要在启动后固定等待太久：过长的 sleep 会导致“启动 App 后长时间无动作”的观感。
            // 这里保留一个很短的缓冲，让前台 Activity 更稳定，但尽量不拖慢首个动作触发。
            Thread.sleep(500)
        } catch (_: InterruptedException) {
        }
        val detected = ForegroundActivityInspector.currentComponent()
        val pkgHints = listOf(profile.packageName, profile.homeSignature.pkg).distinct()
        if (detected != null && pkgHints.any { detected.contains(it) }) {
            homeComponentOverride = detected
            lastKnownComponent = detected
            Log.i("TimeBoxedRunner", "Detected home activity component=$detected")
        } else if (detected != null) {
            Log.w("TimeBoxedRunner", "Ignore detected component(not in target): $detected")
        } else if (profile.homeActivityComponent != null) {
            homeComponentOverride = profile.homeActivityComponent
            lastKnownComponent = profile.homeActivityComponent
            Log.i("TimeBoxedRunner", "Fallback to profile home activity ${profile.homeActivityComponent}")
        } else {
            Log.w("TimeBoxedRunner", "Unable to detect home activity component automatically")
        }
    }

    private fun ensureForegroundActive(): Boolean {
        // 检查间隔：缩短为 2s，确保误退到桌面时能快速拉起目标 App
        val interval = 2_000L
        val now = System.currentTimeMillis()
        if (now - lastForegroundCheck < interval) return true
        lastForegroundCheck = now
        val component = ForegroundActivityInspector.currentComponent()
        if (component != null) {
            lastKnownComponent = component
        }
        if (component == null) {
            Log.w("TimeBoxedRunner", "foreground check failed (component=null); assume still in ${profile.packageName}")
            return true
        }
        val pkgHints = listOf(profile.packageName, profile.homeSignature.pkg).distinct()
        val inApp = pkgHints.any { component.contains(it) }
        Log.d("TimeBoxedRunner", "foreground check component=$component inApp=$inApp")
        if (!inApp) {
            Log.w("TimeBoxedRunner", "foreground lost component=$component, relaunching ${profile.packageName}")
            try {
                appStarter.invoke()
            } catch (t: Throwable) {
                Log.e("TimeBoxedRunner", "relaunch failed: ${t.message}", t)
            }
            // 启动是异步的：这里给一点时间让目标 App 置前，避免 scenario 立刻被判定为“前台丢失”而中止。
            val deadline = System.currentTimeMillis() + 2_000L
            while (System.currentTimeMillis() < deadline) {
                try {
                    Thread.sleep(250L)
                } catch (_: InterruptedException) {
                }
                val componentNow = ForegroundActivityInspector.currentComponent()
                if (componentNow != null) {
                    lastKnownComponent = componentNow
                    val ok = pkgHints.any { componentNow.contains(it) }
                    if (ok) {
                        Log.i("TimeBoxedRunner", "foreground recovered component=$componentNow")
                        return true
                    }
                }
            }
        }
        return inApp
    }
}

/**
 * 场景执行器：逐步消费 Scenario 的步骤，并在每步前执行全局拦截。
 */
class ScenarioExecutor(
    private val driver: Driver,
    private val interceptors: List<Interceptor>,
    private val profile: TargetAppProfile,
    private val homeComponentProvider: () -> String?,
    private val foregroundGuard: () -> Boolean,
    private val isAlive: () -> Boolean,
    private val currentComponentProvider: () -> String? = { ForegroundActivityInspector.currentComponent() },
    private val observer: ExecutionObserver? = null
) {
    private val tag = "ScenarioExecutor"
    private val pageResolver = KnownPageResolver(driver, profile.knownPages)
    private val shell = ShellBridge()
    private val unknownStateRecovery = profile.unknownStateRecoveryPolicy
    private var restartRequested = false
    private var restartReason: String? = null

    fun consumeRestartRequest(): String? = restartReason.also {
        restartRequested = false
        restartReason = null
    }

    fun run(s: Scenario): Boolean {
        val scenarioId = s.id
        observer?.onScenarioStart(s)
        for ((stepIndex, step) in s.steps.withIndex()) {
            if (!isAlive()) return false
            if (!foregroundGuard()) {
                restartRequested = true
                restartReason = "foreground_lost"
                observer?.onScenarioEnd(s, completed = false, restartReason = restartReason)
                return false
            }
            if (!recoverUnknownStateIfNeeded("before_step", scenarioId, stepIndex, null)) {
                observer?.onScenarioEnd(s, completed = false, restartReason = restartReason)
                return false
            }

            val requireOk = checkCondition(step.require)
            if (!requireOk) {
                Log.d(tag, "skip step=$stepIndex require not satisfied scenario=$scenarioId")
                observer?.onStepSkipped(s, stepIndex, step, "require_not_satisfied")
                continue
            }

            observer?.onStepStart(s, stepIndex, step)
            Log.d(tag, "step start scenario=$scenarioId step=$stepIndex actions=${step.actions.size}")
            var acted: Boolean
            var rounds = 0
            do {
                acted = false
                val roundIndex = rounds
                for (itc in interceptors) {
                    if (itc.tryIntercept(driver)) {
                        acted = true
                        Log.d(tag, "interceptor=${itc.javaClass.simpleName} acted scenario=$scenarioId step=$stepIndex round=$roundIndex")
                    }
                }
                rounds++
            } while (acted && rounds < 3)

            for ((actionIndex, action) in step.actions.withIndex()) {
                if (!isAlive()) return false
                if (!foregroundGuard()) {
                    restartRequested = true
                    restartReason = "foreground_lost"
                    observer?.onScenarioEnd(s, completed = false, restartReason = restartReason)
                    return false
                }
                if (!recoverUnknownStateIfNeeded("before_action", scenarioId, stepIndex, actionIndex)) {
                    observer?.onScenarioEnd(s, completed = false, restartReason = restartReason)
                    return false
                }
                observer?.onActionStart(s, stepIndex, actionIndex, action)
                val report = exec(action, scenarioId, stepIndex, actionIndex)
                observer?.onActionEnd(s, stepIndex, actionIndex, action, report)
                if (restartRequested) {
                    Log.w(tag, "recovery requested scenario=$scenarioId reason=$restartReason")
                    observer?.onStepEnd(s, stepIndex, step, completed = false)
                    observer?.onScenarioEnd(s, completed = false, restartReason = restartReason)
                    return false
                }
            }
            observer?.onStepEnd(s, stepIndex, step, completed = true)
        }
        observer?.onScenarioEnd(s, completed = true, restartReason = null)
        return true
    }

    private fun recoverUnknownStateIfNeeded(
        phase: String,
        scenarioId: String,
        stepIndex: Int,
        actionIndex: Int?
    ): Boolean {
        if (!unknownStateRecovery.enabled || profile.knownPages.isEmpty()) {
            return true
        }

        val currentKnown = pageResolver.resolveCurrentPage()
        if (currentKnown != null) {
            return true
        }

        val component = currentComponentProvider()
        if (!isTargetAppComponent(component)) {
            return true
        }

        val recovered = backOutToKnownPage(
            maxBacks = unknownStateRecovery.maxBacks,
            settleDelayMs = unknownStateRecovery.settleDelayMs,
            scenarioId = scenarioId,
            stepIndex = stepIndex,
            actionIndex = actionIndex,
            reason = "unknown_state_$phase"
        )
        if (recovered != null) {
            Log.i(
                tag,
                "unknown state recovered page=${recovered.id} scenario=$scenarioId step=$stepIndex index=$actionIndex phase=$phase"
            )
            return true
        }

        restartRequested = true
        restartReason = "unknown_state_unresolved"
        Log.w(
            tag,
            "unknown state unresolved scenario=$scenarioId step=$stepIndex index=$actionIndex phase=$phase"
        )
        return false
    }

    private fun exec(action: Action, scenarioId: String, stepIndex: Int, actionIndex: Int): ActionExecutionReport {
        return when (action) {
            is Action.Log -> {
                Log.i(tag, "action=Log scenario=$scenarioId step=$stepIndex index=$actionIndex message=${action.message}")
                ActionExecutionReport.success(action.message)
            }
            is Action.Click -> {
                Log.d(tag, "action=Click scenario=$scenarioId step=$stepIndex index=$actionIndex selector=${action.sel}")
                var result = driver.clickResolved(action.sel)
                if (!result.ok && result.resolve?.code != ResolveCode.NOT_CLICKABLE) {
                    // 第一次失败且非 NOT_CLICKABLE（那种 fallback 也无用）时立即重试
                    result = driver.clickResolved(action.sel)
                }
                if (!result.ok && result.resolve?.code != ResolveCode.NOT_CLICKABLE) {
                    Log.w(tag, "click miss[$actionIndex] code=${result.resolve?.code} reason=${result.resolve?.reason} " +
                        "scenario=$scenarioId step=$stepIndex selector=${action.sel}; retrying with delay")
                    Thread.sleep(250)
                    result = driver.clickResolved(action.sel)
                    if (!result.ok) {
                        Log.w(tag, "click final miss code=${result.resolve?.code} reason=${result.resolve?.reason} " +
                            "scenario=$scenarioId step=$stepIndex selector=${action.sel}")
                    }
                }
                if (result.ok) {
                    ActionExecutionReport.success("click_ok")
                } else {
                    ActionExecutionReport.failure(
                        resolveCode = result.resolve?.code,
                        detail = result.resolve?.reason ?: "click_failed"
                    )
                }
            }
            is Action.SmartClick -> {
                Log.d(
                    tag,
                    "action=SmartClick scenario=$scenarioId step=$stepIndex index=$actionIndex " +
                        "trigger=${action.trigger} expected=${action.expectedMarker} timeout=${action.timeoutMs} settle=${action.settleDelayMs}"
                )
                val clickResult = driver.clickResolved(action.trigger)
                if (!clickResult.ok) {
                    Log.w(
                        tag,
                        "smartClick trigger failed code=${clickResult.resolve?.code} reason=${clickResult.resolve?.reason} " +
                            "scenario=$scenarioId step=$stepIndex index=$actionIndex trigger=${action.trigger}"
                    )
                    ActionExecutionReport.failure(
                        resolveCode = clickResult.resolve?.code,
                        detail = clickResult.resolve?.reason ?: "smart_click_trigger_failed"
                    )
                } else {
                    if (action.settleDelayMs > 0) {
                        Thread.sleep(action.settleDelayMs)
                    }

                    val verifyResult = driver.waitVisibleResolved(action.expectedMarker, action.timeoutMs)
                    if (!verifyResult.ok) {
                        Log.w(
                            tag,
                            "smartClick verify failed code=${verifyResult.resolve?.code} reason=${verifyResult.resolve?.reason} " +
                                "scenario=$scenarioId step=$stepIndex index=$actionIndex expected=${action.expectedMarker} timeout=${action.timeoutMs}"
                        )
                        ActionExecutionReport.failure(
                            resolveCode = verifyResult.resolve?.code,
                            detail = verifyResult.resolve?.reason ?: "smart_click_verify_failed"
                        )
                    } else {
                        ActionExecutionReport.success("smart_click_ok")
                    }
                }
            }
            is Action.Navigate -> {
                execNavigate(action, scenarioId, stepIndex, actionIndex)
            }
            is Action.Input -> {
                Log.d(tag, "action=Input scenario=$scenarioId step=$stepIndex index=$actionIndex selector=${action.sel} clear=${action.clearFirst}")
                val result = driver.inputResolved(action.sel, action.text, action.clearFirst)
                if (!result.ok) {
                    Log.w(
                        tag,
                        "input failed code=${result.resolve?.code} reason=${result.resolve?.reason} " +
                            "scenario=$scenarioId step=$stepIndex index=$actionIndex selector=${action.sel}"
                    )
                }
                if (result.ok) {
                    ActionExecutionReport.success("input_ok")
                } else {
                    ActionExecutionReport.failure(
                        resolveCode = result.resolve?.code,
                        detail = result.resolve?.reason ?: "input_failed"
                    )
                }
            }
            is Action.Wait -> {
                Log.d(tag, "action=Wait scenario=$scenarioId step=$stepIndex index=$actionIndex selector=${action.sel} timeout=${action.timeoutMs}")
                val result = driver.waitVisibleResolved(action.sel, action.timeoutMs)
                if (!result.ok) {
                    Log.w(
                        tag,
                        "wait failed code=${result.resolve?.code} reason=${result.resolve?.reason} " +
                            "scenario=$scenarioId step=$stepIndex index=$actionIndex selector=${action.sel} timeout=${action.timeoutMs}"
                    )
                }
                if (result.ok) {
                    ActionExecutionReport.success("wait_ok")
                } else {
                    ActionExecutionReport.failure(
                        resolveCode = result.resolve?.code,
                        detail = result.resolve?.reason ?: "wait_failed"
                    )
                }
            }
            is Action.CleanupDownloadArtifacts -> {
                execCleanupDownloadArtifacts(action, scenarioId, stepIndex, actionIndex)
            }
            is Action.WaitForDownloadArtifact -> {
                execWaitForDownloadArtifact(action, scenarioId, stepIndex, actionIndex)
            }
            is Action.WaitForDownloadStart -> {
                execWaitForDownloadStart(action, scenarioId, stepIndex, actionIndex)
            }
            is Action.Scroll -> {
                Log.d(tag, "action=Scroll scenario=$scenarioId step=$stepIndex index=$actionIndex times=${action.times} dir=${action.direction}")
                val ok = driver.scroll(action.times, action.direction)
                if (!ok) {
                    Log.w(tag, "scroll failed scenario=$scenarioId step=$stepIndex index=$actionIndex times=${action.times} dir=${action.direction}")
                }
                if (ok) ActionExecutionReport.success("scroll_ok")
                else ActionExecutionReport.failure(detail = "scroll_failed")
            }
            is Action.Swipe -> {
                Log.d(tag, "action=Swipe scenario=$scenarioId step=$stepIndex index=$actionIndex from=(${action.fromX},${action.fromY}) to=(${action.toX},${action.toY}) duration=${action.durationMs}")
                val ok = driver.swipe(action.fromX, action.fromY, action.toX, action.toY, action.durationMs)
                if (!ok) {
                    Log.w(tag, "swipe failed scenario=$scenarioId step=$stepIndex index=$actionIndex")
                }
                if (ok) ActionExecutionReport.success("swipe_ok")
                else ActionExecutionReport.failure(detail = "swipe_failed")
            }
            is Action.Sleep -> {
                Log.d(tag, "action=Sleep scenario=$scenarioId step=$stepIndex index=$actionIndex ms=${action.ms}")
                Thread.sleep(action.ms)
                ActionExecutionReport.success("sleep_ok")
            }
            Action.Back -> {
                Log.i(tag, "action=Back scenario=$scenarioId step=$stepIndex index=$actionIndex")
                val homeComponent = homeComponentProvider()
                val skip = homeComponent?.let { component ->
                    ForegroundActivityInspector.isOnComponent(component)
                } ?: false
                if (skip) {
                    Log.i(tag, "skip back because current focus matches $homeComponent")
                    ActionExecutionReport.success("back_skipped_on_home")
                } else {
                    val ok = driver.back()
                    if (!ok) {
                        Log.w(tag, "back failed scenario=$scenarioId step=$stepIndex index=$actionIndex")
                    }
                    if (ok) ActionExecutionReport.success("back_ok")
                    else ActionExecutionReport.failure(detail = "back_failed")
                }
            }
            Action.BackForce -> {
                Log.i(tag, "action=BackForce scenario=$scenarioId step=$stepIndex index=$actionIndex")
                val ok = driver.back()
                if (!ok) {
                    Log.w(tag, "backForce failed scenario=$scenarioId step=$stepIndex index=$actionIndex")
                }
                if (ok) ActionExecutionReport.success("back_force_ok")
                else ActionExecutionReport.failure(detail = "back_force_failed")
            }
            is Action.RequestRestart -> {
                restartRequested = true
                restartReason = action.reason
                Log.w(
                    tag,
                    "action=RequestRestart scenario=$scenarioId step=$stepIndex index=$actionIndex reason=${action.reason}"
                )
                ActionExecutionReport.failure(
                    detail = action.reason,
                    requestedRestart = true
                )
            }
        }
    }

    private fun execCleanupDownloadArtifacts(
        action: Action.CleanupDownloadArtifacts,
        scenarioId: String,
        stepIndex: Int,
        actionIndex: Int
    ): ActionExecutionReport {
        val existing = shell.listFileNames(action.downloadDir)
        if (action.deleteAll) {
            if (existing.isEmpty()) {
                Log.i(
                    tag,
                    "cleanup all download artifacts no-op scenario=$scenarioId step=$stepIndex index=$actionIndex dir=${action.downloadDir}"
                )
                return ActionExecutionReport.success("cleanup_noop")
            }
            var deleted = 0
            for (name in existing) {
                val ok = shell.removeFile("${action.downloadDir}/$name")
                if (ok) {
                    deleted++
                } else {
                    Log.w(
                        tag,
                        "cleanup delete failed scenario=$scenarioId step=$stepIndex index=$actionIndex file=$name dir=${action.downloadDir}"
                    )
                }
            }
            Log.i(
                tag,
                "cleanup all download artifacts deleted=$deleted listed=${existing.size} scenario=$scenarioId step=$stepIndex index=$actionIndex dir=${action.downloadDir}"
            )
            return ActionExecutionReport.success("cleanup_deleted=$deleted")
        }
        val matches = DownloadArtifacts.findMatches(existing, action.baseNames)
        if (matches.isEmpty()) {
            Log.i(
                tag,
                "cleanup download artifacts no-op scenario=$scenarioId step=$stepIndex index=$actionIndex dir=${action.downloadDir}"
            )
            return ActionExecutionReport.success("cleanup_noop")
        }

        var deleted = 0
        for (name in matches) {
            val ok = shell.removeFile("${action.downloadDir}/$name")
            if (ok) {
                deleted++
            } else {
                Log.w(
                    tag,
                    "cleanup delete failed scenario=$scenarioId step=$stepIndex index=$actionIndex file=$name dir=${action.downloadDir}"
                )
            }
        }
        Log.i(
            tag,
            "cleanup download artifacts deleted=$deleted matched=${matches.size} scenario=$scenarioId step=$stepIndex index=$actionIndex dir=${action.downloadDir}"
        )
        return ActionExecutionReport.success("cleanup_deleted=$deleted")
    }

    private fun execWaitForDownloadArtifact(
        action: Action.WaitForDownloadArtifact,
        scenarioId: String,
        stepIndex: Int,
        actionIndex: Int
    ): ActionExecutionReport {
        Log.d(
            tag,
            "action=WaitForDownloadArtifact scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} timeout=${action.timeoutMs} poll=${action.pollIntervalMs}"
        )
        val monitor = action.progressMonitor
        var deadline = System.currentTimeMillis() + action.timeoutMs
        var lastProgressCheckAt = System.currentTimeMillis()
        var lastProgressAt = lastProgressCheckAt
        var lastInterfaceRx = monitor?.let { shell.readInterfaceRxBytes(it.interfaceName) }
        while (isAlive()) {
            val now = System.currentTimeMillis()
            if (monitor == null && now >= deadline) {
                break
            }
            if (monitor != null && now - lastProgressAt >= monitor.idleTimeoutMs) {
                break
            }
            val existing = shell.listFileNames(action.downloadDir)
            val matches = DownloadArtifacts.findMatches(existing, action.baseName)
            if (matches.isNotEmpty()) {
                Log.i(
                    tag,
                    "download artifact detected scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} matched=${matches.joinToString()}"
                )
                return ActionExecutionReport.success("download_artifact_detected")
            }
            if (monitor != null) {
                if (now - lastProgressCheckAt >= monitor.checkIntervalMs) {
                    val currentRx = shell.readInterfaceRxBytes(monitor.interfaceName)
                    if (currentRx != null && lastInterfaceRx != null) {
                        val deltaRx = (currentRx - lastInterfaceRx).coerceAtLeast(0L)
                        if (deltaRx >= monitor.minRxBytesPerCheck) {
                            lastProgressAt = now
                            Log.i(
                                tag,
                                "download recheck_active scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} iface=${monitor.interfaceName} deltaRx=$deltaRx nextIdleDeadline=${now + monitor.idleTimeoutMs}"
                            )
                        } else {
                            Log.i(
                                tag,
                                "download recheck_idle scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} iface=${monitor.interfaceName} deltaRx=$deltaRx idleFor=${now - lastProgressAt}"
                            )
                        }
                    } else {
                        Log.w(
                            tag,
                            "download recheck_unavailable scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} iface=${monitor.interfaceName}"
                        )
                    }
                    lastInterfaceRx = currentRx
                    lastProgressCheckAt = now
                }
            }
            Thread.sleep(action.pollIntervalMs.coerceAtLeast(250L))
        }
        val reason = action.restartReason ?: "download artifact timeout base=${action.baseName}"
        restartRequested = true
        restartReason = reason
        Log.w(
            tag,
            "download artifact timeout scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} reason=$reason"
        )
        return ActionExecutionReport.failure(detail = reason, requestedRestart = true)
    }

    private fun execWaitForDownloadStart(
        action: Action.WaitForDownloadStart,
        scenarioId: String,
        stepIndex: Int,
        actionIndex: Int
    ): ActionExecutionReport {
        Log.d(
            tag,
            "action=WaitForDownloadStart scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} iface=${action.interfaceName} timeout=${action.timeoutMs} sample=${action.sampleIntervalMs}"
        )

        val existingAtStart = shell.listFileNames(action.downloadDir)
        val initialMatches = DownloadArtifacts.findMatches(existingAtStart, action.baseName)
        if (initialMatches.isNotEmpty()) {
            Log.i(
                tag,
                "download start detected by existing artifact scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} matched=${initialMatches.joinToString()}"
            )
            return ActionExecutionReport.success("download_start_detected_by_artifact")
        }

        val initialRx = shell.readInterfaceRxBytes(action.interfaceName)
        if (initialRx == null) {
            Log.w(
                tag,
                "download start detect unavailable interfaceUnsupported scenario=$scenarioId step=$stepIndex index=$actionIndex iface=${action.interfaceName}"
            )
            return ActionExecutionReport.failure(detail = "download_interface_unavailable")
        }

        val initialRxValue: Long = initialRx
        var previous: Long = initialRxValue
        var sustainedCount = 0
        val deadline = System.currentTimeMillis() + action.timeoutMs
        while (System.currentTimeMillis() < deadline) {
            Thread.sleep(action.sampleIntervalMs.coerceAtLeast(500L))

            val existing = shell.listFileNames(action.downloadDir)
            val matches = DownloadArtifacts.findMatches(existing, action.baseName)
            if (matches.isNotEmpty()) {
                Log.i(
                    tag,
                    "download start detected by artifact scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} matched=${matches.joinToString()}"
                )
                return ActionExecutionReport.success("download_start_detected_by_artifact")
            }

            val current = shell.readInterfaceRxBytes(action.interfaceName)
            if (current == null) {
                Log.w(
                    tag,
                    "download start detect interrupted interfaceUnsupported scenario=$scenarioId step=$stepIndex index=$actionIndex iface=${action.interfaceName}"
                )
                return ActionExecutionReport.failure(detail = "download_interface_interrupted")
            }

            val currentRx: Long = current
            val deltaRx = (currentRx - previous).coerceAtLeast(0L)
            val cumulativeRx = (currentRx - initialRxValue).coerceAtLeast(0L)
            Log.i(
                tag,
                "download start sample scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} iface=${action.interfaceName} deltaRx=$deltaRx cumulativeRx=$cumulativeRx"
            )

            sustainedCount = if (deltaRx >= action.sustainedRxBytes) sustainedCount + 1 else 0
            val started = deltaRx >= action.strongRxBytes ||
                sustainedCount >= action.sustainedWindows ||
                cumulativeRx >= action.cumulativeRxBytes
            if (started) {
                Log.i(
                    tag,
                    "download start confirmed scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} iface=${action.interfaceName} cumulativeRx=$cumulativeRx sustainedCount=$sustainedCount"
                )
                return ActionExecutionReport.success("download_start_confirmed")
            }

            previous = currentRx
        }

        val reason = action.restartReason ?: "drive download not started file=${action.baseName}"
        restartRequested = true
        restartReason = reason
        Log.w(
            tag,
            "download start timeout scenario=$scenarioId step=$stepIndex index=$actionIndex base=${action.baseName} reason=$reason"
        )
        return ActionExecutionReport.failure(detail = reason, requestedRestart = true)
    }

    private fun execNavigate(
        action: Action.Navigate,
        scenarioId: String,
        stepIndex: Int,
        actionIndex: Int
    ): ActionExecutionReport {
        val attempts = action.maxAttempts.coerceAtLeast(1)
        for (attempt in 1..attempts) {
            val trigger = if (attempt == 1) action.trigger else (action.fallbackTrigger ?: action.trigger)
            Log.d(
                tag,
                "action=Navigate scenario=$scenarioId step=$stepIndex index=$actionIndex " +
                    "attempt=$attempt/$attempts trigger=$trigger source=${action.sourcePageId} expected=${action.expectedPageId}"
            )

            val clickResult = driver.clickResolved(trigger)
            if (!clickResult.ok) {
                Log.w(
                    tag,
                    "navigate trigger failed code=${clickResult.resolve?.code} reason=${clickResult.resolve?.reason} " +
                        "scenario=$scenarioId step=$stepIndex index=$actionIndex trigger=$trigger"
                )
            }

            if (action.settleDelayMs > 0L) {
                Thread.sleep(action.settleDelayMs)
            }

            val expectedPage = pageResolver.waitForPage(action.expectedPageId, action.timeoutMs)
            if (expectedPage != null) {
                Log.i(
                    tag,
                    "navigate reached expected page=${expectedPage.id} scenario=$scenarioId step=$stepIndex index=$actionIndex"
                )
                return ActionExecutionReport.success("navigate_expected_page=${expectedPage.id}")
            }

            val currentKnown = pageResolver.resolveCurrentPage()
            if (currentKnown != null) {
                if (currentKnown.id != action.sourcePageId) {
                    Log.i(
                        tag,
                        "navigate re-synced on known page=${currentKnown.id} scenario=$scenarioId step=$stepIndex index=$actionIndex"
                    )
                    return ActionExecutionReport.success("navigate_known_page=${currentKnown.id}")
                }
                Log.w(
                    tag,
                    "navigate still on source page=${currentKnown.id} scenario=$scenarioId step=$stepIndex index=$actionIndex attempt=$attempt"
                )
                continue
            }

            val recovered = backOutToKnownPage(
                maxBacks = action.unknownBackMax,
                settleDelayMs = 500L,
                scenarioId = scenarioId,
                stepIndex = stepIndex,
                actionIndex = actionIndex,
                reason = "navigate_unknown"
            )
            if (recovered != null) {
                if (recovered.id == action.sourcePageId && attempt < attempts) {
                    Log.w(
                        tag,
                        "navigate recovered to source page=${recovered.id}, retrying scenario=$scenarioId step=$stepIndex index=$actionIndex"
                    )
                    continue
                }
                Log.i(
                    tag,
                    "navigate recovered to known page=${recovered.id} scenario=$scenarioId step=$stepIndex index=$actionIndex"
                )
                return ActionExecutionReport.success("navigate_recovered_page=${recovered.id}")
            }
        }

        restartRequested = true
        restartReason = action.restartReason
            ?: "navigate failed expected=${action.expectedPageId} source=${action.sourcePageId}"
        Log.w(
            tag,
            "navigate exhausted retries scenario=$scenarioId step=$stepIndex index=$actionIndex reason=$restartReason"
        )
        return ActionExecutionReport.failure(detail = restartReason ?: "navigate_failed", requestedRestart = true)
    }

    private fun backOutToKnownPage(
        maxBacks: Int,
        settleDelayMs: Long,
        scenarioId: String,
        stepIndex: Int,
        actionIndex: Int?,
        reason: String
    ): com.example.autoa11y.core.api.KnownPage? {
        val attempts = maxBacks.coerceAtLeast(0)
        for (i in 1..attempts) {
            Log.w(
                tag,
                "$reason backing out attempt=$i/$attempts scenario=$scenarioId step=$stepIndex index=$actionIndex"
            )
            val ok = driver.back()
            if (!ok) {
                Log.w(tag, "$reason back failed scenario=$scenarioId step=$stepIndex index=$actionIndex")
            }
            if (settleDelayMs > 0L) {
                Thread.sleep(settleDelayMs)
            }
            val known = pageResolver.resolveCurrentPage()
            if (known != null) return known
        }
        return null
    }

    private fun isTargetAppComponent(component: String?): Boolean {
        if (component.isNullOrBlank()) return false
        val pkgHints = listOf(profile.packageName, profile.homeSignature.pkg).distinct()
        return pkgHints.any { component.contains(it) }
    }

    private fun checkCondition(cond: Condition?): Boolean = when (cond) {
        null -> true
        is Condition.OnPage -> checkOnPage(cond.sig)
        is Condition.And -> cond.items.all { checkCondition(it) }
        is Condition.Not -> !checkCondition(cond.item)
    }

    private fun checkOnPage(sig: com.example.autoa11y.core.api.PageSignature): Boolean {
        // require 只用于“是否执行该 step”的轻量判定，不应引入长时间等待；
        // 对预期页面切换的操作应显式添加 Action.Wait 或 Navigate 来做校验/重同步。
        return pageResolver.matches(sig)
    }
}
