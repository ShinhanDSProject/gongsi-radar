package com.gongsiradar.data.source;

/**
 * 원천에 연결 자체가 안 된다(연속 연결 실패로 호출을 잠시 멈춘 상태 포함).
 * <p>
 * "데이터 없음(013)"과 달리 다시 시도하면 될 수도 있는 실패다. 그래서 수집은 이 예외를 받으면 대상을 '확인함'으로
 * 표시하지 않고 단계를 멈춘다(다음 실행이 이어서 한다). 화면은 '데이터 없음'이 아니라 '연결 실패'로 보여 준다.
 */
public class SourceUnavailableException extends DataSourceException {
    public SourceUnavailableException(String message) {
        super(message);
    }

    public SourceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
