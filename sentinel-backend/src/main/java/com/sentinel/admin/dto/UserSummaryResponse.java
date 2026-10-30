package com.sentinel.admin.dto;

import com.sentinel.auth.model.Role;
import com.sentinel.auth.model.User;

import java.util.UUID;

public record UserSummaryResponse(UUID id, String username, String email, Role role, boolean active) {

    public static UserSummaryResponse from(User u) {
        return new UserSummaryResponse(u.getId(), u.getUsername(), u.getEmail(), u.getRole(), u.isActive());
    }
}