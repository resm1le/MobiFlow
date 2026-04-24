package com.example.platform.control.api;

import java.util.List;
import java.util.Map;

public final class ToolApiModels {

    private ToolApiModels() {
    }

    public record ExecuteToolRequest(
            String version,
            String requestId,
            String sessionId,
            String tool,
            Map<String, Object> arguments,
            CallerContext callerContext
    ) {
    }

    public record ResolveConfirmationRequest(
            String version,
            String confirmationId,
            String decision,
            String sessionId,
            CallerContext callerContext
    ) {
    }

    public record CallerContext(
            String agentTaskId,
            String turnId,
            String stepId
    ) {
    }

    public record ToolError(
            String code,
            String message,
            boolean retryable
    ) {
    }

    public record ExecuteToolResponse(
            String version,
            String requestId,
            String sessionId,
            String tool,
            String status,
            Object result,
            List<String> warnings,
            ToolError error,
            ToolAudit audit,
            EntityRefs entityRefs,
            ToolConfirmation confirmation
    ) {
    }

    public record ToolAudit(
            String auditId,
            String riskLevel
    ) {
    }

    public record EntityRefs(
            String proposalId,
            String runId,
            String runTargetId,
            String taskId,
            String attemptId,
            List<String> artifactIds
    ) {
    }

    public record ToolConfirmation(
            String confirmationId,
            long expiresAt,
            String summary
    ) {
    }

    public record ToolGovernance(
            boolean requiresApproval,
            String confirmationMode
    ) {
    }

    public record ToolCatalogItem(
            String name,
            String title,
            String description,
            Map<String, Object> inputSchema,
            Map<String, Object> outputSchema,
            String resultMode,
            String stability,
            String toolKind,
            String riskLevel,
            ToolGovernance governance,
            List<String> semanticTags
    ) {
    }

    public record ToolCatalogResponse(
            String version,
            List<ToolCatalogItem> tools
    ) {
    }

    public record AuditQueryRequest(
            String sessionId,
            String agentTaskId,
            String turnId,
            String runId,
            String runTargetId,
            String attemptId
    ) {
    }

    public record AuditTimelineEntry(
            String auditId,
            String requestId,
            String sessionId,
            String tool,
            String status,
            String riskLevel,
            CallerContext callerContext,
            EntityRefs entityRefs,
            long createdAt,
            long updatedAt
    ) {
    }

    public record AuditQueryResponse(
            String version,
            List<AuditTimelineEntry> entries
    ) {
    }

    public record ResourceHandle(
            String handle,
            String kind,
            String mimeType,
            long sizeBytes,
            String fileName,
            String title
    ) {
    }

    public record AttemptArtifactResource(
            String artifactId,
            String attemptId,
            String taskId,
            String runId,
            String artifactType,
            String fileName,
            String mimeType,
            long sizeBytes,
            long createdAt,
            ResourceHandle resource
    ) {
    }

    public record ReadResourceRequest(
            String handle
    ) {
    }

    public record ReadResourceResponse(
            String handle,
            String kind,
            String mimeType,
            String title,
            Object content
    ) {
    }
}
