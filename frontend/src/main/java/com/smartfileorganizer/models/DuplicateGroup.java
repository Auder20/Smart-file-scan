package com.smartfileorganizer.models;

public class DuplicateGroup {
    private String hash;
    private int fileCount;
    private long totalSize;
    private long wastedSize;

    public DuplicateGroup(String hash, int fileCount, long totalSize, long wastedSize) {
        this.hash = hash;
        this.fileCount = fileCount;
        this.totalSize = totalSize;
        this.wastedSize = wastedSize;
    }

    // Getters
    public String getHash() { return hash; }
    public int getFileCount() { return fileCount; }
    public long getTotalSize() { return totalSize; }
    public long getWastedSize() { return wastedSize; }

    // Setters
    public void setHash(String hash) { this.hash = hash; }
    public void setFileCount(int fileCount) { this.fileCount = fileCount; }
    public void setTotalSize(long totalSize) { this.totalSize = totalSize; }
    public void setWastedSize(long wastedSize) { this.wastedSize = wastedSize; }
}
