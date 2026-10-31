package com.sentinel.config;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.fasterxml.jackson.module.paramnames.ParameterNamesModule;
import com.sentinel.fastapi.exception.FastApiException;
import feign.RequestInterceptor;
import feign.codec.Decoder;
import feign.codec.ErrorDecoder;
import feign.jackson.JacksonDecoder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

// NO @Configuration — Feign-scoped only, not global Spring context
public class FastApiClientConfig {

    @Bean
    public ObjectMapper fastApiObjectMapper() {
        return new ObjectMapper()
                .registerModule(new ParameterNamesModule())
                .registerModule(new JavaTimeModule())
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
    }

    @Bean
    public Decoder feignDecoder(ObjectMapper fastApiObjectMapper) {
        return new JacksonDecoder(fastApiObjectMapper);
    }

    @Bean
    public ErrorDecoder feignErrorDecoder() {
        return (methodKey, response) -> new FastApiException(
                "FastAPI error [" + methodKey + "] HTTP " + response.status()
        );
    }

    @Bean
    public RequestInterceptor fastapiAuthInterceptor(
            @Value("${fastapi.service-token}") String serviceToken) {
        return template -> template.header("X-Service-Token", serviceToken);
    }
}