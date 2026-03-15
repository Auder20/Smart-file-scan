package com.smartfileorganizer.controllers;

import com.smartfileorganizer.api.ApiClient;
import javafx.application.Platform;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.fxml.FXML;
import javafx.fxml.Initializable;
import javafx.scene.control.*;
import javafx.scene.control.cell.PropertyValueFactory;
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

/**
 * FIX: La inner class se llamaba "FileInfo", colisionando con el import de
 * com.smartfileorganizer.models.FileInfo en contextos donde ambos estaban
 * visibles. Renombrada a FileEntry para eliminar la ambigüedad.
 */
public class FilesViewController implements Initializable {

    @FXML private TableView<FileEntry> filesTable;
    @FXML private TableColumn<FileEntry, String> colName;
    @FXML private TableColumn<FileEntry, String> colPath;
    @FXML private TableColumn<FileEntry, Long>   colSize;
    @FXML private TableColumn<FileEntry, String> colExtension;
    @FXML private TableColumn<FileEntry, String> colCategory;
    @FXML private TableColumn<FileEntry, String> colModified;
    @FXML private TextField   txtSearch;
    @FXML private ComboBox<String> cmbCategory;
    @FXML private Label       lblScanInfo;
    @FXML private Label       lblTotalFiles;
    @FXML private Label       lblTotalSize;
    @FXML private ProgressBar progressBar;

    // FIX: paginación — botones de navegación (opcionales, se crean si existen en el FXML)
    @FXML private Button btnPrevPage;
    @FXML private Button btnNextPage;
    @FXML private Label  lblPageInfo;

    private ApiClient apiClient;
    private String scanId;
    private int currentPage = 1;
    private int totalPages  = 1;
    private static final int PAGE_SIZE = 500;

