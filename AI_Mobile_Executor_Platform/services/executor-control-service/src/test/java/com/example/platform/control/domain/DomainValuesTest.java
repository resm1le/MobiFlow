package com.example.platform.control.domain;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DomainValuesTest {

    @Test
    void mapsSuccessToSucceededTask() {
        assertEquals(DomainValues.TASK_STATUS_SUCCEEDED, DomainValues.toTaskStatusFromFinalState("SUCCESS"));
        assertEquals(DomainValues.ATTEMPT_STATUS_SUCCEEDED, DomainValues.toAttemptStatusFromFinalState("SUCCESS"));
    }

    @Test
    void mapsCancelledToCancelledTask() {
        assertEquals(DomainValues.TASK_STATUS_CANCELLED, DomainValues.toTaskStatusFromFinalState("CANCELLED"));
        assertEquals(DomainValues.ATTEMPT_STATUS_CANCELLED, DomainValues.toAttemptStatusFromFinalState("CANCELLED"));
    }

    @Test
    void mapsFailureLikeStatesToFailedTask() {
        assertEquals(DomainValues.TASK_STATUS_FAILED, DomainValues.toTaskStatusFromFinalState("FAILED"));
        assertEquals(DomainValues.ATTEMPT_STATUS_PRECHECK_FAILED, DomainValues.toAttemptStatusFromFinalState("PRECHECK_FAILED"));
    }
}
