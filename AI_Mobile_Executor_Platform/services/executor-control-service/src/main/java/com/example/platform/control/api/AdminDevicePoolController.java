package com.example.platform.control.api;

import com.example.platform.control.api.AdminApiModels.CreateDevicePoolRequest;
import com.example.platform.control.api.AdminApiModels.DevicePoolResponse;
import com.example.platform.control.application.ExperimentRunService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/device-pools")
public class AdminDevicePoolController {

    private final ExperimentRunService experimentRunService;

    public AdminDevicePoolController(ExperimentRunService experimentRunService) {
        this.experimentRunService = experimentRunService;
    }

    @GetMapping
    public List<DevicePoolResponse> list() {
        return experimentRunService.listDevicePools();
    }

    @PostMapping
    public DevicePoolResponse create(@Valid @RequestBody CreateDevicePoolRequest request) {
        return experimentRunService.createDevicePool(request);
    }

    @GetMapping("/{poolId}")
    public DevicePoolResponse get(@PathVariable String poolId) {
        return experimentRunService.getDevicePool(poolId);
    }
}
