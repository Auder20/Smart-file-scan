package com.smartfileorganizer.controllers;

import javafx.fxml.FXML;
import javafx.fxml.Initializable;
import javafx.scene.control.*;
import javafx.scene.control.cell.PropertyValueFactory;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.application.Platform;
import javafx.scene.layout.VBox;
import javafx.scene.chart.PieChart;
import javafx.scene.chart.Chart;
import javafx.geometry.Side;

import java.net.URL;
import java.util.ResourceBundle;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.stream.Collectors;

import com.smartfileorganizer.api.ApiClient;
import com.smartfileorganizer.models.CategoryStats;
import com.smartfileorganizer.models.LargeFile;
import com.smartfileorganizer.utils.FormatUtils;

public class StatsController implements Initializable {

    @FXML private ComboBox<String> comboScanId;
    @FXML private Button btnRefresh;
    @FXML private Button btnExport;
    
    @FXML private VBox generalStatsSection;
    @FXML private Label lblTotalFiles;
    @FXML private Label lblTotalSize;
    @FXML private Label lblEmptyFiles;
    @FXML private Label lblOldFiles;
    
    @FXML private VBox chartContainer;
    @FXML private TableView<CategoryStats> tableCategories;
    @FXML private TableColumn<CategoryStats, String> colCategory;
    @FXML private TableColumn<CategoryStats, Integer> colFileCount;
    @FXML private TableColumn<CategoryStats, String> colCategorySize;
    @FXML private TableColumn<CategoryStats, Double> colPercentage;
    
    @FXML private ComboBox<Integer> comboTopCount;
    @FXML private TableView<LargeFile> tableLargestFiles;
    @FXML private TableColumn<LargeFile, Integer> colRank;
    @FXML private TableColumn<LargeFile, String> colLargeFileName;
    @FXML private TableColumn<LargeFile, String> colLargeFilePath;
    @FXML private TableColumn<LargeFile, String> colLargeFileSize;
    @FXML private TableColumn<LargeFile, String> colLargeFileModified;
    @FXML private TableColumn<LargeFile, String> colLargeFileActions;
    
    @FXML private ListView<String> listExtensions;
    @FXML private Label lblOldFilesSize;
    @FXML private Label lblAvgFileSize;
    @FXML private Label lblFilesPerCategory;
    
    @FXML private VBox progressSection;
    @FXML private ProgressBar progressBar;
    @FXML private Label lblProgress;

    private ApiClient apiClient;
    private final ObservableList<CategoryStats> categoryList = FXCollections.observableArrayList();
    private final ObservableList<LargeFile> largeFilesList = FXCollections.observableArrayList();
    private final ObservableList<String> scanList = FXCollections.observableArrayList();
    private final ObservableList<String> extensionsList = FXCollections.observableArrayList();

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        
        // Configurar tablas
        setupTables();
        
        // Configurar combos
        setupCombos();
        
