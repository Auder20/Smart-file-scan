package com.smartfileorganizer.models;

import javafx.beans.property.BooleanProperty;
import javafx.beans.property.SimpleBooleanProperty;

public class DuplicateFile {
    private String groupId;
    private String path;
    private String fileName;
    private long sizeBytes;
    private String modified;
    private boolean isOriginal;
    private BooleanProperty selected;

    public DuplicateFile(String groupId, String path, String fileName, long sizeBytes, String modified, boolean isOriginal) {
        this.groupId = groupId;
        this.path = path;
        this.fileName = fileName;
        this.sizeBytes = sizeBytes;
        this.modified = modified;
        this.isOriginal = isOriginal;
        this.selected = new SimpleBooleanProperty(false);
    }

    // Getters
    public String getGroupId() { return groupId; }
    public String getPath() { return path; }
    public String getFileName() { return fileName; }
    public long getSizeBytes() { return sizeBytes; }
    public String getModified() { return modified; }
    public boolean isOriginal() { return isOriginal; }
    public boolean isSelected() { return selected.get(); }
    public BooleanProperty selectedProperty() { return selected; }
    public void setSelected(boolean selected) { this.selected.set(selected); }

    // Propiedades calculadas
    public String getFormattedSize() {
        return com.smartfileorganizer.utils.FormatUtils.formatFileSize(sizeBytes);
    }

    public String getFormattedModified() {
        try {
            // Formato simple de fecha (asumimos que viene en formato ISO)
            return modified.substring(0, 10); // YYYY-MM-DD
        } catch (Exception e) {
            return modified;
        }
    }

    public String getStatus() {
        return isOriginal ? "Original" : "Duplicado";
    }

    public String getActions() {
        return "Eliminar | Abrir";
    }

    // Setters
    public void setGroupId(String groupId) { this.groupId = groupId; }
    public void setPath(String path) { this.path = path; }
    public void setFileName(String fileName) { this.fileName = fileName; }
    public void setSizeBytes(long sizeBytes) { this.sizeBytes = sizeBytes; }
    public void setModified(String modified) { this.modified = modified; }
    public void setOriginal(boolean original) { isOriginal = original; }
}
