package com.smartfileorganizer.controllers;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import javafx.application.Platform;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.collections.transformation.FilteredList;
import javafx.collections.transformation.SortedList;
import javafx.fxml.FXML;
import javafx.fxml.Initializable;
import javafx.scene.control.*;
import javafx.scene.control.cell.CheckBoxTableCell;
import javafx.scene.control.cell.PropertyValueFactory;
import javafx.scene.layout.HBox;
import javafx.scene.layout.VBox;

import java.net.URL;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.stream.Collectors;

import com.smartfileorganizer.api.ApiClient;
import com.smartfileorganizer.models.DuplicateFile;
import com.smartfileorganizer.models.DuplicateGroup;
import com.smartfileorganizer.utils.FormatUtils;
import com.smartfileorganizer.utils.UIUtils;
import com.smartfileorganizer.utils.ConcurrencyUtils;

public class DuplicatesController implements Initializable {

    // ── Header ────────────────────────────────────────────────────────────────
    @FXML private ComboBox<String> comboScanId;
    @FXML private Button           btnRefresh;

    // ── Stats ─────────────────────────────────────────────────────────────────
    @FXML private HBox  statsSection;
    @FXML private Label lblTotalGroups;
    @FXML private Label lblTotalDuplicates;
    @FXML private Label lblSpaceWasted;
    @FXML private Label lblSpaceRecoverable;

    // ── Filters + actions ─────────────────────────────────────────────────────
    @FXML private TextField        txtFilter;
    @FXML private ComboBox<String> comboSizeFilter;
    // @FXML private ComboBox<String> comboCategoryFilter;  // FEAT 4: Category filter - disabled for now
    @FXML private CheckBox         chkShowOnlyLarge;
    @FXML private Button           btnSelectAll;
    @FXML private Button           btnDeselectAll;
    @FXML private Button           btnDeleteSelected;

    // ── Table ─────────────────────────────────────────────────────────────────
    @FXML private TableView<DuplicateFile>           tableDuplicates;
    @FXML private TableColumn<DuplicateFile, Boolean> colSelect;
    @FXML private TableColumn<DuplicateFile, String>  colGroup;
    @FXML private TableColumn<DuplicateFile, String>  colFileName;
    @FXML private TableColumn<DuplicateFile, String>  colPath;
    @FXML private TableColumn<DuplicateFile, String>  colSize;
    @FXML private TableColumn<DuplicateFile, String>  colModified;
    @FXML private TableColumn<DuplicateFile, String>  colStatus;

    // ── Group details ─────────────────────────────────────────────────────────
    @FXML private VBox  groupDetailsSection;
    @FXML private Label lblGroupHash;
    @FXML private Label lblGroupFileCount;
    @FXML private Label lblGroupTotalSize;
    @FXML private Label lblGroupWastedSize;
    @FXML private Button btnKeepOriginal;
    @FXML private Button btnDeleteAllExcept;
    @FXML private Button btnOpenFolder;

    // ── Progress ──────────────────────────────────────────────────────────────
    @FXML private VBox        progressSection;
    @FXML private ProgressBar progressBar;
    @FXML private Label       lblProgress;

    private ApiClient apiClient;
    private final ObservableList<DuplicateFile> duplicateList = FXCollections.observableArrayList();
    private final ObservableList<String>        scanList      = FXCollections.observableArrayList();
    private FilteredList<DuplicateFile>         filteredDuplicates;
    private final Map<String, DuplicateGroup>   groupMap      = new HashMap<>();

    // Currently selected group hash (for group-level actions)
    private String selectedGroupHash = null;

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        
        // Initialize UI components first
        if (comboScanId != null) {
            comboScanId.setItems(FXCollections.observableArrayList());
        }
        if (comboSizeFilter != null) {
            comboSizeFilter.setItems(FXCollections.observableArrayList());
        }
        
