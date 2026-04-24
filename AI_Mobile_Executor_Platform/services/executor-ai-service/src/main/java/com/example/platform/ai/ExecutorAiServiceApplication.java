package com.example.platform.ai;

import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ExecutorAiServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExecutorAiServiceApplication.class, args);
    }
}
