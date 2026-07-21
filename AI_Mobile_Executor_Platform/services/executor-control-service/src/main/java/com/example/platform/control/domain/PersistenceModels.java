package com.example.platform.control.domain;

public final class PersistenceModels {

    private PersistenceModels() {
    }

    public static class DeviceEntity {
        private String deviceId;
        private String protocolVersion;
        private String executorVersion;
        private String brand;
        private String model;
        private String androidVersion;
        private int screenWidth;
        private int screenHeight;
        private String installedProfilesJson;
        private String tagsJson;
        private String hostGroup;
        private long createdAt;
        private long updatedAt;

        public String getDeviceId() {
            return deviceId;
        }

        public void setDeviceId(String deviceId) {
            this.deviceId = deviceId;
        }

        public String getProtocolVersion() {
            return protocolVersion;
        }

        public void setProtocolVersion(String protocolVersion) {
            this.protocolVersion = protocolVersion;
        }

        public String getExecutorVersion() {
            return executorVersion;
        }

        public void setExecutorVersion(String executorVersion) {
            this.executorVersion = executorVersion;
        }

        public String getBrand() {
            return brand;
        }

        public void setBrand(String brand) {
            this.brand = brand;
        }

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }

        public String getAndroidVersion() {
            return androidVersion;
        }

        public void setAndroidVersion(String androidVersion) {
            this.androidVersion = androidVersion;
        }

        public int getScreenWidth() {
            return screenWidth;
        }

        public void setScreenWidth(int screenWidth) {
            this.screenWidth = screenWidth;
        }

        public int getScreenHeight() {
            return screenHeight;
        }

        public void setScreenHeight(int screenHeight) {
            this.screenHeight = screenHeight;
        }

        public String getInstalledProfilesJson() {
            return installedProfilesJson;
        }

        public void setInstalledProfilesJson(String installedProfilesJson) {
            this.installedProfilesJson = installedProfilesJson;
        }

        public String getTagsJson() {
            return tagsJson;
        }

        public void setTagsJson(String tagsJson) {
            this.tagsJson = tagsJson;
        }

        public String getHostGroup() {
            return hostGroup;
        }

