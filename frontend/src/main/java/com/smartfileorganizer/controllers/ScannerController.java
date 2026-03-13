package com.smartfileorganizer.controllers;

import javafx.fxml.FXML;
import javafx.fxml.Initializable;
import javafx.scene.control.*;
import javafx.stage.DirectoryChooser;
import javafx.stage.Stage;
import javafx.application.Platform;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.scene.control.cell.PropertyValueFactory;
import javafx.geometry.Insets;
import javafx.scene.layout.VBox;
import javafx.scene.control.ButtonBar;
import javafx.util.StringConverter;
import javafx.scene.control.Dialog;
import javafx.scene.control.TreeView;
import javafx.scene.control.TreeItem;
import javafx.scene.Node;
import com.smartfileorganizer.utils.UIUtils;

import java.io.File;
import java.net.URL;
import java.util.ResourceBundle;
import java.util.Timer;
import java.util.TimerTask;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

import com.smartfileorganizer.api.ApiClient;
import com.smartfileorganizer.models.ScanInfo;
import com.smartfileorganizer.models.ScanProgress;
import com.smartfileorganizer.utils.FormatUtils;
import com.google.gson.JsonObject;

// Helper class to store both display name and full path
class PathItem {
    private final String displayName;
    private final String fullPath;
    
    public PathItem(String displayName, String fullPath) {
        this.displayName = displayName;
        this.fullPath = fullPath;
    }
    
    public String getDisplayName() {
        return displayName;
    }
    
    public String getFullPath() {
        return fullPath;
    }
    
    @Override
    public String toString() {
        return displayName;
    }
}

public class ScannerController implements Initializable {

    @FXML private TextField txtFolderPath;
    @FXML private Button btnBrowse;
    @FXML private Spinner<Integer> spinnerMaxDepth;
    @FXML private CheckBox chkIncludeHidden;
    @FXML private Button btnStartScan;
    @FXML private Button btnStopScan;
    @FXML private Button btnRefresh;
    @FXML private Label lblStatus;
    
    @FXML private VBox progressSection;
    @FXML private ProgressBar progressBar;
    @FXML private Label lblProgress;
    @FXML private Label lblFilesFound;
    @FXML private Label lblCurrentDir;
    
    @FXML private VBox resultsSection;
    @FXML private Button btnViewFiles;
    @FXML private Button btnExport;
    @FXML private Label lblTotalFiles;
    @FXML private Label lblTotalSize;
    @FXML private Label lblScanTime;
    @FXML private Label lblScanId;
    
    @FXML private TableView<ScanInfo> tableScans;
    @FXML private TableColumn<ScanInfo, String> colScanId;
    @FXML private TableColumn<ScanInfo, String> colStatus;
    @FXML private TableColumn<ScanInfo, Integer> colFiles;
    @FXML private TableColumn<ScanInfo, String> colDate;
    @FXML private TableColumn<ScanInfo, javafx.scene.layout.HBox> colActions;  // FIX: Change to HBox type

    private ApiClient apiClient;
    private Timer progressTimer;
    private String currentScanId;
    private final ObservableList<ScanInfo> scanList = FXCollections.observableArrayList();
    private boolean isWebSocketConnected = false;
    private boolean scanCompleted = false;

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        
        // Inicializar tabla
        setupTable();
        
        // Configurar listeners
        setupListeners();
        
