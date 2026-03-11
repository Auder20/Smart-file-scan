package com.smartfileorganizer.api;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import okhttp3.*;

import java.io.IOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class ApiClient {

    private static final String BASE_URL = "http://localhost:8000";
    private static final Gson gson = new Gson();

    // Un solo cliente OkHttp compartido por toda la app
    // OkHttp gestiona internamente el pool de conexiones
    private static final OkHttpClient client = new OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(300, TimeUnit.SECONDS)  // 5 min para scans grandes
        .build();

    private static final MediaType JSON = MediaType.get("application/json");

    // ── Health check ────────────────────────────────────────────────────────

    public static CompletableFuture<Boolean> isBackendReady() {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request request = new Request.Builder()
                    .url(BASE_URL + "/api/health")
                    .build();
                try (Response response = client.newCall(request).execute()) {
                    return response.isSuccessful();
                }
            } catch (IOException e) {
                return false;
            }
        });
    }

    // ── Iniciar escaneo ─────────────────────────────────────────────────────

    public static CompletableFuture<String> startScan(String path) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                JsonObject body = new JsonObject();
                body.addProperty("path", path);

                Request request = new Request.Builder()
                    .url(BASE_URL + "/api/scan")
                    .post(RequestBody.create(body.toString(), JSON))
                    .build();

                try (Response response = client.newCall(request).execute()) {
                    if (!response.isSuccessful()) {
                        throw new RuntimeException("Error al iniciar scan: " + response.code());
                    }
                    JsonObject json = gson.fromJson(response.body().string(), JsonObject.class);
                    return json.get("scan_id").getAsString();
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    // ── Consultar progreso ──────────────────────────────────────────────────

    public static CompletableFuture<JsonObject> getScanProgress(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request request = new Request.Builder()
                    .url(BASE_URL + "/api/scan/" + scanId + "/progress")
                    .build();

                try (Response response = client.newCall(request).execute()) {
                    return gson.fromJson(response.body().string(), JsonObject.class);
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    // ── Obtener resultado completo ──────────────────────────────────────────

    public static CompletableFuture<JsonObject> getScanResult(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request request = new Request.Builder()
                    .url(BASE_URL + "/api/scan/" + scanId)
                    .build();

                try (Response response = client.newCall(request).execute()) {
                    return gson.fromJson(response.body().string(), JsonObject.class);
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    // ── Estadísticas ────────────────────────────────────────────────────────

    public static CompletableFuture<JsonObject> getStats(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request request = new Request.Builder()
                    .url(BASE_URL + "/api/stats/" + scanId)
                    .build();

                try (Response response = client.newCall(request).execute()) {
                    return gson.fromJson(response.body().string(), JsonObject.class);
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    // ── Duplicados ──────────────────────────────────────────────────────────

    public static CompletableFuture<JsonObject> getDuplicates(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request request = new Request.Builder()
                    .url(BASE_URL + "/api/duplicates/" + scanId)
                    .build();

                try (Response response = client.newCall(request).execute()) {
                    return gson.fromJson(response.body().string(), JsonObject.class);
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }
}