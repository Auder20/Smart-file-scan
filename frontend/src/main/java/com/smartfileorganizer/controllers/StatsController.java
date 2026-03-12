package com.smartfileorganizer.controllers;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import javafx.application.Platform;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.fxml.FXML;
import javafx.fxml.Initializable;
import javafx.geometry.Side;
import javafx.scene.chart.PieChart;
import javafx.scene.control.*;
import javafx.scene.control.cell.PropertyValueFactory;
import javafx.scene.layout.VBox;

import java.net.URL;
import java.util.*;
import java.util.concurrent.CompletableFuture;

import com.smartfileorganizer.api.ApiClient;
import com.smartfileorganizer.models.CategoryStats;
import com.smartfileorganizer.models.LargeFile;
import com.smartfileorganizer.utils.FormatUtils;

public class StatsController implements Initializable {

    // ── Header ────────────────────────────────────────────────────────────────
    @FXML private ComboBox<String> comboScanId;
    @FXML private Button btnRefresh;
    @FXML private Button btnExport;

    // ── General stats cards ───────────────────────────────────────────────────
    @FXML private VBox  generalStatsSection;
    @FXML private Label lblTotalFiles;
    @FXML private Label lblTotalSize;
    @FXML private Label lblEmptyFiles;
    @FXML private Label lblOldFiles;

    // ── Chart + category table ────────────────────────────────────────────────
    @FXML private VBox chartContainer;
    @FXML private TableView<CategoryStats>          tableCategories;
    @FXML private TableColumn<CategoryStats, String>  colCategory;
    @FXML private TableColumn<CategoryStats, Integer> colFileCount;
    @FXML private TableColumn<CategoryStats, String>  colCategorySize;
    @FXML private TableColumn<CategoryStats, Double>  colPercentage;

    // ── Largest files ─────────────────────────────────────────────────────────
    @FXML private ComboBox<Integer>            comboTopCount;
    @FXML private TableView<LargeFile>         tableLargestFiles;
    @FXML private TableColumn<LargeFile, Integer> colRank;
    @FXML private TableColumn<LargeFile, String>  colLargeFileName;
    @FXML private TableColumn<LargeFile, String>  colLargeFilePath;
    @FXML private TableColumn<LargeFile, String>  colLargeFileSize;
    @FXML private TableColumn<LargeFile, String>  colLargeFileModified;

    // ── Extensions + extra stats ──────────────────────────────────────────────
    @FXML private ListView<String> listExtensions;
    @FXML private Label lblOldFilesSize;
    @FXML private Label lblAvgFileSize;
    @FXML private Label lblFilesPerCategory;

    // ── Progress ──────────────────────────────────────────────────────────────
    @FXML private VBox        progressSection;
    @FXML private ProgressBar progressBar;
    @FXML private Label       lblProgress;

    private ApiClient apiClient;
    private final ObservableList<CategoryStats> categoryList   = FXCollections.observableArrayList();
    private final ObservableList<LargeFile>     largeFilesList = FXCollections.observableArrayList();
    private final ObservableList<String>        scanList       = FXCollections.observableArrayList();
    private final ObservableList<String>        extensionsList = FXCollections.observableArrayList();

