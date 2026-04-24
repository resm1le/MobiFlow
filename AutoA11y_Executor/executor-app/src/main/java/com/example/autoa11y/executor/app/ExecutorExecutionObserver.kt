package com.example.autoa11y.executor.app

import com.example.autoa11y.executor.control.RunEventDto
import com.example.autoa11y.executor.reporting.EventReporter
import com.example.autoa11y.core.api.Action
import com.example.autoa11y.core.api.Scenario
import com.example.autoa11y.core.api.Step
import com.example.autoa11y.engine.ActionExecutionReport
import com.example.autoa11y.engine.ExecutionObserver

class ExecutorExecutionObserver(
    private val attemptId: String,
    private val taskId: String,
    private val deviceId: String,
    private val runId: String,
    private val eventReporter: EventReporter
) : ExecutionObserver {
    override fun onScenarioStart(scenario: Scenario) {
        report("scenario_start", scenario.id, null, null, null, "scenario started")
    }

    override fun onScenarioEnd(scenario: Scenario, completed: Boolean, restartReason: String?) {
        report(
            "scenario_end",
            scenario.id,
            null,
            null,
            null,
            if (completed) "scenario completed" else (restartReason ?: "scenario aborted")
        )
    }

    override fun onStepStart(scenario: Scenario, stepIndex: Int, step: Step) {
        report("step_start", scenario.id, stepIndex, null, null, "step started")
    }

    override fun onStepSkipped(scenario: Scenario, stepIndex: Int, step: Step, reason: String) {
        report("step_skipped", scenario.id, stepIndex, null, null, reason)
    }

    override fun onStepEnd(scenario: Scenario, stepIndex: Int, step: Step, completed: Boolean) {
        report(
            "step_end",
            scenario.id,
            stepIndex,
            null,
            null,
            if (completed) "step completed" else "step aborted"
        )
    }

    override fun onActionStart(scenario: Scenario, stepIndex: Int, actionIndex: Int, action: Action) {
        report("action_start", scenario.id, stepIndex, actionIndex, null, action.javaClass.simpleName)
    }

    override fun onActionEnd(
        scenario: Scenario,
        stepIndex: Int,
        actionIndex: Int,
        action: Action,
        report: ActionExecutionReport
    ) {
        this.report(
            "action_end",
            scenario.id,
            stepIndex,
            actionIndex,
            report.resolveCode?.name,
            report.detail.ifBlank {
                if (report.ok) "${action.javaClass.simpleName} ok" else "${action.javaClass.simpleName} failed"
            }
        )
    }

    private fun report(
        eventType: String,
        scenarioId: String?,
        stepIndex: Int?,
        actionIndex: Int?,
        resolveCode: String?,
        message: String
    ) {
        eventReporter.reportEvent(
            event = RunEventDto(
                attemptId = attemptId,
                taskId = taskId,
                deviceId = deviceId,
                runId = runId,
                scenarioId = scenarioId,
                stepIndex = stepIndex,
                actionIndex = actionIndex,
                eventType = eventType,
                code = resolveCode,
                message = message
            )
        )
    }
}
