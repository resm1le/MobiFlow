package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.RunDraftResult;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;

@Component
public class RunPlanningSemanticCanonicalizer {

    private final ObjectMapper objectMapper;

    public RunPlanningSemanticCanonicalizer(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public CanonicalRunPlanningResult canonicalize(RunDraftResult.RunDraftDto draft,
                                                   RunPlanningIntentSignals signals,
                                                   RunPlanningContext context) {
        ObjectNode runConfig = draft.runConfig().deepCopy();
        ObjectNode artifactPolicy = draft.artifactPolicy().deepCopy();
        List<String> reviewHints = new ArrayList<>();
        LinkedHashSet<String> warnings = new LinkedHashSet<>();

        String devicePoolId = draft.devicePoolId();
        if (signals.hasExplicitDevicePoolId()) {
            boolean available = context.availableDevicePools().stream()
                    .anyMatch(pool -> pool.poolId().equals(signals.devicePoolId()));
            if (available) {
                devicePoolId = signals.devicePoolId();
            } else {
                reviewHints.add("Requested devicePoolId is not currently available and requires operator review.");
            }
        }

        String profilePackage = draft.profilePackage();
        if (signals.hasExplicitProfilePackage()) {
            boolean available = context.availableProfiles().stream()
                    .anyMatch(profile -> profile.profilePackage().equals(signals.profilePackage()));
            if (available) {
                profilePackage = signals.profilePackage();
            } else {
                reviewHints.add("Requested profilePackage is not currently available and requires operator review.");
            }
        }

        String taskType = signals.hasExplicitTaskType() ? signals.taskType() : draft.taskType();
        int priority = signals.hasExplicitPriority() ? signals.priority() : draft.priority();
        if (signals.hasExplicitPriority()) {
            warnings.add("Applied explicit priority intent from goal/constraints.");
        }

        if (signals.hasExplicitLoopCount()) {
            runConfig.put("loopCount", signals.loopCount());
        }
        if (signals.hasExplicitBudgetMs()) {
            runConfig.put("budgetMs", signals.budgetMs());
        }
        if (signals.hasExplicitNetworkIsolationEnabled()) {
            runConfig.put("networkIsolationEnabled", signals.networkIsolationEnabled());
        }
        if (signals.hasExplicitArtifactPolicy()) {
            artifactPolicy.put("uploadLog", artifactPolicy.path("uploadLog").asBoolean(false) || signals.artifactPolicy().uploadLog());
            artifactPolicy.put("uploadScreenshot", artifactPolicy.path("uploadScreenshot").asBoolean(false) || signals.artifactPolicy().uploadScreenshot());
            artifactPolicy.put("uploadDump", artifactPolicy.path("uploadDump").asBoolean(false) || signals.artifactPolicy().uploadDump());
        }

        RunDraftResult.RunDraftDto normalized = new RunDraftResult.RunDraftDto(
                draft.name(),
                draft.description(),
                devicePoolId,
                taskType,
                profilePackage,
                draft.taskPayload().deepCopy(),
                runConfig,
                artifactPolicy,
                priority,
                List.copyOf(draft.labels()),
                signals.hasExplicitMaxRetriesPerDevice() ? signals.maxRetriesPerDevice() : draft.maxRetriesPerDevice(),
                signals.hasExplicitQueueTimeoutMs() ? signals.queueTimeoutMs() : draft.queueTimeoutMs()
        );
        return new CanonicalRunPlanningResult(normalized, List.copyOf(warnings), List.copyOf(reviewHints));
    }

    public RunDraftResult.RunDraftDto defaultDraft(RunPlanningContext context,
                                                   RunPlanningIntentSignals signals,
                                                   String goal) {
        RunPlanningContext.AvailableDevicePoolDto pool = pickPool(context, signals);
        RunPlanningContext.AvailableProfileDto profile = pickProfile(context, signals);
        String taskType = signals.hasExplicitTaskType()
                ? signals.taskType()
                : context.allowedTaskTypes().contains("PLUGIN_RUN") ? "PLUGIN_RUN" : context.allowedTaskTypes().get(0);
        ObjectNode taskPayload = objectMapper.createObjectNode();
        taskPayload.put("goal", goal);
        ObjectNode runConfig = context.defaultRunPolicy().defaultRunConfig().deepCopy();
        ObjectNode artifactPolicy = context.defaultRunPolicy().defaultArtifactPolicy().deepCopy();
        if (signals.hasExplicitLoopCount()) {
            runConfig.put("loopCount", signals.loopCount());
        }
        if (signals.hasExplicitBudgetMs()) {
            runConfig.put("budgetMs", signals.budgetMs());
        }
        if (signals.hasExplicitNetworkIsolationEnabled()) {
            runConfig.put("networkIsolationEnabled", signals.networkIsolationEnabled());
        }
        if (signals.hasExplicitArtifactPolicy()) {
            artifactPolicy.put("uploadLog", artifactPolicy.path("uploadLog").asBoolean(false) || signals.artifactPolicy().uploadLog());
            artifactPolicy.put("uploadScreenshot", artifactPolicy.path("uploadScreenshot").asBoolean(false) || signals.artifactPolicy().uploadScreenshot());
            artifactPolicy.put("uploadDump", artifactPolicy.path("uploadDump").asBoolean(false) || signals.artifactPolicy().uploadDump());
        }
        return new RunDraftResult.RunDraftDto(
                "AI run for " + summarizeGoal(goal),
                goal,
                pool.poolId(),
                taskType,
                profile.profilePackage(),
                taskPayload,
                runConfig,
                artifactPolicy,
                signals.hasExplicitPriority() ? signals.priority() : context.defaultRunPolicy().priority(),
                List.of("ai", "run-draft"),
                signals.hasExplicitMaxRetriesPerDevice()
                        ? signals.maxRetriesPerDevice()
                        : context.defaultRunPolicy().maxRetriesPerDevice(),
                signals.hasExplicitQueueTimeoutMs()
                        ? signals.queueTimeoutMs()
                        : context.defaultRunPolicy().queueTimeoutMs()
        );
    }

    private RunPlanningContext.AvailableDevicePoolDto pickPool(RunPlanningContext context, RunPlanningIntentSignals signals) {
        if (signals.hasExplicitDevicePoolId()) {
            return context.availableDevicePools().stream()
                    .filter(pool -> pool.poolId().equals(signals.devicePoolId()))
                    .findFirst()
                    .orElse(context.availableDevicePools().get(0));
        }
        return context.availableDevicePools().get(0);
    }

    private RunPlanningContext.AvailableProfileDto pickProfile(RunPlanningContext context, RunPlanningIntentSignals signals) {
        if (signals.hasExplicitProfilePackage()) {
            return context.availableProfiles().stream()
                    .filter(profile -> profile.profilePackage().equals(signals.profilePackage()))
                    .findFirst()
                    .orElse(context.availableProfiles().get(0));
        }
        return context.availableProfiles().get(0);
    }

    private String summarizeGoal(String goal) {
        String trimmed = goal == null ? "goal" : goal.trim();
        return trimmed.length() <= 40 ? trimmed : trimmed.substring(0, 40);
    }

    public record CanonicalRunPlanningResult(
            RunDraftResult.RunDraftDto runDraft,
            List<String> warnings,
            List<String> reviewHints
    ) {
    }
}
