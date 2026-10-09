package com.ivpds;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.List;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;

/** Real SMTP server that captures mail (same image as docker-compose), with access to what it received. */
public class MailpitContainer extends GenericContainer<MailpitContainer> {

    private static final int SMTP_PORT = 1025;
    private static final int HTTP_PORT = 8025;

    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();

    public MailpitContainer() {
        super("axllent/mailpit:v1.31.3");
        withExposedPorts(SMTP_PORT, HTTP_PORT);
        waitingFor(Wait.forHttp("/readyz").forPort(HTTP_PORT));
    }

    public int smtpPort() {
        return getMappedPort(SMTP_PORT);
    }

    /** Plain-text bodies of all captured messages addressed to the given recipient. */
    public List<String> messageTextsTo(String address) {
        List<String> texts = new ArrayList<>();
        for (JsonNode message : get("/api/v1/messages?limit=500").get("messages")) {
            for (JsonNode to : message.get("To")) {
                if (address.equalsIgnoreCase(to.get("Address").asText())) {
                    texts.add(get("/api/v1/message/" + message.get("ID").asText()).get("Text").asText());
                }
            }
        }
        return texts;
    }

    private JsonNode get(String path) {
        URI uri = URI.create("http://" + getHost() + ":" + getMappedPort(HTTP_PORT) + path);
        try {
            HttpResponse<String> response = http.send(HttpRequest.newBuilder(uri).build(),
                    HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() != 200) {
                throw new IllegalStateException("Mailpit returned " + response.statusCode() + " for " + path);
            }
            return json.readTree(response.body());
        } catch (IOException e) {
            throw new IllegalStateException("Could not query Mailpit", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while querying Mailpit", e);
        }
    }
}
