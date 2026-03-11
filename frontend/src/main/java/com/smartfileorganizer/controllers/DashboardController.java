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
import java.util.ResourceBundle;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.CompletableFuture;

import com.smartfileorganizer.api.ApiClient;
import com.smartfileorganizer.models.RecentScan;
import com.smartfileorganizer.utils.FormatUtils;

public class DashboardController implements Initializable {

    @FXML private Button btnRefresh;
    @FXML private Button btnNewScan;
    
    @FXML private Label lblBackendStatus;
    @FXML private Label lblTotalScans;
    @FXML private Label lblLastScanTime;
    @FXML private Label lblTotalAnalyzed;
    
    @FXML private TableView<RecentScan> tableRecentScans;
    @FXML private TableColumn<RecentScan, String> colRecentScanId;
    @FXML private TableColumn<RecentScan, String> colRecentPath;
    @FXML private TableColumn<RecentScan, String> colRecentStatus;
    @FXML private TableColumn<RecentScan, Integer> colRecentFiles;
    @FXML private TableColumn<RecentScan, String> colRecentSize;
    @FXML private TableColumn<RecentScan, String> colRecentDate;
    @FXML private TableColumn<RecentScan, String> colRecentActions;
    
    @FXML private Label lblTotalSpace;
    @FXML private Label lblDuplicateSpace;
    @FXML private ProgressBar spaceUsageBar;
    @FXML private Label lblSpaceUsage;
    
    @FXML private Button btnQuickScan;
    @FXML private Button btnFindDuplicates;
    @FXML private Button btnViewStats;
    @FXML private Button btnCleanUp;
    
    @FXML private VBox scanChartContainer;
    @FXML private ListView<String> listTopCategories;
    
    @FXML private Label lblRecommendation1;
    @FXML private Label lblRecommendation2;
    @FXML private Label lblRecommendation3;
    
    @FXML private VBox progressSection;
    @FXML private ProgressBar progressBar;
    @FXML private Label lblProgress;

    private ApiClient apiClient;
    private final ObservableList<RecentScan> recentScansList = FXCollections.observableArrayList();
    private final ObservableList<String> topCategoriesList = FXCollections.observableArrayList();

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        
        // Configurar tabla
        setupTable();
        
        // Configurar lista de categorías
        listTopCategories.setItems(topCategoriesList);
        
        // Cargar datos iniciales
        refreshDashboard();
        
