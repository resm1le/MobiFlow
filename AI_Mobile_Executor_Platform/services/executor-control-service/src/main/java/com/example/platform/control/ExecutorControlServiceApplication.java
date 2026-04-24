package com.example.platform.control;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@MapperScan("com.example.platform.control.infrastructure.mapper")
@ConfigurationPropertiesScan("com.example.platform.control.application")
@EnableScheduling
public class ExecutorControlServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExecutorControlServiceApplication.class, args);
    }
}
