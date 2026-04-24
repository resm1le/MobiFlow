package com.example.platform.control.application;

import com.example.platform.control.api.ExecutorAuthContext;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.web.server.ResponseStatusException;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

class ExecutorAuthServiceTest {

    private StringRedisTemplate stringRedisTemplate;
    private ValueOperations<String, String> valueOperations;
    private ControlProperties properties;
    private ExecutorAuthService authService;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        stringRedisTemplate = Mockito.mock(StringRedisTemplate.class);
        valueOperations = Mockito.mock(ValueOperations.class);
        when(stringRedisTemplate.opsForValue()).thenReturn(valueOperations);

        properties = new ControlProperties();
        properties.getAuth().setAllowUnsignedDevices(false);
        properties.getAuth().setDeviceTokens(Map.of("device-1", "secret-token"));
        authService = new ExecutorAuthService(properties, stringRedisTemplate);
    }

    @Test
    void authenticatesConfiguredDeviceWithValidSignature() throws Exception {
        when(valueOperations.setIfAbsent(anyString(), anyString(), any(Duration.class))).thenReturn(true);
        byte[] body = "{\"deviceId\":\"device-1\"}".getBytes(StandardCharsets.UTF_8);
        String timestamp = String.valueOf(Instant.now().toEpochMilli());
        String signature = sign("POST", "/executor/register", timestamp, "nonce-1", body, "secret-token");

        ExecutorAuthContext context = authService.authenticate(
                "POST",
                "/executor/register",
                "device-1",
                "v1",
                timestamp,
                "nonce-1",
                signature,
                body
        );

        assertEquals("device-1", context.deviceId());
        assertTrue(context.authConfigured());
    }

    @Test
    void rejectsDeviceWithoutConfiguredTokenWhenUnsignedDevicesDisabled() {
        when(valueOperations.setIfAbsent(anyString(), anyString(), any(Duration.class))).thenReturn(true);
        byte[] body = "{\"deviceId\":\"device-2\"}".getBytes(StandardCharsets.UTF_8);
        String timestamp = String.valueOf(Instant.now().toEpochMilli());

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () ->
                authService.authenticate(
                        "POST",
                        "/executor/register",
                        "device-2",
                        "v1",
                        timestamp,
                        "nonce-2",
                        null,
                        body
                ));

        assertEquals(ControlErrorCode.EXECUTOR_UNAUTHORIZED, exception.getReason());
    }

    @Test
    void allowsDeviceWithoutConfiguredTokenWhenUnsignedDevicesEnabled() {
        properties.getAuth().setAllowUnsignedDevices(true);
        when(valueOperations.setIfAbsent(anyString(), anyString(), any(Duration.class))).thenReturn(true);
        byte[] body = "{\"deviceId\":\"device-2\"}".getBytes(StandardCharsets.UTF_8);
        String timestamp = String.valueOf(Instant.now().toEpochMilli());

        ExecutorAuthContext context = authService.authenticate(
                "POST",
                "/executor/register",
                "device-2",
                "v1",
                timestamp,
                "nonce-2",
                null,
                body
        );

        assertEquals("device-2", context.deviceId());
        assertFalse(context.authConfigured());
    }

    @Test
    void rejectsReplayNonce() throws Exception {
        when(valueOperations.setIfAbsent(anyString(), anyString(), any(Duration.class))).thenReturn(false);
        byte[] body = "{\"deviceId\":\"device-1\"}".getBytes(StandardCharsets.UTF_8);
        String timestamp = String.valueOf(Instant.now().toEpochMilli());
        String signature = sign("POST", "/executor/register", timestamp, "nonce-3", body, "secret-token");

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () ->
                authService.authenticate("POST", "/executor/register", "device-1", "v1", timestamp, "nonce-3", signature, body));

        assertEquals("EXECUTOR_NONCE_REPLAYED", exception.getReason());
    }

    @Test
    void rejectsOutOfWindowTimestamp() {
        byte[] body = "{\"deviceId\":\"device-1\"}".getBytes(StandardCharsets.UTF_8);
        String timestamp = String.valueOf(Instant.now().minusSeconds(1000).toEpochMilli());

        ResponseStatusException exception = assertThrows(ResponseStatusException.class, () ->
                authService.authenticate("POST", "/executor/register", "device-1", "v1", timestamp, "nonce-4", "ignored", body));

        assertEquals("EXECUTOR_TIMESTAMP_INVALID", exception.getReason());
    }

    private String sign(String method, String path, String timestamp, String nonce, byte[] body, String token) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        String bodySha256 = HexFormat.of().formatHex(digest.digest(body));
        String content = method + path + timestamp + nonce + bodySha256;

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(token.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        return HexFormat.of().formatHex(mac.doFinal(content.getBytes(StandardCharsets.UTF_8)));
    }
}
