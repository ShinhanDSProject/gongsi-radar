package com.gongsiradar.report.repository;

/**
 * 리포트 결재 상태. 생성 시 DRAFT → 발행 요청 PENDING → 승인 APPROVED(잠김) / 반려 REJECTED(다시 수정·재요청 가능).
 * <p>
 * PENDING·APPROVED에서는 본문을 고칠 수 없다. 결재자가 본 내용과 발행되는 내용이 같아야 한다.
 */
public enum ApprovalStatus {
    DRAFT, PENDING, APPROVED, REJECTED;

    public boolean locked() {
        return this == PENDING || this == APPROVED;
    }
}
