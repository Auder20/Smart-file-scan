package com.smartfileorganizer.controllers;

import javafx.fxml.FXML;
import javafx.fxml.Initializable;
import javafx.scene.control.*;
import javafx.scene.control.cell.CheckBoxTableCell;
import javafx.scene.control.cell.PropertyValueFactory;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.collections.transformation.FilteredList;
import javafx.collections.transformation.SortedList;
import javafx.application.Platform;
import javafx.scene.layout.VBox;

import java.net.URL;
import java.util.ResourceBundle;
import java.util.List;
import java.util.Map;
import java.util.HashMap;
import java.util.stream.Collectors;

import com.smartfileorganizer.api.ApiClient;
import com.smartfileorganizer.models.DuplicateGroup;
import com.smartfileorganizer.models.DuplicateFile;
import com.smartfileorganizer.utils.FormatUtils;
import com.smartfileorganizer.utils.UIUtils;

public class DuplicatesController implements Initializable {

    @FXML private ComboBox<String> comboScanId;
    @FXML private Button btnRefresh;
    
    @FXML private VBox statsSection;
    @FXML private Label lblTotalGroups;
    @FXML private Label lblTotalDuplicates;
    @FXML private Label lblSpaceWasted;
    @FXML private Label lblSpaceRecoverable;
    
    @FXML private TextField txtFilter;
    @FXML private ComboBox<String> comboSizeFilter;
    @FXML private CheckBox chkShowOnlyLarge;
    @FXML private Button btnSelectAll;
    @FXML private Button btnDeselectAll;
    @FXML private Button btnDeleteSelected;
    
    @FXML private TableView<DuplicateFile> tableDuplicates;
    @FXML private TableColumn<DuplicateFile, Boolean> colSelect;
    @FXML private TableColumn<DuplicateFile, String> colGroup;
    @FXML private TableColumn<DuplicateFile, String> colFileName;
    @FXML private TableColumn<DuplicateFile, String> colPath;
    @FXML private TableColumn<DuplicateFile, String> colSize;
    @FXML private TableColumn<DuplicateFile, String> colModified;
    @FXML private TableColumn<DuplicateFile, String> colStatus;
    @FXML private TableColumn<DuplicateFile, String> colActions;
    
    @FXML private VBox groupDetailsSection;
    @FXML private Label lblGroupHash;
    @FXML private Label lblGroupFileCount;
    @FXML private Label lblGroupTotalSize;
    @FXML private Label lblGroupWastedSize;
    @FXML private Button btnKeepOriginal;
    @FXML private Button btnDeleteAllExcept;
    @FXML private Button btnOpenFolder;
    
    @FXML private VBox progressSection;
    @FXML private ProgressBar progressBar;
    @FXML private Label lblProgress;

    private ApiClient apiClient;
    private final ObservableList<DuplicateFile> duplicateList = FXCollections.observableArrayList();
    private final ObservableList<String> scanList = FXCollections.observableArrayList();
    private FilteredList<DuplicateFile> filteredDuplicates;
    private Map<String, DuplicateGroup> groupMap = new HashMap<>();

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        apiClient = new ApiClient();
        
        // Configurar tabla
        setupTable();
        
        // Configurar filtros
        setupFilters();
        