        // Verificar estado del backend periódicamente
        checkBackendStatus();
    }

    private void setupTable() {
        colRecentScanId.setCellValueFactory(new PropertyValueFactory<>("scanId"));
        colRecentPath.setCellValueFactory(new PropertyValueFactory<>("path"));
        colRecentStatus.setCellValueFactory(new PropertyValueFactory<>("status"));
        colRecentFiles.setCellValueFactory(new PropertyValueFactory<>("fileCount"));
        colRecentSize.setCellValueFactory(new PropertyValueFactory<>("formattedSize"));
        colRecentDate.setCellValueFactory(new PropertyValueFactory<>("formattedDate"));
        colRecentActions.setCellValueFactory(new PropertyValueFactory<>("actions"));
        
        tableRecentScans.setItems(recentScansList);
    }

    private void checkBackendStatus() {
        CompletableFuture<Boolean> statusCheck = ApiClient.isBackendReady();
        statusCheck.thenAccept(isReady -> {
            Platform.runLater(() -> {
                if (isReady) {
                    lblBackendStatus.setText("🟢 Conectado");
                    lblBackendStatus.setStyle("-fx-text-fill: #10B981;");
                } else {
                    lblBackendStatus.setText("🔴 Desconectado");
                    lblBackendStatus.setStyle("-fx-text-fill: #EF4444;");
                }
            });
        });
    }

    @FXML
    private void refreshDashboard() {
        showProgress(true, "Actualizando dashboard...");
        
        // Simular carga de datos
        CompletableFuture.runAsync(() -> {
            try {
                // Simular delay
                Thread.sleep(1000);
                
                Platform.runLater(() -> {
                    updateSystemStats();
                    updateRecentScans();
                    updateSpaceUsage();
                    updateTopCategories();
                    updateRecommendations();
                    updateCharts();
                    
                    showProgress(false, "");
                });
                
            } catch (InterruptedException e) {
                Platform.runLater(() -> {
                    showProgress(false, "");
                    showAlert("Error", "Error actualizando dashboard: " + e.getMessage());
                });
            }
        });
    }

    private void updateSystemStats() {
        // TODO: Obtener datos reales desde API
        lblTotalScans.setText("12");
        lblLastScanTime.setText("Hace 2 horas");
        lblTotalAnalyzed.setText("45,892");
    }

    private void updateRecentScans() {
        recentScansList.clear();
        
        // TODO: Obtener escaneos reales desde API
        recentScansList.addAll(
            new RecentScan("scan_1234", "C:/Users/Documents", "completed", 1250, 50 * 1024 * 1024, "2024-03-11 14:30"),
            new RecentScan("scan_5678", "C:/Users/Downloads", "completed", 3420, 150 * 1024 * 1024, "2024-03-11 12:15"),
            new RecentScan("scan_9012", "D:/Projects", "running", 890, 25 * 1024 * 1024, "2024-03-11 10:45"),
            new RecentScan("scan_3456", "C:/Users/Pictures", "failed", 0, 0, "2024-03-10 18:20"),
            new RecentScan("scan_7890", "C:/Users/Videos", "completed", 156, 200 * 1024 * 1024, "2024-03-10 16:30")
        );
    }

    private void updateSpaceUsage() {
        // TODO: Obtener datos reales desde API
        long totalSpace = 425 * 1024 * 1024 * 1024L; // 425 GB
        long duplicateSpace = 15 * 1024 * 1024 * 1024L; // 15 GB
        
        lblTotalSpace.setText(FormatUtils.formatFileSize(totalSpace));
        lblDuplicateSpace.setText(FormatUtils.formatFileSize(duplicateSpace));
        
        double percentage = (double) duplicateSpace / totalSpace;
        spaceUsageBar.setProgress(percentage);
        lblSpaceUsage.setText(String.format("%.1f%% del espacio es duplicado", percentage * 100));
    }

    private void updateTopCategories() {
        topCategoriesList.clear();
        
        // TODO: Obtener categorías reales desde API
        topCategoriesList.addAll(
            "📄 Documents - 15.2 GB (28%)",
            "🖼️ Images - 12.8 GB (24%)", 
            "🎥 Videos - 8.5 GB (16%)",
            "💿 Archives - 6.3 GB (12%)",
            "🎵 Audio - 4.1 GB (8%)",
            "💻 Code - 2.7 GB (5%)",
            "📁 Other - 4.4 GB (7%)"
        );
    }

    private void updateRecommendations() {
        // TODO: Generar recomendaciones basadas en datos reales
        lblRecommendation1.setText("💡 Tienes 15 GB en archivos duplicados. Considera limpiarlos para liberar espacio.");
        lblRecommendation2.setText("📁 Tu carpeta Downloads ha crecido 25% esta semana. Revisa archivos innecesarios.");
        lblRecommendation3.setText("🔍 No has escaneado tu carpeta Pictures. Podrías tener duplicados de fotos.");
    }

    private void updateCharts() {
        // TODO: Implementar gráficos reales
        scanChartContainer.getChildren().clear();
        Label placeholder = new Label("📈");
        placeholder.setStyle("-fx-font-size: 32; -fx-opacity: 0.3;");
        Label text = new Label("Gráfico de actividad próximamente...");
        text.setStyle("-fx-text-fill: #64748B;");
        scanChartContainer.getChildren().addAll(placeholder, text);
    }

    @FXML
    private void startNewScan() {
        // Navegar a vista de scanner
        navigateToScanner();
    }

    @FXML
    private void quickScan() {
        // Escanear carpeta común (Documents)
        String commonPath = System.getProperty("user.home") + "/Documents";
        // TODO: Iniciar escaneo rápido
        showAlert("Info", "Iniciando escaneo rápido de: " + commonPath);
    }

    @FXML
    private void findDuplicates() {
        // Navegar a vista de duplicados
        navigateToDuplicates();
    }

    @FXML
    private void viewStats() {
        // Navegar a vista de estadísticas
        navigateToStats();
    }

    @FXML
    private void quickCleanup() {
        Alert confirm = new Alert(Alert.AlertType.CONFIRMATION);
        confirm.setTitle("Limpieza Rápida");
        confirm.setHeaderText("¿Deseas realizar una limpieza rápida?");
        confirm.setContentText("Esto eliminará archivos temporales y duplicados obvios.");
        
        if (confirm.showAndWait().get() == ButtonType.OK) {
            showProgress(true, "Realizando limpieza rápida...");
            
            CompletableFuture.runAsync(() -> {
                try {
                    // Simular proceso de limpieza
                    Thread.sleep(2000);
                    
                    Platform.runLater(() -> {
                        showProgress(false, "");
                        showAlert("Éxito", "Limpieza completada. Se liberaron 2.3 GB de espacio.");
                        refreshDashboard();
                    });
                    
                } catch (InterruptedException e) {
                    Platform.runLater(() -> {
                        showProgress(false, "");
                        showAlert("Error", "Error durante la limpieza: " + e.getMessage());
                    });
                }
            });
        }
    }

    @FXML
    private void viewAllScans() {
        navigateToScanner();
    }

    private void navigateToScanner() {
        // TODO: Navegar a vista de scanner
        showAlert("Info", "Navegando a Scanner...");
    }

    private void navigateToDuplicates() {
        // TODO: Navegar a vista de duplicados
        showAlert("Info", "Navegando a Duplicados...");
    }

    private void navigateToStats() {
        // TODO: Navegar a vista de estadísticas
        showAlert("Info", "Navegando a Estadísticas...");
    }

    private void showProgress(boolean show, String message) {
        progressSection.setVisible(show);
        progressSection.setManaged(show);
        if (!message.isEmpty()) {
            lblProgress.setText(message);
        }
    }

    private void showAlert(String title, String message) {
        Alert alert = new Alert(Alert.AlertType.INFORMATION);
        alert.setTitle(title);
        alert.setHeaderText(null);
        alert.setContentText(message);
        alert.showAndWait();
    }
}
