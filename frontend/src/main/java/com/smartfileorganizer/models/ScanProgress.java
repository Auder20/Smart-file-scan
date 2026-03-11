package com.smartfileorganizer.models;

public class ScanProgress {
    private String scanId;
    private String status;
    private double progress;
    private int filesFound;
    private String message;

    public ScanProgress(String scanId, String status, double progress, int filesFound, String message) {
        this.scanId = scanId;
        this.status = status;
        this.progress = progress;
        this.filesFound = filesFound;
        this.message = message;
    }

    // Getters
    public String getScanId() { return scanId; }
    public String getStatus() { return status; }
    public double getProgress() { return progress; }
    public int getFilesFound() { return filesFound; }
    public String getMessage() { return message; }

    // Setters
    public void setScanId(String scanId) { this.scanId = scanId; }
    public void setStatus(String status) { this.status = status; }
    public void setProgress(double progress) { this.progress = progress; }
    public void setFilesFound(int filesFound) { this.filesFound = filesFound; }
    public void setMessage(String message) { this.message = message; }
}
