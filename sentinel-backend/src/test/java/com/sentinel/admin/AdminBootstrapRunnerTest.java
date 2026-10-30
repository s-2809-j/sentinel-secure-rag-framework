package com.sentinel.admin;

import com.sentinel.admin.bootstrap.AdminBootstrapRunner;
import com.sentinel.auth.model.Role;
import com.sentinel.auth.model.User;
import com.sentinel.auth.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.transaction.annotation.Transactional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.H2Dialect")
@Transactional
class AdminBootstrapRunnerTest {

    @Autowired UserRepository userRepository;

    private User seed(String name, Role role) {
        return userRepository.saveAndFlush(User.builder()
                .username(name).email(name + "@t.io").passwordHash("x").role(role).build());
    }

    private Role roleOf(String name) {
        return userRepository.findByUsername(name).orElseThrow().getRole();
    }

    @Test
    void promotes_whenNoAdminExists() {
        seed("first", Role.VIEWER);
        new AdminBootstrapRunner(userRepository, "first").run(null);
        assertEquals(Role.ADMIN, roleOf("first"));
    }

    @Test
    void noOp_whenAdminAlreadyExists() {
        seed("existing", Role.ADMIN);
        seed("first", Role.VIEWER);
        new AdminBootstrapRunner(userRepository, "first").run(null);
        assertEquals(Role.VIEWER, roleOf("first"));
    }

    @Test
    void noOp_whenPropertyBlank() {
        seed("first", Role.VIEWER);
        new AdminBootstrapRunner(userRepository, "").run(null);
        assertEquals(Role.VIEWER, roleOf("first"));
    }

    @Test
    void noOp_whenUserNotRegistered() {
        new AdminBootstrapRunner(userRepository, "ghost").run(null);
        assertFalse(userRepository.existsByRoleAndActiveTrue(Role.ADMIN));
    }
}