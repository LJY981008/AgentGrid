# Agent Grid backend — multi-stage build
# build: 컨텍스트는 backend/ (compose.yaml 의 build.context 참조)

FROM eclipse-temurin:21-jdk AS build
WORKDIR /app
# 의존성 레이어 캐시: wrapper/빌드 스크립트 먼저
COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN ./gradlew dependencies --no-daemon -q || true
COPY src ./src
RUN ./gradlew bootJar --no-daemon -q

FROM eclipse-temurin:21-jre-alpine
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
USER app
COPY --from=build /app/build/libs/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
