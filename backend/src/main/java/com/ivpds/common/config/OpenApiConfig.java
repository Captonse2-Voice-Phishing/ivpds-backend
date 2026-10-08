package com.ivpds.common.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Cấu hình tài liệu OpenAPI / Swagger UI của backend. */
@Configuration
public class OpenApiConfig {

    private static final String BEARER = "bearerAuth";

    /**
     * Khai báo thông tin chung của API và cơ chế xác thực bằng JWT (Bearer token),
     * để nút "Authorize" trên Swagger UI hoạt động.
     */
    @Bean
    public OpenAPI ivpdsOpenApi() {
        return new OpenAPI()
                .info(new Info()
                        .title("IVPDS Backend API")
                        .description("Intelligent Voice Phishing Detection System: REST API for the mobile app and admin web.")
                        .version("v1"))
                .components(new Components().addSecuritySchemes(BEARER, new SecurityScheme()
                        .type(SecurityScheme.Type.HTTP)
                        .scheme("bearer")
                        .bearerFormat("JWT")))
                // Mặc định mọi API đều cần Bearer token; API công khai tự bỏ yêu cầu này bằng @SecurityRequirements.
                .addSecurityItem(new SecurityRequirement().addList(BEARER));
    }
}
