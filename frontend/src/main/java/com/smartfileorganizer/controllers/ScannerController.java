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
import com.smartfileorganizer.utils.ConcurrencyUtils;

import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.util.prefs.Preferences;
import javafx.stage.FileChooser;
import java.net.URL;
import java.util.ResourceBundle;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

import com.smartfileorganizer.api.ApiClient;
import com.smartfileorganizer.models.ScanInfo;
import com.smartfileorganizer.models.ScanProgress;
import com.smartfileorganizer.utils.FormatUtils;
import com.google.gson.JsonObject;

public class ScannerController implements Initializable {

    // ── FXML fields ───────────────────────────────────────────────────────────

    @FXML private TextField         txtFolderPath;
    @FXML private Button            btnBrowse;
    @FXML private Spinner<Integer>  spinnerMaxDepth;
    @FXML private CheckBox          chkIncludeHidden;
    @FXML private Button            btnStartScan;
    @FXML private Button            btnStopScan;
    @FXML private Button            btnRefresh;
    @FXML private Label             lblStatus;
    @FXML private javafx.scene.shape.Circle statusIndicator;
    @FXML private VBox              progressSection;
    @FXML private ProgressBar       progressBar;
    @FXML private Label             lblProgress;
    @FXML private Label             lblFilesFound;
    @FXML private Label             lblCurrentDir;
    @FXML private VBox              resultsSection;
    @FXML private Button            btnViewFiles;
    @FXML private Button            btnExport;
    @FXML private Label             lblTotalFiles;
    @FXML private Label             lblTotalSize;
    @FXML private Label             lblScanTime;
    @FXML private Label             lblScanId;
    @FXML private TableView<ScanInfo>                              tableScans;
    @FXML private TableColumn<ScanInfo, String>                    colScanId;
    @FXML private TableColumn<ScanInfo, String>                    colStatus;
    @FXML private TableColumn<ScanInfo, Integer>                   colFiles;
    @FXML private TableColumn<ScanInfo, String>                    colDate;
    @FXML private TableColumn<ScanInfo, javafx.scene.layout.HBox> colActions;

    // ── State ─────────────────────────────────────────────────────────────────

    private ApiClient apiClient;
    private String    currentScanId;
    private final ObservableList<ScanInfo> scanList = FXCollections.observableArrayList();

    private volatile boolean isScanning    = false;
    private volatile boolean scanCompleted = false;
    private volatile boolean wsConnected   = false;

    // ── Init ──────────────────────────────────────────────────────────────────

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        setupTable();
        setupListeners();
        
        Preferences prefs = Preferences.userNodeForPackage(ScannerController.class);
        String lastPath = prefs.get("last_scanned_path", "");
        if (!lastPath.isEmpty()) {
            txtFolderPath.setText(lastPath);
        }
        