        public void setHostGroup(String hostGroup) {
            this.hostGroup = hostGroup;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class DeviceRuntimeStateEntity {
        private String deviceId;
        private boolean registered;
        private boolean online;
        private boolean busy;
        private String status;
        private String currentTaskId;
        private String currentAttemptId;
        private String currentTaskType;
        private String configVersion;
        private Long leaseExpireAt;
        private long lastHeartbeatAt;
        private String lastCommand;
        private String healthJson;
        private long updatedAt;

        public String getDeviceId() {
            return deviceId;
        }

        public void setDeviceId(String deviceId) {
            this.deviceId = deviceId;
        }

        public boolean isRegistered() {
            return registered;
        }

        public void setRegistered(boolean registered) {
            this.registered = registered;
        }

        public boolean isOnline() {
            return online;
        }

        public void setOnline(boolean online) {
            this.online = online;
        }

        public boolean isBusy() {
            return busy;
        }

        public void setBusy(boolean busy) {
            this.busy = busy;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getCurrentTaskId() {
            return currentTaskId;
        }

        public void setCurrentTaskId(String currentTaskId) {
            this.currentTaskId = currentTaskId;
        }

        public String getCurrentAttemptId() {
            return currentAttemptId;
        }

        public void setCurrentAttemptId(String currentAttemptId) {
            this.currentAttemptId = currentAttemptId;
        }

        public String getCurrentTaskType() {
            return currentTaskType;
        }

        public void setCurrentTaskType(String currentTaskType) {
            this.currentTaskType = currentTaskType;
        }

        public String getConfigVersion() {
            return configVersion;
        }

        public void setConfigVersion(String configVersion) {
            this.configVersion = configVersion;
        }

        public Long getLeaseExpireAt() {
            return leaseExpireAt;
        }

        public void setLeaseExpireAt(Long leaseExpireAt) {
            this.leaseExpireAt = leaseExpireAt;
        }

        public long getLastHeartbeatAt() {
            return lastHeartbeatAt;
        }

        public void setLastHeartbeatAt(long lastHeartbeatAt) {
            this.lastHeartbeatAt = lastHeartbeatAt;
        }

        public String getLastCommand() {
            return lastCommand;
        }

        public void setLastCommand(String lastCommand) {
            this.lastCommand = lastCommand;
        }

        public String getHealthJson() {
            return healthJson;
        }

        public void setHealthJson(String healthJson) {
            this.healthJson = healthJson;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class TaskEntity {
        private String taskId;
        private String runId;
        private String runTargetId;
        private String targetDeviceId;
        private String taskType;
        private String profilePackage;
        private String taskPayloadJson;
        private String runConfigJson;
        private String artifactPolicyJson;
        private int priority;
        private String labelsJson;
        private String source;
        private String scheduleVersion;
        private String idempotencyKey;
        private String status;
        private String createdBy;
        private long createdAt;
        private long updatedAt;

        public String getTaskId() {
            return taskId;
        }

        public void setTaskId(String taskId) {
            this.taskId = taskId;
        }

        public String getRunId() {
            return runId;
        }

        public void setRunId(String runId) {
            this.runId = runId;
        }

        public String getRunTargetId() {
            return runTargetId;
        }

        public void setRunTargetId(String runTargetId) {
            this.runTargetId = runTargetId;
        }

        public String getTargetDeviceId() {
            return targetDeviceId;
        }

        public void setTargetDeviceId(String targetDeviceId) {
            this.targetDeviceId = targetDeviceId;
        }

        public String getTaskType() {
            return taskType;
        }

        public void setTaskType(String taskType) {
            this.taskType = taskType;
        }

        public String getProfilePackage() {
            return profilePackage;
        }

        public void setProfilePackage(String profilePackage) {
            this.profilePackage = profilePackage;
        }

        public String getTaskPayloadJson() {
            return taskPayloadJson;
        }

        public void setTaskPayloadJson(String taskPayloadJson) {
            this.taskPayloadJson = taskPayloadJson;
        }

        public String getRunConfigJson() {
            return runConfigJson;
        }

        public void setRunConfigJson(String runConfigJson) {
            this.runConfigJson = runConfigJson;
        }

        public String getArtifactPolicyJson() {
            return artifactPolicyJson;
        }

        public void setArtifactPolicyJson(String artifactPolicyJson) {
            this.artifactPolicyJson = artifactPolicyJson;
        }

        public int getPriority() {
            return priority;
        }

        public void setPriority(int priority) {
            this.priority = priority;
        }

        public String getLabelsJson() {
            return labelsJson;
        }

        public void setLabelsJson(String labelsJson) {
            this.labelsJson = labelsJson;
        }

        public String getSource() {
            return source;
        }

        public void setSource(String source) {
            this.source = source;
        }

        public String getScheduleVersion() {
            return scheduleVersion;
        }

        public void setScheduleVersion(String scheduleVersion) {
            this.scheduleVersion = scheduleVersion;
        }

        public String getIdempotencyKey() {
            return idempotencyKey;
        }

        public void setIdempotencyKey(String idempotencyKey) {
            this.idempotencyKey = idempotencyKey;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getCreatedBy() {
            return createdBy;
        }

        public void setCreatedBy(String createdBy) {
            this.createdBy = createdBy;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class DevicePoolEntity {
        private String poolId;
        private String name;
        private String description;
        private String hostGroup;
        private String deviceIdsJson;
        private String requiredTagsJson;
        private String excludedTagsJson;
        private String createdBy;
        private long createdAt;
        private long updatedAt;

        public String getPoolId() {
            return poolId;
        }

        public void setPoolId(String poolId) {
            this.poolId = poolId;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getDescription() {
            return description;
        }

        public void setDescription(String description) {
            this.description = description;
        }

        public String getHostGroup() {
            return hostGroup;
        }

        public void setHostGroup(String hostGroup) {
            this.hostGroup = hostGroup;
        }

        public String getDeviceIdsJson() {
            return deviceIdsJson;
        }

        public void setDeviceIdsJson(String deviceIdsJson) {
            this.deviceIdsJson = deviceIdsJson;
        }

        public String getRequiredTagsJson() {
            return requiredTagsJson;
        }

        public void setRequiredTagsJson(String requiredTagsJson) {
            this.requiredTagsJson = requiredTagsJson;
        }

        public String getExcludedTagsJson() {
            return excludedTagsJson;
        }

        public void setExcludedTagsJson(String excludedTagsJson) {
            this.excludedTagsJson = excludedTagsJson;
        }

        public String getCreatedBy() {
            return createdBy;
        }

        public void setCreatedBy(String createdBy) {
            this.createdBy = createdBy;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class ExperimentRunEntity {
        private String runId;
        private String name;
        private String description;
        private String poolId;
        private String status;
        private String finalState;
        private String taskType;
        private String profilePackage;
        private String taskPayloadJson;
        private String runConfigJson;
        private String artifactPolicyJson;
        private int priority;
        private String labelsJson;
        private String source;
        private String createdBy;
        private int maxRetriesPerDevice;
        private long queueTimeoutMs;
        private boolean cancelRequested;
        private long createdAt;
        private long updatedAt;
        private Long startedAt;
        private Long finishedAt;

        public String getRunId() {
            return runId;
        }

        public void setRunId(String runId) {
            this.runId = runId;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getDescription() {
            return description;
        }

        public void setDescription(String description) {
            this.description = description;
        }

        public String getPoolId() {
            return poolId;
        }

        public void setPoolId(String poolId) {
            this.poolId = poolId;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getFinalState() {
            return finalState;
        }

        public void setFinalState(String finalState) {
            this.finalState = finalState;
        }

        public String getTaskType() {
            return taskType;
        }

        public void setTaskType(String taskType) {
            this.taskType = taskType;
        }

        public String getProfilePackage() {
            return profilePackage;
        }

        public void setProfilePackage(String profilePackage) {
            this.profilePackage = profilePackage;
        }

        public String getTaskPayloadJson() {
            return taskPayloadJson;
        }

        public void setTaskPayloadJson(String taskPayloadJson) {
            this.taskPayloadJson = taskPayloadJson;
        }

        public String getRunConfigJson() {
            return runConfigJson;
        }

        public void setRunConfigJson(String runConfigJson) {
            this.runConfigJson = runConfigJson;
        }

        public String getArtifactPolicyJson() {
            return artifactPolicyJson;
        }

        public void setArtifactPolicyJson(String artifactPolicyJson) {
            this.artifactPolicyJson = artifactPolicyJson;
        }

        public int getPriority() {
            return priority;
        }

        public void setPriority(int priority) {
            this.priority = priority;
        }

        public String getLabelsJson() {
            return labelsJson;
        }

        public void setLabelsJson(String labelsJson) {
            this.labelsJson = labelsJson;
        }

        public String getSource() {
            return source;
        }

        public void setSource(String source) {
            this.source = source;
        }

        public String getCreatedBy() {
            return createdBy;
        }

        public void setCreatedBy(String createdBy) {
            this.createdBy = createdBy;
        }

        public int getMaxRetriesPerDevice() {
            return maxRetriesPerDevice;
        }

        public void setMaxRetriesPerDevice(int maxRetriesPerDevice) {
            this.maxRetriesPerDevice = maxRetriesPerDevice;
        }

        public long getQueueTimeoutMs() {
            return queueTimeoutMs;
        }

        public void setQueueTimeoutMs(long queueTimeoutMs) {
            this.queueTimeoutMs = queueTimeoutMs;
        }

        public boolean isCancelRequested() {
            return cancelRequested;
        }

        public void setCancelRequested(boolean cancelRequested) {
            this.cancelRequested = cancelRequested;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }

        public Long getStartedAt() {
            return startedAt;
        }

        public void setStartedAt(Long startedAt) {
            this.startedAt = startedAt;
        }

        public Long getFinishedAt() {
            return finishedAt;
        }

        public void setFinishedAt(Long finishedAt) {
            this.finishedAt = finishedAt;
        }
    }

    public static class ExperimentRunTargetEntity {
        private String runTargetId;
        private String runId;
        private String deviceId;
        private String sequenceId;
        private String status;
        private int attemptCount;
        private String currentTaskId;
        private String latestAttemptId;
        private String failureReason;
        private long createdAt;
        private long updatedAt;
        private Long startedAt;
        private Long finishedAt;

        public String getRunTargetId() {
            return runTargetId;
        }

        public void setRunTargetId(String runTargetId) {
            this.runTargetId = runTargetId;
        }

        public String getRunId() {
            return runId;
        }

        public void setRunId(String runId) {
            this.runId = runId;
        }

        public String getDeviceId() {
            return deviceId;
        }

        public void setDeviceId(String deviceId) {
            this.deviceId = deviceId;
        }

        public String getSequenceId() {
            return sequenceId;
        }

        public void setSequenceId(String sequenceId) {
            this.sequenceId = sequenceId;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public int getAttemptCount() {
            return attemptCount;
        }

        public void setAttemptCount(int attemptCount) {
            this.attemptCount = attemptCount;
        }

        public String getCurrentTaskId() {
            return currentTaskId;
        }

        public void setCurrentTaskId(String currentTaskId) {
            this.currentTaskId = currentTaskId;
        }

        public String getLatestAttemptId() {
            return latestAttemptId;
        }

        public void setLatestAttemptId(String latestAttemptId) {
            this.latestAttemptId = latestAttemptId;
        }

        public String getFailureReason() {
            return failureReason;
        }

        public void setFailureReason(String failureReason) {
            this.failureReason = failureReason;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }

        public Long getStartedAt() {
            return startedAt;
        }

        public void setStartedAt(Long startedAt) {
            this.startedAt = startedAt;
        }

        public Long getFinishedAt() {
            return finishedAt;
        }

        public void setFinishedAt(Long finishedAt) {
            this.finishedAt = finishedAt;
        }
    }

    public static class TaskAttemptEntity {
        private String attemptId;
        private String taskId;
        private String deviceId;
        private String runId;
        private String status;
        private String finalState;
        private Long leaseExpireAt;
        private String failureReason;
        private String preflightSummaryJson;
        private String failureDetailJson;
        private Long startedAt;
        private Long finishedAt;
        private long createdAt;
        private long updatedAt;

        public String getAttemptId() {
            return attemptId;
        }

        public void setAttemptId(String attemptId) {
            this.attemptId = attemptId;
        }

        public String getTaskId() {
            return taskId;
        }

        public void setTaskId(String taskId) {
            this.taskId = taskId;
        }

        public String getDeviceId() {
            return deviceId;
        }

        public void setDeviceId(String deviceId) {
            this.deviceId = deviceId;
        }

        public String getRunId() {
            return runId;
        }

        public void setRunId(String runId) {
            this.runId = runId;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getFinalState() {
            return finalState;
        }

        public void setFinalState(String finalState) {
            this.finalState = finalState;
        }

        public Long getLeaseExpireAt() {
            return leaseExpireAt;
        }

        public void setLeaseExpireAt(Long leaseExpireAt) {
            this.leaseExpireAt = leaseExpireAt;
        }

        public String getFailureReason() {
            return failureReason;
        }

        public void setFailureReason(String failureReason) {
            this.failureReason = failureReason;
        }

        public String getPreflightSummaryJson() {
            return preflightSummaryJson;
        }

        public void setPreflightSummaryJson(String preflightSummaryJson) {
            this.preflightSummaryJson = preflightSummaryJson;
        }

        public String getFailureDetailJson() {
            return failureDetailJson;
        }

        public void setFailureDetailJson(String failureDetailJson) {
            this.failureDetailJson = failureDetailJson;
        }

        public Long getStartedAt() {
            return startedAt;
        }

        public void setStartedAt(Long startedAt) {
            this.startedAt = startedAt;
        }

        public Long getFinishedAt() {
            return finishedAt;
        }

        public void setFinishedAt(Long finishedAt) {
            this.finishedAt = finishedAt;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class DeviceCommandEntity {
        private Long commandId;
        private String deviceId;
        private String type;
        private String attemptId;
        private String status;
        private String payloadJson;
        private long issuedAt;
        private Long ackedAt;
        private Long expireAt;

        public Long getCommandId() {
            return commandId;
        }

        public void setCommandId(Long commandId) {
            this.commandId = commandId;
        }

        public String getDeviceId() {
            return deviceId;
        }

        public void setDeviceId(String deviceId) {
            this.deviceId = deviceId;
        }

        public String getType() {
            return type;
        }

        public void setType(String type) {
            this.type = type;
        }

        public String getAttemptId() {
            return attemptId;
        }

        public void setAttemptId(String attemptId) {
            this.attemptId = attemptId;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getPayloadJson() {
            return payloadJson;
        }

        public void setPayloadJson(String payloadJson) {
            this.payloadJson = payloadJson;
        }

        public long getIssuedAt() {
            return issuedAt;
        }

        public void setIssuedAt(long issuedAt) {
            this.issuedAt = issuedAt;
        }

        public Long getAckedAt() {
            return ackedAt;
        }

        public void setAckedAt(Long ackedAt) {
            this.ackedAt = ackedAt;
        }

        public Long getExpireAt() {
            return expireAt;
        }

        public void setExpireAt(Long expireAt) {
            this.expireAt = expireAt;
        }
    }

    public static class RunEventEntity {
        private Long id;
        private String attemptId;
        private String taskId;
        private String deviceId;
        private String runId;
        private String scenarioId;
        private Integer stepIndex;
        private Integer actionIndex;
        private String eventType;
        private String eventKey;
        private String state;
        private String code;
        private String message;
        private String payloadJson;
        private long ts;

        public Long getId() {
            return id;
        }

        public void setId(Long id) {
            this.id = id;
        }

        public String getAttemptId() {
            return attemptId;
        }

        public void setAttemptId(String attemptId) {
            this.attemptId = attemptId;
        }

        public String getTaskId() {
            return taskId;
        }

        public void setTaskId(String taskId) {
            this.taskId = taskId;
        }

        public String getDeviceId() {
            return deviceId;
        }

        public void setDeviceId(String deviceId) {
            this.deviceId = deviceId;
        }

        public String getRunId() {
            return runId;
        }

        public void setRunId(String runId) {
            this.runId = runId;
        }

        public String getScenarioId() {
            return scenarioId;
        }

        public void setScenarioId(String scenarioId) {
            this.scenarioId = scenarioId;
        }

        public Integer getStepIndex() {
            return stepIndex;
        }

        public void setStepIndex(Integer stepIndex) {
            this.stepIndex = stepIndex;
        }

        public Integer getActionIndex() {
            return actionIndex;
        }

        public void setActionIndex(Integer actionIndex) {
            this.actionIndex = actionIndex;
        }

        public String getEventType() {
            return eventType;
        }

        public void setEventType(String eventType) {
            this.eventType = eventType;
        }

        public String getEventKey() {
            return eventKey;
        }

        public void setEventKey(String eventKey) {
            this.eventKey = eventKey;
        }

        public String getState() {
            return state;
        }

        public void setState(String state) {
            this.state = state;
        }

        public String getCode() {
            return code;
        }

        public void setCode(String code) {
            this.code = code;
        }

        public String getMessage() {
            return message;
        }

        public void setMessage(String message) {
            this.message = message;
        }

        public String getPayloadJson() {
            return payloadJson;
        }

        public void setPayloadJson(String payloadJson) {
            this.payloadJson = payloadJson;
        }

        public long getTs() {
            return ts;
        }

        public void setTs(long ts) {
            this.ts = ts;
        }
    }

    public static class ArtifactEntity {
        private String artifactId;
        private String attemptId;
        private String taskId;
        private String runId;
        private String artifactType;
        private String fileName;
        private String mimeType;
        private long sizeBytes;
        private String objectKey;
        private long createdAt;

        public String getArtifactId() {
            return artifactId;
        }

        public void setArtifactId(String artifactId) {
            this.artifactId = artifactId;
        }

        public String getAttemptId() {
            return attemptId;
        }

        public void setAttemptId(String attemptId) {
            this.attemptId = attemptId;
        }

        public String getTaskId() {
            return taskId;
        }

        public void setTaskId(String taskId) {
            this.taskId = taskId;
        }

        public String getRunId() {
            return runId;
        }

        public void setRunId(String runId) {
            this.runId = runId;
        }

        public String getArtifactType() {
            return artifactType;
        }

        public void setArtifactType(String artifactType) {
            this.artifactType = artifactType;
        }

        public String getFileName() {
            return fileName;
        }

        public void setFileName(String fileName) {
            this.fileName = fileName;
        }

        public String getMimeType() {
            return mimeType;
        }

        public void setMimeType(String mimeType) {
            this.mimeType = mimeType;
        }

        public long getSizeBytes() {
            return sizeBytes;
        }

        public void setSizeBytes(long sizeBytes) {
            this.sizeBytes = sizeBytes;
        }

        public String getObjectKey() {
            return objectKey;
        }

        public void setObjectKey(String objectKey) {
            this.objectKey = objectKey;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }
    }

    public static class ArtifactUploadSessionEntity {
        private String artifactId;
        private String attemptId;
        private String taskId;
        private String deviceId;
        private String runId;
        private String artifactType;
        private String fileName;
        private String mimeType;
        private long declaredSizeBytes;
        private String objectKey;
        private String status;
        private long uploadExpiresAt;
        private Long finalizedAt;
        private long createdAt;
        private long updatedAt;

        public String getArtifactId() {
            return artifactId;
        }

        public void setArtifactId(String artifactId) {
            this.artifactId = artifactId;
        }

        public String getAttemptId() {
            return attemptId;
        }

        public void setAttemptId(String attemptId) {
            this.attemptId = attemptId;
        }

        public String getTaskId() {
            return taskId;
        }

        public void setTaskId(String taskId) {
            this.taskId = taskId;
        }

        public String getDeviceId() {
            return deviceId;
        }

        public void setDeviceId(String deviceId) {
            this.deviceId = deviceId;
        }

        public String getRunId() {
            return runId;
        }

        public void setRunId(String runId) {
            this.runId = runId;
        }

        public String getArtifactType() {
            return artifactType;
        }

        public void setArtifactType(String artifactType) {
            this.artifactType = artifactType;
        }

        public String getFileName() {
            return fileName;
        }

        public void setFileName(String fileName) {
            this.fileName = fileName;
        }

        public String getMimeType() {
            return mimeType;
        }

        public void setMimeType(String mimeType) {
            this.mimeType = mimeType;
        }

        public long getDeclaredSizeBytes() {
            return declaredSizeBytes;
        }

        public void setDeclaredSizeBytes(long declaredSizeBytes) {
            this.declaredSizeBytes = declaredSizeBytes;
        }

        public String getObjectKey() {
            return objectKey;
        }

        public void setObjectKey(String objectKey) {
            this.objectKey = objectKey;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public long getUploadExpiresAt() {
            return uploadExpiresAt;
        }

        public void setUploadExpiresAt(long uploadExpiresAt) {
            this.uploadExpiresAt = uploadExpiresAt;
        }

        public Long getFinalizedAt() {
            return finalizedAt;
        }

        public void setFinalizedAt(Long finalizedAt) {
            this.finalizedAt = finalizedAt;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class AiRunPlanRequestEntity {
        private String requestId;
        private String goalText;
        private String constraintsJson;
        private String contextJson;
        private String status;
        private String materializedRunId;
        private String materializedBy;
        private Long materializedAt;
        private long createdAt;
        private long updatedAt;

        public String getRequestId() {
            return requestId;
        }

        public void setRequestId(String requestId) {
            this.requestId = requestId;
        }

        public String getGoalText() {
            return goalText;
        }

        public void setGoalText(String goalText) {
            this.goalText = goalText;
        }

        public String getConstraintsJson() {
            return constraintsJson;
        }

        public void setConstraintsJson(String constraintsJson) {
            this.constraintsJson = constraintsJson;
        }

        public String getContextJson() {
            return contextJson;
        }

        public void setContextJson(String contextJson) {
            this.contextJson = contextJson;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getMaterializedRunId() {
            return materializedRunId;
        }

        public void setMaterializedRunId(String materializedRunId) {
            this.materializedRunId = materializedRunId;
        }

        public String getMaterializedBy() {
            return materializedBy;
        }

        public void setMaterializedBy(String materializedBy) {
            this.materializedBy = materializedBy;
        }

        public Long getMaterializedAt() {
            return materializedAt;
        }

        public void setMaterializedAt(Long materializedAt) {
            this.materializedAt = materializedAt;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class AiRunPlanResultEntity {
        private String requestId;
        private String resultJson;
        private String validationJson;
        private String modelMetaJson;
        private String status;
        private long createdAt;
        private long updatedAt;

        public String getRequestId() {
            return requestId;
        }

        public void setRequestId(String requestId) {
            this.requestId = requestId;
        }

        public String getResultJson() {
            return resultJson;
        }

        public void setResultJson(String resultJson) {
            this.resultJson = resultJson;
        }

        public String getValidationJson() {
            return validationJson;
        }

        public void setValidationJson(String validationJson) {
            this.validationJson = validationJson;
        }

        public String getModelMetaJson() {
            return modelMetaJson;
        }

        public void setModelMetaJson(String modelMetaJson) {
            this.modelMetaJson = modelMetaJson;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class AiFailureTriageResultEntity {
        private String triageResultId;
        private String runId;
        private String runTargetId;
        private String attemptId;
        private String contextJson;
        private String resultJson;
        private String validationJson;
        private String modelMetaJson;
        private String status;
        private long createdAt;
        private long updatedAt;

        public String getTriageResultId() {
            return triageResultId;
        }

        public void setTriageResultId(String triageResultId) {
            this.triageResultId = triageResultId;
        }

        public String getRunId() {
            return runId;
        }

        public void setRunId(String runId) {
            this.runId = runId;
        }

        public String getRunTargetId() {
            return runTargetId;
        }

        public void setRunTargetId(String runTargetId) {
            this.runTargetId = runTargetId;
        }

        public String getAttemptId() {
            return attemptId;
        }

        public void setAttemptId(String attemptId) {
            this.attemptId = attemptId;
        }

        public String getContextJson() {
            return contextJson;
        }

        public void setContextJson(String contextJson) {
            this.contextJson = contextJson;
        }

        public String getResultJson() {
            return resultJson;
        }

        public void setResultJson(String resultJson) {
            this.resultJson = resultJson;
        }

        public String getValidationJson() {
            return validationJson;
        }

        public void setValidationJson(String validationJson) {
            this.validationJson = validationJson;
        }

        public String getModelMetaJson() {
            return modelMetaJson;
        }

        public void setModelMetaJson(String modelMetaJson) {
            this.modelMetaJson = modelMetaJson;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class AiRunSummaryResultEntity {
        private String summaryId;
        private String runId;
        private String contextJson;
        private String resultJson;
        private String validationJson;
        private String modelMetaJson;
        private String status;
        private long createdAt;
        private long updatedAt;

        public String getSummaryId() {
            return summaryId;
        }

        public void setSummaryId(String summaryId) {
            this.summaryId = summaryId;
        }

        public String getRunId() {
            return runId;
        }

        public void setRunId(String runId) {
            this.runId = runId;
        }

        public String getContextJson() {
            return contextJson;
        }

        public void setContextJson(String contextJson) {
            this.contextJson = contextJson;
        }

        public String getResultJson() {
            return resultJson;
        }

        public void setResultJson(String resultJson) {
            this.resultJson = resultJson;
        }

        public String getValidationJson() {
            return validationJson;
        }

        public void setValidationJson(String validationJson) {
            this.validationJson = validationJson;
        }

        public String getModelMetaJson() {
            return modelMetaJson;
        }

        public void setModelMetaJson(String modelMetaJson) {
            this.modelMetaJson = modelMetaJson;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class ToolExecutionAuditEntity {
        private String auditId;
        private String requestId;
        private String sessionId;
        private String toolName;
        private String riskLevel;
        private String status;
        private String requestJson;
        private String callerContextJson;
        private String responseJson;
        private String entityRefsJson;
        private long createdAt;
        private long updatedAt;

        public String getAuditId() {
            return auditId;
        }

        public void setAuditId(String auditId) {
            this.auditId = auditId;
        }

        public String getRequestId() {
            return requestId;
        }

        public void setRequestId(String requestId) {
            this.requestId = requestId;
        }

        public String getSessionId() {
            return sessionId;
        }

        public void setSessionId(String sessionId) {
            this.sessionId = sessionId;
        }

        public String getToolName() {
            return toolName;
        }

        public void setToolName(String toolName) {
            this.toolName = toolName;
        }

        public String getRiskLevel() {
            return riskLevel;
        }

        public void setRiskLevel(String riskLevel) {
            this.riskLevel = riskLevel;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public String getRequestJson() {
            return requestJson;
        }

        public void setRequestJson(String requestJson) {
            this.requestJson = requestJson;
        }

        public String getResponseJson() {
            return responseJson;
        }

        public void setResponseJson(String responseJson) {
            this.responseJson = responseJson;
        }

        public String getCallerContextJson() {
            return callerContextJson;
        }

        public void setCallerContextJson(String callerContextJson) {
            this.callerContextJson = callerContextJson;
        }

        public String getEntityRefsJson() {
            return entityRefsJson;
        }

        public void setEntityRefsJson(String entityRefsJson) {
            this.entityRefsJson = entityRefsJson;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }

    public static class ToolConfirmationTokenEntity {
        private String confirmationId;
        private String auditId;
        private String toolName;
        private String sessionId;
        private String argumentsJson;
        private String callerContextJson;
        private String tokenHash;
        private String status;
        private long expiresAt;
        private Long usedAt;
        private long createdAt;
        private long updatedAt;

        public String getConfirmationId() {
            return confirmationId;
        }

        public void setConfirmationId(String confirmationId) {
            this.confirmationId = confirmationId;
        }

        public String getAuditId() {
            return auditId;
        }

        public void setAuditId(String auditId) {
            this.auditId = auditId;
        }

        public String getToolName() {
            return toolName;
        }

        public void setToolName(String toolName) {
            this.toolName = toolName;
        }

        public String getSessionId() {
            return sessionId;
        }

        public void setSessionId(String sessionId) {
            this.sessionId = sessionId;
        }

        public String getArgumentsJson() {
            return argumentsJson;
        }

        public void setArgumentsJson(String argumentsJson) {
            this.argumentsJson = argumentsJson;
        }

        public String getTokenHash() {
            return tokenHash;
        }

        public void setTokenHash(String tokenHash) {
            this.tokenHash = tokenHash;
        }

        public String getCallerContextJson() {
            return callerContextJson;
        }

        public void setCallerContextJson(String callerContextJson) {
            this.callerContextJson = callerContextJson;
        }

        public String getStatus() {
            return status;
        }

        public void setStatus(String status) {
            this.status = status;
        }

        public long getExpiresAt() {
            return expiresAt;
        }

        public void setExpiresAt(long expiresAt) {
            this.expiresAt = expiresAt;
        }

        public Long getUsedAt() {
            return usedAt;
        }

        public void setUsedAt(Long usedAt) {
            this.usedAt = usedAt;
        }

        public long getCreatedAt() {
            return createdAt;
        }

        public void setCreatedAt(long createdAt) {
            this.createdAt = createdAt;
        }

        public long getUpdatedAt() {
            return updatedAt;
        }

        public void setUpdatedAt(long updatedAt) {
            this.updatedAt = updatedAt;
        }
    }
}
