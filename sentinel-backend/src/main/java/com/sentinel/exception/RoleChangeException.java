package com.sentinel.exception;

public class RoleChangeException extends SentinelException {

    public static final String SELF_ROLE_CHANGE = "SELF_ROLE_CHANGE";
    public static final String LAST_ADMIN = "LAST_ADMIN";

    public RoleChangeException(String errorCode, String message) {
        super(errorCode, message);
    }
}