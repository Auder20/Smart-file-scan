package com.smartfileorganizer.utils;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import javafx.application.Platform;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

/**
 * WebSocketManager — gestiona la conexión WebSocket de seguimiento de escaneo
 * con reconexión automática y backoff exponencial.
 *
 * Problema anterior: si la conexión se caía durante un escaneo largo
 * (timeout de red, reinicio del backend, etc.) el frontend quedaba
 * congelado sin progreso ni error visible.
 *
 * Solución: reintenta hasta MAX_RETRIES veces con espera creciente
 * (1s, 2s, 4s, 8s, 16s). Si el escaneo ya terminó (mensaje "completed"
 * o "error") cancela los reintentos inmediatamente.
 */
public class WebSocketManager {

    private static final int    MAX_RETRIES      = 5;
    private static final long   BASE_DELAY_MS    = 1_000;
    private static final Gson   gson             = new Gson();

    private final OkHttpClient  client;
    private final String        wsUrl;
    private final Consumer<JsonObject> onMessage;
    private final Runnable             onComplete;
    private final Consumer<String>     onError;

    private WebSocket                  activeSocket;
    private final AtomicBoolean        finished    = new AtomicBoolean(false);
    private final AtomicInteger        retryCount  = new AtomicInteger(0);
    private final ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "WS-Reconnect");
            t.setDaemon(true);
            return t;
        });

    public WebSocketManager(
        OkHttpClient client, String scanId,
        Consumer<JsonObject> onMessage,
        Runnable onComplete,
        Consumer<String> onError
    ) {
        this.client     = client;
        this.wsUrl      = "ws://localhost:8000/api/scan/ws/scan/" + scanId;
        this.onMessage  = onMessage;
        this.onComplete = onComplete;
        this.onError    = onError;
    }

    /** Inicia la conexión. Llama desde el hilo principal o un background thread. */
    public void connect() {
        if (finished.get()) return;
        Request request = new Request.Builder().url(wsUrl).build();
        activeSocket = client.newWebSocket(request, new Listener());
    }

    /** Cierra la conexión y cancela reintentos pendientes. */
    public void close() {
        finished.set(true);
        scheduler.shutdownNow();
        if (activeSocket != null) {
            activeSocket.close(1000, "Closed by client");
            activeSocket = null;
        }
    }

    // ── Listener interno ──────────────────────────────────────────────────────

    private class Listener extends WebSocketListener {

        @Override
        public void onOpen(WebSocket ws, Response response) {
            retryCount.set(0); // conexión exitosa, resetear contador
        }

        @Override
        public void onMessage(WebSocket ws, String text) {
            try {
                JsonObject data = gson.fromJson(text, JsonObject.class);
                String type = data.has("type") ? data.get("type").getAsString() : "";

                // Marcar como terminado antes de notificar para evitar reintentos
                if ("completed".equals(type) || "error".equals(type)) {
                    finished.set(true);
                }

                Platform.runLater(() -> {
                    if (onMessage != null) onMessage.accept(data);
                    if ("completed".equals(type) && onComplete != null) onComplete.run();
                    if ("error".equals(type) && onError != null)
                        onError.accept(data.has("message") ? data.get("message").getAsString() : "Error");
                });
            } catch (Exception e) {
                System.err.println("[WS] Error parsing message: " + e.getMessage());
            }
        }

        @Override
        public void onFailure(WebSocket ws, Throwable t, Response response) {
            if (finished.get()) return;

            int attempt = retryCount.incrementAndGet();
            if (attempt > MAX_RETRIES) {
                finished.set(true);
                Platform.runLater(() -> {
                    if (onError != null)
                        onError.accept("Conexión WebSocket perdida tras " + MAX_RETRIES + " intentos.");
                });
                return;
            }

            // Backoff exponencial: 1s, 2s, 4s, 8s, 16s
            long delayMs = BASE_DELAY_MS * (1L << (attempt - 1));
            System.out.printf("[WS] Conexión perdida, reintentando en %dms (intento %d/%d)%n",
                delayMs, attempt, MAX_RETRIES);

            scheduler.schedule(() -> {
                if (!finished.get()) connect();
            }, delayMs, TimeUnit.MILLISECONDS);
        }

        @Override
        public void onClosed(WebSocket ws, int code, String reason) {
            // Cierre limpio: no reintentar
        }
    }
}