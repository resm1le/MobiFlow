package com.example.platform.control.application;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

public final class ControlApiExceptions {

    private ControlApiExceptions() {
    }

    public static ResponseStatusException badRequest(String code) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, code);
    }

    public static ResponseStatusException unauthorized(String code) {
        return new ResponseStatusException(HttpStatus.UNAUTHORIZED, code);
    }

    public static ResponseStatusException forbidden(String code) {
        return new ResponseStatusException(HttpStatus.FORBIDDEN, code);
    }

    public static ResponseStatusException notFound(String code) {
        return new ResponseStatusException(HttpStatus.NOT_FOUND, code);
    }

    public static ResponseStatusException conflict(String code) {
        return new ResponseStatusException(HttpStatus.CONFLICT, code);
    }

    public static ResponseStatusException gone(String code) {
        return new ResponseStatusException(HttpStatus.GONE, code);
    }

    public static ResponseStatusException badGateway(String code) {
        return new ResponseStatusException(HttpStatus.BAD_GATEWAY, code);
    }

    public static ResponseStatusException internal(String code, Throwable cause) {
        return new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, code, cause);
    }
}
