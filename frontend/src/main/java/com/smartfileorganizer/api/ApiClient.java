package com.smartfileorganizer.api;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.smartfileorganizer.utils.WebSocketManager;
import okhttp3.*;

import java.io.IOException;
import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import javafx.application.Platform;

public class ApiClient {

    private static final String BASE_URL = "http://localhost:8000";
    private static final Gson   gson     = new Gson();
    private static final MediaType JSON  = MediaType.get("application/json");

    private static final OkHttpClient httpClient = new OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(300, TimeUnit.SECONDS)
        .writeTimeout(300, TimeUnit.SECONDS)
        .build();

    // FIX: WebSocketManager reemplaza el WebSocket raw anterior,
    // añadiendo reconexión automática con backoff exponencial.
    private WebSocketManager wsManager;

    public ApiClient() {}

    // ── Health ────────────────────────────────────────────────────────────────

    public static CompletableFuture<Boolean> isBackendReady() {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder().url(BASE_URL + "/api/health").build();
                try (Response r = httpClient.newCall(req).execute()) { return r.isSuccessful(); }
            } catch (IOException e) { return false; }
        });
    }

    // ── Scanner ───────────────────────────────────────────────────────────────

    public CompletableFuture<String> startScanAsync(String path, int maxDepth, boolean includeHidden) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                JsonObject body = new JsonObject();
                body.addProperty("path", path);
                body.addProperty("max_depth", maxDepth);
                body.addProperty("include_hidden", includeHidden);
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/scan")
                    .post(RequestBody.create(body.toString(), JSON))
                    .build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error al iniciar scan: " + r.code());
                    return gson.fromJson(r.body().string(), JsonObject.class).get("scan_id").getAsString();
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public String startScan(String path, int maxDepth, boolean includeHidden) throws Exception {
        return startScanAsync(path, maxDepth, includeHidden).get();
    }

    public CompletableFuture<com.smartfileorganizer.models.ScanProgress> getScanProgressAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder().url(BASE_URL + "/api/scan/" + scanId + "/progress").build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error progreso: " + r.code());
                    JsonObject j = gson.fromJson(r.body().string(), JsonObject.class);
                    return new com.smartfileorganizer.models.ScanProgress(
                        j.get("scan_id").getAsString(), j.get("status").getAsString(),
                        j.get("progress").getAsDouble(), j.get("files_found").getAsInt(),
                        j.get("message").getAsString());
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public com.smartfileorganizer.models.ScanProgress getScanProgress(String scanId) throws Exception {
        return getScanProgressAsync(scanId).get();
    }

    public CompletableFuture<com.smartfileorganizer.models.ScanResult> getScanResultAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder().url(BASE_URL + "/api/scan/" + scanId).build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error resultado: " + r.code());
                    JsonObject j = gson.fromJson(r.body().string(), JsonObject.class);
                    return new com.smartfileorganizer.models.ScanResult(
                        j.get("scan_id").getAsString(), j.get("root_path").getAsString(),
                        j.get("status").getAsString(), j.get("total_files").getAsInt(),
                        j.get("total_size").getAsLong(), j.get("duration_sec").getAsDouble());
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public com.smartfileorganizer.models.ScanResult getScanResult(String scanId) throws Exception {
        return getScanResultAsync(scanId).get();
    }

    public CompletableFuture<Map<String, Object>> getScanFilesAsync(String scanId, int page, int pageSize) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                HttpUrl url = HttpUrl.parse(BASE_URL + "/api/scan/" + scanId + "/files")
                    .newBuilder()
                    .addQueryParameter("page", String.valueOf(page))
                    .addQueryParameter("page_size", String.valueOf(pageSize))
                    .build();
                try (Response r = httpClient.newCall(new Request.Builder().url(url).build()).execute()) {
                    if (!r.isSuccessful()) throw new IOException("Unexpected code " + r);
                    return gson.fromJson(r.body().string(), Map.class);
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public Map<String, Object> getScanFiles(String scanId, int page, int pageSize) throws Exception {
        return getScanFilesAsync(scanId, page, pageSize).get();
    }

    public CompletableFuture<List<Map<String, Object>>> listAllScansAsync() {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder().url(BASE_URL + "/api/scan/all").build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error listando scans: " + r.code());
                    JsonArray arr = gson.fromJson(r.body().string(), JsonArray.class);
                    List<Map<String, Object>> scans = new ArrayList<>();
                    for (JsonElement el : arr) {
                        JsonObject o = el.getAsJsonObject();
                        Map<String, Object> m = new HashMap<>();
                        m.put("scan_id",      safeStr(o, "scan_id"));
                        m.put("status",       safeStr(o, "status"));
                        m.put("files_found",  safeInt(o, "files_found"));
                        m.put("progress",     safeDouble(o, "progress"));
                        m.put("root_path",    safeStr(o, "root_path"));
                        m.put("total_files",  safeInt(o, "total_files"));
                        m.put("total_size",   safeLong(o, "total_size"));
                        m.put("scanned_at",   safeStr(o, "scanned_at"));
                        m.put("duration_sec", safeDouble(o, "duration_sec"));
                        scans.add(m);
                    }
                    return scans;
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public List<Map<String, Object>> listScans() throws Exception {
        return listAllScansAsync().get();
    }

    public CompletableFuture<Void> deleteScanAsync(String scanId) {
        return CompletableFuture.runAsync(() -> {
            try {
                Request req = new Request.Builder().url(BASE_URL + "/api/scan/" + scanId).delete().build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error eliminando scan: " + r.code());
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public void deleteScan(String scanId) throws Exception {
        deleteScanAsync(scanId).get();
    }

    // ── Stats ─────────────────────────────────────────────────────────────────

    public CompletableFuture<Map<String, Object>> getStatsAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder().url(BASE_URL + "/api/stats/" + scanId).build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error stats: " + r.code());
                    JsonObject j = gson.fromJson(r.body().string(), JsonObject.class);
                    Map<String, Object> result = new HashMap<>();
                    result.put("total_files",    safeInt(j, "total_files"));
                    result.put("total_size",     safeLong(j, "total_size"));
                    result.put("empty_files",    safeInt(j, "empty_files"));
                    result.put("old_files_count",safeInt(j, "old_files_count"));
                    result.put("old_files_size", safeLong(j, "old_files_size"));
                    result.put("by_category",    j.get("by_category").getAsJsonArray());
                    return result;
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public Map<String, Object> getStats(String scanId) throws Exception {
        return getStatsAsync(scanId).get();
    }

    // ── Files ─────────────────────────────────────────────────────────────────

    public CompletableFuture<List<Map<String, Object>>> getLargestFilesAsync(String scanId, int limit) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/files/" + scanId + "/largest?limit=" + limit).build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error archivos grandes: " + r.code());
                    JsonArray arr = gson.fromJson(r.body().string(), JsonArray.class);
                    List<Map<String, Object>> files = new ArrayList<>();
                    for (JsonElement el : arr) {
                        JsonObject o = el.getAsJsonObject();
                        Map<String, Object> m = new HashMap<>();
                        m.put("name", safeStr(o, "name")); m.put("path", safeStr(o, "path"));
                        m.put("size", safeLong(o, "size")); m.put("modified", safeStr(o, "modified"));
                        m.put("category", safeStr(o, "category"));
                        files.add(m);
                    }
                    return files;
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public CompletableFuture<List<Map<String, Object>>> getExtensionStatsAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/files/" + scanId + "/extensions").build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error extensiones: " + r.code());
                    JsonArray arr = gson.fromJson(r.body().string(), JsonArray.class);
                    List<Map<String, Object>> exts = new ArrayList<>();
                    for (JsonElement el : arr) {
                        JsonObject o = el.getAsJsonObject();
                        Map<String, Object> m = new HashMap<>();
                        m.put("extension", safeStr(o, "extension")); m.put("count", safeInt(o, "count"));
                        m.put("total_size", safeLong(o, "total_size")); m.put("percentage", safeDouble(o, "percentage"));
                        exts.add(m);
                    }
                    return exts;
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    // ── Duplicates ────────────────────────────────────────────────────────────

    public CompletableFuture<Map<String, Object>> getDuplicatesAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder().url(BASE_URL + "/api/duplicates/" + scanId).build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error duplicados: " + r.code());
                    JsonObject j = gson.fromJson(r.body().string(), JsonObject.class);
                    Map<String, Object> result = new HashMap<>();
                    result.put("total_groups",     safeInt(j, "total_groups"));
                    result.put("total_duplicates", safeInt(j, "total_duplicates"));
                    result.put("total_wasted",     safeLong(j, "total_wasted"));
                    result.put("analyzed_files",   safeInt(j, "analyzed_files"));
                    result.put("groups",           j.get("groups").getAsJsonArray());
                    return result;
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public Map<String, Object> getDuplicates(String scanId) throws Exception {
        return getDuplicatesAsync(scanId).get();
    }

    public CompletableFuture<Map<String, Object>> deleteFilesAsync(List<String> paths, boolean useRecycle) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                JsonObject body = new JsonObject();
                JsonArray arr = new JsonArray();
                paths.forEach(arr::add);
                body.add("paths", arr);
                body.addProperty("use_recycle", useRecycle);
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/duplicates/files")
                    .delete(RequestBody.create(body.toString(), JSON))
                    .build();
                try (Response r = httpClient.newCall(req).execute()) {
                    if (!r.isSuccessful()) throw new RuntimeException("Error eliminando archivos: " + r.code());
                    JsonObject j = gson.fromJson(r.body().string(), JsonObject.class);
                    Map<String, Object> result = new HashMap<>();
                    result.put("deleted_count", safeInt(j, "deleted_count"));
                    result.put("space_freed",   safeLong(j, "space_freed"));
                    List<String> deleted = new ArrayList<>(), failed = new ArrayList<>();
                    if (j.has("deleted")) j.get("deleted").getAsJsonArray().forEach(e -> deleted.add(e.getAsString()));
                    if (j.has("failed"))  j.get("failed").getAsJsonArray().forEach(e -> failed.add(e.getAsString()));
                    result.put("deleted", deleted); result.put("failed", failed);
                    return result;
                }
            } catch (IOException e) { throw new RuntimeException(e); }
        });
    }

    public Map<String, Object> deleteFiles(List<String> paths, boolean useRecycle) throws Exception {
        return deleteFilesAsync(paths, useRecycle).get();
    }

    // ── Explorer ──────────────────────────────────────────────────────────────

    public List<Map<String, Object>> getAvailableDrives() throws Exception {
        Request req = new Request.Builder().url(BASE_URL + "/api/explorer/drives").build();
        try (Response r = httpClient.newCall(req).execute()) {
            if (!r.isSuccessful()) throw new RuntimeException("Error drives: " + r.code());
            JsonArray arr = gson.fromJson(r.body().string(), JsonArray.class);
            List<Map<String, Object>> drives = new ArrayList<>();
            for (JsonElement el : arr) {
                JsonObject o = el.getAsJsonObject();
                Map<String, Object> m = new HashMap<>();
                m.put("name", safeStr(o, "name")); m.put("path", safeStr(o, "path"));
                if (o.has("total_space") && !o.get("total_space").isJsonNull()) m.put("total_space", o.get("total_space").getAsLong());
                if (o.has("free_space")  && !o.get("free_space").isJsonNull())  m.put("free_space",  o.get("free_space").getAsLong());
                if (o.has("used_space")  && !o.get("used_space").isJsonNull())  m.put("used_space",  o.get("used_space").getAsLong());
                if (o.has("filesystem")  && !o.get("filesystem").isJsonNull())  m.put("filesystem",  safeStr(o, "filesystem"));
                if (o.has("is_removable")) m.put("is_removable", o.get("is_removable").getAsBoolean());
                drives.add(m);
            }
            return drives;
        }
    }

    public List<Map<String, Object>> exploreFolders(String path, boolean includeHidden, int maxDepth) throws Exception {
        String url = BASE_URL + "/api/explorer/folders?path="
            + java.net.URLEncoder.encode(path, "UTF-8")
            + "&include_hidden=" + includeHidden + "&max_depth=" + maxDepth;
        try (Response r = httpClient.newCall(new Request.Builder().url(url).build()).execute()) {
            if (!r.isSuccessful()) throw new RuntimeException("Error folders: " + r.code());
            JsonArray arr = gson.fromJson(r.body().string(), JsonArray.class);
            List<Map<String, Object>> folders = new ArrayList<>();
            for (JsonElement el : arr) {
                JsonObject o = el.getAsJsonObject();
                Map<String, Object> m = new HashMap<>();
                m.put("name", safeStr(o, "name")); m.put("path", safeStr(o, "path"));
                m.put("is_directory", o.has("is_directory") && o.get("is_directory").getAsBoolean());
                if (o.has("size")       && !o.get("size").isJsonNull())       m.put("size",       o.get("size").getAsLong());
                if (o.has("file_count") && !o.get("file_count").isJsonNull()) m.put("file_count", o.get("file_count").getAsInt());
                folders.add(m);
            }
            return folders;
        }
    }

    public Map<String, Object> validateScanPath(String path) throws Exception {
        String url = BASE_URL + "/api/explorer/validate-path?path="
            + java.net.URLEncoder.encode(path, "UTF-8");
        try (Response r = httpClient.newCall(new Request.Builder().url(url).build()).execute()) {
            if (!r.isSuccessful()) throw new RuntimeException("Error validate: " + r.code());
            JsonObject j = gson.fromJson(r.body().string(), JsonObject.class);
            Map<String, Object> result = new HashMap<>();
            result.put("valid", j.get("valid").getAsBoolean());
            if (j.has("reason"))          result.put("reason",          safeStr(j, "reason"));
            if (j.has("suggestion"))      result.put("suggestion",      safeStr(j, "suggestion"));
            if (j.has("estimated_files")) result.put("estimated_files", safeInt(j, "estimated_files"));
            if (j.has("message"))         result.put("message",         safeStr(j, "message"));
            return result;
        }
    }

    // ── WebSocket con reconexión automática ───────────────────────────────────

    /**
     * FIX: reemplaza la conexión WebSocket raw por WebSocketManager,
     * que añade reconexión automática con backoff exponencial.
     */
    public void connectScanWebSocket(
        String scanId,
        Consumer<JsonObject> onMessage,
        Runnable onComplete,
        Consumer<String> onError
    ) {
        closeScanWebSocket();
        wsManager = new WebSocketManager(httpClient, scanId, onMessage, onComplete, onError);
        wsManager.connect();
    }

    public void closeScanWebSocket() {
        if (wsManager != null) {
            wsManager.close();
            wsManager = null;
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static String safeStr(JsonObject o, String k)    { return (o.has(k) && !o.get(k).isJsonNull()) ? o.get(k).getAsString() : ""; }
    private static int    safeInt(JsonObject o, String k)    { return (o.has(k) && !o.get(k).isJsonNull()) ? o.get(k).getAsInt()    : 0;  }
    private static long   safeLong(JsonObject o, String k)   { return (o.has(k) && !o.get(k).isJsonNull()) ? o.get(k).getAsLong()   : 0L; }
    private static double safeDouble(JsonObject o, String k) { return (o.has(k) && !o.get(k).isJsonNull()) ? o.get(k).getAsDouble() : 0.0;}
}