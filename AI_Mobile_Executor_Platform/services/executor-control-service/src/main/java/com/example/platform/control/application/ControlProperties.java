package com.example.platform.control.application;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.ArrayList;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;

@ConfigurationProperties(prefix = "platform.control")
public class ControlProperties {

    private String configVersion = "cfg-v1";
    private String scheduleVersion = "sched-v1";
    private long leaseMs = 60000;
    private Auth auth = new Auth();
    private Admin admin = new Admin();
    private Ai ai = new Ai();
    private Console console = new Console();
    private Tools tools = new Tools();
    private DefaultRunConfig defaultRunConfig = new DefaultRunConfig();
    private Artifacts artifacts = new Artifacts();
    private Jobs jobs = new Jobs();

    public String getConfigVersion() {
        return configVersion;
    }

    public void setConfigVersion(String configVersion) {
        this.configVersion = configVersion;
    }

    public String getScheduleVersion() {
        return scheduleVersion;
    }

    public void setScheduleVersion(String scheduleVersion) {
        this.scheduleVersion = scheduleVersion;
    }

    public long getLeaseMs() {
        return leaseMs;
    }

    public void setLeaseMs(long leaseMs) {
        this.leaseMs = leaseMs;
    }

    public Auth getAuth() {
        return auth;
    }

    public void setAuth(Auth auth) {
        this.auth = auth;
    }

    public Ai getAi() {
        return ai;
    }

    public void setAi(Ai ai) {
        this.ai = ai;
    }

    public Admin getAdmin() {
        return admin;
    }

    public void setAdmin(Admin admin) {
        this.admin = admin;
    }

    public DefaultRunConfig getDefaultRunConfig() {
        return defaultRunConfig;
    }

    public void setDefaultRunConfig(DefaultRunConfig defaultRunConfig) {
        this.defaultRunConfig = defaultRunConfig;
    }

    public Console getConsole() {
        return console;
    }

    public void setConsole(Console console) {
        this.console = console;
    }

    public Tools getTools() {
        return tools;
    }

    public void setTools(Tools tools) {
        this.tools = tools;
    }

    public Jobs getJobs() {
        return jobs;
    }

    public void setJobs(Jobs jobs) {
        this.jobs = jobs;
    }

    public Artifacts getArtifacts() {
        return artifacts;
    }

    public void setArtifacts(Artifacts artifacts) {
        this.artifacts = artifacts;
    }

    public static class Auth {
        private long allowedTimestampSkewSeconds = 300;
        private long nonceTtlSeconds = 600;
        private String nonceKeyPrefix = "executor:nonce:";
        private boolean allowUnsignedDevices = false;
        private Map<String, String> deviceTokens = new LinkedHashMap<>();

        public long getAllowedTimestampSkewSeconds() {
            return allowedTimestampSkewSeconds;
        }

        public void setAllowedTimestampSkewSeconds(long allowedTimestampSkewSeconds) {
            this.allowedTimestampSkewSeconds = allowedTimestampSkewSeconds;
        }

        public long getNonceTtlSeconds() {
            return nonceTtlSeconds;
        }

        public void setNonceTtlSeconds(long nonceTtlSeconds) {
            this.nonceTtlSeconds = nonceTtlSeconds;
        }

        public String getNonceKeyPrefix() {
            return nonceKeyPrefix;
        }

        public void setNonceKeyPrefix(String nonceKeyPrefix) {
            this.nonceKeyPrefix = nonceKeyPrefix;
        }

        public boolean isAllowUnsignedDevices() {
            return allowUnsignedDevices;
        }

        public void setAllowUnsignedDevices(boolean allowUnsignedDevices) {
            this.allowUnsignedDevices = allowUnsignedDevices;
        }

        public Map<String, String> getDeviceTokens() {
            return deviceTokens;
        }

        public void setDeviceTokens(Map<String, String> deviceTokens) {
            this.deviceTokens = deviceTokens;
        }
    }

    public static class Admin {
        private String authToken;

        public String getAuthToken() {
            return authToken;
        }

        public void setAuthToken(String authToken) {
            this.authToken = authToken;
        }
    }

    public static class Ai {
        private String baseUrl = "http://localhost:8081";
        private long connectTimeoutMs = 3000;
        private long readTimeoutMs = 60000;

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public long getConnectTimeoutMs() {
            return connectTimeoutMs;
        }

        public void setConnectTimeoutMs(long connectTimeoutMs) {
            this.connectTimeoutMs = connectTimeoutMs;
        }

        public long getReadTimeoutMs() {
            return readTimeoutMs;
        }

        public void setReadTimeoutMs(long readTimeoutMs) {
            this.readTimeoutMs = readTimeoutMs;
        }
    }

    public static class Console {
        private List<String> allowedOrigins = new ArrayList<>(List.of(
                "http://127.0.0.1:5173",
                "http://localhost:5173"
        ));

        public List<String> getAllowedOrigins() {
            return allowedOrigins;
        }

        public void setAllowedOrigins(List<String> allowedOrigins) {
            this.allowedOrigins = allowedOrigins;
        }
    }

    public static class Tools {
        private long confirmationTtlMs = 300000;
        private List<String> enabled = new ArrayList<>();
        private List<String> disabled = new ArrayList<>();

        public long getConfirmationTtlMs() {
            return confirmationTtlMs;
        }

        public void setConfirmationTtlMs(long confirmationTtlMs) {
            this.confirmationTtlMs = confirmationTtlMs;
        }

        public List<String> getEnabled() {
            return enabled;
        }

        public void setEnabled(List<String> enabled) {
            this.enabled = enabled;
        }

