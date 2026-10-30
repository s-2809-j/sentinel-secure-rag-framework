package com.sentinel.admin.dto;

import com.sentinel.auth.model.Role;
import jakarta.validation.constraints.NotNull;

public record RoleChangeRequest(@NotNull(message = "role is required") Role role) {}