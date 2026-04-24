package com.example.platform.control.api;

import com.example.platform.control.application.AdminApiService;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.mockito.Mockito.mock;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ApiExceptionHandlerTest {

    @Test
    void taskValidationMapsToTaskStateInvalid() throws Exception {
        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new AdminTaskController(mock(AdminApiService.class)))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();

        mockMvc.perform(post("/api/tasks")
                        .contentType("application/json")
                        .content("""
                                {
                                  "taskType": "",
                                  "profilePackage": "com.google.android.apps.maps",
                                  "taskPayload": {},
                                  "runConfig": {
                                    "loopCount": 1,
                                    "budgetMs": 60000,
                                    "loopIntervalMs": 0,
                                    "networkIsolationEnabled": false,
                                    "pollIntervalMs": 15000,
                                    "heartbeatIntervalMs": 30000
                                  },
                                  "artifactPolicy": {
                                    "uploadLog": true,
                                    "uploadScreenshot": true,
                                    "uploadDump": false
                                  }
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("TASK_STATE_INVALID"));
    }
}