    // Cached data for the currently selected scan
    private String lastLoadedScanId = null;

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        setupTables();
        setupCombos();
        loadAvailableScans();
    }

    // ── Setup ─────────────────────────────────────────────────────────────────

    private void setupTables() {
        colCategory.setCellValueFactory(new PropertyValueFactory<>("category"));
        colFileCount.setCellValueFactory(new PropertyValueFactory<>("fileCount"));
        colCategorySize.setCellValueFactory(new PropertyValueFactory<>("formattedSize"));
        colPercentage.setCellValueFactory(new PropertyValueFactory<>("formattedPercentage"));
        tableCategories.setItems(categoryList);

        colRank.setCellValueFactory(new PropertyValueFactory<>("rank"));
        colLargeFileName.setCellValueFactory(new PropertyValueFactory<>("fileName"));
        colLargeFilePath.setCellValueFactory(new PropertyValueFactory<>("path"));
        colLargeFileSize.setCellValueFactory(new PropertyValueFactory<>("formattedSize"));
        colLargeFileModified.setCellValueFactory(new PropertyValueFactory<>("formattedModified"));
        tableLargestFiles.setItems(largeFilesList);

        listExtensions.setItems(extensionsList);
    }

    private void setupCombos() {
        comboTopCount.setItems(FXCollections.observableArrayList(5, 10, 20, 50, 100));
        comboTopCount.getSelectionModel().select(Integer.valueOf(10));
        comboTopCount.getSelectionModel().selectedItemProperty().addListener(
            (obs, o, n) -> { if (lastLoadedScanId != null) loadLargestFiles(lastLoadedScanId, n); }
        );
    }

    private void loadAvailableScans() {
        apiClient.listAllScansAsync()
            .thenAccept(scans -> Platform.runLater(() -> {
                scanList.clear();
                for (Map<String, Object> s : scans) {
                    if ("completed".equals(s.get("status"))) {
                        scanList.add(s.get("scan_id").toString());
                    }
                }
                comboScanId.setItems(scanList);
                if (!scanList.isEmpty()) {
                    comboScanId.getSelectionModel().selectFirst();
                }
            }))
            .exceptionally(ex -> {
                Platform.runLater(() ->
                    showAlert("Error", "No se pudieron cargar los escaneos: " + ex.getMessage()));
                return null;
            });
    }

    // ── Refresh ───────────────────────────────────────────────────────────────

    @FXML
    private void refreshStats() {
        String scanId = comboScanId.getSelectionModel().getSelectedItem();
        if (scanId == null || scanId.isEmpty()) {
            showAlert("Info", "Por favor selecciona un escaneo completado.");
            return;
        }

        lastLoadedScanId = scanId;
        showProgress(true, "Cargando estadísticas...");

        int topLimit = Optional.ofNullable(comboTopCount.getValue()).orElse(10);

        // Run both calls in parallel
        CompletableFuture<Map<String, Object>>    statsFuture  = apiClient.getStatsAsync(scanId);
        CompletableFuture<List<Map<String, Object>>> largestFuture = apiClient.getLargestFilesAsync(scanId, topLimit);
        CompletableFuture<List<Map<String, Object>>> extsFuture    = apiClient.getExtensionStatsAsync(scanId);

        CompletableFuture.allOf(statsFuture, largestFuture, extsFuture)
            .thenRun(() -> {
                try {
                    Map<String, Object>    stats   = statsFuture.get();
                    List<Map<String, Object>> largest = largestFuture.get();
                    List<Map<String, Object>> exts    = extsFuture.get();

                    Platform.runLater(() -> {
                        updateGeneralStats(stats);
                        updateCategoryStats(stats);
                        updateLargestFiles(largest);
                        updateExtensions(exts);
                        updateAdditionalStats(stats);

                        generalStatsSection.setVisible(true);
                        generalStatsSection.setManaged(true);
                        showProgress(false, "");
                    });
                } catch (Exception e) {
                    Platform.runLater(() -> {
                        showProgress(false, "");
                        showAlert("Error", "Error cargando estadísticas: " + e.getMessage());
                    });
                }
            })
            .exceptionally(ex -> {
                Platform.runLater(() -> {
                    showProgress(false, "");
                    showAlert("Error", "Error de conexión: " + ex.getMessage());
                });
                return null;
            });
    }

    // ── Data updaters ─────────────────────────────────────────────────────────

    private void updateGeneralStats(Map<String, Object> stats) {
        lblTotalFiles.setText(FormatUtils.formatNumber(intVal(stats, "total_files")));
        lblTotalSize.setText(FormatUtils.formatFileSize(longVal(stats, "total_size")));
        lblEmptyFiles.setText(FormatUtils.formatNumber(intVal(stats, "empty_files")));
        lblOldFiles.setText(FormatUtils.formatNumber(intVal(stats, "old_files_count")));
    }

    private void updateCategoryStats(Map<String, Object> stats) {
        categoryList.clear();

        Object raw = stats.get("by_category");
        if (!(raw instanceof JsonArray)) return;

        JsonArray arr = (JsonArray) raw;
        for (JsonElement el : arr) {
            JsonObject o = el.getAsJsonObject();
            categoryList.add(new CategoryStats(
                safeStr(o, "category"),
                safeInt(o, "file_count"),
                safeLong(o, "total_size"),
                safeDouble(o, "percentage")
            ));
        }

        buildPieChart();
    }

    private void buildPieChart() {
        chartContainer.getChildren().clear();

        if (categoryList.isEmpty()) {
            chartContainer.getChildren().add(new Label("No hay datos de categorías"));
            return;
        }

        ObservableList<PieChart.Data> pieData = FXCollections.observableArrayList();
        for (CategoryStats c : categoryList) {
            double mb = c.getTotalSize() / (1024.0 * 1024.0);
            if (mb > 0) {
                pieData.add(new PieChart.Data(
                    c.getCategory() + "\n" + String.format("%.1f MB", mb),
                    mb
                ));
            }
        }

        PieChart chart = new PieChart(pieData);
        chart.setTitle("Distribución por Categoría");
        chart.setLegendSide(Side.BOTTOM);
        chart.setLabelsVisible(true);
        chart.setStartAngle(90);
        chart.setPrefSize(420, 320);
        chart.setMaxSize(Double.MAX_VALUE, Double.MAX_VALUE);

        // Apply colors after layout
        String[] COLORS = {
            "#3B82F6", "#10B981", "#F59E0B", "#EF4444",
            "#8B5CF6", "#EC4899", "#14B8A6", "#F97316"
        };
        chart.getData().forEach(data ->
            data.getNode().setStyle(
                "-fx-pie-color: " + COLORS[pieData.indexOf(data) % COLORS.length] + ";"
            )
        );

        // Tooltip on hover
        chart.getData().forEach(data ->
            Tooltip.install(data.getNode(), new Tooltip(data.getName()))
        );

        chartContainer.getChildren().add(chart);
    }

    private void updateLargestFiles(List<Map<String, Object>> files) {
        largeFilesList.clear();
        for (int i = 0; i < files.size(); i++) {
            Map<String, Object> f = files.get(i);
            String modified = str(f, "modified");
            if (modified.length() > 10) modified = modified.substring(0, 10);
            largeFilesList.add(new LargeFile(
                i + 1,
                str(f, "name"),
                str(f, "path"),
                longVal(f, "size"),
                modified
            ));
        }
    }

    private void loadLargestFiles(String scanId, int limit) {
        apiClient.getLargestFilesAsync(scanId, limit)
            .thenAccept(files -> Platform.runLater(() -> updateLargestFiles(files)))
            .exceptionally(ex -> {
                Platform.runLater(() -> showAlert("Error", "No se pudo cargar archivos grandes: " + ex.getMessage()));
                return null;
            });
    }

    private void updateExtensions(List<Map<String, Object>> exts) {
        extensionsList.clear();
        int shown = Math.min(exts.size(), 15);
        for (int i = 0; i < shown; i++) {
            Map<String, Object> e = exts.get(i);
            extensionsList.add(String.format(
                "%-12s  %d archivos  (%s / %.1f%%)",
                str(e, "extension"),
                intVal(e, "count"),
                FormatUtils.formatFileSize(longVal(e, "total_size")),
                doubleVal(e, "percentage")
            ));
        }
    }

    private void updateAdditionalStats(Map<String, Object> stats) {
        lblOldFilesSize.setText(FormatUtils.formatFileSize(longVal(stats, "old_files_size")));

        int  totalFiles = intVal(stats, "total_files");
        long totalSize  = longVal(stats, "total_size");
        long avgSize    = totalFiles > 0 ? totalSize / totalFiles : 0;
        lblAvgFileSize.setText(FormatUtils.formatFileSize(avgSize));

        lblFilesPerCategory.setText(String.valueOf(categoryList.size()));
    }

    // ── Export ────────────────────────────────────────────────────────────────

    @FXML
    private void exportStats() {
        String scanId = comboScanId.getSelectionModel().getSelectedItem();
        if (scanId == null) { showAlert("Info", "Selecciona un escaneo primero."); return; }

        showProgress(true, "Preparando exportación...");

        CompletableFuture.runAsync(() -> {
            try {
                StringBuilder sb = new StringBuilder();
                sb.append("Smart File Organizer — Estadísticas\n");
                sb.append("Escaneo: ").append(scanId).append("\n\n");
                sb.append("CATEGORÍAS:\n");
                for (CategoryStats c : categoryList) {
                    sb.append(String.format("  %-12s  %d archivos  %s  (%.1f%%)\n",
                        c.getCategory(), c.getFileCount(),
                        FormatUtils.formatFileSize(c.getTotalSize()), c.getPercentage()));
                }
                sb.append("\nARCHIVOS MÁS GRANDES:\n");
                for (LargeFile f : largeFilesList) {
                    sb.append(String.format("  %2d. %-40s  %s\n",
                        f.getRank(), f.getFileName(), f.getFormattedSize()));
                }
                sb.append("\nEXTENSIONES:\n");
                for (String ext : extensionsList) sb.append("  ").append(ext).append("\n");

                // Write to temp file
                java.nio.file.Path out = java.nio.file.Files.createTempFile(
                    "sfo_stats_" + scanId + "_", ".txt");
                java.nio.file.Files.writeString(out, sb.toString());

                Platform.runLater(() -> {
                    showProgress(false, "");
                    showAlert("Exportación completada", "Archivo guardado en:\n" + out.toString());
                });

            } catch (Exception e) {
                Platform.runLater(() -> {
                    showProgress(false, "");
                    showAlert("Error", "Error exportando: " + e.getMessage());
                });
            }
        });
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void showProgress(boolean show, String message) {
        progressSection.setVisible(show);
        progressSection.setManaged(show);
        if (!message.isEmpty()) lblProgress.setText(message);
    }

    private void showAlert(String title, String message) {
        Alert a = new Alert(Alert.AlertType.INFORMATION);
        a.setTitle(title); a.setHeaderText(null); a.setContentText(message);
        a.showAndWait();
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
    private static double doubleVal(Map<String, Object> m, String k) {
        try { return Double.parseDouble(str(m, k)); } catch (Exception e) { return 0.0; }
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
    private static double safeDouble(JsonObject o, String k) {
        return (o.has(k) && !o.get(k).isJsonNull()) ? o.get(k).getAsDouble() : 0.0;
    }
}