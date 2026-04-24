package com.example.autoa11y.executor.reporting

import com.example.autoa11y.executor.control.ArtifactDescriptor
import com.example.autoa11y.executor.control.ExecutorClient

class ArtifactUploader(
    private val client: ExecutorClient,
    private val buffer: LocalDeliveryStore,
    private val deviceIdProvider: () -> String
) {
    fun upload(attemptId: String, artifact: ArtifactDescriptor): Boolean {
        val result = client.uploadArtifactDetailed(attemptId, artifact)
        if (!result.ok) {
            buffer.enqueueArtifact(deviceIdProvider(), attemptId, artifact)
        }
        return result.ok
    }
}
