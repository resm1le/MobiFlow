package com.example.autoa11y.executor.control

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class ExecutorClientSignatureTest {
    @Test
    fun signatureUsesDirectConcatenationWhenTokenPresent() {
        val token = "test-token"
        val method = "post"
        val path = "/executor/register"
        val timestamp = "1770000000000"
        val nonce = "nonce-1"
        val body = """{"deviceId":"abc"}""".toByteArray(StandardCharsets.UTF_8)

        val actual = ExecutorRequestSigner.buildSignature(token, method, path, timestamp, nonce, body)
        val expected = hmacSha256Hex(
            key = token,
            text = method.uppercase() + path + timestamp + nonce + sha256Hex(body)
        )

        assertEquals(expected, actual)
    }

    @Test
    fun signatureIsEmptyWhenTokenMissing() {
        val actual = ExecutorRequestSigner.buildSignature(
            token = "",
            method = "POST",
            path = "/executor/heartbeat",
            timestamp = "1770000000000",
            nonce = "nonce-1",
            bodyBytes = "{}".toByteArray(StandardCharsets.UTF_8)
        )

        assertEquals("", actual)
    }

    @Test
    fun pathChangeChangesSignature() {
        val token = "test-token"
        val timestamp = "1770000000000"
        val nonce = "nonce-1"
        val body = "{}".toByteArray(StandardCharsets.UTF_8)

        val registerSig = ExecutorRequestSigner.buildSignature(token, "POST", "/executor/register", timestamp, nonce, body)
        val heartbeatSig = ExecutorRequestSigner.buildSignature(token, "POST", "/executor/heartbeat", timestamp, nonce, body)

        assertNotEquals(registerSig, heartbeatSig)
    }

    @Test
    fun bodyChangeChangesSignature() {
        val token = "test-token"
        val method = "POST"
        val path = "/executor/tasks/claim"
        val timestamp = "1770000000000"
        val nonce = "nonce-1"

        val sigA = ExecutorRequestSigner.buildSignature(token, method, path, timestamp, nonce, """{"a":1}""".toByteArray(StandardCharsets.UTF_8))
        val sigB = ExecutorRequestSigner.buildSignature(token, method, path, timestamp, nonce, """{"a":2}""".toByteArray(StandardCharsets.UTF_8))

        assertNotEquals(sigA, sigB)
    }

    private fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    private fun hmacSha256Hex(key: String, text: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key.toByteArray(StandardCharsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(text.toByteArray(StandardCharsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }
}
