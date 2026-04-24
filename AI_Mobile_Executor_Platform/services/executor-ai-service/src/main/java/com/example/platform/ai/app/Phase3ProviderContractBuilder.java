package com.example.platform.ai.app;

import com.example.platform.ai.api.dto.FailureTriageContext;
import com.example.platform.ai.api.dto.RunPlanningContext;
import com.example.platform.ai.api.dto.RunSummaryContext;
import org.springframework.stereotype.Component;

import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class Phase3ProviderContractBuilder {

    public Map<String, Object> buildRunPlanningContract(RunPlanningContext context) {
        Map<String, Object> contract = new LinkedHashMap<>();
        contract.put("type", "run-planning");
        contract.put("context", context);
        contract.put("requirements", Map.of(
                "mustReturnCanonicalRunDraft", true,
                "mustNotInventSourceOrCreatedBy", true
        ));
        return contract;
    }

    public Map<String, Object> buildFailureTriageContract(FailureTriageContext context) {
        Map<String, Object> contract = new LinkedHashMap<>();
        contract.put("type", "failure-triage");
        contract.put("context", context);
        contract.put("requirements", Map.of(
                "mustUseCanonicalEnums", true,
                "mustNotTriggerPlatformSideEffects", true
        ));
        return contract;
    }

    public Map<String, Object> buildRunSummaryContract(RunSummaryContext context) {
        Map<String, Object> contract = new LinkedHashMap<>();
        contract.put("type", "run-summary");
        contract.put("context", context);
        contract.put("requirements", Map.of(
                "mustReturnCanonicalRunSummary", true,
                "mustCiteConcreteRunEvidence", true
        ));
        return contract;
    }
}
