package com.smartfileorganizer.models;

import javafx.application.Platform;
import javafx.scene.control.Alert;
import javafx.scene.control.Button;
import javafx.scene.layout.HBox;
import javafx.collections.ObservableList;
import com.smartfileorganizer.api.ApiClient;

public class ScanInfo {
    private String scanId;
    private String status;
    private int    filesFound;
    private String date;
    private HBox   actions;
    private ObservableList<ScanInfo> scanList;
    private ApiClient apiClient;

    public ScanInfo(String scanId, String status, int filesFound, String date,
                    ObservableList<ScanInfo> scanList, ApiClient apiClient) {
        this.scanId     = scanId;
        this.status     = status;
        this.filesFound = filesFound;
        this.date       = date;
        this.scanList   = scanList;
        this.apiClient  = apiClient;
        this.actions    = createActionButtons(scanId, status);
    }

    private HBox createActionButtons(String scanId, String status) {
        HBox box = new HBox(5);

        Button viewBtn = new Button("Ver");
        viewBtn.setStyle("-fx-font-size: 11px; -fx-padding: 2 8px;");
        viewBtn.setOnAction(e -> {
            try {
                com.smartfileorganizer.utils.UIUtils.showFilesView(scanId, status);
            } catch (Exception ex) {
                System.err.println("Error opening files view: " + ex.getMessage());
            }
        });
        box.getChildren().add(viewBtn);

        if ("completed".equals(status)) {
            Button deleteBtn = new Button("Eliminar");
            deleteBtn.setStyle(
                "-fx-font-size: 11px; -fx-padding: 2 8px;" +
                "-fx-background-color: #ef4444; -fx-text-fill: white;"
            );
            deleteBtn.setOnAction(e -> {
                // FIX: el original llamaba deleteScanAsync sin .get() ni manejo de error
                // (fire-and-forget). Ahora deshabilita el botón, ejecuta en background
                // y muestra un alert si falla.
                deleteBtn.setDisable(true);
                deleteBtn.setText("...");

                apiClient.deleteScanAsync(scanId)
                    .thenRun(() -> Platform.runLater(() -> {
                        scanList.removeIf(s -> s.getScanId().equals(scanId));
                    }))
                    .exceptionally(ex -> {
                        Platform.runLater(() -> {
                            deleteBtn.setDisable(false);
                            deleteBtn.setText("Eliminar");
                            Alert alert = new Alert(Alert.AlertType.ERROR);
                            alert.setTitle("Error al eliminar");
                            alert.setHeaderText(null);
                            alert.setContentText("No se pudo eliminar el scan: " + ex.getMessage());
                            alert.showAndWait();
                        });
                        return null;
                    });
            });
            box.getChildren().add(deleteBtn);
        }

        return box;
    }

    // Getters
    public String getScanId()    { return scanId; }
    public String getStatus()    { return status; }
    public int    getFilesFound(){ return filesFound; }
    public String getDate()      { return date; }
    public HBox   getActions()   { return actions; }

    // Setters
    public void setScanId(String v)    { this.scanId = v;     this.actions = createActionButtons(v, status); }
    public void setStatus(String v)    { this.status = v;     this.actions = createActionButtons(scanId, v); }
    public void setFilesFound(int v)   { this.filesFound = v; }
    public void setDate(String v)      { this.date = v; }
    public void setActions(HBox v)     { this.actions = v; }
    public void setScanList(ObservableList<ScanInfo> v) { this.scanList = v; }
    public void setApiClient(ApiClient v)               { this.apiClient = v; }
}