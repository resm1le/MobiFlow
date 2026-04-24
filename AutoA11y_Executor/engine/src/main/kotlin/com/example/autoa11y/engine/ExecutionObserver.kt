package com.example.autoa11y.engine

import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.ResolveCode
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.Step

data class ActionExecutionReport(
    val ok: Boolean,
    val resolveCode: ResolveCode? = null,
    val detail: String = "",
    val requestedRestart: Boolean = false
) {
    companion object {
        fun success(detail: String = "") = ActionExecutionReport(ok = true, detail = detail)
        fun failure(
            resolveCode: ResolveCode? = null,
            detail: String = "",
            requestedRestart: Boolean = false
        ) = ActionExecutionReport(
            ok = false,
            resolveCode = resolveCode,
            detail = detail,
            requestedRestart = requestedRestart
        )
    }
}

interface ExecutionObserver {
    fun onScenarioStart(scenario: Scenario) {}
    fun onScenarioEnd(scenario: Scenario, completed: Boolean, restartReason: String?) {}
    fun onStepStart(scenario: Scenario, stepIndex: Int, step: Step) {}
    fun onStepSkipped(scenario: Scenario, stepIndex: Int, step: Step, reason: String) {}
    fun onStepEnd(scenario: Scenario, stepIndex: Int, step: Step, completed: Boolean) {}
    fun onActionStart(scenario: Scenario, stepIndex: Int, actionIndex: Int, action: Action) {}
    fun onActionEnd(
        scenario: Scenario,
        stepIndex: Int,
        actionIndex: Int,
        action: Action,
        report: ActionExecutionReport
    ) {
    }
}
