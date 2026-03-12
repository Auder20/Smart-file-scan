package com.smartfileorganizer.controllers;

import javafx.fxml.FXML;
import javafx.fxml.Initializable;
import javafx.scene.control.*;
import javafx.scene.control.cell.PropertyValueFactory;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.application.Platform;
import javafx.scene.layout.VBox;

import java.net.URL;
import java.util.*;
import java.util.concurrent.CompletableFuture;

import com.smartfileorganizer.api.ApiClient;
import com.smartfileorganizer.models.RecentScan;
import com.smartfileorganizer.utils.FormatUtils;

public class DashboardController implements Initializable {

    // ── Header ────────────────────────────────────────────────────────────────
    @FXML private Button btnRefresh;
    @FXML private Button btnNewScan;

    // ── Stats cards ───────────────────────────────────────────────────────────
    @FXML private Label lblBackendStatus;
    @FXML private Label lblTotalScans;
    @FXML private Label lblLastScanTime;
    @FXML private Label lblTotalAnalyzed;

    // ── Recent scans table ────────────────────────────────────────────────────
    @FXML private TableView<RecentScan>          tableRecentScans;
    @FXML private TableColumn<RecentScan, String>  colRecentScanId;
    @FXML private TableColumn<RecentScan, String>  colRecentPath;
    @FXML private TableColumn<RecentScan, String>  colRecentStatus;
    @FXML private TableColumn<RecentScan, Integer> colRecentFiles;
    @FXML private TableColumn<RecentScan, String>  colRecentSize;
    @FXML private TableColumn<RecentScan, String>  colRecentDate;

    // ── Space summary ─────────────────────────────────────────────────────────
    @FXML private Label       lblTotalSpace;
    @FXML private Label       lblDuplicateSpace;
    @FXML private ProgressBar spaceUsageBar;
    @FXML private Label       lblSpaceUsage;

    // ── Quick actions ─────────────────────────────────────────────────────────
    @FXML private Button btnQuickScan;
    @FXML private Button btnFindDuplicates;
    @FXML private Button btnViewStats;
    @FXML private Button btnCleanUp;

    // ── Categories list ───────────────────────────────────────────────────────
    @FXML private VBox           scanChartContainer;
    @FXML private ListView<String> listTopCategories;

    // ── Recommendations ───────────────────────────────────────────────────────
    @FXML private Label lblRecommendation1;
    @FXML private Label lblRecommendation2;
    @FXML private Label lblRecommendation3;

    // ── Progress ──────────────────────────────────────────────────────────────
    @FXML private VBox        progressSection;
    @FXML private ProgressBar progressBar;
    @FXML private Label       lblProgress;

    private ApiClient apiClient;
    private final ObservableList<RecentScan>  recentScansList   = FXCollections.observableArrayList();
    private final ObservableList<String>      topCategoriesList = FXCollections.observableArrayList();