    private final ObservableList<FileEntry> allFiles      = FXCollections.observableArrayList();
    private final ObservableList<FileEntry> filteredFiles = FXCollections.observableArrayList();

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        setupTable();
        setupFilters();
    }

    public void setScanId(String scanId) {
        this.scanId = scanId;
        currentPage = 1;
        loadFiles(currentPage);
    }

    // ── Table ─────────────────────────────────────────────────────────────────

    private void setupTable() {
        colName.setCellValueFactory(new PropertyValueFactory<>("name"));
        colPath.setCellValueFactory(new PropertyValueFactory<>("path"));
        colSize.setCellValueFactory(new PropertyValueFactory<>("size"));
        colExtension.setCellValueFactory(new PropertyValueFactory<>("extension"));
        colCategory.setCellValueFactory(new PropertyValueFactory<>("category"));
        colModified.setCellValueFactory(new PropertyValueFactory<>("modified"));

        colSize.setCellFactory(column -> new TableCell<FileEntry, Long>() {
            @Override
            protected void updateItem(Long size, boolean empty) {
                super.updateItem(size, empty);
                setText(empty || size == null ? null : formatFileSize(size));
            }
        });

        filesTable.setItems(filteredFiles);
    }

    // ── Filters ───────────────────────────────────────────────────────────────

    private void setupFilters() {
        cmbCategory.getItems().addAll("Todas", "document", "image", "video",
                                       "audio", "code", "archive", "executable", "other");
        cmbCategory.setValue("Todas");
        cmbCategory.setOnAction(e -> applyFilters());
        txtSearch.textProperty().addListener((obs, o, n) -> applyFilters());
    }

    private void applyFilters() {
        String search = txtSearch.getText().toLowerCase().trim();
        String cat    = cmbCategory.getValue();

        filteredFiles.clear();
        for (FileEntry f : allFiles) {
            boolean matchSearch = search.isEmpty()
                || f.getName().toLowerCase().contains(search)
                || f.getPath().toLowerCase().contains(search);
            boolean matchCat = "Todas".equals(cat) || cat.equalsIgnoreCase(f.getCategory());
            if (matchSearch && matchCat) filteredFiles.add(f);
        }
        updateStats();
    }

    // ── Load ──────────────────────────────────────────────────────────────────

    /**
     * FIX: paginación real — el original cargaba 1000 archivos de golpe.
     * Ahora carga PAGE_SIZE por página y permite navegar con btnPrevPage / btnNextPage.
     */
    private void loadFiles(int page) {
        progressBar.setVisible(true);
        lblScanInfo.setText("Cargando archivos (página " + page + ")...");

        CompletableFuture.runAsync(() -> {
            try {
                Map<String, Object> response = apiClient.getScanFiles(scanId, page, PAGE_SIZE);

                @SuppressWarnings("unchecked")
                List<Map<String, Object>> files = (List<Map<String, Object>>) response.get("files");

                Object tp = response.get("total_pages");
                totalPages = tp != null ? ((Number) tp).intValue() : 1;

                Platform.runLater(() -> {
                    allFiles.clear();
                    if (files != null) {
                        for (Map<String, Object> fd : files) {
                            allFiles.add(new FileEntry(
                                (String) fd.get("name"),
                                (String) fd.get("path"),
                                ((Number) fd.get("size")).longValue(),
                                (String) fd.get("extension"),
                                (String) fd.get("category"),
                                (String) fd.get("modified")
                            ));
                        }
                    }
                    filteredFiles.setAll(allFiles);
                    updateStats();
                    updateScanInfo(response);
                    updatePagination();
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
        int total    = filteredFiles.size();
        long size    = filteredFiles.stream().mapToLong(FileEntry::getSize).sum();
        lblTotalFiles.setText(String.format("Archivos: %,d", total));
        lblTotalSize.setText("Tamaño total: " + formatFileSize(size));
    }

    private void updateScanInfo(Map<String, Object> r) {
        Object tf = r.get("total_files");
        Object ts = r.get("total_size");
        String info = String.format("Scan: %s | %s archivos",
            r.get("scan_id"),
            tf != null ? String.format("%,d", ((Number) tf).intValue()) : "?");
        if (ts != null) info += " | " + formatFileSize(((Number) ts).longValue());
        lblScanInfo.setText(info);
    }

    private void updatePagination() {
        if (lblPageInfo != null)
            lblPageInfo.setText("Página " + currentPage + " / " + totalPages);
        if (btnPrevPage != null) btnPrevPage.setDisable(currentPage <= 1);
        if (btnNextPage != null) btnNextPage.setDisable(currentPage >= totalPages);
    }

    // ── Pagination actions ────────────────────────────────────────────────────

    @FXML
    private void prevPage() {
        if (currentPage > 1) {
            currentPage--;
            loadFiles(currentPage);
        }
    }

    @FXML
    private void nextPage() {
        if (currentPage < totalPages) {
            currentPage++;
            loadFiles(currentPage);
        }
    }

    // ── Export ────────────────────────────────────────────────────────────────

    @FXML
    private void clearFilters() {
        txtSearch.clear();
        cmbCategory.setValue("Todas");
    }

    @FXML
    private void exportCsv() {
        try {
            FileChooser fc = new FileChooser();
            fc.setTitle("Exportar archivos a CSV");
            fc.getExtensionFilters().add(new FileChooser.ExtensionFilter("CSV Files", "*.csv"));
            fc.setInitialFileName("scan_files_" + scanId + ".csv");
            java.io.File selected = fc.showSaveDialog(new Stage());
            if (selected == null) return;

            try (BufferedWriter w = Files.newBufferedWriter(selected.toPath())) {
                w.write("name,path,size,extension,category,modified\n");
                for (FileEntry f : allFiles) {
                    w.write(String.format("%s,%s,%d,%s,%s,%s%n",
                        csv(f.getName()), csv(f.getPath()), f.getSize(),
                        csv(f.getExtension()), csv(f.getCategory()), csv(f.getModified())));
                }
            }
            showAlert("Éxito", "Archivo CSV exportado correctamente en:\n" + selected.getPath());
        } catch (Exception e) {
            showAlert("Error", "No se pudo exportar a CSV: " + e.getMessage());
        }
    }

    @FXML
    private void exportJson() {
        try {
            FileChooser fc = new FileChooser();
            fc.setTitle("Exportar archivos a JSON");
            fc.getExtensionFilters().add(new FileChooser.ExtensionFilter("JSON Files", "*.json"));
            fc.setInitialFileName("scan_files_" + scanId + ".json");
            java.io.File selected = fc.showSaveDialog(new Stage());
            if (selected == null) return;

            Gson gson = new Gson();
            JsonArray arr = new JsonArray();
            for (FileEntry f : allFiles) {
                JsonObject o = new JsonObject();
                o.addProperty("name",      f.getName());
                o.addProperty("path",      f.getPath());
                o.addProperty("size",      f.getSize());
                o.addProperty("extension", f.getExtension());
                o.addProperty("category",  f.getCategory());
                o.addProperty("modified",  f.getModified());
                arr.add(o);
            }
            JsonObject root = new JsonObject();
            root.addProperty("scan_id",     scanId);
            root.addProperty("export_date", new java.util.Date().toString());
            root.addProperty("total_files", allFiles.size());
            root.add("files", arr);
            Files.writeString(selected.toPath(), gson.toJson(root));
            showAlert("Éxito", "Archivo JSON exportado correctamente en:\n" + selected.getPath());
        } catch (Exception e) {
            showAlert("Error", "No se pudo exportar a JSON: " + e.getMessage());
        }
    }

    @FXML
    private void close() {
        txtSearch.getScene().getWindow().hide();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private String formatFileSize(long bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return String.format("%.1f KB", bytes / 1024.0);
        if (bytes < 1024L * 1024 * 1024) return String.format("%.1f MB", bytes / (1024.0 * 1024));
        return String.format("%.1f GB", bytes / (1024.0 * 1024 * 1024));
    }

    private String csv(String v) {
        if (v == null) return "";
        return v.replace("\"", "\"\"").replace(",", ";").replace("\n", " ");
    }

    private void showAlert(String title, String message) {
        Alert a = new Alert(Alert.AlertType.INFORMATION);
        a.setTitle(title);
        a.setHeaderText(null);
        a.setContentText(message);
        a.showAndWait();
    }

    // ── Inner model ───────────────────────────────────────────────────────────

    /**
     * FIX: renombrado de FileInfo → FileEntry para evitar colisión con
     * com.smartfileorganizer.models.FileInfo y con javafx.scene.control imports.
     */
    public static class FileEntry {
        private final String name;
        private final String path;
        private final long   size;
        private final String extension;
        private final String category;
        private final String modified;

        public FileEntry(String name, String path, long size,
                         String extension, String category, String modified) {
            this.name = name; this.path = path; this.size = size;
            this.extension = extension; this.category = category; this.modified = modified;
        }

        public String getName()      { return name; }
        public String getPath()      { return path; }
        public long   getSize()      { return size; }
        public String getExtension() { return extension; }
        public String getCategory()  { return category; }
        public String getModified()  { return modified; }
    }
}