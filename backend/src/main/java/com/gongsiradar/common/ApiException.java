package com.gongsiradar.common;

import lombok.Getter;

@Getter
public class ApiException extends RuntimeException {
    private final ErrorCode errorCode;
    private final Object details;

    public ApiException(ErrorCode errorCode, String message) {
        super(message);
        this.errorCode = errorCode;
        this.details = null;
    }

    public ApiException(ErrorCode errorCode, String message, Object details) {
        super(message);
        this.errorCode = errorCode;
        this.details = details;
    }
}
