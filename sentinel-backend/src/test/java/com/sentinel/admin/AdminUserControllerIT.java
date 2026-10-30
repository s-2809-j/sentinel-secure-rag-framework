package com.sentinel.admin;

import com.sentinel.auth.model.Role;
import com.sentinel.auth.model.User;
import com.sentinel.auth.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.H2Dialect")
@Transactional
class AdminUserControllerIT {

    private static final String BASE = "/api/v1/admin/users";

    @Autowired MockMvc mockMvc;
    @Autowired UserRepository userRepository;

    private User seed(String name, Role role) {
        return userRepository.saveAndFlush(User.builder()
                .username(name).email(name + "@t.io").passwordHash("x").role(role).build());
    }

    private String body(String role) {
        return "{\"role\":" + (role == null ? "null" : "\"" + role + "\"") + "}";
    }

    @Test
    void anonymous_gets401() throws Exception {
        mockMvc.perform(get(BASE)).andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "v", roles = "VIEWER")
    void viewer_gets403_onList() throws Exception {
        mockMvc.perform(get(BASE)).andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "a", roles = "ANALYST")
    void analyst_gets403_onPatch() throws Exception {
        User t = seed("target", Role.VIEWER);
        mockMvc.perform(patch(BASE + "/" + t.getId() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("ADMIN")))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "boss", roles = "ADMIN")
    void admin_lists_withoutPasswordHash() throws Exception {
        seed("boss", Role.ADMIN);
        mockMvc.perform(get(BASE))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].username").exists())
                .andExpect(jsonPath("$[0].passwordHash").doesNotExist())
                .andExpect(jsonPath("$[0].password").doesNotExist());
    }

    @Test
    @WithMockUser(username = "boss", roles = "ADMIN")
    void admin_canPromote_andDemote() throws Exception {
        seed("boss", Role.ADMIN);
        User t = seed("alice", Role.VIEWER);

        mockMvc.perform(patch(BASE + "/" + t.getId() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("ANALYST")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("ANALYST"));
        assertEquals(Role.ANALYST, userRepository.findById(t.getId()).orElseThrow().getRole());

        mockMvc.perform(patch(BASE + "/" + t.getId() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("VIEWER")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("VIEWER"));
    }

    @Test
    @WithMockUser(username = "boss", roles = "ADMIN")
    void sameRole_isNoOp200() throws Exception {
        seed("boss", Role.ADMIN);
        User t = seed("alice", Role.VIEWER);
        mockMvc.perform(patch(BASE + "/" + t.getId() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("VIEWER")))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "boss", roles = "ADMIN")
    void selfChange_isRejected403() throws Exception {
        User self = seed("boss", Role.ADMIN);
        seed("second", Role.ADMIN);
        mockMvc.perform(patch(BASE + "/" + self.getId() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("VIEWER")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode").value("SELF_ROLE_CHANGE"));
    }

    @Test
    @WithMockUser(username = "someone-else", roles = "ADMIN")
    void lastAdmin_cannotBeDemoted409() throws Exception {
        User solo = seed("solo", Role.ADMIN);
        mockMvc.perform(patch(BASE + "/" + solo.getId() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("VIEWER")))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode").value("LAST_ADMIN"));
        assertEquals(Role.ADMIN, userRepository.findById(solo.getId()).orElseThrow().getRole());
    }

    @Test
    @WithMockUser(username = "someone-else", roles = "ADMIN")
    void admin_canBeDemoted_whenAnotherAdminExists() throws Exception {
        User a = seed("adm1", Role.ADMIN);
        seed("adm2", Role.ADMIN);
        mockMvc.perform(patch(BASE + "/" + a.getId() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("VIEWER")))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "boss", roles = "ADMIN")
    void unknownUser_is404() throws Exception {
        mockMvc.perform(patch(BASE + "/" + UUID.randomUUID() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("ANALYST")))
                .andExpect(status().isNotFound());
    }

    @Test
    @WithMockUser(username = "boss", roles = "ADMIN")
    void invalidRole_is400() throws Exception {
        User t = seed("alice", Role.VIEWER);
        mockMvc.perform(patch(BASE + "/" + t.getId() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("SUPERUSER")))
                .andExpect(status().isBadRequest());
    }

    @Test
    @WithMockUser(username = "boss", roles = "ADMIN")
    void nullRole_is400() throws Exception {
        User t = seed("alice", Role.VIEWER);
        mockMvc.perform(patch(BASE + "/" + t.getId() + "/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body(null)))
                .andExpect(status().isBadRequest());
    }

    @Test
    @WithMockUser(username = "boss", roles = "ADMIN")
    void malformedId_is400() throws Exception {
        mockMvc.perform(patch(BASE + "/not-a-uuid/role")
                        .contentType(MediaType.APPLICATION_JSON).content(body("ANALYST")))
                .andExpect(status().isBadRequest());
    }
}