        // Cargar escaneos existentes
        refreshScans();
    }

    private void setupTable() {
        colScanId.setCellValueFactory(new PropertyValueFactory<>("scanId"));
        colStatus.setCellValueFactory(new PropertyValueFactory<>("status"));
        colFiles.setCellValueFactory(new PropertyValueFactory<>("filesFound"));
        colDate.setCellValueFactory(new PropertyValueFactory<>("date"));
        colActions.setCellValueFactory(new PropertyValueFactory<>("actions"));  // FIX: Now works with HBox
        
        tableScans.setItems(scanList);
    }

    private void setupListeners() {
        // Listener para el campo de ruta
        txtFolderPath.textProperty().addListener((obs, oldVal, newVal) -> {
            btnStartScan.setDisable(newVal == null || newVal.trim().isEmpty());
        });

        // Configurar spinner
        SpinnerValueFactory.IntegerSpinnerValueFactory factory = 
            new SpinnerValueFactory.IntegerSpinnerValueFactory(1, 50, 20);
        spinnerMaxDepth.setValueFactory(factory);
    }

    @FXML
    private void browseFolder() {
        try {
            // Usar el nuevo endpoint de validación de rutas
            var drives = apiClient.getAvailableDrives();
            
            // Mostrar diálogo de selección personalizado
            showFolderSelectionDialog(drives);
            
        } catch (Exception e) {
            // Fallback al diálogo nativo si falla la API
            DirectoryChooser directoryChooser = new DirectoryChooser();
            directoryChooser.setTitle("Seleccionar Carpeta");
            
            String currentPath = txtFolderPath.getText();
            if (currentPath != null && !currentPath.trim().isEmpty()) {
                File currentDir = new File(currentPath);
                if (currentDir.exists()) {
                    directoryChooser.setInitialDirectory(currentDir);
                }
            }
            
            File selectedDirectory = directoryChooser.showDialog(getStage());
            if (selectedDirectory != null) {
                txtFolderPath.setText(selectedDirectory.getAbsolutePath());
            }
        }
    }

    private void showFolderSelectionDialog(List<Map<String, Object>> drives) {
        // Crear diálogo personalizado para seleccionar carpetas
        Dialog<String> dialog = new Dialog<>();
        dialog.setTitle("Seleccionar Carpeta para Escanear");
        dialog.setHeaderText("Elige una unidad y luego navega hasta la carpeta deseada");

        // Botones
        ButtonType selectButtonType = new ButtonType("Seleccionar", ButtonBar.ButtonData.OK_DONE);
        ButtonType cancelButtonType = new ButtonType("Cancelar", ButtonBar.ButtonData.CANCEL_CLOSE);
        dialog.getDialogPane().getButtonTypes().addAll(selectButtonType, cancelButtonType);

        // Crear contenido del diálogo
        VBox content = new VBox(10);
        content.setPadding(new Insets(20));

        // ComboBox para unidades
        ComboBox<Map<String, Object>> driveCombo = new ComboBox<>();
        driveCombo.getItems().addAll(drives);
        driveCombo.setConverter(new StringConverter<Map<String, Object>>() {
            @Override
            public String toString(Map<String, Object> drive) {
                String name = (String) drive.get("name");
                Long freeSpace = ((Number) drive.get("free_space")).longValue();
                Boolean isRemovable = (Boolean) drive.get("is_removable");
                String filesystem = (String) drive.get("filesystem");
                
                // Mejorar nombres de rutas WSL para mostrar nombres más amigables
                String displayName = name;
                if (name.contains("/host/parent-distro/mnt/host/wsl/")) {
                    // Extraer nombre amigable de la ruta WSL
                    String[] parts = name.split("/");
                    if (parts.length > 0) {
                        displayName = parts[parts.length - 1];  // Última parte de la ruta
                    }
                } else if (name.startsWith("/host/")) {
                    // Para otras rutas de host, mostrar el último directorio
                    String[] parts = name.split("/");
                    if (parts.length > 1) {
                        displayName = parts[parts.length - 1];
                    }
                }
                
                StringBuilder display = new StringBuilder(displayName);
                
                if (isRemovable != null && isRemovable) {
                    display.append(" (USB)");
                }
                
                if (filesystem != null && !filesystem.isEmpty()) {
                    display.append(" [").append(filesystem).append("]");
                }
                
                if (freeSpace != null) {
                    display.append(" (").append(FormatUtils.formatFileSize(freeSpace)).append(" libre)");
                }
                
                return display.toString();
            }

            @Override
            public Map<String, Object> fromString(String string) {
                return null; // No necesario
            }
        });

        // TreeView para carpetas
        TreeView<PathItem> folderTree = new TreeView<>();
        folderTree.setPrefHeight(300);
        folderTree.setPrefWidth(400);

        // Listener para seleccion de unidad
        driveCombo.getSelectionModel().selectedItemProperty().addListener((obs, oldVal, newVal) -> {
            if (newVal != null) {
                loadFolderTree(folderTree, (String) newVal.get("path"));
            }
        });

        // Seleccionar primera unidad por defecto
        if (!drives.isEmpty()) {
            driveCombo.getSelectionModel().selectFirst();
        }
        
        content.getChildren().addAll(
            new Label("Unidad:"),
            driveCombo,
            new Label("Carpetas:"),
            folderTree
        );

        dialog.getDialogPane().setContent(content);

        // Habilitar botón de selección solo cuando se selecciona una carpeta
        Node selectButton = dialog.getDialogPane().lookupButton(selectButtonType);
        selectButton.setDisable(true);

        folderTree.getSelectionModel().selectedItemProperty().addListener((obs, oldVal, newVal) -> {
            selectButton.setDisable(newVal == null || newVal.getValue().toString().equals("Loading..."));
        });

        // Resultado
        dialog.setResultConverter(dialogButton -> {
            if (dialogButton == selectButtonType) {
                TreeItem<PathItem> selectedItem = folderTree.getSelectionModel().getSelectedItem();
                if (selectedItem != null) {
                    PathItem pathItem = selectedItem.getValue();
                    if (pathItem != null) {
                        return pathItem.getFullPath();
                    }
                }
            }
            return null;
        });

        // Mostrar diálogo y procesar resultado
        Optional<String> result = dialog.showAndWait();
        result.ifPresent(selectedPath -> {
            txtFolderPath.setText(selectedPath);
            validateSelectedPath(selectedPath);
        });
    }

    private void loadFolderTree(TreeView<PathItem> treeView, String rootPath) {
        TreeItem<PathItem> rootItem = new TreeItem<>(new PathItem("Loading...", rootPath));
        treeView.setRoot(rootItem);
        rootItem.setExpanded(true);

        // Cargar en background para no bloquear UI
        CompletableFuture.runAsync(() -> {
            try {
                List<Map<String, Object>> folders = apiClient.exploreFolders(rootPath, false, 2);
                
                Platform.runLater(() -> {
                    rootItem.getChildren().clear();
                    rootItem.setValue(new PathItem(rootPath, rootPath));
                    
                    for (Map<String, Object> folder : folders) {
                        if ((Boolean) folder.get("is_directory")) {
                            String folderPath = (String) folder.get("path");
                            String folderName = (String) folder.get("name");
                            Integer fileCount = ((Number) folder.get("file_count")).intValue();
                            
                            // Handle permission error folders
                            String displayName = folderName;
                            if (folderName.contains("(sin acceso)")) {
                                displayName = folderName.replace("(sin acceso)", "(sin acceso)");
                            }
                            
                            PathItem pathItem = new PathItem(
                                displayName + (fileCount != null ? " (" + fileCount + " archivos)" : ""),
                                folderPath
                            );
                            
                            TreeItem<PathItem> folderItem = new TreeItem<>(pathItem);
                            folderItem.setExpanded(false);
                            
                            // Only add placeholder if folder doesn't have permission error
                            if (!folderName.contains("(sin acceso)")) {
                                // Placeholder para subcarpetas
                                folderItem.getChildren().add(new TreeItem<>(new PathItem("Loading...", "")));
                                
                                // Listener para expandir subcarpetas
                                folderItem.expandedProperty().addListener((obs, wasExpanded, isNowExpanded) -> {
                                    if (isNowExpanded && folderItem.getChildren().size() == 1 && 
                                        folderItem.getChildren().get(0).getValue().toString().equals("Loading...")) {
                                        loadSubFolders(folderItem, folderPath);
                                    }
                                });
                            }
                            
                            rootItem.getChildren().add(folderItem);
                        }
                    }
                });
                
            } catch (Exception e) {
                Platform.runLater(() -> {
                    rootItem.getChildren().clear();
                    // Check if it's a permission error
                    String errorMessage = e.getMessage();
                    if (errorMessage != null && errorMessage.contains("403")) {
                        rootItem.setValue(new PathItem(rootPath + " (sin acceso)", rootPath));
                    } else {
                        rootItem.setValue(new PathItem("Error: " + e.getMessage(), ""));
                    }
                });
            }
        });
    }

    private void loadSubFolders(TreeItem<PathItem> parentItem, String parentPath) {
        CompletableFuture.runAsync(() -> {
            try {
                List<Map<String, Object>> subFolders = apiClient.exploreFolders(parentPath, false, 1);
                
                Platform.runLater(() -> {
                    parentItem.getChildren().clear();
                    
                    for (Map<String, Object> folder : subFolders) {
                        if ((Boolean) folder.get("is_directory")) {
                            String folderPath = (String) folder.get("path");
                            String folderName = (String) folder.get("name");
                            Integer fileCount = ((Number) folder.get("file_count")).intValue();
                            
                            PathItem pathItem = new PathItem(
                                folderName + (fileCount != null ? " (" + fileCount + " archivos)" : ""),
                                folderPath
                            );
                            
                            TreeItem<PathItem> folderItem = new TreeItem<>(pathItem);
                            
                            // FIX: Always add placeholder for lazy loading, remove blocking hasSubFolders call
                            folderItem.getChildren().add(new TreeItem<>(new PathItem("Loading...", "")));
                            
                            parentItem.getChildren().add(folderItem);
                        }
                    }
                });
                
            } catch (Exception e) {
                Platform.runLater(() -> {
                    parentItem.getChildren().clear();
                    parentItem.getChildren().add(new TreeItem<>(new PathItem("Error: " + e.getMessage(), "")));
                });
            }
        });
    }

    private void validateSelectedPath(String path) {
        try {
            var validation = apiClient.validateScanPath(path);
            
            if ((Boolean) validation.get("valid")) {
                lblStatus.setText("Ruta válida para escaneo");
                lblStatus.setStyle("-fx-text-fill: #10B981;");
                
                Integer estimatedFiles = ((Number) validation.get("estimated_files")).intValue();
                if (estimatedFiles != null) {
                    lblStatus.setText(lblStatus.getText() + " (~" + FormatUtils.formatNumber(estimatedFiles) + " archivos)");
                }
            } else {
                lblStatus.setText((String) validation.get("reason"));
                lblStatus.setStyle("-fx-text-fill: #EF4444;");
                
                if (validation.containsKey("suggestion")) {
                    showAlert("Advertencia", (String) validation.get("suggestion"));
                }
            }
        } catch (Exception e) {
            lblStatus.setText("Error validando ruta: " + e.getMessage());
            lblStatus.setStyle("-fx-text-fill: #EF4444;");
        }
    }

    @FXML
    private void startScan() {
        String path = txtFolderPath.getText().trim();
        if (path.isEmpty()) {
            showAlert("Error", "Por favor selecciona una carpeta válida.");
            return;
        }

        try {
            // Reset completion flag
            scanCompleted = false;
            
            // Iniciar escaneo
            currentScanId = apiClient.startScan(
                path, 
                spinnerMaxDepth.getValue(), 
                chkIncludeHidden.isSelected()
            );

            // Actualizar UI
            btnStartScan.setDisable(true);
            btnStopScan.setDisable(false);
            progressSection.setVisible(true);
            progressSection.setManaged(true);
            resultsSection.setVisible(false);
            resultsSection.setManaged(false);
            lblStatus.setText("Escaneando...");

            // Iniciar monitoreo de progreso
            startProgressMonitoring();

            // Refrescar lista de escaneos
            refreshScans();

        } catch (Exception e) {
            showAlert("Error", "No se pudo iniciar el escaneo: " + e.getMessage());
        }
    }

    @FXML
    private void stopScan() {
        if (progressTimer != null) {
            progressTimer.cancel();
            progressTimer = null;
        }
        
        // Cerrar WebSocket si está conectado
        if (isWebSocketConnected) {
            apiClient.closeScanWebSocket();  // FIX: Use instance method instead of static
            isWebSocketConnected = false;
            
            // FIX: Only cancel progress locally, don't delete scan from backend
            // The scan remains in history for user to view or delete manually
        }

        // Resetear UI
        btnStartScan.setDisable(false);
        btnStopScan.setDisable(true);
        progressSection.setVisible(false);
        progressSection.setManaged(false);
        lblStatus.setText("Detenido");

        refreshScans();
    }

    @FXML
    private void refreshScans() {
        try {
            var scans = apiClient.listScans();
            scanList.clear();
            
            for (var scan : scans) {
                scanList.add(new ScanInfo(
                    scan.get("scan_id").toString(),
                    scan.get("status").toString(),
                    Integer.parseInt(scan.get("files_found").toString()),
                    FormatUtils.formatDate(java.time.LocalDateTime.now()),
                    scanList,
                    apiClient
                ));
            }
        } catch (Exception e) {
            System.err.println("Error refrescando escaneos: " + e.getMessage());
        }
    }

    @FXML
    private void viewFiles() {
        if (currentScanId != null) {
            UIUtils.showFilesView(currentScanId, "completed");
        }
    }

    @FXML
    private void exportResults() {
        if (currentScanId != null) {
            // TODO: Implementar exportación
            showAlert("Info", "Función de exportación próximamente...");
        }
    }

    private void startProgressMonitoring() {
        // Usar WebSocket para monitoreo en tiempo real
        apiClient.connectScanWebSocket(currentScanId, this::handleWsMessage,  // FIX: Use instance method
            this::onScanComplete, this::onScanError);
        isWebSocketConnected = true;
    }
    
    private void handleWsMessage(JsonObject data) {
        String type = data.get("type").getAsString();
        
        switch (type) {
            case "progress":
                updateProgressUIFromWs(data);
                break;
            case "completed":
                onScanComplete();
                break;
            case "error":
                onScanError(data.get("message").getAsString());
                break;
        }
    }
    
    private void updateProgressUIFromWs(JsonObject data) {
        double progress = data.get("progress").getAsDouble();
        int filesFound = data.get("files_found").getAsInt();
        String message = data.get("message").getAsString();
        String currentDir = data.has("current_dir") ? data.get("current_dir").getAsString() : "";
        
        Platform.runLater(() -> {
            progressBar.setProgress(progress / 100.0);
            lblProgress.setText(String.format("%.1f%%", progress));
            lblFilesFound.setText(String.format("%,d archivos encontrados", filesFound));
            lblCurrentDir.setText(message);
            lblStatus.setText("Escaneando en progreso...");
        });
    }
    
    private void onScanComplete() {
        if (scanCompleted) {
            return; // Already processed completion
        }
        scanCompleted = true;
        
        Platform.runLater(() -> {
            // Close WebSocket
            apiClient.closeScanWebSocket();  // FIX: Use instance method instead of static
            isWebSocketConnected = false;
            
            // Reset UI buttons manually
            btnStartScan.setDisable(false);
            btnStopScan.setDisable(true);
            
            // Hide progress section
            progressSection.setVisible(false);
            progressSection.setManaged(false);
            
            // Show results
            showResultsFromWs();
            
            // Set status
            lblStatus.setText("✅ Completado");
        });
    }
    
    private void onScanError(String errorMessage) {
        Platform.runLater(() -> {
            stopScan();
            lblStatus.setText("Error: " + errorMessage);
            showAlert("Error de Escaneo", errorMessage);
        });
    }
    
    private void showResultsFromWs() {
        try {
            var result = apiClient.getScanResult(currentScanId);
            
            lblTotalFiles.setText(String.format("%,d", result.getTotalFiles()));
            lblTotalSize.setText(FormatUtils.formatFileSize(result.getTotalSize()));
            lblScanTime.setText(String.format("%.1fs", result.getDurationSec()));
            lblScanId.setText(currentScanId);
            
            resultsSection.setVisible(true);
            resultsSection.setManaged(true);
            
        } catch (Exception e) {
            showAlert("Error", "Error obteniendo resultados: " + e.getMessage());
        }
    }

    private void updateProgressUI(ScanProgress progress) {
        progressBar.setProgress(progress.getProgress() / 100.0);
        lblProgress.setText(String.format("%.1f%%", progress.getProgress()));
        lblFilesFound.setText(String.format("%,d archivos encontrados", progress.getFilesFound()));
        lblCurrentDir.setText(progress.getMessage());
    }

    private void showResults(ScanProgress progress) {
        try {
            var result = apiClient.getScanResult(currentScanId);
            
            lblTotalFiles.setText(String.format("%,d", result.getTotalFiles()));
            lblTotalSize.setText(FormatUtils.formatFileSize(result.getTotalSize()));
            lblScanTime.setText(String.format("%.1fs", result.getDurationSec()));
            lblScanId.setText(currentScanId);
            
            resultsSection.setVisible(true);
            resultsSection.setManaged(true);
            lblStatus.setText("Completado");
            
        } catch (Exception e) {
            showAlert("Error", "Error obteniendo resultados: " + e.getMessage());
        }
    }

    private Stage getStage() {
        return (Stage) txtFolderPath.getScene().getWindow();
    }

    private void showAlert(String title, String message) {
        Alert alert = new Alert(Alert.AlertType.INFORMATION);
        alert.setTitle(title);
        alert.setHeaderText(null);
        alert.setContentText(message);
        alert.showAndWait();
    }
}
