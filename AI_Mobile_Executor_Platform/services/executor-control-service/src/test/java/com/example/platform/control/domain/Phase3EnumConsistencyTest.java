package com.example.platform.control.domain;

import com.example.platform.control.application.Phase3AiModels;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Guards the otherwise-unreferenced {@code DomainValues.PHASE3_*} string sets against
 * silent drift from the authoritative {@link Phase3AiModels} enums. If an enum value is
 * added or removed on one side without the other, this test fails.
 *
 * <p>Scope note: this locks the two copies that live inside the control module. The
 * executor-ai-service holds a third copy of these enums in its own {@code api/dto}
 * package; because the two services are independent Maven builds with no shared module,
 * that copy cannot be asserted from here and remains a separate drift risk.
 */
class Phase3EnumConsistencyTest {

    private static Set<String> names(Class<? extends Enum<?>> enumType) {
        return Arrays.stream(enumType.getEnumConstants())
                .map(Enum::name)
                .collect(Collectors.toSet());
    }

    @Test
    void failureCategoryEnumMatchesDomainValues() {
        assertEquals(
                DomainValues.PHASE3_FAILURE_CATEGORIES,
                names(Phase3AiModels.FailureCategory.class));
    }

    @Test
    void retryRecommendationEnumMatchesDomainValues() {
        assertEquals(
                DomainValues.PHASE3_RETRY_RECOMMENDATIONS,
                names(Phase3AiModels.RetryRecommendation.class));
    }

    @Test
    void suggestedNextActionEnumMatchesDomainValues() {
        assertEquals(
                DomainValues.PHASE3_SUGGESTED_NEXT_ACTIONS,
                names(Phase3AiModels.SuggestedNextAction.class));
    }

    @Test
    void deviceSnapshotTypeEnumMatchesDomainValues() {
        assertEquals(
                DomainValues.PHASE3_DEVICE_SNAPSHOT_TYPES,
                names(Phase3AiModels.DeviceOperationalSnapshotType.class));
    }
}
