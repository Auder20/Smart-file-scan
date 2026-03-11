FROM eclipse-temurin:17

RUN apt-get update && apt-get install -y maven && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pom.xml .
RUN mvn dependency:resolve -q

CMD ["tail", "-f", "/dev/null"]