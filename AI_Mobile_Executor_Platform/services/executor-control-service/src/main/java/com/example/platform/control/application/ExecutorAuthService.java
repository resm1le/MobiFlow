package com.example.platform.control.application;

import com.example.platform.control.api.ExecutorAuthContext;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Map;

@Service
public class ExecutorAuthService {

    public static final String HEADER_DEVICE_ID = "X-Executor-DeviceId";
    public static final String HEADER_PROTOCOL_VERSION = "X-Executor-Protocol-Version";
    public static final String HEADER_TIMESTAMP = "X-Executor-Timestamp";
    public static final String HEADER_NONCE = "X-Executor-Nonce";
    public static final String HEADER_SIGNATURE = "X-Executor-Signature";

    private final ControlProperties controlProperties;
    private final StringRedisTemplate stringRedisTemplate;
    private final Clock clock = Clock.systemUTC();

    public ExecutorAuthService(ControlProperties controlProperties, StringRedisTemplate stringRedisTemplate) {
        this.controlProperties = controlProperties;
        this.stringRedisTemplate = stringRedisTemplate;
    }

    public ExecutorAuthContext authenticate(String method,
                                         String path,
                                         String deviceId,
                                         String protocolVersion,
                                         String timestampValue,
                                         String nonce,
                                         String signature,
                                         byte[] body) {
        requireHeader(deviceId, "EXECUTOR_DEVICE_ID_MISSING");
        requireHeader(protocolVersion, "EXECUTOR_PROTOCOL_VERSION_MISSING");
        requireHeader(timestampValue, "EXECUTOR_TIMESTAMP_MISSING");
        requireHeader(nonce, "EXECUTOR_NONCE_MISSING");

        long timestamp = parseTimestamp(timestampValue);
        validateTimestamp(timestamp);

        String configuredToken = configuredToken(deviceId);
        boolean authConfigured = configuredToken != null;
        if (!authConfigured && !controlProperties.getAuth().isAllowUnsignedDevices()) {
            throw ControlApiExceptions.unauthorized(ControlErrorCode.EXECUTOR_UNAUTHORIZED);
        }
        if (authConfigured) {
            requireHeader(signature, "EXECUTOR_SIGNATURE_MISSING");
            validateSignature(method, path, timestampValue, nonce, signature, configuredToken, body);
        }
        rememberNonce(deviceId, nonce);

        return new ExecutorAuthContext(deviceId, protocolVersion, timestamp, nonce, authConfigured);
    }

    private void validateTimestamp(long timestamp) {
        long skewMs = Duration.ofSeconds(controlProperties.getAuth().getAllowedTimestampSkewSeconds()).toMillis();
        long now = clock.millis();
        if (Math.abs(now - timestamp) > skewMs) {
            throw ControlApiExceptions.unauthorized("EXECUTOR_TIMESTAMP_INVALID");
        }
    }

    private void validateSignature(String method,
                                   String path,
                                   String timestamp,
                                   String nonce,
                                   String signature,
                                   String token,
                                   byte[] body) {
        String bodySha256 = sha256Hex(body == null ? new byte[0] : body);
        String content = method + path + timestamp + nonce + bodySha256;
        String expected = hmacSha256Hex(content, token);
        if (!MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8), signature.toLowerCase().getBytes(StandardCharsets.UTF_8))) {
            throw ControlApiExceptions.unauthorized("EXECUTOR_SIGNATURE_INVALID");
        }
    }

    private void rememberNonce(String deviceId, String nonce) {
        String key = controlProperties.getAuth().getNonceKeyPrefix() + deviceId + ":" + nonce;
        Duration ttl = Duration.ofSeconds(controlProperties.getAuth().getNonceTtlSeconds());
        Boolean stored = stringRedisTemplate.opsForValue().setIfAbsent(key, "1", ttl);
        if (!Boolean.TRUE.equals(stored)) {
            throw ControlApiExceptions.unauthorized("EXECUTOR_NONCE_REPLAYED");
        }
    }

    private String configuredToken(String deviceId) {
        Map<String, String> deviceTokens = controlProperties.getAuth().getDeviceTokens();
        if (deviceTokens == null) {
            return null;
        }
        String token = deviceTokens.get(deviceId);
        if (token == null || token.isBlank()) {
            return null;
        }
        return token;
    }

    private long parseTimestamp(String timestampValue) {
        try {
            return Long.parseLong(timestampValue);
        } catch (NumberFormatException exception) {
            throw ControlApiExceptions.badRequest("EXECUTOR_TIMESTAMP_INVALID");
        }
    }

    private void requireHeader(String value, String code) {
        if (value == null || value.isBlank()) {
            throw ControlApiExceptions.badRequest(code);
        }
    }

    private String sha256Hex(byte[] body) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(body));
        } catch (Exception exception) {
            throw ControlApiExceptions.internal("EXECUTOR_AUTH_INTERNAL_ERROR", exception);
        }
    }

    private String hmacSha256Hex(String content, String token) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(token.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(content.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw ControlApiExceptions.internal("EXECUTOR_AUTH_INTERNAL_ERROR", exception);
        }
    }
}
