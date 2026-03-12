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
    private final BooleanProperty selected;

    public DuplicateFile(String groupId, String path, String fileName,
                         long sizeBytes, String modified, boolean isOriginal) {
        this.groupId    = groupId;
        this.path       = path;
        this.fileName   = fileName;
        this.sizeBytes  = sizeBytes;
        this.modified   = modified;
        this.isOriginal = isOriginal;
        this.selected   = new SimpleBooleanProperty(false);

        // Auto-listen to selection changes so the delete button can update
        this.selected.addListener((obs, o, n) -> {
            // Listeners will be added externally if needed
        });
    }

    // ── Getters ───────────────────────────────────────────────────────────────
    public String  getGroupId()    { return groupId; }
    public String  getPath()       { return path; }
    public String  getFileName()   { return fileName; }
    public long    getSizeBytes()  { return sizeBytes; }
    public String  getModified()   { return modified; }
    public boolean isOriginal()    { return isOriginal; }
    public boolean isSelected()    { return selected.get(); }
    public BooleanProperty selectedProperty() { return selected; }

    // ── Computed properties ───────────────────────────────────────────────────

    /** Abbreviated hash shown in the Group column */
    public String getShortGroupId() {
        return groupId != null && groupId.length() > 8
            ? groupId.substring(0, 8) + "…"
            : groupId;
    }

    public String getFormattedSize() {
        return com.smartfileorganizer.utils.FormatUtils.formatFileSize(sizeBytes);
    }

    public String getFormattedModified() {
        try {
            return modified != null && modified.length() >= 10
                ? modified.substring(0, 10)
                : modified;
        } catch (Exception e) {
            return modified;
        }
    }

    public String getStatus() {
        return isOriginal ? "✅ Original" : "📋 Duplicado";
    }

    public String getActions() {
        return "Abrir";
    }

    // ── Setters ───────────────────────────────────────────────────────────────
    public void setSelected(boolean v)    { selected.set(v); }
    public void setGroupId(String v)      { groupId = v; }
    public void setPath(String v)         { path = v; }
    public void setFileName(String v)     { fileName = v; }
    public void setSizeBytes(long v)      { sizeBytes = v; }
    public void setModified(String v)     { modified = v; }
    public void setOriginal(boolean v)    { isOriginal = v; }
}