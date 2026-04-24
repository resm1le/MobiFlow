package com.example.platform.ai.app;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

@ConfigurationProperties(prefix = "executor.ai")
public class AiProperties {

    private Provider provider = new Provider();

    public Provider getProvider() {
        return provider;
    }

    public void setProvider(Provider provider) {
        this.provider = provider;
    }

    public static class Provider {

        private AiProviderMode mode = AiProviderMode.STUB;
        private OpenAiCompatible openAiCompatible = new OpenAiCompatible();

        public AiProviderMode getMode() {
            return mode;
        }

        public void setMode(AiProviderMode mode) {
            this.mode = mode;
        }

        public OpenAiCompatible getOpenAiCompatible() {
            return openAiCompatible;
        }

        public void setOpenAiCompatible(OpenAiCompatible openAiCompatible) {
            this.openAiCompatible = openAiCompatible;
        }
    }

    public static class OpenAiCompatible {

        private String baseUrl = "https://api.openai.com/v1";
        private String apiKey;
        private String model = "gpt-5.4";
        private Duration timeout = Duration.ofSeconds(30);
        private int maxConcurrent = 4;
        private int failureThreshold = 3;
        private Duration cooldown = Duration.ofSeconds(30);
        private int retry429MaxAttempts = 2;
        private Duration retry429Backoff = Duration.ofSeconds(1);

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }

        public String getApiKey() {
            return apiKey;
        }

        public void setApiKey(String apiKey) {
            this.apiKey = apiKey;
        }

        public String getModel() {
            return model;
        }

        public void setModel(String model) {
            this.model = model;
        }

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }

        public int getMaxConcurrent() {
            return maxConcurrent;
        }

        public void setMaxConcurrent(int maxConcurrent) {
            this.maxConcurrent = maxConcurrent;
        }

        public int getFailureThreshold() {
            return failureThreshold;
        }

        public void setFailureThreshold(int failureThreshold) {
            this.failureThreshold = failureThreshold;
        }

        public Duration getCooldown() {
            return cooldown;
        }

        public void setCooldown(Duration cooldown) {
            this.cooldown = cooldown;
        }

        public int getRetry429MaxAttempts() {
            return retry429MaxAttempts;
        }

        public void setRetry429MaxAttempts(int retry429MaxAttempts) {
            this.retry429MaxAttempts = retry429MaxAttempts;
        }

        public Duration getRetry429Backoff() {
            return retry429Backoff;
        }

        public void setRetry429Backoff(Duration retry429Backoff) {
            this.retry429Backoff = retry429Backoff;
        }
    }
}
