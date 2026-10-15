package com.gongsiradar.user;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface UserScopeRepository extends JpaRepository<UserScope, Long> {
    List<UserScope> findByUserId(Long userId);
}