    // Aggregated stats from all completed scans
    private long   totalAnalyzedFiles = 0;
    private long   totalAnalyzedSize  = 0;

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        setupTable();
        listTopCategories.setItems(topCategoriesList);
        checkBackendStatus();
        refreshDashboard();
    }

    // ── Table setup ───────────────────────────────────────────────────────────

    private void setupTable() {
        colRecentScanId.setCellValueFactory(new PropertyValueFactory<>("scanId"));
        colRecentPath.setCellValueFactory(new PropertyValueFactory<>("path"));
        colRecentStatus.setCellValueFactory(new PropertyValueFactory<>("formattedStatus"));
        colRecentFiles.setCellValueFactory(new PropertyValueFactory<>("fileCount"));
        colRecentSize.setCellValueFactory(new PropertyValueFactory<>("formattedSize"));
        colRecentDate.setCellValueFactory(new PropertyValueFactory<>("formattedDate"));
        tableRecentScans.setItems(recentScansList);

        // Row double-click → navigate to scanner
        tableRecentScans.setRowFactory(tv -> {
            TableRow<RecentScan> row = new TableRow<>();
            row.setOnMouseClicked(e -> {
                if (e.getClickCount() == 2 && !row.isEmpty()) {
                    navigateToScanner();
                }
            });
            return row;
        });
    }

    // ── Backend status ────────────────────────────────────────────────────────

    private void checkBackendStatus() {
        ApiClient.isBackendReady().thenAccept(isReady ->
            Platform.runLater(() -> {
                if (isReady) {
                    lblBackendStatus.setText("🟢 Conectado");
                    lblBackendStatus.setStyle("-fx-text-fill: #10B981;");
                } else {
                    lblBackendStatus.setText("🔴 Desconectado");
                    lblBackendStatus.setStyle("-fx-text-fill: #EF4444;");
                }
            })
        );
    }

    // ── Main refresh ─────────────────────────────────────────────────────────

    @FXML
    private void refreshDashboard() {
        showProgress(true, "Actualizando dashboard...");

        apiClient.listAllScansAsync()
            .thenAccept(scans -> Platform.runLater(() -> {
                populateRecentScans(scans);
                updateSystemStats(scans);
                updateSpaceUsage(scans);
                updateTopCategories(scans);
                updateRecommendations(scans);
                showProgress(false, "");
            }))
            .exceptionally(ex -> {
                Platform.runLater(() -> {
                    showProgress(false, "");
                    showAlert("Error", "No se pudo conectar con el backend: " + ex.getMessage());
                });
                return null;
            });
    }

    // ── Data processing ───────────────────────────────────────────────────────

    private void populateRecentScans(List<Map<String, Object>> scans) {
        recentScansList.clear();
        for (Map<String, Object> s : scans) {
            String scanId   = str(s, "scan_id");
            String path     = str(s, "root_path");
            String status   = str(s, "status");
            int    files    = intVal(s, "total_files");
            long   size     = longVal(s, "total_size");
            String date     = str(s, "scanned_at");

            // For in-progress scans, show files_found instead
            if (!"completed".equals(status)) {
                files = intVal(s, "files_found");
                size  = 0;
            }

            recentScansList.add(new RecentScan(
                scanId,
                path.isEmpty() ? "(en progreso)" : path,
                status,
                files,
                size,
                date.isEmpty() ? "—" : date
            ));
        }
    }

    private void updateSystemStats(List<Map<String, Object>> scans) {
        long total    = scans.size();
        long analyzed = scans.stream()
            .filter(s -> "completed".equals(str(s, "status")))
            .mapToLong(s -> intVal(s, "total_files"))
            .sum();

        // Find most recent completed scan
        String lastTime = scans.stream()
            .filter(s -> "completed".equals(str(s, "status")))
            .map(s -> str(s, "scanned_at"))
            .filter(t -> !t.isEmpty())
            .findFirst()
            .map(t -> t.length() >= 16 ? t.substring(0, 16).replace("T", " ") : t)
            .orElse("Nunca");

        totalAnalyzedFiles = analyzed;
        totalAnalyzedSize  = scans.stream()
            .filter(s -> "completed".equals(str(s, "status")))
            .mapToLong(s -> longVal(s, "total_size"))
            .sum();

        lblTotalScans.setText(String.valueOf(total));
        lblLastScanTime.setText(lastTime);
        lblTotalAnalyzed.setText(FormatUtils.formatNumber((int) analyzed));
    }

    private void updateSpaceUsage(List<Map<String, Object>> scans) {
        // Use aggregate totals from all completed scans
        lblTotalSpace.setText(FormatUtils.formatFileSize(totalAnalyzedSize));

        // Duplicate space: we'd need a per-scan duplicates call — show placeholder
        // unless we have a cached value
        lblDuplicateSpace.setText("—");
        spaceUsageBar.setProgress(0);
        lblSpaceUsage.setText("Ejecuta la detección de duplicados para ver espacio recuperable");
    }

    private void updateTopCategories(List<Map<String, Object>> scans) {
        topCategoriesList.clear();
        // Aggregate category data from the most recent completed scan that has stats
        // For the dashboard we show a summary per scan count instead
        Map<String, Integer> statusCount = new LinkedHashMap<>();
        statusCount.put("completed", 0);
        statusCount.put("running",   0);
        statusCount.put("failed",    0);
        statusCount.put("pending",   0);

        for (Map<String, Object> s : scans) {
            String st = str(s, "status");
            statusCount.merge(st, 1, Integer::sum);
        }

        statusCount.forEach((status, count) -> {
            if (count > 0) {
                String icon = switch (status) {
                    case "completed" -> "✅";
                    case "running"   -> "🔄";
                    case "failed"    -> "❌";
                    default          -> "⏳";
                };
                topCategoriesList.add(icon + " " + capitalize(status) + " — " + count + " escaneos");
            }
        });

        if (topCategoriesList.isEmpty()) {
            topCategoriesList.add("📭 No hay escaneos aún");
        }
    }

    private void updateRecommendations(List<Map<String, Object>> scans) {
        long completedCount = scans.stream()
            .filter(s -> "completed".equals(str(s, "status")))
            .count();

        long failedCount = scans.stream()
            .filter(s -> "failed".equals(str(s, "status")))
            .count();

        if (completedCount == 0) {
            lblRecommendation1.setText("🚀 Comienza escaneando una carpeta para obtener análisis.");
            lblRecommendation2.setText("📁 Puedes escanear Documents, Downloads o cualquier carpeta.");
            lblRecommendation3.setText("💡 Usa la pestaña Escanear del menú lateral para empezar.");
        } else {
            lblRecommendation1.setText("💡 Tienes " + completedCount + " escaneo(s) completado(s). Revisa los duplicados para liberar espacio.");
            lblRecommendation2.setText("📈 Ve a Estadísticas para ver la distribución de archivos por categoría.");
            lblRecommendation3.setText(failedCount > 0
                ? "⚠️ " + failedCount + " escaneo(s) fallaron. Verifica los permisos de las carpetas."
                : "✅ Todos los escaneos completaron correctamente.");
        }
    }

    // ── Quick actions ─────────────────────────────────────────────────────────

    @FXML private void startNewScan()    { navigateToScanner();    }
    @FXML private void findDuplicates()  { navigateToDuplicates(); }
    @FXML private void viewStats()       { navigateToStats();      }
    @FXML private void viewAllScans()    { navigateToScanner();    }

    @FXML
    private void quickScan() {
        navigateToScanner();
    }

    @FXML
    private void quickCleanup() {
        Alert confirm = new Alert(Alert.AlertType.CONFIRMATION);
        confirm.setTitle("Limpieza Rápida");
        confirm.setHeaderText("¿Deseas realizar una limpieza rápida?");
        confirm.setContentText("Esto iniciará la detección de duplicados en el último escaneo disponible.");

        if (confirm.showAndWait().orElse(ButtonType.CANCEL) == ButtonType.OK) {
            navigateToDuplicates();
        }
    }

    // ── Navigation (via MainController) ──────────────────────────────────────

    private void navigateToScanner() {
        getMainController().ifPresent(MainController::showScanner);
    }

    private void navigateToDuplicates() {
        getMainController().ifPresent(MainController::showDuplicates);
    }

    private void navigateToStats() {
        getMainController().ifPresent(MainController::showStats);
    }

    private Optional<MainController> getMainController() {
        try {
            javafx.scene.Node node = btnRefresh.getScene().lookup("#contentArea");
            if (node != null) {
                Object ctrl = node.getProperties().get("mainController");
                if (ctrl instanceof MainController mc) return Optional.of(mc);
            }
        } catch (Exception ignored) {}
        return Optional.empty();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void showProgress(boolean show, String message) {
        progressSection.setVisible(show);
        progressSection.setManaged(show);
        if (!message.isEmpty()) lblProgress.setText(message);
    }

    private void showAlert(String title, String message) {
        Alert alert = new Alert(Alert.AlertType.INFORMATION);
        alert.setTitle(title);
        alert.setHeaderText(null);
        alert.setContentText(message);
        alert.showAndWait();
    }

    private static String str(Map<String, Object> m, String k) {
        Object v = m.get(k);
        return v != null ? v.toString() : "";
    }
    private static int intVal(Map<String, Object> m, String k) {
        try { return Integer.parseInt(str(m, k)); } catch (Exception e) { return 0; }
    }
    private static long longVal(Map<String, Object> m, String k) {
        try { return Long.parseLong(str(m, k)); } catch (Exception e) { return 0L; }
    }
    private static String capitalize(String s) {
        return s.isEmpty() ? s : Character.toUpperCase(s.charAt(0)) + s.substring(1);
    }
}