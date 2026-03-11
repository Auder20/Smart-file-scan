package com.smartfileorganizer.models;

public class LargeFile {
    private int rank;
    private String fileName;
    private String path;
    private long size;
    private String modified;

    public LargeFile(int rank, String fileName, String path, long size, String modified) {
        this.rank = rank;
        this.fileName = fileName;
        this.path = path;
        this.size = size;
        this.modified = modified;
    }

    // Getters
    public int getRank() { return rank; }
    public String getFileName() { return fileName; }
    public String getPath() { return path; }
    public long getSize() { return size; }
    public String getModified() { return modified; }

    // Propiedades calculadas
    public String getFormattedSize() {
        return com.smartfileorganizer.utils.FormatUtils.formatFileSize(size);
    }

    public String getFormattedModified() {
        try {
            // Formato simple de fecha (asumimos que viene en formato ISO)
            return modified.substring(0, 10); // YYYY-MM-DD
        } catch (Exception e) {
            return modified;
        }
    }

    public String getActions() {
        return "Abrir";
    }

    // Setters
    public void setRank(int rank) { this.rank = rank; }
    public void setFileName(String fileName) { this.fileName = fileName; }
    public void setPath(String path) { this.path = path; }
    public void setSize(long size) { this.size = size; }
    public void setModified(String modified) { this.modified = modified; }
}
