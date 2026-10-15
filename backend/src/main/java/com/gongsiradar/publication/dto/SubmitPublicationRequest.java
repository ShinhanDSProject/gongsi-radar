package com.gongsiradar.publication.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record SubmitPublicationRequest(
        @NotNull Long reportId,
        @Size(max = 500) String comment
) {}