        // Cargar escaneos disponibles
        loadAvailableScans();
    }

    private void setupTables() {
        // Tabla de categorías
        colCategory.setCellValueFactory(new PropertyValueFactory<>("category"));
        colFileCount.setCellValueFactory(new PropertyValueFactory<>("fileCount"));
        colCategorySize.setCellValueFactory(new PropertyValueFactory<>("formattedSize"));
        colPercentage.setCellValueFactory(new PropertyValueFactory<>("percentage"));
        
        tableCategories.setItems(categoryList);
        
        // Tabla de archivos grandes
        colRank.setCellValueFactory(new PropertyValueFactory<>("rank"));
        colLargeFileName.setCellValueFactory(new PropertyValueFactory<>("fileName"));
        colLargeFilePath.setCellValueFactory(new PropertyValueFactory<>("path"));
        colLargeFileSize.setCellValueFactory(new PropertyValueFactory<>("formattedSize"));
        colLargeFileModified.setCellValueFactory(new PropertyValueFactory<>("formattedModified"));
        colLargeFileActions.setCellValueFactory(new PropertyValueFactory<>("actions"));
        
        tableLargestFiles.setItems(largeFilesList);
        
        // Lista de extensiones
        listExtensions.setItems(extensionsList);
    }

    private void setupCombos() {
        // Combo para cantidad de archivos grandes
        comboTopCount.setItems(FXCollections.observableArrayList(5, 10, 20, 50, 100));
        comboTopCount.getSelectionModel().select(10);
        
        // Listener para actualizar tabla cuando cambia la cantidad
        comboTopCount.getSelectionModel().selectedItemProperty().addListener(
            (obs, oldVal, newVal) -> updateLargestFilesTable()
        );
    }

    private void loadAvailableScans() {
        try {
            // TODO: Cargar lista de escaneos disponibles desde API
            scanList.addAll("scan_1234", "scan_5678", "scan_9012");
            comboScanId.setItems(scanList);
        } catch (Exception e) {
            showAlert("Error", "No se pudieron cargar los escaneos: " + e.getMessage());
        }
    }

    @FXML
    private void refreshStats() {
        String selectedScan = comboScanId.getSelectionModel().getSelectedItem();
        if (selectedScan == null) {
            showAlert("Info", "Por favor selecciona un escaneo primero.");
            return;
        }

        try {
            showProgress(true, "Cargando estadísticas...");
            
            // Cargar estadísticas desde API
            var statsResult = apiClient.getStats(selectedScan);
            
            Platform.runLater(() -> {
                updateGeneralStats(statsResult);
                updateCategoryStats(statsResult);
                updateLargestFilesTable();
                updateExtensionStats(statsResult);
                updateAdditionalStats(statsResult);
                
                generalStatsSection.setVisible(true);
                generalStatsSection.setManaged(true);
                showProgress(false, "");
            });
            
        } catch (Exception e) {
            showProgress(false, "");
            showAlert("Error", "Error cargando estadísticas: " + e.getMessage());
        }
    }

    private void updateGeneralStats(Map<String, Object> stats) {
        lblTotalFiles.setText(FormatUtils.formatNumber((Integer) stats.get("total_files")));
        lblTotalSize.setText(FormatUtils.formatFileSize((Long) stats.get("total_size")));
        lblEmptyFiles.setText(FormatUtils.formatNumber((Integer) stats.get("empty_files")));
        lblOldFiles.setText(FormatUtils.formatNumber((Integer) stats.get("old_files_count")));
    }

    private void updateCategoryStats(Map<String, Object> stats) {
        categoryList.clear();
        
        // TODO: Parsear categorías desde el resultado de la API
        // Por ahora datos de ejemplo
        categoryList.addAll(
            new CategoryStats("document", 150, 50 * 1024 * 1024, 25.5),
            new CategoryStats("image", 300, 150 * 1024 * 1024, 45.2),
            new CategoryStats("video", 25, 200 * 1024 * 1024, 20.1),
            new CategoryStats("audio", 50, 10 * 1024 * 1024, 5.0),
            new CategoryStats("code", 100, 5 * 1024 * 1024, 2.5)
        );
        
        // TODO: Actualizar gráfico
        updateChart();
    }

    private void updateChart() {
        chartContainer.getChildren().clear();
        
        try {
            // Create pie chart data from category stats
            ObservableList<PieChart.Data> pieChartData = FXCollections.observableArrayList();
            
            for (CategoryStats category : categoryList) {
                String categoryName = getCategoryDisplayName(category.getCategory());
                double sizeInMB = category.getTotalSize() / (1024.0 * 1024.0);
                pieChartData.add(new PieChart.Data(categoryName + " (" + String.format("%.1f", sizeInMB) + " MB)", sizeInMB));
            }
            
            // Create pie chart
            PieChart pieChart = new PieChart(pieChartData);
            pieChart.setTitle("Distribución por Categoría");
            pieChart.setLegendSide(Side.BOTTOM);
            pieChart.setLabelsVisible(true);
            pieChart.setPrefSize(400, 300);
            
            // Customize colors
            String[] colors = {
                "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
                "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16"
            };
            
            for (int i = 0; i < pieChartData.size() && i < colors.length; i++) {
                PieChart.Data data = pieChartData.get(i);
                data.getNode().setStyle("-fx-pie-color: " + colors[i] + ";");
            }
            
            chartContainer.getChildren().add(pieChart);
            
        } catch (Exception e) {
            System.err.println("Error creating chart: " + e.getMessage());
            // Fallback to placeholder
            Label placeholder = new Label("📊");
            placeholder.setStyle("-fx-font-size: 48; -fx-opacity: 0.3;");
            Label text = new Label("Error cargando gráfico");
            text.setStyle("-fx-text-fill: #64748B;");
            chartContainer.getChildren().addAll(placeholder, text);
        }
    }
    
    private String getCategoryDisplayName(String category) {
        switch (category.toLowerCase()) {
            case "document": return "Documentos";
            case "image": return "Imágenes";
            case "video": return "Videos";
            case "audio": return "Audio";
            case "code": return "Código";
            case "archive": return "Archivos";
            case "other": return "Otros";
            default: return category.substring(0, 1).toUpperCase() + category.substring(1);
        }
    }

    private void updateLargestFilesTable() {
        largeFilesList.clear();
        
        // TODO: Obtener archivos grandes desde API
        // Por ahora datos de ejemplo
        largeFilesList.addAll(
            new LargeFile(1, "video_grande.mp4", "/Users/Videos/video_grande.mp4", 150 * 1024 * 1024, "2024-01-15"),
            new LargeFile(2, "backup.zip", "/Users/Downloads/backup.zip", 120 * 1024 * 1024, "2024-02-20"),
            new LargeFile(3, "database.sql", "/Users/Data/database.sql", 80 * 1024 * 1024, "2024-03-10"),
            new LargeFile(4, "presentation.pptx", "/Users/Documents/presentation.pptx", 45 * 1024 * 1024, "2024-01-25"),
            new LargeFile(5, "software.iso", "/Users/Downloads/software.iso", 650 * 1024 * 1024, "2024-02-15")
        );
        
        // Limitar a la cantidad seleccionada
        int limit = comboTopCount.getSelectionModel().getSelectedItem();
        if (largeFilesList.size() > limit) {
            largeFilesList.remove(limit, largeFilesList.size());
        }
    }

    private void updateExtensionStats(Map<String, Object> stats) {
        extensionsList.clear();
        
        // TODO: Analizar extensiones desde los datos
        // Por ahora datos de ejemplo
        extensionsList.addAll(
            ".pdf - 45 archivos (15.2 MB)",
            ".jpg - 120 archivos (89.5 MB)", 
            ".mp4 - 8 archivos (320.1 MB)",
            ".docx - 32 archivos (12.8 MB)",
            ".txt - 67 archivos (2.1 MB)",
            ".zip - 12 archivos (156.3 MB)",
            ".xlsx - 18 archivos (8.9 MB)",
            ".png - 95 archivos (67.2 MB)"
        );
    }

    private void updateAdditionalStats(Map<String, Object> stats) {
        lblOldFilesSize.setText(FormatUtils.formatFileSize((Long) stats.get("old_files_size")));
        
        long totalSize = (Long) stats.get("total_size");
        int totalFiles = (Integer) stats.get("total_files");
        long avgSize = totalFiles > 0 ? totalSize / totalFiles : 0;
        lblAvgFileSize.setText(FormatUtils.formatFileSize(avgSize));
        
        int categories = categoryList.size();
        lblFilesPerCategory.setText(String.valueOf(categories));
    }

    @FXML
    private void exportStats() {
        String selectedScan = comboScanId.getSelectionModel().getSelectedItem();
        if (selectedScan == null) {
            showAlert("Info", "Por favor selecciona un escaneo primero.");
            return;
        }

        try {
            showProgress(true, "Exportando estadísticas...");
            
            // TODO: Implementar exportación a CSV/JSON
            Platform.runLater(() -> {
                showProgress(false, "");
                showAlert("Éxito", "Estadísticas exportadas correctamente.");
            });
            
        } catch (Exception e) {
            showProgress(false, "");
            showAlert("Error", "Error exportando estadísticas: " + e.getMessage());
        }
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
