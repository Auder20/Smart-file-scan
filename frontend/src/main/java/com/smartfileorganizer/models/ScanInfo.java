package com.smartfileorganizer.models;

public class ScanInfo {
    private String scanId;
    private String status;
    private int filesFound;
    private String date;
    private String actions;

    public ScanInfo(String scanId, String status, int filesFound, String date) {
        this.scanId = scanId;
        this.status = status;
        this.filesFound = filesFound;
        this.date = date;
        this.actions = "Ver";
    }

    // Getters
    public String getScanId() { return scanId; }
    public String getStatus() { return status; }
    public int getFilesFound() { return filesFound; }
    public String getDate() { return date; }
    public String getActions() { return actions; }

    // Setters
    public void setScanId(String scanId) { this.scanId = scanId; }
    public void setStatus(String status) { this.status = status; }
    public void setFilesFound(int filesFound) { this.filesFound = filesFound; }
    public void setDate(String date) { this.date = date; }
    public void setActions(String actions) { this.actions = actions; }
}
