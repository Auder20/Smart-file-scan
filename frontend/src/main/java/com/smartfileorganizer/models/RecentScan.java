package com.smartfileorganizer.models;

public class RecentScan {
    private String scanId;
    private String path;
    private String status;
    private int fileCount;
    private long size;
    private String date;

    public RecentScan(String scanId, String path, String status, int fileCount, long size, String date) {
        this.scanId = scanId;
        this.path = path;
        this.status = status;
        this.fileCount = fileCount;
        this.size = size;
        this.date = date;
    }

    // Getters
    public String getScanId() { return scanId; }
    public String getPath() { return path; }
    public String getStatus() { return status; }
    public int getFileCount() { return fileCount; }
    public long getSize() { return size; }
    public String getDate() { return date; }

    // Propiedades calculadas
    public String getFormattedSize() {
        return com.smartfileorganizer.utils.FormatUtils.formatFileSize(size);
    }

    public String getFormattedDate() {
        try {
            // Formato simple de fecha (asumimos que viene en formato ISO)
            return date.substring(0, 16); // YYYY-MM-DD HH:MM
        } catch (Exception e) {
            return date;
        }
    }

    public String getFormattedStatus() {
        switch (status.toLowerCase()) {
            case "completed":
                return "✅ Completado";
            case "running":
                return "🔄 En progreso";
            case "failed":
                return "❌ Fallido";
            case "pending":
                return "⏳ Pendiente";
            default:
                return status;
        }
    }

    public String getActions() {
        return "Ver | Eliminar";
    }

    // Setters
    public void setScanId(String scanId) { this.scanId = scanId; }
    public void setPath(String path) { this.path = path; }
    public void setStatus(String status) { this.status = status; }
    public void setFileCount(int fileCount) { this.fileCount = fileCount; }
    public void setSize(long size) { this.size = size; }
    public void setDate(String date) { this.date = date; }
}
