package com.sentinel.admin.bootstrap;

import com.sentinel.auth.model.Role;
import com.sentinel.auth.repository.UserRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Slf4j
@Component
public class AdminBootstrapRunner implements ApplicationRunner {

    private final UserRepository userRepository;
    private final String bootstrapUsername;

    public AdminBootstrapRunner(UserRepository userRepository,
                                @Value("${sentinel.bootstrap-admin-username:}") String bootstrapUsername) {
        this.userRepository = userRepository;
        this.bootstrapUsername = bootstrapUsername;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (bootstrapUsername == null || bootstrapUsername.isBlank()) {
            return;
        }
        if (userRepository.existsByRoleAndActiveTrue(Role.ADMIN)) {
            return;
        }
        userRepository.findByUsername(bootstrapUsername.trim()).ifPresentOrElse(user -> {
            user.setRole(Role.ADMIN);
            userRepository.save(user);
            log.warn("No ADMIN existed. Bootstrapped '{}' to ADMIN. Unset BOOTSTRAP_ADMIN_USERNAME now.",
                    user.getUsername());
        }, () -> log.warn("BOOTSTRAP_ADMIN_USERNAME is set but user '{}' is not registered; nothing changed.",
                bootstrapUsername));
    }
}