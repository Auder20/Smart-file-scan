package com.smartfileorganizer.controllers;

import com.smartfileorganizer.api.ApiClient;
import javafx.application.Platform;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.fxml.FXML;
import javafx.fxml.Initializable;
import javafx.scene.control.*;
import javafx.scene.control.cell.PropertyValueFactory;
import javafx.scene.layout.HBox;
import javafx.stage.FileChooser;
import javafx.stage.Stage;

import java.net.URL;
import java.util.List;
import java.util.Map;
import java.util.ResourceBundle;
import java.util.concurrent.CompletableFuture;
import java.nio.file.Files;
import java.io.BufferedWriter;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

public class FilesViewController implements Initializable {
    
    @FXML private TableView<FileInfo> filesTable;
    @FXML private TableColumn<FileInfo, String> colName;
    @FXML private TableColumn<FileInfo, String> colPath;
    @FXML private TableColumn<FileInfo, Long> colSize;
    @FXML private TableColumn<FileInfo, String> colExtension;
    @FXML private TableColumn<FileInfo, String> colCategory;
    @FXML private TableColumn<FileInfo, String> colModified;
    @FXML private TextField txtSearch;
    @FXML private ComboBox<String> cmbCategory;
    @FXML private Label lblScanInfo;
    @FXML private Label lblTotalFiles;
    @FXML private Label lblTotalSize;
    @FXML private ProgressBar progressBar;
    
