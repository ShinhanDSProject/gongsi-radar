package com.gongsiradar.data;

/**
 * 원천에서 데이터를 받지 못했다(파이썬 radar의 {@code SourceError}).
 * <p>
 * "데이터 없음(OpenDART 013)"도 여기에 든다. 호출하는 쪽은 이 예외를 사유로 바꿔 notes에 남기고 계속한다 —
 * 값이 없다고 0으로 채우지 않는다. 내부 데이터 API는 이 예외를 404 {@code {"detail": ...}}로 내보낸다.
 */
public class DataSourceException extends RuntimeException {

    public DataSourceException(String message) {
        super(message);
    }

    public DataSourceException(String message, Throwable cause) {
        super(message, cause);
    }
}
