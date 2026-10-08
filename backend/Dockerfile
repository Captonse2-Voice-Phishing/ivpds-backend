FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -B -q dependency:go-offline
COPY src src
# Tests run on the host/CI (they will need Docker for Testcontainers), not during the image build.
RUN mvn -B -q package -DskipTests

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S ivpds && adduser -S ivpds -G ivpds
USER ivpds
WORKDIR /app
COPY --from=build /src/target/ivpds-backend.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]
