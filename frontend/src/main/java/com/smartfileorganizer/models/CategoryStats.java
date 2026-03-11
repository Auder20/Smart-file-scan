package com.smartfileorganizer.models;

public class CategoryStats {
    private String category;
    private int fileCount;
    private long totalSize;
    private double percentage;

    public CategoryStats(String category, int fileCount, long totalSize, double percentage) {
        this.category = category;
        this.fileCount = fileCount;
        this.totalSize = totalSize;
        this.percentage = percentage;
    }

    // Getters
    public String getCategory() { 
        return category.substring(0, 1).toUpperCase() + category.substring(1); 
    }
    public int getFileCount() { return fileCount; }
    public long getTotalSize() { return totalSize; }
    public double getPercentage() { return percentage; }

    // Propiedades calculadas
    public String getFormattedSize() {
        return com.smartfileorganizer.utils.FormatUtils.formatFileSize(totalSize);
    }

    public String getFormattedPercentage() {
        return String.format("%.1f%%", percentage);
    }

    // Setters
    public void setCategory(String category) { this.category = category; }
    public void setFileCount(int fileCount) { this.fileCount = fileCount; }
    public void setTotalSize(long totalSize) { this.totalSize = totalSize; }
    public void setPercentage(double percentage) { this.percentage = percentage; }
}