        refreshScans();
    }

    private void setupTable() {
        colScanId.setCellValueFactory(new PropertyValueFactory<>("scanId"));
        colStatus.setCellValueFactory(new PropertyValueFactory<>("status"));
        colFiles.setCellValueFactory(new PropertyValueFactory<>("filesFound"));
        colDate.setCellValueFactory(new PropertyValueFactory<>("date"));
        colActions.setCellValueFactory(new PropertyValueFactory<>("actions"));
        tableScans.setItems(scanList);
    }

    private void setupListeners() {
        txtFolderPath.textProperty().addListener((obs, o, n) ->
            btnStartScan.setDisable(n == null || n.trim().isEmpty()));
        SpinnerValueFactory.IntegerSpinnerValueFactory factory =
            new SpinnerValueFactory.IntegerSpinnerValueFactory(1, 50, 20);
        spinnerMaxDepth.setValueFactory(factory);
    }

    // ── Browse ────────────────────────────────────────────────────────────────

    @FXML
    private void browseFolder() {
        try {
            List<Map<String, Object>> drives = apiClient.getAvailableDrives();
            showFolderSelectionDialog(drives);
        } catch (Exception e) {
            UIUtils.showErrorDialog("Error", "Usa el explorador de carpetas integrado. " + e.getMessage());
        }
    }

    private void showFolderSelectionDialog(List<Map<String, Object>> drives) {
        if (drives == null || drives.isEmpty()) {
            UIUtils.showErrorDialog("Error", "No se detectaron unidades disponibles.");
            return;
        }

        Dialog<String> dialog = new Dialog<>();
        dialog.setTitle("Seleccionar Carpeta para Escanear");
        dialog.setHeaderText("Elige una unidad y navega hasta la carpeta deseada");

        ButtonType selectBT = new ButtonType("Seleccionar", ButtonBar.ButtonData.OK_DONE);
        ButtonType cancelBT = new ButtonType("Cancelar",    ButtonBar.ButtonData.CANCEL_CLOSE);
        dialog.getDialogPane().getButtonTypes().addAll(selectBT, cancelBT);

        VBox content = new VBox(10);
        content.setPadding(new Insets(20));

        ComboBox<Map<String, Object>> driveCombo = new ComboBox<>();
        driveCombo.getItems().addAll(drives);
        driveCombo.setConverter(new StringConverter<Map<String, Object>>() {
            @Override
            public String toString(Map<String, Object> d) {
                if (d == null) return "";
                String name = (String) d.get("name");
                Object fs   = d.get("free_space");
                Object rem  = d.get("is_removable");
                Object fsys = d.get("filesystem");
                StringBuilder sb = new StringBuilder(name != null ? name : "?");
                if (Boolean.TRUE.equals(rem)) sb.append(" (USB)");
                if (fsys != null && !fsys.toString().isEmpty())
                    sb.append(" [").append(fsys).append("]");
                if (fs instanceof Number)
                    sb.append(" (")
                      .append(FormatUtils.formatFileSize(((Number) fs).longValue()))
                      .append(" libre)");
                return sb.toString();
            }
            @Override
            public Map<String, Object> fromString(String s) { return null; }
        });

        TreeView<PathItem> folderTree = new TreeView<>();
        folderTree.setPrefHeight(300);
        folderTree.setPrefWidth(400);

        driveCombo.getSelectionModel().selectedItemProperty().addListener((obs, o, n) -> {
            if (n != null) loadFolderTree(folderTree, (String) n.get("path"));
        });
        if (!drives.isEmpty()) driveCombo.getSelectionModel().selectFirst();

        content.getChildren().addAll(
            new Label("Unidad:"), driveCombo,
            new Label("Carpetas:"), folderTree
        );
        dialog.getDialogPane().setContent(content);

        Node selectBtn = dialog.getDialogPane().lookupButton(selectBT);
        selectBtn.setDisable(true);
        folderTree.getSelectionModel().selectedItemProperty().addListener((obs, o, n) ->
            selectBtn.setDisable(
                n == null || "Loading...".equals(n.getValue().toString())
            )
        );

        dialog.setResultConverter(bt -> {
            if (bt == selectBT) {
                TreeItem<PathItem> sel = folderTree.getSelectionModel().getSelectedItem();
                if (sel != null && sel.getValue() != null)
                    return sel.getValue().getFullPath();
            }
            return null;
        });

        dialog.showAndWait().ifPresent(path -> {
            txtFolderPath.setText(path);
            validateSelectedPath(path);
        });
    }

    private void loadFolderTree(TreeView<PathItem> treeView, String rootPath) {
        TreeItem<PathItem> rootItem = new TreeItem<>(new PathItem("Loading...", rootPath));
        treeView.setRoot(rootItem);
        rootItem.setExpanded(true);

        CompletableFuture.runAsync(() -> {
            try {
                List<Map<String, Object>> folders = apiClient.exploreFolders(rootPath, false, 1);
                Platform.runLater(() -> {
                    rootItem.getChildren().clear();
                    rootItem.setValue(new PathItem(rootPath, rootPath));

                    for (Map<String, Object> f : folders) {
                        if (!Boolean.TRUE.equals(f.get("is_directory"))) continue;

                        String fp   = (String) f.get("path");
                        String fn   = (String) f.get("name");
                        Object fc   = f.get("file_count");
                        String disp = fn + (fc != null ? " (" + fc + " archivos)" : "");

                        TreeItem<PathItem> item = new TreeItem<>(new PathItem(disp, fp));

                        if (!fn.contains("(sin acceso)")) {
                            item.getChildren().add(
                                new TreeItem<>(new PathItem("Loading...", "")));
                            item.expandedProperty().addListener((obs, was, now) -> {
                                if (now && item.getChildren().size() == 1 && "Loading...".equals(item.getChildren().get(0).getValue().toString())) {
                                    loadSubFolders(item, fp);
                                }
                            });
                        } else {
                            // Fix phantom arrow: Empty node to show it contains 0 folders, or just don't add dummy node.
                        }
                        rootItem.getChildren().add(item);
                    }
                });
            } catch (Exception e) {
                Platform.runLater(() ->
                    rootItem.setValue(new PathItem("Error: " + e.getMessage(), "")));
            }
        });
    }

    private void loadSubFolders(TreeItem<PathItem> parentItem, String parentPath) {
        CompletableFuture.runAsync(() -> {
            try {
                List<Map<String, Object>> subFolders =
                    apiClient.exploreFolders(parentPath, false, 1);
                Platform.runLater(() -> {
                    parentItem.getChildren().clear();
                    for (Map<String, Object> f : subFolders) {
                        if (!Boolean.TRUE.equals(f.get("is_directory"))) continue;
                        String fp = (String) f.get("path");
                        String fn = (String) f.get("name");
                        Object fc = f.get("file_count");
                        TreeItem<PathItem> item = new TreeItem<>(new PathItem(fn + (fc != null ? " (" + fc + " archivos)" : ""), fp));
                        
                        // We do not know if subfolder has more, we add dummy to allow expanding.
                        if (!fn.contains("(sin acceso)")) {
                            item.getChildren().add(new TreeItem<>(new PathItem("Loading...", "")));
                            item.expandedProperty().addListener((obs, was, now) -> {
                                if (now && item.getChildren().size() == 1 && "Loading...".equals(item.getChildren().get(0).getValue().toString())) {
                                    loadSubFolders(item, fp);
                                }
                            });
                        }
                        
                        parentItem.getChildren().add(item);
                    }
                });
            } catch (Exception e) {
                Platform.runLater(() -> {
                    parentItem.getChildren().clear();
                    parentItem.getChildren().add(
                        new TreeItem<>(new PathItem("Error: " + e.getMessage(), "")));
                });
            }
        });
    }

    private void validateSelectedPath(String path) {
        try {
            Map<String, Object> v = apiClient.validateScanPath(path);
            boolean valid = Boolean.TRUE.equals(v.get("valid"));
            String msg = valid
                ? "Ruta válida"
                : ((String) v.getOrDefault("reason", "Ruta inválida") + 
                  (v.containsKey("resolved_path") ? " (Intentado: " + v.get("resolved_path") + ")" : ""));
            if (valid && v.get("estimated_files") != null) {
                msg += " (~" + FormatUtils.formatNumber(
                    ((Number) v.get("estimated_files")).intValue()) + " archivos)";
            }
            lblStatus.setText(msg);
            lblStatus.setStyle(valid
                ? "-fx-text-fill: #10B981;"
                : "-fx-text-fill: #EF4444;");
            statusIndicator.setFill(javafx.scene.paint.Color.web(valid ? "#10B981" : "#EF4444"));
        } catch (Exception e) {
            lblStatus.setText("Error validando ruta: " + e.getMessage());
            lblStatus.setStyle("-fx-text-fill: #EF4444;");
            statusIndicator.setFill(javafx.scene.paint.Color.web("#EF4444"));
        }
    }

    // ── Scan ──────────────────────────────────────────────────────────────────

    @FXML
    private void startScan() {
        String path = txtFolderPath.getText().trim();
        if (path.isEmpty()) {
            UIUtils.showErrorDialog("Error", "Selecciona una carpeta.");
            return;
        }

        btnStartScan.setDisable(true);
        btnStopScan.setDisable(false);
        progressSection.setVisible(true);  progressSection.setManaged(true);
        resultsSection.setVisible(false);  resultsSection.setManaged(false);
        lblStatus.setText("Iniciando escaneo...");
        lblStatus.setStyle("-fx-text-fill: #4B9EFF;");
        statusIndicator.setFill(javafx.scene.paint.Color.web("#4B9EFF"));
        isScanning    = true;
        scanCompleted = false;

        ConcurrencyUtils.runAsync(() -> {
            try {
                Preferences prefs = Preferences.userNodeForPackage(ScannerController.class);
                prefs.put("last_scanned_path", path);

                currentScanId = apiClient.startScan(
                    path, spinnerMaxDepth.getValue(), chkIncludeHidden.isSelected());

                Platform.runLater(() -> {
                    lblStatus.setText("Escaneando...");
                    lblStatus.setStyle("-fx-text-fill: #4B9EFF;");
                    statusIndicator.setFill(javafx.scene.paint.Color.web("#4B9EFF"));
                    apiClient.connectScanWebSocket(
                        currentScanId,
                        this::handleWsMessage,
                        this::onScanComplete,
                        this::onScanError);
                    wsConnected = true;
                    refreshScans();
                });
            } catch (Exception e) {
                Platform.runLater(() -> {
                    resetScanUI();
                    lblStatus.setText("Error");
                    lblStatus.setStyle("-fx-text-fill: #EF4444;");
                    statusIndicator.setFill(javafx.scene.paint.Color.web("#EF4444"));
                    UIUtils.showErrorDialog("Error",
                        "No se pudo iniciar el escaneo: " + e.getMessage());
                });
            }
        });
    }

    @FXML
    private void stopScan() {
        isScanning = false;
        if (wsConnected) { apiClient.closeScanWebSocket(); wsConnected = false; }

        if (currentScanId != null) {
            String tempId = currentScanId;
            ConcurrencyUtils.runAsync(() -> {
                try { 
                    apiClient.deleteScan(tempId); 
                    Platform.runLater(() -> UIUtils.showInfoDialog("Detenido", "El escaneo ha sido cancelado exitosamente."));
                }
                catch (Exception e) {
                    System.err.println("Error cancelling scan: " + e.getMessage());
                }
            });
        }

        resetScanUI();
        lblStatus.setText("Detenido");
        lblStatus.setStyle("-fx-text-fill: #E8E8E8;");
        statusIndicator.setFill(javafx.scene.paint.Color.web("#E8E8E8"));
        refreshScans();
    }

    private void resetScanUI() {
        btnStartScan.setDisable(false);
        btnStopScan.setDisable(true);
        progressSection.setVisible(false);
        progressSection.setManaged(false);
    }

    // ── WebSocket handlers ────────────────────────────────────────────────────

    private void handleWsMessage(JsonObject data) {
        if (!data.has("type")) return;
        switch (data.get("type").getAsString()) {
            case "progress"  -> updateProgressUIFromWs(data);
            case "completed" -> onScanComplete();
            case "error"     -> onScanError(
                data.has("message") ? data.get("message").getAsString() : "Error desconocido");
        }
    }

    private void updateProgressUIFromWs(JsonObject data) {
        double progress = data.has("progress")    ? data.get("progress").getAsDouble()  : 0;
        int    found    = data.has("files_found")  ? data.get("files_found").getAsInt()  : 0;
        String message  = data.has("message")     ? data.get("message").getAsString()   : "";

        progressBar.setProgress(progress / 100.0);
        lblProgress.setText(String.format("%.1f%%", progress));
        lblFilesFound.setText(String.format("%,d archivos encontrados", found));
        lblCurrentDir.setText(message);
        lblStatus.setText("Escaneando en progreso...");
        lblStatus.setStyle("-fx-text-fill: #4B9EFF;");
        statusIndicator.setFill(javafx.scene.paint.Color.web("#4B9EFF"));
    }

    private void onScanComplete() {
        if (scanCompleted) return;
        scanCompleted = true;
        isScanning    = false;
        if (wsConnected) { apiClient.closeScanWebSocket(); wsConnected = false; }
        resetScanUI();
        lblStatus.setText("✅ Completado");
        lblStatus.setStyle("-fx-text-fill: #10B981;");
        statusIndicator.setFill(javafx.scene.paint.Color.web("#10B981"));

        ConcurrencyUtils.runAsync(() -> {
            try {
                var result = apiClient.getScanResult(currentScanId);
                Platform.runLater(() -> {
                    lblTotalFiles.setText(String.format("%,d", result.getTotalFiles()));
                    lblTotalSize.setText(FormatUtils.formatFileSize(result.getTotalSize()));
                    lblScanTime.setText(String.format("%.1fs", result.getDurationSec()));
                    lblScanId.setText(currentScanId);
                    resultsSection.setVisible(true);
                    resultsSection.setManaged(true);
                    refreshScans();
                });
            } catch (Exception e) {
                Platform.runLater(() ->
                    UIUtils.showErrorDialog("Error",
                        "Error obteniendo resultados: " + e.getMessage()));
            }
        });
    }

    private void onScanError(String error) {
        isScanning = false;
        if (wsConnected) { apiClient.closeScanWebSocket(); wsConnected = false; }
        resetScanUI();
        lblStatus.setText("Error: " + error);
        lblStatus.setStyle("-fx-text-fill: #EF4444;");
        statusIndicator.setFill(javafx.scene.paint.Color.web("#EF4444"));
        UIUtils.showErrorDialog("Error de Escaneo", error);
    }

    // ── Other actions ─────────────────────────────────────────────────────────

    @FXML
    private void viewFiles() {
        if (currentScanId != null) UIUtils.showFilesView(currentScanId, "completed");
    }

    @FXML
    private void exportResults() {
        if (currentScanId == null) {
            UIUtils.showErrorDialog("Error", "No hay resultados para exportar.");
            return;
        }

        FileChooser fc = new FileChooser();
        fc.setTitle("Exportar Resultados");
        fc.getExtensionFilters().addAll(
            new FileChooser.ExtensionFilter("CSV (*.csv)", "*.csv"),
            new FileChooser.ExtensionFilter("JSON (*.json)", "*.json")
        );
        File file = fc.showSaveDialog(getStage());
        if (file == null) return;

        ConcurrencyUtils.runAsync(() -> {
            try {
                boolean isJson = file.getName().toLowerCase().endsWith(".json");
                int page = 1;
                int pageSize = 1000;
                List<Map<String, Object>> allFiles = new java.util.ArrayList<>();
                
                while (true) {
                    Map<String, Object> resp = apiClient.getScanFiles(currentScanId, page, pageSize);
                    List<Map<String, Object>> files = (List<Map<String, Object>>) resp.get("files");
                    if (files != null) allFiles.addAll(files);
                    
                    if (!Boolean.TRUE.equals(resp.get("files_truncated"))) break;
                    int totalPages = ((Number) resp.get("total_pages")).intValue();
                    if (page >= totalPages) break;
                    page++;
                }

                if (isJson) {
                    try (FileWriter writer = new FileWriter(file)) {
                        new com.google.gson.GsonBuilder().setPrettyPrinting().create().toJson(allFiles, writer);
                    }
                } else {
                    try (FileWriter writer = new FileWriter(file)) {
                        writer.write("scan_id,path,name,size,extension,category,modified\n");
                        for (Map<String, Object> f : allFiles) {
                            writer.write(String.format("%s,\"%s\",\"%s\",%s,%s,%s,%s\n",
                                currentScanId,
                                f.get("path"), f.get("name"), f.get("size"),
                                f.get("extension"), f.get("category"), f.get("modified")
                            ));
                        }
                    }
                }

                Platform.runLater(() -> UIUtils.showInfoDialog("Exportación exitosa", "Resultados guardados a " + file.getName()));
            } catch (Exception e) {
                Platform.runLater(() -> UIUtils.showErrorDialog("Error", "Fallo al exportar: " + e.getMessage()));
            }
        });
    }

    @FXML
    private void refreshScans() {
        ConcurrencyUtils.runAsync(() -> {
            try {
                var scans = apiClient.listScans();
                Platform.runLater(() -> {
                    scanList.clear();
                    for (var s : scans)
                        scanList.add(new ScanInfo(
                            s.get("scan_id").toString(),
                            s.get("status").toString(),
                            Integer.parseInt(s.get("files_found").toString()),
                            FormatUtils.formatDate(java.time.LocalDateTime.now()),
                            scanList, apiClient));
                });
            } catch (Exception e) {
                System.err.println("Error refrescando escaneos: " + e.getMessage());
            }
        });
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private Stage getStage() {
        return (Stage) txtFolderPath.getScene().getWindow();
    }

    // =========================================================================
    // Inner class: PathItem
    // =========================================================================
    /**
     * FIX: en el archivo original PathItem era una clase de nivel superior
     * definida al final del mismo fichero (fuera de ScannerController).
     * Java permite esto en un archivo .java no-public, pero al reescribir
     * el controlador como clase única se omitió.
     *
     * Ahora vive como static inner class dentro de ScannerController,
     * que es el patrón correcto: solo ScannerController la usa, y así
     * el compilador la encuentra sin ningún import adicional.
     */
    static class PathItem {
        private final String displayName;
        private final String fullPath;

        PathItem(String displayName, String fullPath) {
            this.displayName = displayName;
            this.fullPath    = fullPath;
        }

        public String getDisplayName() { return displayName; }
        public String getFullPath()    { return fullPath; }

        @Override
        public String toString() { return displayName; }
    }
}