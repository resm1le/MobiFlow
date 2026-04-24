package com.example.autoa11y.executor.control

class DeviceRegistrar(
    private val client: ExecutorClient,
    private val identityProvider: () -> ExecutorIdentity
) {
    fun register(): Boolean = client.register(identityProvider())
}

class HeartbeatScheduler(private val intervalMs: Long) {
    private var lastSentAt: Long = 0L

    fun shouldSend(now: Long = System.currentTimeMillis()): Boolean = now - lastSentAt >= intervalMs

    fun markSent(now: Long = System.currentTimeMillis()) {
        lastSentAt = now
    }
}

class TaskPoller(
    private val client: ExecutorClient,
    private val identityProvider: () -> ExecutorIdentity
) {
    fun claim(): RemoteTask? = client.claimTask(identityProvider())
}

class TaskDispatcher {
    private val lock = Any()
    private var currentTaskId: String? = null
    private var currentAttemptId: String? = null
    private var currentTaskType: String? = null
    private var currentLeaseExpireAt: Long? = null

    fun tryBegin(task: RemoteTask): Boolean = synchronized(lock) {
        if (currentAttemptId != null) return@synchronized false
        currentTaskId = task.taskId
        currentAttemptId = task.attemptId
        currentTaskType = task.taskType
        currentLeaseExpireAt = task.leaseExpireAt
        true
    }

    fun finish(attemptId: String) = synchronized(lock) {
        if (currentAttemptId == attemptId) {
            currentTaskId = null
            currentAttemptId = null
            currentTaskType = null
            currentLeaseExpireAt = null
        }
    }

    fun currentTaskId(): String? = synchronized(lock) { currentTaskId }
    fun currentAttemptId(): String? = synchronized(lock) { currentAttemptId }
    fun currentTaskType(): String? = synchronized(lock) { currentTaskType }
    fun currentLeaseExpireAt(): Long? = synchronized(lock) { currentLeaseExpireAt }
    fun isBusy(): Boolean = synchronized(lock) { currentAttemptId != null }
    fun isIdle(): Boolean = synchronized(lock) { currentAttemptId == null }
}
