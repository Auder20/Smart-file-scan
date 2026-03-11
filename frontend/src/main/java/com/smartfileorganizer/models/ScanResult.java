package com.smartfileorganizer.models;

public class ScanResult {
    private String scanId;
    private String rootPath;
    private String status;
    private int totalFiles;
    private long totalSize;
    private double durationSec;

    public ScanResult(String scanId, String rootPath, String status, int totalFiles, long totalSize, double durationSec) {
        this.scanId = scanId;
        this.rootPath = rootPath;
        this.status = status;
        this.totalFiles = totalFiles;
        this.totalSize = totalSize;
        this.durationSec = durationSec;
    }

    // Getters
    public String getScanId() { return scanId; }
    public String getRootPath() { return rootPath; }
    public String getStatus() { return status; }
    public int getTotalFiles() { return totalFiles; }
    public long getTotalSize() { return totalSize; }
    public double getDurationSec() { return durationSec; }

    // Setters
    public void setScanId(String scanId) { this.scanId = scanId; }
    public void setRootPath(String rootPath) { this.rootPath = rootPath; }
    public void setStatus(String status) { this.status = status; }
    public void setTotalFiles(int totalFiles) { this.totalFiles = totalFiles; }
    public void setTotalSize(long totalSize) { this.totalSize = totalSize; }
    public void setDurationSec(double durationSec) { this.durationSec = durationSec; }
}
