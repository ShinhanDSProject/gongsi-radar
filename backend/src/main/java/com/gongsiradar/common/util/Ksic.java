package com.gongsiradar.common.util;

import java.util.HashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 한국표준산업분류(KSIC 11) 코드 → 이름. OpenDART 기업개황의 induty_code(2~5자리)를 앞 두 자리(중분류)로 읽는다.
 * 시장 화면의 업종 트리와 기업 목록·상세의 업종 표시가 같은 표를 쓴다.
 */
public final class Ksic {

    private Ksic() {
    }

    /** KSIC 11 대분류(중분류 범위) */
    static final Object[][] KSIC_SECTIONS = {
            {"A", 1, 3, "농업, 임업 및 어업"}, {"B", 5, 8, "광업"}, {"C", 10, 34, "제조업"},
            {"D", 35, 35, "전기, 가스, 증기 및 공기조절 공급업"}, {"E", 36, 39, "수도, 하수 및 폐기물 처리, 원료 재생업"},
            {"F", 41, 42, "건설업"}, {"G", 45, 47, "도매 및 소매업"}, {"H", 49, 52, "운수 및 창고업"},
            {"I", 55, 56, "숙박 및 음식점업"}, {"J", 58, 63, "정보통신업"}, {"K", 64, 66, "금융 및 보험업"},
            {"L", 68, 68, "부동산업"}, {"M", 70, 73, "전문, 과학 및 기술 서비스업"},
            {"N", 74, 76, "사업시설 관리, 사업 지원 및 임대 서비스업"}, {"O", 84, 84, "공공 행정, 국방 및 사회보장 행정"},
            {"P", 85, 85, "교육 서비스업"}, {"Q", 86, 87, "보건업 및 사회복지 서비스업"},
            {"R", 90, 91, "예술, 스포츠 및 여가관련 서비스업"}, {"S", 94, 96, "협회 및 단체, 수리 및 기타 개인 서비스업"},
            {"T", 97, 98, "가구 내 고용활동 및 달리 분류되지 않은 자가 소비 생산활동"}, {"U", 99, 99, "국제 및 외국기관"},
    };
    static final Map<String, String> KSIC_DIVISIONS = new HashMap<>();

    static {
        String[] kv = {
                "10", "식료품 제조업", "11", "음료 제조업", "12", "담배 제조업", "13", "섬유제품 제조업", "14", "의복 제조업",
                "15", "가죽·가방·신발 제조업", "16", "목재 및 나무제품 제조업", "17", "펄프·종이 제조업", "18", "인쇄 및 기록매체 복제업",
                "19", "코크스·석유정제품 제조업", "20", "화학물질 및 화학제품 제조업", "21", "의료용 물질 및 의약품 제조업",
                "22", "고무 및 플라스틱제품 제조업", "23", "비금속 광물제품 제조업", "24", "1차 금속 제조업", "25", "금속 가공제품 제조업",
                "26", "전자부품·컴퓨터·영상·음향·통신장비 제조업", "27", "의료·정밀·광학 기기 및 시계 제조업", "28", "전기장비 제조업",
                "29", "기타 기계 및 장비 제조업", "30", "자동차 및 트레일러 제조업", "31", "기타 운송장비 제조업", "32", "가구 제조업",
                "33", "기타 제품 제조업", "34", "산업용 기계 및 장비 수리업", "35", "전기, 가스, 증기 및 공기조절 공급업",
                "36", "수도업", "37", "하수·폐수 및 분뇨 처리업", "38", "폐기물 수집·처리 및 원료 재생업", "39", "환경 정화 및 복원업",
                "41", "종합 건설업", "42", "전문직별 공사업", "45", "자동차 및 부품 판매업", "46", "도매 및 상품 중개업",
                "47", "소매업(자동차 제외)", "49", "육상 운송 및 파이프라인 운송업", "50", "수상 운송업", "51", "항공 운송업",
                "52", "창고 및 운송관련 서비스업", "55", "숙박업", "56", "음식점 및 주점업", "58", "출판업",
                "59", "영상·오디오 기록물 제작 및 배급업", "60", "방송업", "61", "우편 및 통신업",
                "62", "컴퓨터 프로그래밍·시스템 통합 및 관리업", "63", "정보서비스업", "64", "금융업", "65", "보험 및 연금업",
                "66", "금융 및 보험관련 서비스업", "68", "부동산업", "70", "연구개발업", "71", "전문 서비스업",
                "72", "건축기술·엔지니어링 및 기타 과학기술 서비스업", "73", "기타 전문·과학 및 기술 서비스업",
                "74", "사업시설 관리 및 조경 서비스업", "75", "사업 지원 서비스업", "76", "임대업(부동산 제외)", "85", "교육 서비스업",
                "86", "보건업", "87", "사회복지 서비스업", "90", "창작·예술 및 여가관련 서비스업", "91", "스포츠 및 오락관련 서비스업",
        };
        for (int i = 0; i < kv.length; i += 2) KSIC_DIVISIONS.put(kv[i], kv[i + 1]);
    }

    public static final String UNKNOWN_CODE = "?";
    public static final String UNKNOWN_NAME = "업종 미확인";
    private static final Pattern DIV2 = Pattern.compile("^\\s*(\\d{2})");

    /** 코드 → (대분류 문자, 이름). */
    public static String[] section(String code) {
        Matcher m = DIV2.matcher(code == null ? "" : code);
        if (!m.find()) return new String[]{UNKNOWN_CODE, UNKNOWN_NAME};
        int div = Integer.parseInt(m.group(1));
        for (Object[] s : KSIC_SECTIONS) {
            if ((Integer) s[1] <= div && div <= (Integer) s[2]) return new String[]{(String) s[0], (String) s[3]};
        }
        return new String[]{UNKNOWN_CODE, UNKNOWN_NAME};
    }

    /** 코드 → (중분류 두 자리, 이름). 표에 없는 중분류는 "중분류 NN". */
    public static String[] division(String code) {
        Matcher m = DIV2.matcher(code == null ? "" : code);
        if (!m.find()) return new String[]{"??", UNKNOWN_NAME};
        return new String[]{m.group(1), KSIC_DIVISIONS.getOrDefault(m.group(1), "중분류 " + m.group(1))};
    }

    /** 화면에 보일 업종 이름. 중분류 이름이 있으면 그것, 없으면 대분류 이름, 코드가 없으면 null. */
    public static String name(String code) {
        if (code == null || code.isBlank()) return null;
        String[] d = division(code);
        if (KSIC_DIVISIONS.containsKey(d[0])) return d[1];
        String[] s = section(code);
        return UNKNOWN_CODE.equals(s[0]) ? null : s[1];
    }
}