    private ApiClient apiClient;
    private String scanId;
    private ObservableList<FileInfo> allFiles = FXCollections.observableArrayList();
    private ObservableList<FileInfo> filteredFiles = FXCollections.observableArrayList();
    
    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        setupTable();
        setupFilters();
    }
    
    public void setScanId(String scanId) {
        this.scanId = scanId;
        loadFiles();
    }
    
    private void setupTable() {
        colName.setCellValueFactory(new PropertyValueFactory<>("name"));
        colPath.setCellValueFactory(new PropertyValueFactory<>("path"));
        colSize.setCellValueFactory(new PropertyValueFactory<>("size"));
        colExtension.setCellValueFactory(new PropertyValueFactory<>("extension"));
        colCategory.setCellValueFactory(new PropertyValueFactory<>("category"));
        colModified.setCellValueFactory(new PropertyValueFactory<>("modified"));
        
        // Format size column
        colSize.setCellFactory(column -> new TableCell<FileInfo, Long>() {
            @Override
            protected void updateItem(Long size, boolean empty) {
                super.updateItem(size, empty);
                if (empty || size == null) {
                    setText(null);
                } else {
                    setText(formatFileSize(size));
                }
            }
        });
        
        filesTable.setItems(filteredFiles);
    }
    
    private void setupFilters() {
        // Category filter
        cmbCategory.getItems().addAll("Todas", "Documentos", "Imágenes", "Videos", "Audio", "Código", "Otros");
        cmbCategory.setValue("Todas");
        
        cmbCategory.setOnAction(e -> applyFilters());
        
        // Search filter
        txtSearch.textProperty().addListener((obs, oldVal, newVal) -> applyFilters());
    }
    
    private void applyFilters() {
        String searchText = txtSearch.getText().toLowerCase();
        String selectedCategory = cmbCategory.getValue();
        
        filteredFiles.clear();
        
        for (FileInfo file : allFiles) {
            boolean matchesSearch = searchText.isEmpty() || 
                file.getName().toLowerCase().contains(searchText) ||
                file.getPath().toLowerCase().contains(searchText);
            
            boolean matchesCategory = "Todas".equals(selectedCategory) ||
                selectedCategory.equalsIgnoreCase(file.getCategory());
            
            if (matchesSearch && matchesCategory) {
                filteredFiles.add(file);
            }
        }
        
        updateStats();
    }
    
    private void loadFiles() {
        progressBar.setVisible(true);
        lblScanInfo.setText("Cargando archivos...");
        
        CompletableFuture.runAsync(() -> {
            try {
                // FEAT 1: Load files from backend using the new files endpoint
                Map<String, Object> filesResponse = apiClient.getScanFiles(scanId, 1, 1000);
                List<Map<String, Object>> files = (List<Map<String, Object>>) filesResponse.get("files");
                
                Platform.runLater(() -> {
                    allFiles.clear();
                    for (Map<String, Object> fileData : files) {
                        FileInfo fileInfo = new FileInfo(
                            (String) fileData.get("name"),
                            (String) fileData.get("path"),
                            ((Number) fileData.get("size")).longValue(),
                            (String) fileData.get("extension"),
                            (String) fileData.get("category"),
                            (String) fileData.get("modified")
                        );
                        allFiles.add(fileInfo);
                    }
                    
                    filteredFiles.setAll(allFiles);
                    updateStats();
                    updateScanInfo(filesResponse);
                    progressBar.setVisible(false);
                });
                
            } catch (Exception e) {
                Platform.runLater(() -> {
                    showAlert("Error", "No se pudieron cargar los archivos: " + e.getMessage());
                    progressBar.setVisible(false);
                });
            }
        });
    }
    
    private void updateStats() {
        int totalFiles = filteredFiles.size();
        long totalSize = filteredFiles.stream()
            .mapToLong(FileInfo::getSize)
            .sum();
        
        lblTotalFiles.setText(String.format("Archivos: %,d", totalFiles));
        lblTotalSize.setText(String.format("Tamaño total: %s", formatFileSize(totalSize)));
    }
    
    private void updateScanInfo(Map<String, Object> scanResult) {
        String info = String.format("Scan: %s | %s archivos | %s", 
            scanResult.get("scan_id"),
            scanResult.get("total_files"),
            formatFileSize(((Number) scanResult.get("total_size")).longValue()));
        lblScanInfo.setText(info);
    }
    
    private String formatFileSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return String.format("%.1f KB", bytes / 1024.0);
        if (bytes < 1024 * 1024 * 1024) return String.format("%.1f MB", bytes / (1024.0 * 1024));
        return String.format("%.1f GB", bytes / (1024.0 * 1024 * 1024));
    }
    
    private void showAlert(String title, String message) {
        Alert alert = new Alert(Alert.AlertType.INFORMATION);
        alert.setTitle(title);
        alert.setHeaderText(null);
        alert.setContentText(message);
        alert.showAndWait();
    }
    
    @FXML
    private void clearFilters() {
        txtSearch.clear();
        cmbCategory.setValue("Todas");
    }
    
    @FXML
    private void exportCsv() {
        try {
            FileChooser fileChooser = new FileChooser();
            fileChooser.setTitle("Exportar archivos a CSV");
            fileChooser.getExtensionFilters().addAll(
                new FileChooser.ExtensionFilter("CSV Files", "*.csv"),
                new FileChooser.ExtensionFilter("All Files", "*.*")
            );
            fileChooser.setInitialFileName("scan_files_" + scanId + ".csv");
            
            java.io.File selectedFile = fileChooser.showSaveDialog(new Stage());
            if (selectedFile != null) {
                try (BufferedWriter writer = Files.newBufferedWriter(selectedFile.toPath())) {
                    // CSV Header
                    writer.write("name,path,size,extension,category,modified\n");
                    
                    // Write file data
                    for (FileInfo file : allFiles) {
                        writer.write(String.format("%s,%s,%d,%s,%s,%s%n",
                            escapeCsv(file.getName()),
                            escapeCsv(file.getPath()),
                            file.getSize(),
                            escapeCsv(file.getExtension()),
                            escapeCsv(file.getCategory()),
                            escapeCsv(file.getModified())
                        ));
                    }
                }
                showAlert("Éxito", "Archivo CSV exportado correctamente");
            }
        } catch (Exception e) {
            showAlert("Error", "No se pudo exportar a CSV: " + e.getMessage());
        }
    }
    
    @FXML
    private void exportJson() {
        try {
            FileChooser fileChooser = new FileChooser();
            fileChooser.setTitle("Exportar archivos a JSON");
            fileChooser.getExtensionFilters().addAll(
                new FileChooser.ExtensionFilter("JSON Files", "*.json"),
                new FileChooser.ExtensionFilter("All Files", "*.*")
            );
            fileChooser.setInitialFileName("scan_files_" + scanId + ".json");
            
            java.io.File selectedFile = fileChooser.showSaveDialog(new Stage());
            if (selectedFile != null) {
                Gson gson = new Gson();
                JsonArray filesArray = new JsonArray();
                
                for (FileInfo file : allFiles) {
                    JsonObject fileObj = new JsonObject();
                    fileObj.addProperty("name", file.getName());
                    fileObj.addProperty("path", file.getPath());
                    fileObj.addProperty("size", file.getSize());
                    fileObj.addProperty("extension", file.getExtension());
                    fileObj.addProperty("category", file.getCategory());
                    fileObj.addProperty("modified", file.getModified());
                    filesArray.add(fileObj);
                }
                
                JsonObject root = new JsonObject();
                root.addProperty("scan_id", scanId);
                root.addProperty("export_date", new java.util.Date().toString());
                root.addProperty("total_files", allFiles.size());
                root.add("files", filesArray);
                
                Files.writeString(selectedFile.toPath(), gson.toJson(root));
                showAlert("Éxito", "Archivo JSON exportado correctamente");
            }
        } catch (Exception e) {
            showAlert("Error", "No se pudo exportar a JSON: " + e.getMessage());
        }
    }
    
    private String escapeCsv(String value) {
        if (value == null) return "";
        return value.replace("\"", "\"\"").replace(",", ";").replace("\n", " ");
    }
    
    @FXML
    private void close() {
        // Close the dialog/stage
        txtSearch.getScene().getWindow().hide();
    }
    
    // Inner class for file data
    public static class FileInfo {
        private String name;
        private String path;
        private long size;
        private String extension;
        private String category;
        private String modified;
        
        public FileInfo(String name, String path, long size, String extension, String category, String modified) {
            this.name = name;
            this.path = path;
            this.size = size;
            this.extension = extension;
            this.category = category;
            this.modified = modified;
        }
        
        // Getters
        public String getName() { return name; }
        public String getPath() { return path; }
        public long getSize() { return size; }
        public String getExtension() { return extension; }
        public String getCategory() { return category; }
        public String getModified() { return modified; }
    }
}
