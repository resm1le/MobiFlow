package com.example.platform.control.api;

import com.example.platform.control.api.AdminApiModels.CreateHeterogeneousRunRequest;
import com.example.platform.control.api.ExecutorApiModels.ArtifactPolicy;
import com.example.platform.control.api.ExecutorApiModels.RunConfig;
import com.example.platform.control.application.ExperimentRunService;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertSame;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AdminRunControllerTest {

    @Test
    void createHeterogeneousDelegatesToRunService() {
        ExperimentRunService service = mock(ExperimentRunService.class);
        AdminRunController controller = new AdminRunController(service);
        CreateHeterogeneousRunRequest request = new CreateHeterogeneousRunRequest(
                "mixed", null, "PLUGIN_RUN",
                new RunConfig(1, 60_000, 0, false, 15_000, 30_000),
                new ArtifactPolicy(true, true, true),
                100, List.of(), "agent", "agent", 0, 300_000L, List.of()
        );
        AdminApiModels.ExperimentRunDetailResponse expected = mock(AdminApiModels.ExperimentRunDetailResponse.class);
        when(service.createHeterogeneousRun(request)).thenReturn(expected);

        assertSame(expected, controller.createHeterogeneous(request));
        verify(service).createHeterogeneousRun(request);
    }
}
