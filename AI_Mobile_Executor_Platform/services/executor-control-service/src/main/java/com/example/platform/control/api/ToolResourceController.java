package com.example.platform.control.api;

import com.example.platform.control.application.ToolResourceService;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;

@RestController
@RequestMapping("/tools/resources")
public class ToolResourceController {

    private final ToolResourceService toolResourceService;

    public ToolResourceController(ToolResourceService toolResourceService) {
        this.toolResourceService = toolResourceService;
    }

    @PostMapping("/read")
    public ToolApiModels.ReadResourceResponse read(@RequestBody ToolApiModels.ReadResourceRequest request) {
        return toolResourceService.read(request.handle());
    }

    @GetMapping("/{handle}/download")
    public ResponseEntity<InputStreamResource> download(@PathVariable String handle) {
        ToolResourceService.ToolResourceDownload resource = toolResourceService.download(handle);
        return ResponseEntity.ok()
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename(resource.fileName(), StandardCharsets.UTF_8)
                                .build()
                                .toString()
                )
                .contentType(MediaType.parseMediaType(resource.mimeType()))
                .body(new InputStreamResource(resource.inputStream()));
    }
}
