package com.gongsiradar.data.source;

import java.util.List;
import java.util.Map;

/**
 * 데이터 소스. 샘플(가상 기업)·OpenDART·적재 DB를 같은 인터페이스로 다룬다(파이썬 {@code radar/sources/base.py}와 같은 메서드).
 * <p>
 * 반환 모양은 원천 응답 그대로다(OpenDART·공공데이터포털 필드 이름, snake_case). 내부 데이터 API가 이 값을
 * 가공하지 않고 AI 서버로 넘기므로, radar 파이프라인 코드는 소스가 바뀐 것을 모른다.
 * 데이터가 없으면 {@link DataSourceException}을 던진다(시세처럼 "없으면 빈 목록"인 메서드는 예외 없이 빈 값).
 */
public interface RadarSource {

    /** {@code sample} 또는 {@code opendart}. 적재 DB 래퍼도 원천 이름을 그대로 돌려준다. */
    String name();

    /** 실제 원천 호출 수(캐시 적중은 세지 않는다). 수집 작업의 호출 예산이 이 값의 증가분으로 센다. */
    long calls();

    /** 종목코드·고유번호·회사명 → {@code {corp_code, corp_name, stock_code, ...}} */
    Map<String, Object> resolve(String query);

    /** 사업연도·보고서 종류의 정기보고서(정정 반영 최종본). {@code {…list 행, bsns_year, reprt_code, url}} */
    Map<String, Object> findReport(String corpCode, int bsnsYear, String reprtCode);

    /** 원문 ZIP(document.xml) 바이트 */
    byte[] document(String rceptNo);

    /** 단일회사 전체 재무(fnlttSinglAcntAll). 연결(CFS)이 없으면 별도(OFS) */
    Financials financials(String corpCode, int bsnsYear, String reprtCode);

    /** 다중회사 주요계정(fnlttMultiAcnt) — 업종 피어 */
    List<Map<String, Object>> peers(String corpCode, int bsnsYear, String reprtCode);

    /** 소송 등 제기(lwstLg). bgn·end는 YYYYMMDD */
    List<Map<String, Object>> lawsuits(String corpCode, String bgn, String end);

    /** 상장사 목록 {@code [{corp_code, corp_name, stock_code, induty, induty_code, market}]} */
    List<Map<String, Object>> companies();

    /** 정기보고서 목록 {@code [{rcept_no, report_nm, rcept_dt, reprt_code, bsns_year, hasDocument}]} 최신순 */
    List<Map<String, Object>> filings(String corpCode);

    /** {@code {shareholders, executives, investments, rcept_no}} — hyslrSttus·exctvSttus·otrCprInvstmntSttus 행 그대로 */
    Map<String, Object> governance(String corpCode, int bsnsYear, String reprtCode);

    /** 시세(getStockPriceInfo 행), 최신일 먼저. 키가 없으면 빈 목록 */
    List<Map<String, Object>> market(String stockCode);

    /** 종목코드 → 일별 시세 행(시장 화면). 삽입 순서를 지킨다 */
    Map<String, List<Map<String, Object>>> marketHistory();

    /** 공식 지수(코스피·코스닥) 일별 종가. 없으면 빈 목록 → 시장 화면이 대체 지수를 만든다 */
    List<Map<String, Object>> indexSeries(String name);

    /** 최근 정기공시(list 행 + reprt_code·bsns_year·hasDocument), 접수일·접수번호 내림차순 */
    List<Map<String, Object>> recentFilings();

    /** 기업개황의 업종 코드(KSIC). 모르면 null */
    String indutyCode(String corpCode);

    /** 적재 DB를 읽고 있는가(시장 화면의 {@code ingested}·신규 확인 기업 표시). */
    default boolean ingested() {
        return false;
    }

    /** 최근 처음 확인한 기업. 적재 DB가 없으면 빈 목록 */
    default List<Map<String, Object>> newListings(int days) {
        return List.of();
    }

    /** 재무 행과 쓴 범위(CFS·OFS) */
    record Financials(List<Map<String, Object>> rows, String fsDiv) {
    }
}
