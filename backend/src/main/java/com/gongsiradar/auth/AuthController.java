package com.gongsiradar.auth;

import com.gongsiradar.auth.dto.LoginRequest;
import com.gongsiradar.auth.dto.LoginResponse;
import com.gongsiradar.auth.dto.RefreshRequest;
import com.gongsiradar.auth.dto.RefreshResponse;
import com.gongsiradar.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/login")
    public ApiResponse<LoginResponse> login(@Valid @RequestBody LoginRequest req) {
        return ApiResponse.success(authService.login(req));
    }

    @PostMapping("/refresh")
    public ApiResponse<RefreshResponse> refresh(@Valid @RequestBody RefreshRequest req) {
        return ApiResponse.success(authService.refresh(req.refreshToken()));
    }

    /**
     * Stateless라 서버가 지울 세션이 없다. 토큰 폐기는 클라이언트가 저장소에서 지우는 것으로 끝난다.
     * 엔드포인트를 두는 이유는 프런트가 로그아웃 흐름을 한 곳으로 맞추게 하기 위해서다.
     */
    @PostMapping("/logout")
    public ApiResponse<Void> logout() {
        return ApiResponse.success(null);
    }
}
