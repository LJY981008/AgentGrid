package com.agentgrid;

import org.springframework.boot.SpringApplication;

/**
 * 로컬 인프라(compose) 없이 앱 실행: `./gradlew bootTestRun`
 * — Testcontainers 가 PG/RabbitMQ/Redis 를 자동 기동·연결한다.
 */
public class TestAgentgridBackendApplication {

	public static void main(String[] args) {
		SpringApplication.from(AgentgridBackendApplication::main).with(TestcontainersConfiguration.class).run(args);
	}

}
