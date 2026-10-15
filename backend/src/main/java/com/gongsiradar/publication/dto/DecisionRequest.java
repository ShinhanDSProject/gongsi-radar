package com.gongsiradar.publication.dto;

import jakarta.validation.constraints.Size;

/** 승인이면 comment, 반려면 reason을 쓴다. 둘 다 없어도 통과하지만 남기는 편이 낫다. */
public record DecisionRequest(
        @Size(max = 500) String comment,
        @Size(max = 500) String reason
) {}