        setupTable();
        setupFilters();
        loadAvailableScans();
    }

    // ── Table setup ───────────────────────────────────────────────────────────

    private void setupTable() {
        colSelect.setCellValueFactory(new PropertyValueFactory<>("selected"));
        colSelect.setCellFactory(CheckBoxTableCell.forTableColumn(colSelect));
        colSelect.setEditable(true);

        colGroup.setCellValueFactory(new PropertyValueFactory<>("shortGroupId"));
        colFileName.setCellValueFactory(new PropertyValueFactory<>("fileName"));
        colPath.setCellValueFactory(new PropertyValueFactory<>("path"));
        colSize.setCellValueFactory(new PropertyValueFactory<>("formattedSize"));
        colModified.setCellValueFactory(new PropertyValueFactory<>("formattedModified"));
        colStatus.setCellValueFactory(new PropertyValueFactory<>("status"));

        tableDuplicates.setEditable(true);

        filteredDuplicates = new FilteredList<>(duplicateList, p -> true);
        SortedList<DuplicateFile> sorted = new SortedList<>(filteredDuplicates);
        sorted.comparatorProperty().bind(tableDuplicates.comparatorProperty());
        tableDuplicates.setItems(sorted);

        // Selection listener → show group details
        tableDuplicates.getSelectionModel().selectedItemProperty().addListener(
            (obs, oldVal, newVal) -> {
                if (newVal != null) {
                    selectedGroupHash = newVal.getGroupId();
                    showGroupDetails(newVal);
                }
            }
        );
    }

    // ── Filters ───────────────────────────────────────────────────────────────

    private void setupFilters() {
        comboSizeFilter.setItems(FXCollections.observableArrayList(
            "Todos", "< 1 MB", "1–10 MB", "10–100 MB", "> 100 MB"
        ));
        comboSizeFilter.getSelectionModel().selectFirst();

        // Category filter is not implemented yet - skip for now
        // comboCategoryFilter.setItems(FXCollections.observableArrayList(
        //     "Todas", "Documentos", "Imágenes", "Videos", "Audio", "Código", "Otros"
        // ));
        // comboCategoryFilter.getSelectionModel().selectFirst();

        txtFilter.textProperty().addListener((obs, o, n) -> applyFilters());
        comboSizeFilter.getSelectionModel().selectedItemProperty().addListener((obs, o, n) -> applyFilters());
        // comboCategoryFilter.getSelectionModel().selectedItemProperty().addListener((obs, o, n) -> applyFilters());  // FEAT 4
        chkShowOnlyLarge.selectedProperty().addListener((obs, o, n) -> applyFilters());
    }

    private void applyFilters() {
        String text      = txtFilter.getText().toLowerCase().trim();
        String sizeRange = comboSizeFilter.getSelectionModel().getSelectedItem();
        boolean onlyLarge = chkShowOnlyLarge.isSelected();

        filteredDuplicates.setPredicate(file -> {
            boolean matchesText = text.isEmpty() || 
                file.getFileName().toLowerCase().contains(text) || 
                file.getPath().toLowerCase().contains(text);
            
            boolean matchesSize = sizeRange == null || sizeRange.equals("Todos") || checkSizeRange(file, sizeRange);
            
            boolean matchesCategory = true;  // Always true for now (category filter disabled)
            
            return matchesText && matchesSize && matchesCategory && (!onlyLarge || file.getSizeBytes() > 10_000_000);
        });
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private boolean checkSizeRange(DuplicateFile file, String sizeRange) {
        long sizeBytes = file.getSizeBytes();
        return switch (sizeRange) {
            case "< 1 MB" -> sizeBytes < 1_000_000;
            case "1–10 MB" -> sizeBytes >= 1_000_000 && sizeBytes <= 10_000_000;
            case "10–100 MB" -> sizeBytes > 10_000_000 && sizeBytes <= 100_000_000;
            case "> 100 MB" -> sizeBytes > 100_000_000;
            default -> true; // "Todos" or null
        };
    }

    // FEAT 4: Helper method to get file category based on extension
    private String getFileCategory(String fileName) {
        String extension = "";
        int lastDot = fileName.lastIndexOf('.');
        if (lastDot > 0) {
            extension = fileName.substring(lastDot + 1).toLowerCase();
        }

        return switch (extension) {
            case "txt", "doc", "docx", "pdf", "rtf", "odt" -> "Documentos";
            case "jpg", "jpeg", "png", "gif", "bmp", "svg", "webp", "ico" -> "Imágenes";
            case "mp4", "avi", "mkv", "mov", "wmv", "flv", "webm", "mpg" -> "Videos";
            case "mp3", "wav", "flac", "aac", "ogg", "wma", "m4a" -> "Audio";
            case "java", "py", "js", "cpp", "c", "h", "cs", "php", "rb", "go", "rs", "swift", "kt", "ts", "html", "css", "xml", "json", "yaml", "yml" -> "Código";
            default -> "Otros";
        };
    }

    // ── Load scans ────────────────────────────────────────────────────────────

    private void loadAvailableScans() {
        ConcurrencyUtils.runAsync(() -> {
            try {
                var scans = apiClient.listScans();
                
                Platform.runLater(() -> {
                    scanList.clear();
                    for (Map<String, Object> s : scans) {
                        if ("completed".equals(s.get("status"))) {
                            scanList.add(s.get("scan_id").toString());
                        }
                    }
                    
                    if (comboScanId != null) {
                        comboScanId.setItems(scanList);
                        if (!scanList.isEmpty()) {
                            comboScanId.getSelectionModel().selectFirst();
                        }
                    }
                });
            } catch (Exception e) {
                Platform.runLater(() ->
                    UIUtils.showErrorDialog("Error", "No se pudieron cargar los escaneos: " + e.getMessage()));
            }
        });
    }

    // ── Refresh duplicates ────────────────────────────────────────────────────

    @FXML
    private void refreshDuplicates() {
        String scanId = comboScanId.getSelectionModel().getSelectedItem();
        if (scanId == null || scanId.isEmpty()) {
            UIUtils.showWarningDialog("Información", "Por favor selecciona un escaneo completado.");
            return;
        }

        setLoading(true, "Analizando duplicados… (esto puede tardar)");
        duplicateList.clear();
        groupMap.clear();

        apiClient.getDuplicatesAsync(scanId)
            .thenAccept(result -> Platform.runLater(() -> {
                parseDuplicatesResult(result);
                setLoading(false, "");
            }))
            .exceptionally(ex -> {
                Platform.runLater(() -> {
                    setLoading(false, "");
                    UIUtils.showErrorDialog("Error de conexión",
                        "No se pudieron cargar los duplicados: " + ex.getMessage());
                });
                return null;
            });
    }

    @SuppressWarnings("unchecked")
    private void parseDuplicatesResult(Map<String, Object> result) {
        updateStats(result);

        Object raw = result.get("groups");
        if (!(raw instanceof JsonArray)) return;

        JsonArray groups = (JsonArray) raw;

        if (groups.size() == 0) {
            UIUtils.showInfoDialog("Sin duplicados", "🎉 No se encontraron archivos duplicados en este escaneo.");
            return;
        }

        for (JsonElement groupEl : groups) {
            JsonObject g = groupEl.getAsJsonObject();

            String groupHash = safeStr(g, "hash");
            int    fileCount  = safeInt(g, "file_count");
            long   totalSize  = safeLong(g, "total_size");
            long   wasted     = safeLong(g, "wasted_size");

            groupMap.put(groupHash, new DuplicateGroup(groupHash, fileCount, totalSize, wasted));

            if (!g.has("duplicates")) continue;
            for (JsonElement fileEl : g.get("duplicates").getAsJsonArray()) {
                JsonObject f = fileEl.getAsJsonObject();
                duplicateList.add(new DuplicateFile(
                    groupHash,
                    safeStr(f, "path"),
                    safeStr(f, "name"),
                    safeLong(f, "size"),
                    safeStr(f, "modified"),
                    f.has("is_original") && f.get("is_original").getAsBoolean()
                ));
            }
        }
    }

    private void updateStats(Map<String, Object> result) {
        int  groups     = intVal(result, "total_groups");
        int  dups       = intVal(result, "total_duplicates");
        long wasted     = longVal(result, "total_wasted");

        statsSection.setVisible(true);
        statsSection.setManaged(true);
        lblTotalGroups.setText(String.valueOf(groups));
        lblTotalDuplicates.setText(String.valueOf(dups));
        lblSpaceWasted.setText(FormatUtils.formatFileSize(wasted));
        lblSpaceRecoverable.setText(FormatUtils.formatFileSize(wasted));
    }

    // ── Group details panel ───────────────────────────────────────────────────

    private void showGroupDetails(DuplicateFile file) {
        DuplicateGroup group = groupMap.get(file.getGroupId());
        if (group == null) { hideGroupDetails(); return; }

        groupDetailsSection.setVisible(true);
        groupDetailsSection.setManaged(true);

        // Show abbreviated hash
        String hash = group.getHash();
        lblGroupHash.setText(hash.length() > 16 ? hash.substring(0, 16) + "…" : hash);
        lblGroupFileCount.setText(String.valueOf(group.getFileCount()));
        lblGroupTotalSize.setText(FormatUtils.formatFileSize(group.getTotalSize()));
        lblGroupWastedSize.setText(FormatUtils.formatFileSize(group.getWastedSize()));
    }

    private void hideGroupDetails() {
        groupDetailsSection.setVisible(false);
        groupDetailsSection.setManaged(false);
    }

    // ── Selection ─────────────────────────────────────────────────────────────

    @FXML
    private void selectAll() {
        // Select only duplicates (not originals) in current filtered view
        filteredDuplicates.forEach(f -> {
            if (!f.isOriginal()) f.setSelected(true);
        });
        tableDuplicates.refresh();
        updateDeleteButton();
    }

    @FXML
    private void deselectAll() {
        duplicateList.forEach(f -> f.setSelected(false));
        tableDuplicates.refresh();
        updateDeleteButton();
    }

    private void updateDeleteButton() {
        // FIX: Count only over filtered duplicates to match selectAll behavior
        long count = filteredDuplicates.stream().filter(DuplicateFile::isSelected).count();
        btnDeleteSelected.setDisable(count == 0);
        if (count > 0) {
            long size = filteredDuplicates.stream()
                .filter(DuplicateFile::isSelected)
                .mapToLong(DuplicateFile::getSizeBytes).sum();
            btnDeleteSelected.setText("🗑️ Eliminar " + count + " (" + FormatUtils.formatFileSize(size) + ")");
        } else {
            btnDeleteSelected.setText("🗑️ Eliminar Seleccionados");
        }
    }

    // ── Delete selected ───────────────────────────────────────────────────────

    @FXML
    private void deleteSelected() {
        List<String> toDelete = duplicateList.stream()
            .filter(DuplicateFile::isSelected)
            .map(DuplicateFile::getPath)
            .collect(Collectors.toList());

        if (toDelete.isEmpty()) {
            UIUtils.showInfoDialog("Información", "No hay archivos seleccionados.");
            return;
        }

        long totalSize = duplicateList.stream()
            .filter(DuplicateFile::isSelected)
            .mapToLong(DuplicateFile::getSizeBytes).sum();

        boolean confirmed = UIUtils.showConfirmationDialog(
            "Confirmar Eliminación",
            "¿Eliminar " + toDelete.size() + " archivos (" + FormatUtils.formatFileSize(totalSize) + ")?",
            "Los archivos se moverán a la papelera de reciclaje."
        );

        if (!confirmed) return;

        setLoading(true, "Eliminando archivos…");

        apiClient.deleteFilesAsync(toDelete, true)
            .thenAccept(result -> Platform.runLater(() -> {
                setLoading(false, "");
                int deleted = intVal(result, "deleted_count");
                long freed  = longVal(result, "space_freed");

                @SuppressWarnings("unchecked")
                List<String> failed = (List<String>) result.getOrDefault("failed", List.of());

                String msg = "✅ Eliminados: " + deleted + " archivos\n"
                           + "💾 Espacio liberado: " + FormatUtils.formatFileSize(freed);
                if (!failed.isEmpty()) msg += "\n⚠️ Fallidos: " + failed.size();

                UIUtils.showInfoDialog("Eliminación completada", msg);

                // Remove deleted files from UI list
                @SuppressWarnings("unchecked")
                List<String> deletedPaths = (List<String>) result.getOrDefault("deleted", List.of());
                duplicateList.removeIf(f -> deletedPaths.contains(f.getPath()));
                updateDeleteButton();
            }))
            .exceptionally(ex -> {
                Platform.runLater(() -> {
                    setLoading(false, "");
                    UIUtils.showErrorDialog("Error", "Error eliminando: " + ex.getMessage());
                });
                return null;
            });
    }

    // ── Group-level actions ───────────────────────────────────────────────────

    @FXML
    private void keepOriginal() {
        if (selectedGroupHash == null) {
            UIUtils.showWarningDialog("Info", "Selecciona un archivo primero.");
            return;
        }

        // Select all non-originals in the selected group
        duplicateList.stream()
            .filter(f -> f.getGroupId().equals(selectedGroupHash) && !f.isOriginal())
            .forEach(f -> f.setSelected(true));

        tableDuplicates.refresh();
        updateDeleteButton();
        UIUtils.showInfoDialog("Listo", "Duplicados del grupo seleccionados. Presiona 'Eliminar Seleccionados' para borrarlos.");
    }

    @FXML
    private void deleteAllExcept() {
        keepOriginal();   // same logic: selects the duplicates
        deleteSelected(); // then deletes them
    }

    @FXML
    private void openFolder() {
        DuplicateFile sel = tableDuplicates.getSelectionModel().getSelectedItem();
        if (sel == null) { UIUtils.showWarningDialog("Info", "Selecciona un archivo primero."); return; }

        try {
            String folder = new java.io.File(sel.getPath()).getParent();
            if (folder != null) {
                new ProcessBuilder("explorer", folder).start();
            }
        } catch (Exception e) {
            UIUtils.showErrorDialog("Error", "No se pudo abrir la carpeta: " + e.getMessage());
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void setLoading(boolean loading, String message) {
        progressSection.setVisible(loading);
        progressSection.setManaged(loading);
        if (!message.isEmpty()) lblProgress.setText(message);

        btnRefresh.setDisable(loading);
        btnDeleteSelected.setDisable(loading);
        if (loading) progressBar.setProgress(ProgressBar.INDETERMINATE_PROGRESS);
    }

    private static String safeStr(JsonObject o, String k) {
        return (o.has(k) && !o.get(k).isJsonNull()) ? o.get(k).getAsString() : "";
    }
    private static int safeInt(JsonObject o, String k) {
        return (o.has(k) && !o.get(k).isJsonNull()) ? o.get(k).getAsInt() : 0;
    }
    private static long safeLong(JsonObject o, String k) {
        return (o.has(k) && !o.get(k).isJsonNull()) ? o.get(k).getAsLong() : 0L;
    }
    private static String str(Map<String, Object> m, String k) {
        Object v = m.get(k); return v != null ? v.toString() : "";
    }
    private static int intVal(Map<String, Object> m, String k) {
        try { return Integer.parseInt(str(m, k)); } catch (Exception e) { return 0; }
    }
    private static long longVal(Map<String, Object> m, String k) {
        try { return Long.parseLong(str(m, k)); } catch (Exception e) { return 0L; }
    }
}