package com.smartfileorganizer.models;

import javafx.scene.control.Button;
import javafx.scene.layout.HBox;
import javafx.collections.ObservableList;
import com.smartfileorganizer.api.ApiClient;

public class ScanInfo {
    private String scanId;
    private String status;
    private int filesFound;
    private String date;
    private HBox actions;  // FIX: Change from String to HBox for multiple buttons
    private ObservableList<ScanInfo> scanList;  // Reference to parent list for delete functionality
    private ApiClient apiClient;  // Reference to API client

    public ScanInfo(String scanId, String status, int filesFound, String date, 
                  ObservableList<ScanInfo> scanList, ApiClient apiClient) {
        this.scanId = scanId;
        this.status = status;
        this.filesFound = filesFound;
        this.date = date;
        this.scanList = scanList;
        this.apiClient = apiClient;
        this.actions = createActionButtons(scanId, status);
    }

    private HBox createActionButtons(String scanId, String status) {
        HBox buttonBox = new HBox(5);
        
        Button viewButton = new Button("Ver");
        viewButton.setStyle("-fx-font-size: 11px; -fx-padding: 2 8px;");
        viewButton.setOnAction(e -> {
            // FEAT 1: Implement view files functionality
            try {
                com.smartfileorganizer.utils.UIUtils.showFilesView(scanId, status);
            } catch (Exception ex) {
                System.err.println("Error opening files view: " + ex.getMessage());
            }
        });
        
        buttonBox.getChildren().add(viewButton);
        
        // Only add delete button for completed scans
        if ("completed".equals(status)) {
            Button deleteButton = new Button("Eliminar");
            deleteButton.setStyle("-fx-font-size: 11px; -fx-padding: 2 8px; -fx-background-color: #ef4444; -fx-text-fill: white;");
            deleteButton.setOnAction(e -> {
                try {
                    // Call API to delete scan
                    apiClient.deleteScanAsync(scanId);
                    
                    // Remove from the list (which will update the table)
                    scanList.removeIf(scan -> scan.getScanId().equals(scanId));
                    
                } catch (Exception ex) {
                    System.err.println("Error deleting scan: " + ex.getMessage());
                }
            });
            buttonBox.getChildren().add(deleteButton);
        }
        
        return buttonBox;
    }

    // Getters
    public String getScanId() { return scanId; }
    public String getStatus() { return status; }
    public int getFilesFound() { return filesFound; }
    public String getDate() { return date; }
    public HBox getActions() { return actions; }

    // Setters
    public void setScanId(String scanId) { 
        this.scanId = scanId;
        this.actions = createActionButtons(scanId, status);
    }
    public void setStatus(String status) { 
        this.status = status;
        this.actions = createActionButtons(scanId, status);
    }
    public void setFilesFound(int filesFound) { this.filesFound = filesFound; }
    public void setDate(String date) { this.date = date; }
    public void setActions(HBox actions) { this.actions = actions; }
    
    // Additional setters for the new fields
    public void setScanList(ObservableList<ScanInfo> scanList) { this.scanList = scanList; }
    public void setApiClient(ApiClient apiClient) { this.apiClient = apiClient; }
}
