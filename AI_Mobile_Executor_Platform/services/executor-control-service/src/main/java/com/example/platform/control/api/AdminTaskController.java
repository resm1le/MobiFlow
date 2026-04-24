package com.example.platform.control.api;

import com.example.platform.control.api.AdminApiModels.CreateTaskRequest;
import com.example.platform.control.api.AdminApiModels.TaskResponse;
import com.example.platform.control.application.AdminApiService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/tasks")
public class AdminTaskController {

    private final AdminApiService adminApiService;

    public AdminTaskController(AdminApiService adminApiService) {
        this.adminApiService = adminApiService;
    }

    @PostMapping
    public TaskResponse create(@Valid @RequestBody CreateTaskRequest request) {
        return adminApiService.createTask(request);
    }

    @GetMapping
    public List<TaskResponse> list() {
        return adminApiService.listTasks();
    }

    @GetMapping("/{taskId}")
    public TaskResponse get(@PathVariable String taskId) {
        return adminApiService.getTask(taskId);
    }

    @PostMapping("/{taskId}/cancel")
    public void cancel(@PathVariable String taskId) {
        adminApiService.cancelTask(taskId);
    }
}
