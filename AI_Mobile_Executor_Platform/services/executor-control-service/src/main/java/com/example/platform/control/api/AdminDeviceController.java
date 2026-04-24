package com.example.platform.control.api;

import com.example.platform.control.api.AdminApiModels.AttemptSummary;
import com.example.platform.control.api.AdminApiModels.CommandAcceptedResponse;
import com.example.platform.control.api.AdminApiModels.CreateCommandRequest;
import com.example.platform.control.api.AdminApiModels.DeviceResponse;
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
@RequestMapping("/api/devices")
public class AdminDeviceController {

    private final AdminApiService adminApiService;

    public AdminDeviceController(AdminApiService adminApiService) {
        this.adminApiService = adminApiService;
    }

    @GetMapping
    public List<DeviceResponse> list() {
        return adminApiService.listDevices();
    }

    @GetMapping("/{deviceId}")
    public DeviceResponse get(@PathVariable String deviceId) {
        return adminApiService.getDevice(deviceId);
    }

    @PostMapping("/{deviceId}/resume")
    public DeviceResponse resume(@PathVariable String deviceId) {
        return adminApiService.resumeDevice(deviceId);
    }

    @GetMapping("/{deviceId}/attempts")
    public List<AttemptSummary> attempts(@PathVariable String deviceId) {
        return adminApiService.getDeviceAttempts(deviceId);
    }

    @PostMapping("/{deviceId}/commands")
    public CommandAcceptedResponse command(@PathVariable String deviceId, @Valid @RequestBody CreateCommandRequest request) {
        return adminApiService.enqueueCommand(deviceId, request);
    }
}
