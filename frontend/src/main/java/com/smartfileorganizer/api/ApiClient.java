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

    // Un solo cliente OkHttp compartido por toda la app
    private static final OkHttpClient client = new OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(300, TimeUnit.SECONDS)  // 5 min para scans grandes
        .build();

    private static final MediaType JSON = MediaType.get("application/json");

    public ApiClient() {
        // Constructor para instanciar el cliente
    }

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

    // ── Métodos de instancia para ScannerController ─────────────────────────────

    public String startScan(String path, int maxDepth, boolean includeHidden) throws Exception {
        JsonObject body = new JsonObject();
        body.addProperty("path", path);
        body.addProperty("max_depth", maxDepth);
        body.addProperty("include_hidden", includeHidden);

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
    }

    public com.smartfileorganizer.models.ScanProgress getScanProgress(String scanId) throws Exception {
        Request request = new Request.Builder()
            .url(BASE_URL + "/api/scan/" + scanId + "/progress")
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error obteniendo progreso: " + response.code());
            }
            JsonObject json = gson.fromJson(response.body().string(), JsonObject.class);
            
            return new com.smartfileorganizer.models.ScanProgress(
                json.get("scan_id").getAsString(),
                json.get("status").getAsString(),
                json.get("progress").getAsDouble(),
                json.get("files_found").getAsInt(),
                json.get("message").getAsString()
            );
        }
    }

    public com.smartfileorganizer.models.ScanResult getScanResult(String scanId) throws Exception {
        Request request = new Request.Builder()
            .url(BASE_URL + "/api/scan/" + scanId)
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error obteniendo resultado: " + response.code());
            }
            JsonObject json = gson.fromJson(response.body().string(), JsonObject.class);
            
            return new com.smartfileorganizer.models.ScanResult(
                json.get("scan_id").getAsString(),
                json.get("root_path").getAsString(),
                json.get("status").getAsString(),
                json.get("total_files").getAsInt(),
                json.get("total_size").getAsLong(),
                json.get("duration_sec").getAsDouble()
            );
        }
    }

    public List<Map<String, Object>> listScans() throws Exception {
        Request request = new Request.Builder()
            .url(BASE_URL + "/api/scan")
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error listando escaneos: " + response.code());
            }
            
            String responseBody = response.body().string();
            JsonArray jsonArray = gson.fromJson(responseBody, JsonArray.class);
            
            List<Map<String, Object>> scans = new ArrayList<>();
            for (JsonElement element : jsonArray) {
                JsonObject scanObj = element.getAsJsonObject();
                Map<String, Object> scanMap = new HashMap<>();
                scanMap.put("scan_id", scanObj.get("scan_id").getAsString());
                scanMap.put("status", scanObj.get("status").getAsString());
                scanMap.put("files_found", scanObj.get("files_found").getAsInt());
                scans.add(scanMap);
            }
            return scans;
        }
    }

    public Map<String, Object> getDuplicates(String scanId) throws Exception {
        Request request = new Request.Builder()
            .url(BASE_URL + "/api/duplicates/" + scanId)
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error obteniendo duplicados: " + response.code());
            }
            
            JsonObject json = gson.fromJson(response.body().string(), JsonObject.class);
            
            Map<String, Object> result = new HashMap<>();
            result.put("total_groups", json.get("total_groups").getAsInt());
            result.put("total_duplicates", json.get("total_duplicates").getAsInt());
            result.put("total_wasted", json.get("total_wasted").getAsLong());
            result.put("groups", json.get("groups").getAsJsonArray());
            
            return result;
        }
    }

    public Map<String, Object> getStats(String scanId) throws Exception {
        Request request = new Request.Builder()
            .url(BASE_URL + "/api/stats/" + scanId)
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error obteniendo estadísticas: " + response.code());
            }
            
            JsonObject json = gson.fromJson(response.body().string(), JsonObject.class);
            
            Map<String, Object> result = new HashMap<>();
            result.put("total_files", json.get("total_files").getAsInt());
            result.put("total_size", json.get("total_size").getAsLong());
            result.put("empty_files", json.get("empty_files").getAsInt());
            result.put("old_files_count", json.get("old_files_count").getAsInt());
            result.put("old_files_size", json.get("old_files_size").getAsLong());
            result.put("by_category", json.get("by_category").getAsJsonArray());
            
            return result;
        }
    }

    public Map<String, Object> deleteFiles(List<String> paths, boolean useRecycle) throws Exception {
        JsonObject body = new JsonObject();
        JsonArray pathsArray = new JsonArray();
        for (String path : paths) {
            pathsArray.add(path);
        }
        body.add("paths", pathsArray);
        body.addProperty("use_recycle", useRecycle);

        Request request = new Request.Builder()
            .url(BASE_URL + "/api/duplicates/files")
            .delete(RequestBody.create(body.toString(), JSON))
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error eliminando archivos: " + response.code());
            }
            
            JsonObject json = gson.fromJson(response.body().string(), JsonObject.class);
            
            Map<String, Object> result = new HashMap<>();
            result.put("deleted_count", json.get("deleted_count").getAsInt());
            result.put("space_freed", json.get("space_freed").getAsLong());
            
            return result;
        }
    }

    // ── Métodos para explorar carpetas ─────────────────────────────────────

    public List<Map<String, Object>> getAvailableDrives() throws Exception {
        Request request = new Request.Builder()
            .url(BASE_URL + "/api/explorer/drives")
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error obteniendo unidades: " + response.code());
            }
            
            String responseBody = response.body().string();
            JsonArray jsonArray = gson.fromJson(responseBody, JsonArray.class);
            
            List<Map<String, Object>> drives = new ArrayList<>();
            for (JsonElement element : jsonArray) {
                JsonObject driveObj = element.getAsJsonObject();
                Map<String, Object> driveMap = new HashMap<>();
                driveMap.put("name", driveObj.get("name").getAsString());
                driveMap.put("path", driveObj.get("path").getAsString());
                if (driveObj.has("total_space")) {
                    driveMap.put("total_space", driveObj.get("total_space").getAsLong());
                }
                if (driveObj.has("free_space")) {
                    driveMap.put("free_space", driveObj.get("free_space").getAsLong());
                }
                drives.add(driveMap);
            }
            return drives;
        }
    }

    public List<Map<String, Object>> exploreFolders(String path, boolean includeHidden, int maxDepth) throws Exception {
        String url = BASE_URL + "/api/explorer/folders?path=" + 
                     java.net.URLEncoder.encode(path, "UTF-8") +
                     "&include_hidden=" + includeHidden +
                     "&max_depth=" + maxDepth;
        
        Request request = new Request.Builder()
            .url(url)
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error explorando carpetas: " + response.code());
            }
            
            String responseBody = response.body().string();
            JsonArray jsonArray = gson.fromJson(responseBody, JsonArray.class);
            
            List<Map<String, Object>> folders = new ArrayList<>();
            for (JsonElement element : jsonArray) {
                JsonObject folderObj = element.getAsJsonObject();
                Map<String, Object> folderMap = new HashMap<>();
                folderMap.put("name", folderObj.get("name").getAsString());
                folderMap.put("path", folderObj.get("path").getAsString());
                folderMap.put("is_directory", folderObj.get("is_directory").getAsBoolean());
                if (folderObj.has("size")) {
                    folderMap.put("size", folderObj.get("size").getAsLong());
                }
                if (folderObj.has("file_count")) {
                    folderMap.put("file_count", folderObj.get("file_count").getAsInt());
                }
                folders.add(folderMap);
            }
            return folders;
        }
    }

    public List<Map<String, Object>> getCommonFolders() throws Exception {
        Request request = new Request.Builder()
            .url(BASE_URL + "/api/explorer/common-folders")
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error obteniendo carpetas comunes: " + response.code());
            }
            
            String responseBody = response.body().string();
            JsonArray jsonArray = gson.fromJson(responseBody, JsonArray.class);
            
            List<Map<String, Object>> folders = new ArrayList<>();
            for (JsonElement element : jsonArray) {
                JsonObject folderObj = element.getAsJsonObject();
                Map<String, Object> folderMap = new HashMap<>();
                folderMap.put("name", folderObj.get("name").getAsString());
                folderMap.put("path", folderObj.get("path").getAsString());
                folderMap.put("is_directory", folderObj.get("is_directory").getAsBoolean());
                if (folderObj.has("file_count")) {
                    folderMap.put("file_count", folderObj.get("file_count").getAsInt());
                }
                folders.add(folderMap);
            }
            return folders;
        }
    }

    public Map<String, Object> validateScanPath(String path) throws Exception {
        String url = BASE_URL + "/api/explorer/validate-path?path=" + 
                     java.net.URLEncoder.encode(path, "UTF-8");
        
        Request request = new Request.Builder()
            .url(url)
            .build();

        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) {
                throw new RuntimeException("Error validando ruta: " + response.code());
            }
            
            JsonObject json = gson.fromJson(response.body().string(), JsonObject.class);
            
            Map<String, Object> result = new HashMap<>();
            result.put("valid", json.get("valid").getAsBoolean());
            
            if (json.has("reason")) {
                result.put("reason", json.get("reason").getAsString());
            }
            if (json.has("suggestion")) {
                result.put("suggestion", json.get("suggestion").getAsString());
            }
            if (json.has("estimated_files")) {
                result.put("estimated_files", json.get("estimated_files").getAsInt());
            }
            if (json.has("message")) {
                result.put("message", json.get("message").getAsString());
            }
            
            return result;
        }
    }
}
