package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.ArtifactPolicyDto;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class RunPlanningIntentExtractor {

    private static final Pattern DURATION_PATTERN = Pattern.compile(
            "(\\d+)\\s*(ms|msec|milliseconds?|sec|secs|seconds?|min|mins|minutes?|\\u6beb\\u79d2|\\u79d2|\\u79d2\\u949f|\\u5206|\\u5206\\u949f)",
            Pattern.CASE_INSENSITIVE
    );
    private static final Pattern LOOP_COUNT_PATTERN = Pattern.compile(
            "(?:(?:repeat|loop)\\s*(\\d+)\\s*(?:times?))|(?:(\\d+)\\s*(?:times?|x))|(?:(?:\\u91cd\\u590d|\\u5faa\\u73af)\\s*(\\d+)\\s*\\u6b21)|(?:(\\d+)\\s*\\u6b21)",
            Pattern.CASE_INSENSITIVE
    );
    private static final Map<String, String> PROFILE_KEYWORDS = Map.ofEntries(
            Map.entry("tik tok", "com.zhiliaoapp.musically"),
            Map.entry("tiktok", "com.zhiliaoapp.musically"),
            Map.entry("\u6296\u97f3", "com.zhiliaoapp.musically"),
            Map.entry("google maps", "com.google.android.apps.maps"),
            Map.entry("maps", "com.google.android.apps.maps"),
            Map.entry("\u8c37\u6b4c\u5730\u56fe", "com.google.android.apps.maps"),
            Map.entry("shein", "com.zzkko")
    );
    private static final Map<String, Integer> PRIORITY_KEYWORDS = Map.ofEntries(
            Map.entry("urgent", 200),
            Map.entry("high priority", 200),
            Map.entry("critical", 200),
            Map.entry("\u7d27\u6025", 200),
            Map.entry("low priority", 50),
            Map.entry("\u4f4e\u4f18\u5148\u7ea7", 50)
    );
    private static final List<String> NETWORK_ISOLATION_KEYWORDS = List.of(
            "offline",
            "no network",
            "without network",
            "network isolation",
            "\u79bb\u7ebf",
            "\u65e0\u7f51\u7edc",
            "\u65ad\u7f51"
    );

    public RunPlanningIntentSignals extract(RunPlanningContext context) {
        String normalizedGoal = normalize(context.goal());
        JsonNode constraints = context.constraints();
        return new RunPlanningIntentSignals(
                resolveDevicePoolId(constraints, normalizedGoal, context.availableDevicePools()),
                resolveProfilePackage(constraints, normalizedGoal),
                resolvePriority(constraints, normalizedGoal),
                resolveLoopCount(constraints, normalizedGoal),
                resolveBudgetMs(constraints, normalizedGoal),
                resolveNetworkIsolation(constraints, normalizedGoal),
                resolveTaskType(constraints, normalizedGoal),
                resolveMaxRetriesPerDevice(constraints),
                resolveQueueTimeoutMs(constraints),
                resolveArtifactPolicy(constraints, normalizedGoal)
        );
    }

    private String resolveDevicePoolId(JsonNode constraints,
                                       String normalizedGoal,
                                       List<RunPlanningContext.AvailableDevicePoolDto> pools) {
        String explicit = textConstraint(constraints, "devicePoolId");
        if (explicit != null) {
            return explicit;
        }
        for (RunPlanningContext.AvailableDevicePoolDto pool : pools) {
            if (normalizedGoal.contains(pool.poolId().toLowerCase(Locale.ROOT))
                    || normalizedGoal.contains(pool.name().toLowerCase(Locale.ROOT))) {
                return pool.poolId();
            }
        }
        return null;
    }

    private String resolveProfilePackage(JsonNode constraints, String normalizedGoal) {
        String explicit = textConstraint(constraints, "profilePackage");
        if (explicit != null) {
            return explicit;
        }
        for (Map.Entry<String, String> entry : PROFILE_KEYWORDS.entrySet()) {
            if (normalizedGoal.contains(entry.getKey())) {
                return entry.getValue();
            }
        }
        return null;
    }

    private Integer resolvePriority(JsonNode constraints, String normalizedGoal) {
        Integer explicit = integerConstraint(constraints, "priority");
        if (explicit != null) {
            return explicit;
        }
        for (Map.Entry<String, Integer> entry : PRIORITY_KEYWORDS.entrySet()) {
            if (normalizedGoal.contains(entry.getKey().toLowerCase(Locale.ROOT))) {
                return entry.getValue();
            }
        }
        return null;
    }

    private Integer resolveLoopCount(JsonNode constraints, String normalizedGoal) {
        Integer explicit = integerConstraint(objectConstraint(constraints, "runConfig"), "loopCount");
        if (explicit != null) {
            return explicit;
        }
        explicit = integerConstraint(constraints, "loopCount");
        if (explicit != null) {
            return explicit;
        }
        Matcher matcher = LOOP_COUNT_PATTERN.matcher(normalizedGoal);
        if (!matcher.find()) {
            return null;
        }
        for (int index = 1; index <= matcher.groupCount(); index++) {
            String value = matcher.group(index);
            if (value != null) {
                return Integer.parseInt(value);
            }
        }
        return null;
    }

    private Long resolveBudgetMs(JsonNode constraints, String normalizedGoal) {
        Long explicit = longConstraint(objectConstraint(constraints, "runConfig"), "budgetMs");
        if (explicit != null) {
            return explicit;
        }
        explicit = longConstraint(constraints, "budgetMs");
        if (explicit != null) {
            return explicit;
        }
        Matcher matcher = DURATION_PATTERN.matcher(normalizedGoal);
        if (!matcher.find()) {
            return null;
        }
        long value = Long.parseLong(matcher.group(1));
        String unit = matcher.group(2).toLowerCase(Locale.ROOT);
        if (unit.startsWith("min") || unit.equals("\u5206") || unit.equals("\u5206\u949f")) {
            return value * 60_000L;
        }
        if (unit.startsWith("sec") || unit.equals("\u79d2") || unit.equals("\u79d2\u949f")) {
            return value * 1_000L;
        }
        return value;
    }

    private Boolean resolveNetworkIsolation(JsonNode constraints, String normalizedGoal) {
        Boolean explicit = booleanConstraint(objectConstraint(constraints, "runConfig"), "networkIsolationEnabled");
        if (explicit != null) {
            return explicit;
        }
        explicit = booleanConstraint(constraints, "networkIsolationEnabled");
        if (explicit != null) {
            return explicit;
        }
        return NETWORK_ISOLATION_KEYWORDS.stream()
                .map(keyword -> keyword.toLowerCase(Locale.ROOT))
                .anyMatch(normalizedGoal::contains) ? Boolean.TRUE : null;
    }

    private String resolveTaskType(JsonNode constraints, String normalizedGoal) {
        String explicit = textConstraint(constraints, "taskType");
        if (explicit != null) {
            return explicit;
        }
        if (normalizedGoal.contains("smoke") || normalizedGoal.contains("\u9a8c\u8bc1")) {
            return "PLUGIN_SMOKE";
        }
        if (normalizedGoal.contains("debug") || normalizedGoal.contains("\u8c03\u8bd5")) {
            return "LOCAL_DEBUG";
        }
        return null;
    }

    private Integer resolveMaxRetriesPerDevice(JsonNode constraints) {
        Integer explicit = integerConstraint(constraints, "maxRetriesPerDevice");
        if (explicit != null) {
            return explicit;
        }
        return integerConstraint(objectConstraint(constraints, "runConfig"), "maxRetriesPerDevice");
    }

    private Long resolveQueueTimeoutMs(JsonNode constraints) {
        Long explicit = longConstraint(constraints, "queueTimeoutMs");
        if (explicit != null) {
            return explicit;
        }
        return longConstraint(objectConstraint(constraints, "runConfig"), "queueTimeoutMs");
    }

    private ArtifactPolicyDto resolveArtifactPolicy(JsonNode constraints, String normalizedGoal) {
        JsonNode artifactPolicy = objectConstraint(constraints, "artifactPolicy");
        Boolean uploadLog = booleanConstraint(artifactPolicy, "uploadLog");
        Boolean uploadScreenshot = booleanConstraint(artifactPolicy, "uploadScreenshot");
        Boolean uploadDump = booleanConstraint(artifactPolicy, "uploadDump");

        boolean goalLog = normalizedGoal.contains("log") || normalizedGoal.contains("\u65e5\u5fd7");
        boolean goalScreenshot = normalizedGoal.contains("screenshot") || normalizedGoal.contains("\u622a\u56fe");
        boolean goalDump = normalizedGoal.contains("dump") || normalizedGoal.contains("\u754c\u9762\u7ed3\u6784");
        if (uploadLog == null && uploadScreenshot == null && uploadDump == null && !goalLog && !goalScreenshot && !goalDump) {
            return null;
        }
        return new ArtifactPolicyDto(
                Boolean.TRUE.equals(uploadLog) || goalLog,
                Boolean.TRUE.equals(uploadScreenshot) || goalScreenshot,
                Boolean.TRUE.equals(uploadDump) || goalDump
        );
    }

    private String normalize(String goal) {
        return goal == null ? "" : goal.toLowerCase(Locale.ROOT);
    }

    private JsonNode objectConstraint(JsonNode constraints, String key) {
        if (constraints == null || constraints.isMissingNode() || !constraints.isObject()) {
            return null;
        }
        JsonNode value = constraints.get(key);
        return value != null && value.isObject() ? value : null;
    }

    private String textConstraint(JsonNode constraints, String key) {
        if (constraints == null || constraints.isMissingNode() || !constraints.isObject()) {
            return null;
        }
        JsonNode value = constraints.get(key);
        return value != null && value.isTextual() && !value.asText().isBlank() ? value.asText() : null;
    }

    private Integer integerConstraint(JsonNode constraints, String key) {
        if (constraints == null || constraints.isMissingNode() || !constraints.isObject()) {
            return null;
        }
        JsonNode value = constraints.get(key);
        return value != null && value.canConvertToInt() ? value.asInt() : null;
    }

    private Long longConstraint(JsonNode constraints, String key) {
        if (constraints == null || constraints.isMissingNode() || !constraints.isObject()) {
            return null;
        }
        JsonNode value = constraints.get(key);
        return value != null && value.canConvertToLong() ? value.asLong() : null;
    }

    private Boolean booleanConstraint(JsonNode constraints, String key) {
        if (constraints == null || constraints.isMissingNode() || !constraints.isObject()) {
            return null;
        }
        JsonNode value = constraints.get(key);
        return value != null && value.isBoolean() ? value.asBoolean() : null;
    }
}
