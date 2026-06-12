package com.agentgrid;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;

/**
 * 통합 스모크 테스트 — Testcontainers(PG/RabbitMQ/Redis) 기동 후 컨텍스트 로드 검증.
 * 자가 검증 루프의 베이스라인: 빈 배선/설정 오류를 커밋 전에 잡는다.
 */
@Import(TestcontainersConfiguration.class)
@SpringBootTest
class AgentgridBackendApplicationTests {

	@Test
	void contextLoads() {
	}

}