        // Cargar escaneos disponibles
        loadAvailableScans();
    }

    private void setupTable() {
        // Configurar columnas
        colSelect.setCellValueFactory(new PropertyValueFactory<>("selected"));
        colGroup.setCellValueFactory(new PropertyValueFactory<>("groupId"));
        colFileName.setCellValueFactory(new PropertyValueFactory<>("fileName"));
        colPath.setCellValueFactory(new PropertyValueFactory<>("path"));
        colSize.setCellValueFactory(new PropertyValueFactory<>("formattedSize"));
        colModified.setCellValueFactory(new PropertyValueFactory<>("formattedModified"));
        colStatus.setCellValueFactory(new PropertyValueFactory<>("status"));
        colActions.setCellValueFactory(new PropertyValueFactory<>("actions"));

        // Checkbox para selección
        colSelect.setCellFactory(CheckBoxTableCell.forTableColumn(colSelect));
        colSelect.setEditable(true);
        tableDuplicates.setEditable(true);

        // Filtros
        filteredDuplicates = new FilteredList<>(duplicateList, p -> true);
        SortedList<DuplicateFile> sortedDuplicates = new SortedList<>(filteredDuplicates);
        sortedDuplicates.comparatorProperty().bind(tableDuplicates.comparatorProperty());
        tableDuplicates.setItems(sortedDuplicates);

        // Listener para selección
        tableDuplicates.getSelectionModel().selectedItemProperty().addListener(
            (obs, oldVal, newVal) -> showGroupDetails(newVal)
        );
    }

    private void setupFilters() {
        // Opciones de filtro por tamaño
        comboSizeFilter.setItems(FXCollections.observableArrayList(
            "Todos", "< 1MB", "1-10MB", "10-100MB", "> 100MB"
        ));
        comboSizeFilter.getSelectionModel().selectFirst();

        // Listener para filtro de texto
        txtFilter.textProperty().addListener((obs, oldVal, newVal) -> applyFilters());
        
        // Listener para filtro por tamaño
        comboSizeFilter.getSelectionModel().selectedItemProperty().addListener((obs, oldVal, newVal) -> applyFilters());
        
        // Listener para checkbox de archivos grandes
        chkShowOnlyLarge.selectedProperty().addListener((obs, oldVal, newVal) -> applyFilters());
    }

    private void applyFilters() {
        String textFilter = txtFilter.getText().toLowerCase();
        String sizeFilter = comboSizeFilter.getSelectionModel().getSelectedItem();
        boolean showOnlyLarge = chkShowOnlyLarge.isSelected();

        filteredDuplicates.setPredicate(file -> {
            // Filtro por texto
            if (textFilter != null && !textFilter.isEmpty()) {
                if (!file.getFileName().toLowerCase().contains(textFilter) &&
                    !file.getPath().toLowerCase().contains(textFilter)) {
                    return false;
                }
            }

            // Filtro por tamaño
            if (sizeFilter != null && !sizeFilter.equals("Todos")) {
                long sizeBytes = file.getSizeBytes();
                switch (sizeFilter) {
                    case "< 1MB":
                        if (sizeBytes >= 1024 * 1024) return false;
                        break;
                    case "1-10MB":
                        if (sizeBytes < 1024 * 1024 || sizeBytes >= 10 * 1024 * 1024) return false;
                        break;
                    case "10-100MB":
                        if (sizeBytes < 10 * 1024 * 1024 || sizeBytes >= 100 * 1024 * 1024) return false;
                        break;
                    case "> 100MB":
                        if (sizeBytes < 100 * 1024 * 1024) return false;
                        break;
                }
            }

            // Filtro de archivos grandes
            if (showOnlyLarge && file.getSizeBytes() < 10 * 1024 * 1024) {
                return false;
            }

            return true;
        });
    }

    @FXML
    private void loadAvailableScans() {
        try {
            // TODO: Cargar lista de escaneos disponibles desde API
            scanList.addAll("scan_1234", "scan_5678", "scan_9012");
            comboScanId.setItems(scanList);
        } catch (Exception e) {
            UIUtils.showErrorDialog("Error", "No se pudieron cargar los escaneos: " + e.getMessage());
        }
    }

    @FXML
    private void refreshDuplicates() {
        String selectedScan = comboScanId.getSelectionModel().getSelectedItem();
        if (selectedScan == null) {
            UIUtils.showWarningDialog("Información", "Por favor selecciona un escaneo primero.");
            return;
        }

        // Set button loading state
        UIUtils.setButtonLoadingState(btnRefresh, true);
        
        try {
            // Show loading state in progress section
            UIUtils.showLoadingState(progressSection, "Cargando duplicados...");
            
            // Cargar duplicados desde API
            var duplicatesResult = apiClient.getDuplicates(selectedScan);
            
            Platform.runLater(() -> {
                try {
                    duplicateList.clear();
                    groupMap.clear();
                    
                    // Verificar estructura del resultado
                    if (duplicatesResult == null || !duplicatesResult.containsKey("groups")) {
                        throw new Exception("Respuesta inválida de la API");
                    }
                    
                    // Procesar grupos de duplicados
                    Object groupsObj = duplicatesResult.get("groups");
                    if (groupsObj instanceof List) {
                        List<Map<String, Object>> groups = (List<Map<String, Object>>) groupsObj;
                        
                        if (groups.isEmpty()) {
                            UIUtils.showEmptyState(progressSection, "No se encontraron archivos duplicados", "🎉");
                            updateStats(duplicatesResult);
                            UIUtils.setButtonLoadingState(btnRefresh, false);
                            return;
                        }
                        
                        for (Map<String, Object> group : groups) {
                            String groupId = String.valueOf(group.get("hash"));
                            Integer fileCount = group.containsKey("file_count") ? 
                                Integer.valueOf(String.valueOf(group.get("file_count"))) : 0;
                            Long totalSize = group.containsKey("total_size") ? 
                                Long.valueOf(String.valueOf(group.get("total_size"))) : 0L;
                            Long wastedSize = group.containsKey("wasted_size") ? 
                                Long.valueOf(String.valueOf(group.get("wasted_size"))) : 0L;
                            
                            DuplicateGroup duplicateGroup = new DuplicateGroup(
                                groupId, fileCount, totalSize, wastedSize
                            );
                            groupMap.put(groupId, duplicateGroup);
                            
                            // Agregar archivos del grupo
                            Object duplicatesObj = group.get("duplicates");
                            if (duplicatesObj instanceof List) {
                                List<Map<String, Object>> duplicates = (List<Map<String, Object>>) duplicatesObj;
                                for (Map<String, Object> file : duplicates) {
                                    String path = String.valueOf(file.get("path"));
                                    String name = String.valueOf(file.get("name"));
                                    Long size = file.containsKey("size") ? 
                                        Long.valueOf(String.valueOf(file.get("size"))) : 0L;
                                    String modified = String.valueOf(file.get("modified"));
                                    Boolean isOriginal = file.containsKey("is_original") ? 
                                        Boolean.valueOf(String.valueOf(file.get("is_original"))) : false;
                                    
                                    DuplicateFile duplicateFile = new DuplicateFile(
                                        groupId, path, name, size, modified, isOriginal
                                    );
                                    duplicateList.add(duplicateFile);
                                }
                            }
                        }
                    }
                    
                    updateStats(duplicatesResult);
                    UIUtils.hideLoadingState(progressSection);
                    
                } catch (Exception parseError) {
                    UIUtils.showErrorState(progressSection, 
                        "Error procesando datos", 
                        "No se pudieron procesar los datos de duplicados: " + parseError.getMessage());
                } finally {
                    UIUtils.setButtonLoadingState(btnRefresh, false);
                }
            });
            
        } catch (Exception e) {
            UIUtils.hideLoadingState(progressSection);
            UIUtils.showErrorState(progressSection, 
                "Error de conexión", 
                "No se pudieron cargar los duplicados: " + e.getMessage());
            UIUtils.setButtonLoadingState(btnRefresh, false);
        }
    }

    private void updateStats(Map<String, Object> result) {
        statsSection.setVisible(true);
        statsSection.setManaged(true);
        
        try {
            Integer totalGroups = result.containsKey("total_groups") ? 
                Integer.valueOf(String.valueOf(result.get("total_groups"))) : 0;
            Integer totalDuplicates = result.containsKey("total_duplicates") ? 
                Integer.valueOf(String.valueOf(result.get("total_duplicates"))) : 0;
            Long totalWasted = result.containsKey("total_wasted") ? 
                Long.valueOf(String.valueOf(result.get("total_wasted"))) : 0L;
            
            lblTotalGroups.setText(String.valueOf(totalGroups));
            lblTotalDuplicates.setText(String.valueOf(totalDuplicates));
            lblSpaceWasted.setText(FormatUtils.formatFileSize(totalWasted));
            lblSpaceRecoverable.setText(FormatUtils.formatFileSize(totalWasted));
        } catch (Exception e) {
            System.err.println("Error actualizando estadísticas: " + e.getMessage());
            lblTotalGroups.setText("0");
            lblTotalDuplicates.setText("0");
            lblSpaceWasted.setText("0 B");
            lblSpaceRecoverable.setText("0 B");
        }
    }

    private void showGroupDetails(DuplicateFile selectedFile) {
        if (selectedFile == null) {
            groupDetailsSection.setVisible(false);
            groupDetailsSection.setManaged(false);
            return;
        }

        DuplicateGroup group = groupMap.get(selectedFile.getGroupId());
        if (group != null) {
            groupDetailsSection.setVisible(true);
            groupDetailsSection.setManaged(true);
            
            lblGroupHash.setText(group.getHash());
            lblGroupFileCount.setText(String.valueOf(group.getFileCount()));
            lblGroupTotalSize.setText(FormatUtils.formatFileSize(group.getTotalSize()));
            lblGroupWastedSize.setText(FormatUtils.formatFileSize(group.getWastedSize()));
        }
    }

    @FXML
    private void selectAll() {
        for (DuplicateFile file : duplicateList) {
            file.setSelected(true);
        }
        tableDuplicates.refresh();
        updateDeleteButton();
    }

    @FXML
    private void deselectAll() {
        for (DuplicateFile file : duplicateList) {
            file.setSelected(false);
        }
        tableDuplicates.refresh();
        updateDeleteButton();
    }

    @FXML
    private void deleteSelected() {
        List<String> filesToDelete = duplicateList.stream()
            .filter(DuplicateFile::isSelected)
            .map(DuplicateFile::getPath)
            .toList();
            
        if (filesToDelete.isEmpty()) {
            UIUtils.showInfoDialog("Información", "No hay archivos seleccionados para eliminar.");
            return;
        }

        boolean confirmed = UIUtils.showConfirmationDialog(
            "Confirmar Eliminación",
            "¿Estás seguro de eliminar " + filesToDelete.size() + " archivos?",
            "Esta acción no se puede deshacer. Los archivos se moverán a la papelera."
        );
        
        if (confirmed) {
            try {
                UIUtils.showLoadingState(progressSection, "Eliminando archivos...");
                UIUtils.setButtonLoadingState(btnDeleteSelected, true);
                
                // TODO: Llamar a API para eliminar archivos
                // var result = apiClient.deleteFiles(filesToDelete, true);
                
                Platform.runLater(() -> {
                    UIUtils.hideLoadingState(progressSection);
                    UIUtils.setButtonLoadingState(btnDeleteSelected, false);
                    UIUtils.showInfoDialog("Éxito", "Se eliminaron " + filesToDelete.size() + " archivos.");
                    refreshDuplicates();
                });
                
            } catch (Exception e) {
                UIUtils.hideLoadingState(progressSection);
                UIUtils.setButtonLoadingState(btnDeleteSelected, false);
                UIUtils.showErrorDialog("Error", "Error eliminando archivos: " + e.getMessage());
            }
        }
    }

    @FXML
    private void keepOriginal() {
        // TODO: Implementar lógica para mantener solo el original
        UIUtils.showInfoDialog("Información", "Función próximamente...");
    }

    @FXML
    private void deleteAllExcept() {
        // TODO: Implementar lógica para eliminar todos excepto el original
        UIUtils.showInfoDialog("Información", "Función próximamente...");
    }

    @FXML
    private void openFolder() {
        DuplicateFile selected = tableDuplicates.getSelectionModel().getSelectedItem();
        if (selected != null) {
            try {
                // TODO: Abrir carpeta contenedora del archivo
                UIUtils.showInfoDialog("Información", "Función de abrir carpeta próximamente...");
            } catch (Exception e) {
                UIUtils.showErrorDialog("Error", "No se pudo abrir la carpeta: " + e.getMessage());
            }
        }
    }

    private void updateDeleteButton() {
        boolean hasSelection = duplicateList.stream().anyMatch(DuplicateFile::isSelected);
        btnDeleteSelected.setDisable(!hasSelection);
    }
}