        public List<String> getDisabled() {
            return disabled;
        }

        public void setDisabled(List<String> disabled) {
            this.disabled = disabled;
        }
    }

    public static class DefaultRunConfig {
        private int loopCount = 1;
        private long budgetMs = 60000;
        private long loopIntervalMs = 0;
        private boolean networkIsolationEnabled = false;
        private long pollIntervalMs = 15000;
        private long heartbeatIntervalMs = 30000;
        private long idlePollIntervalMs = 30000;
        private long idleHeartbeatIntervalMs = 60000;
        private long quiescedHeartbeatIntervalMs = 60000;

        public int getLoopCount() {
            return loopCount;
        }

        public void setLoopCount(int loopCount) {
            this.loopCount = loopCount;
        }

        public long getBudgetMs() {
            return budgetMs;
        }

        public void setBudgetMs(long budgetMs) {
            this.budgetMs = budgetMs;
        }

        public long getLoopIntervalMs() {
            return loopIntervalMs;
        }

        public void setLoopIntervalMs(long loopIntervalMs) {
            this.loopIntervalMs = loopIntervalMs;
        }

        public boolean isNetworkIsolationEnabled() {
            return networkIsolationEnabled;
        }

        public void setNetworkIsolationEnabled(boolean networkIsolationEnabled) {
            this.networkIsolationEnabled = networkIsolationEnabled;
        }

        public long getPollIntervalMs() {
            return pollIntervalMs;
        }

        public void setPollIntervalMs(long pollIntervalMs) {
            this.pollIntervalMs = pollIntervalMs;
        }

        public long getHeartbeatIntervalMs() {
            return heartbeatIntervalMs;
        }

        public void setHeartbeatIntervalMs(long heartbeatIntervalMs) {
            this.heartbeatIntervalMs = heartbeatIntervalMs;
        }

        public long getIdlePollIntervalMs() {
            return idlePollIntervalMs;
        }

        public void setIdlePollIntervalMs(long idlePollIntervalMs) {
            this.idlePollIntervalMs = idlePollIntervalMs;
        }

        public long getIdleHeartbeatIntervalMs() {
            return idleHeartbeatIntervalMs;
        }

        public void setIdleHeartbeatIntervalMs(long idleHeartbeatIntervalMs) {
            this.idleHeartbeatIntervalMs = idleHeartbeatIntervalMs;
        }

        public long getQuiescedHeartbeatIntervalMs() {
            return quiescedHeartbeatIntervalMs;
        }

        public void setQuiescedHeartbeatIntervalMs(long quiescedHeartbeatIntervalMs) {
            this.quiescedHeartbeatIntervalMs = quiescedHeartbeatIntervalMs;
        }
    }

    public static class Artifacts {
        private String backend = "disabled";
        private long uploadTicketTtlMs = 300000;
        private long cleanupIntervalMs = 60000;
        private Minio minio = new Minio();

        public String getBackend() {
            return backend;
        }

        public void setBackend(String backend) {
            this.backend = backend;
        }

        public long getUploadTicketTtlMs() {
            return uploadTicketTtlMs;
        }

        public void setUploadTicketTtlMs(long uploadTicketTtlMs) {
            this.uploadTicketTtlMs = uploadTicketTtlMs;
        }

        public long getCleanupIntervalMs() {
            return cleanupIntervalMs;
        }

        public void setCleanupIntervalMs(long cleanupIntervalMs) {
            this.cleanupIntervalMs = cleanupIntervalMs;
        }

        public Minio getMinio() {
            return minio;
        }

        public void setMinio(Minio minio) {
            this.minio = minio;
        }
    }

    public static class Minio {
        private String endpoint;
        private String accessKey;
        private String secretKey;
        private String bucket;

        public String getEndpoint() {
            return endpoint;
        }

        public void setEndpoint(String endpoint) {
            this.endpoint = endpoint;
        }

        public String getAccessKey() {
            return accessKey;
        }

        public void setAccessKey(String accessKey) {
            this.accessKey = accessKey;
        }

        public String getSecretKey() {
            return secretKey;
        }

        public void setSecretKey(String secretKey) {
            this.secretKey = secretKey;
        }

        public String getBucket() {
            return bucket;
        }

        public void setBucket(String bucket) {
            this.bucket = bucket;
        }
    }

    public static class Jobs {
        private long leaseReaperIntervalMs = 5000;
        private long offlineReconcilerIntervalMs = 10000;
        private long commandExpiryIntervalMs = 10000;
        private long offlineThresholdMs = 90000;

        public long getLeaseReaperIntervalMs() {
            return leaseReaperIntervalMs;
        }

        public void setLeaseReaperIntervalMs(long leaseReaperIntervalMs) {
            this.leaseReaperIntervalMs = leaseReaperIntervalMs;
        }

        public long getOfflineReconcilerIntervalMs() {
            return offlineReconcilerIntervalMs;
        }

        public void setOfflineReconcilerIntervalMs(long offlineReconcilerIntervalMs) {
            this.offlineReconcilerIntervalMs = offlineReconcilerIntervalMs;
        }

        public long getCommandExpiryIntervalMs() {
            return commandExpiryIntervalMs;
        }

        public void setCommandExpiryIntervalMs(long commandExpiryIntervalMs) {
            this.commandExpiryIntervalMs = commandExpiryIntervalMs;
        }

        public long getOfflineThresholdMs() {
            return offlineThresholdMs;
        }

        public void setOfflineThresholdMs(long offlineThresholdMs) {
            this.offlineThresholdMs = offlineThresholdMs;
        }
    }
}
