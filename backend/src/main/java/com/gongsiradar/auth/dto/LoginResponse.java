package com.gongsiradar.auth.dto;

import java.util.List;

public record LoginResponse(
        String accessToken,
        String refreshToken,
        UserInfo user
) {
    public record UserInfo(String userId, String name, String role, List<String> scopes) {}
}
