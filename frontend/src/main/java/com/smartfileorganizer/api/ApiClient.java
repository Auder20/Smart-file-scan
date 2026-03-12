package com.smartfileorganizer.api;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import okhttp3.*;

import java.io.IOException;
import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class ApiClient {
    private static final String BASE_URL = "http://localhost:8000";
    private static final Gson gson = new Gson();

    private static final OkHttpClient client = new OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(300, TimeUnit.SECONDS)
        .build();

    private static final MediaType JSON = MediaType.get("application/json");

    public ApiClient() {}

    // ── Health ───────────────────────────────────────────────────────────────

    public static CompletableFuture<Boolean> isBackendReady() {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder().url(BASE_URL + "/api/health").build();
                try (Response resp = client.newCall(req).execute()) {
                    return resp.isSuccessful();
                }
            } catch (IOException e) {
                return false;
            }
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

                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error al iniciar scan: " + resp.code());
                    JsonObject json = gson.fromJson(resp.body().string(), JsonObject.class);
                    return json.get("scan_id").getAsString();
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    // Keep sync version for compatibility
    public String startScan(String path, int maxDepth, boolean includeHidden) throws Exception {
        return startScanAsync(path, maxDepth, includeHidden).get();
    }

    public CompletableFuture<com.smartfileorganizer.models.ScanProgress> getScanProgressAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/scan/" + scanId + "/progress")
                    .build();
                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error obteniendo progreso: " + resp.code());
                    JsonObject json = gson.fromJson(resp.body().string(), JsonObject.class);
                    return new com.smartfileorganizer.models.ScanProgress(
                        json.get("scan_id").getAsString(),
                        json.get("status").getAsString(),
                        json.get("progress").getAsDouble(),
                        json.get("files_found").getAsInt(),
                        json.get("message").getAsString()
                    );
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    public com.smartfileorganizer.models.ScanProgress getScanProgress(String scanId) throws Exception {
        return getScanProgressAsync(scanId).get();
    }

    public CompletableFuture<com.smartfileorganizer.models.ScanResult> getScanResultAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/scan/" + scanId)
                    .build();
                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error obteniendo resultado: " + resp.code());
                    JsonObject json = gson.fromJson(resp.body().string(), JsonObject.class);
                    return new com.smartfileorganizer.models.ScanResult(
                        json.get("scan_id").getAsString(),
                        json.get("root_path").getAsString(),
                        json.get("status").getAsString(),
                        json.get("total_files").getAsInt(),
                        json.get("total_size").getAsLong(),
                        json.get("duration_sec").getAsDouble()
                    );
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    public com.smartfileorganizer.models.ScanResult getScanResult(String scanId) throws Exception {
        return getScanResultAsync(scanId).get();
    }

    public CompletableFuture<List<Map<String, Object>>> listAllScansAsync() {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/scan/all")
                    .build();
                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error listando escaneos: " + resp.code());

                    JsonArray arr = gson.fromJson(resp.body().string(), JsonArray.class);
                    List<Map<String, Object>> scans = new ArrayList<>();
                    for (JsonElement el : arr) {
                        JsonObject o = el.getAsJsonObject();
                        Map<String, Object> m = new HashMap<>();
                        m.put("scan_id",     safeString(o, "scan_id"));
                        m.put("status",      safeString(o, "status"));
                        m.put("files_found", safeInt(o, "files_found"));
                        m.put("progress",    safeDouble(o, "progress"));
                        m.put("root_path",   safeString(o, "root_path"));
                        m.put("total_files", safeInt(o, "total_files"));
                        m.put("total_size",  safeLong(o, "total_size"));
                        m.put("scanned_at",  safeString(o, "scanned_at"));
                        m.put("duration_sec",safeDouble(o, "duration_sec"));
                        scans.add(m);
                    }
                    return scans;
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    public List<Map<String, Object>> listScans() throws Exception {
        return listAllScansAsync().get();
    }

    public CompletableFuture<Void> deleteScanAsync(String scanId) {
        return CompletableFuture.runAsync(() -> {
            try {
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/scan/" + scanId)
                    .delete()
                    .build();
                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error eliminando scan: " + resp.code());
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    // ── Stats ─────────────────────────────────────────────────────────────────

    public CompletableFuture<Map<String, Object>> getStatsAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/stats/" + scanId)
                    .build();
                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error obteniendo estadísticas: " + resp.code());

                    JsonObject json = gson.fromJson(resp.body().string(), JsonObject.class);
                    Map<String, Object> result = new HashMap<>();
                    result.put("total_files",     safeInt(json, "total_files"));
                    result.put("total_size",       safeLong(json, "total_size"));
                    result.put("empty_files",      safeInt(json, "empty_files"));
                    result.put("old_files_count",  safeInt(json, "old_files_count"));
                    result.put("old_files_size",   safeLong(json, "old_files_size"));
                    result.put("by_category",      json.get("by_category").getAsJsonArray());
                    return result;
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
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
                    .url(BASE_URL + "/api/files/" + scanId + "/largest?limit=" + limit)
                    .build();
                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error obteniendo archivos grandes: " + resp.code());

                    JsonArray arr = gson.fromJson(resp.body().string(), JsonArray.class);
                    List<Map<String, Object>> files = new ArrayList<>();
                    for (JsonElement el : arr) {
                        JsonObject o = el.getAsJsonObject();
                        Map<String, Object> m = new HashMap<>();
                        m.put("name",     safeString(o, "name"));
                        m.put("path",     safeString(o, "path"));
                        m.put("size",     safeLong(o, "size"));
                        m.put("modified", safeString(o, "modified"));
                        m.put("category", safeString(o, "category"));
                        files.add(m);
                    }
                    return files;
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    public CompletableFuture<List<Map<String, Object>>> getExtensionStatsAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/files/" + scanId + "/extensions")
                    .build();
                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error obteniendo extensiones: " + resp.code());

                    JsonArray arr = gson.fromJson(resp.body().string(), JsonArray.class);
                    List<Map<String, Object>> exts = new ArrayList<>();
                    for (JsonElement el : arr) {
                        JsonObject o = el.getAsJsonObject();
                        Map<String, Object> m = new HashMap<>();
                        m.put("extension",  safeString(o, "extension"));
                        m.put("count",      safeInt(o, "count"));
                        m.put("total_size", safeLong(o, "total_size"));
                        m.put("percentage", safeDouble(o, "percentage"));
                        exts.add(m);
                    }
                    return exts;
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    // ── Duplicates ────────────────────────────────────────────────────────────

    public CompletableFuture<Map<String, Object>> getDuplicatesAsync(String scanId) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                Request req = new Request.Builder()
                    .url(BASE_URL + "/api/duplicates/" + scanId)
                    .build();
                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error obteniendo duplicados: " + resp.code());

                    JsonObject json = gson.fromJson(resp.body().string(), JsonObject.class);
                    Map<String, Object> result = new HashMap<>();
                    result.put("total_groups",     safeInt(json, "total_groups"));
                    result.put("total_duplicates", safeInt(json, "total_duplicates"));
                    result.put("total_wasted",     safeLong(json, "total_wasted"));
                    result.put("analyzed_files",   safeInt(json, "analyzed_files"));
                    result.put("groups",           json.get("groups").getAsJsonArray());
                    return result;
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
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

                try (Response resp = client.newCall(req).execute()) {
                    if (!resp.isSuccessful())
                        throw new RuntimeException("Error eliminando archivos: " + resp.code());

                    JsonObject json = gson.fromJson(resp.body().string(), JsonObject.class);
                    Map<String, Object> result = new HashMap<>();
                    result.put("deleted_count", safeInt(json, "deleted_count"));
                    result.put("space_freed",   safeLong(json, "space_freed"));

                    List<String> deleted = new ArrayList<>();
                    List<String> failed  = new ArrayList<>();
                    if (json.has("deleted")) {
                        for (JsonElement el : json.get("deleted").getAsJsonArray())
                            deleted.add(el.getAsString());
                    }
                    if (json.has("failed")) {
                        for (JsonElement el : json.get("failed").getAsJsonArray())
                            failed.add(el.getAsString());
                    }
                    result.put("deleted", deleted);
                    result.put("failed",  failed);
                    return result;
                }
            } catch (IOException e) {
                throw new RuntimeException(e);
            }
        });
    }

    public Map<String, Object> deleteFiles(List<String> paths, boolean useRecycle) throws Exception {
        return deleteFilesAsync(paths, useRecycle).get();
    }

    // ── Explorer ──────────────────────────────────────────────────────────────

    public List<Map<String, Object>> getAvailableDrives() throws Exception {
        Request req = new Request.Builder().url(BASE_URL + "/api/explorer/drives").build();
        try (Response resp = client.newCall(req).execute()) {
            if (!resp.isSuccessful())
                throw new RuntimeException("Error obteniendo unidades: " + resp.code());
            JsonArray arr = gson.fromJson(resp.body().string(), JsonArray.class);
            List<Map<String, Object>> drives = new ArrayList<>();
            for (JsonElement el : arr) {
                JsonObject o = el.getAsJsonObject();
                Map<String, Object> m = new HashMap<>();
                m.put("name", safeString(o, "name"));
                m.put("path", safeString(o, "path"));
                if (o.has("total_space") && !o.get("total_space").isJsonNull())
                    m.put("total_space", o.get("total_space").getAsLong());
                if (o.has("free_space") && !o.get("free_space").isJsonNull())
                    m.put("free_space", o.get("free_space").getAsLong());
                drives.add(m);
            }
            return drives;
        }
    }

    public List<Map<String, Object>> exploreFolders(String path, boolean includeHidden, int maxDepth) throws Exception {
        String url = BASE_URL + "/api/explorer/folders?path="
            + java.net.URLEncoder.encode(path, "UTF-8")
            + "&include_hidden=" + includeHidden
            + "&max_depth=" + maxDepth;

        Request req = new Request.Builder().url(url).build();
        try (Response resp = client.newCall(req).execute()) {
            if (!resp.isSuccessful())
                throw new RuntimeException("Error explorando carpetas: " + resp.code());
            JsonArray arr = gson.fromJson(resp.body().string(), JsonArray.class);
            List<Map<String, Object>> folders = new ArrayList<>();
            for (JsonElement el : arr) {
                JsonObject o = el.getAsJsonObject();
                Map<String, Object> m = new HashMap<>();
                m.put("name",         safeString(o, "name"));
                m.put("path",         safeString(o, "path"));
                m.put("is_directory", o.has("is_directory") && o.get("is_directory").getAsBoolean());
                if (o.has("size") && !o.get("size").isJsonNull())
                    m.put("size", o.get("size").getAsLong());
                if (o.has("file_count") && !o.get("file_count").isJsonNull())
                    m.put("file_count", o.get("file_count").getAsInt());
                folders.add(m);
            }
            return folders;
        }
    }

    public Map<String, Object> validateScanPath(String path) throws Exception {
        String url = BASE_URL + "/api/explorer/validate-path?path="
            + java.net.URLEncoder.encode(path, "UTF-8");
        Request req = new Request.Builder().url(url).build();
        try (Response resp = client.newCall(req).execute()) {
            if (!resp.isSuccessful())
                throw new RuntimeException("Error validando ruta: " + resp.code());
            JsonObject json = gson.fromJson(resp.body().string(), JsonObject.class);
            Map<String, Object> result = new HashMap<>();
            result.put("valid", json.get("valid").getAsBoolean());
            if (json.has("reason"))         result.put("reason",          safeString(json, "reason"));
            if (json.has("suggestion"))     result.put("suggestion",      safeString(json, "suggestion"));
            if (json.has("estimated_files")) result.put("estimated_files", safeInt(json, "estimated_files"));
            if (json.has("message"))        result.put("message",         safeString(json, "message"));
            return result;
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static String safeString(JsonObject o, String key) {
        return (o.has(key) && !o.get(key).isJsonNull()) ? o.get(key).getAsString() : "";
    }
    private static int safeInt(JsonObject o, String key) {
        return (o.has(key) && !o.get(key).isJsonNull()) ? o.get(key).getAsInt() : 0;
    }
    private static long safeLong(JsonObject o, String key) {
        return (o.has(key) && !o.get(key).isJsonNull()) ? o.get(key).getAsLong() : 0L;
    }
    private static double safeDouble(JsonObject o, String key) {
        return (o.has(key) && !o.get(key).isJsonNull()) ? o.get(key).getAsDouble() : 0.0;
    }
}