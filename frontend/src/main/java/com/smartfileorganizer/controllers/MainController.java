package com.smartfileorganizer.controllers;

import javafx.fxml.FXML;
import javafx.fxml.FXMLLoader;
import javafx.fxml.Initializable;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;
import javafx.scene.layout.AnchorPane;
import javafx.stage.Stage;
import javafx.scene.Scene;

import java.net.URL;
import java.util.ResourceBundle;

public class MainController implements Initializable {

    @FXML private AnchorPane root;
    @FXML private StackPane contentArea;
    @FXML private Button btnDashboard;
    @FXML private Button btnScanner;
    @FXML private Button btnDuplicates;
    @FXML private Button btnStats;
    @FXML private VBox sidebar;

    private Button activeButton;

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        // Mostrar dashboard al iniciar
        showDashboard();
        
        // Setup responsive behavior after scene is ready
        setupResponsiveLayout();
    }
    
    private void setupResponsiveLayout() {
        // Listen for window size changes
        contentArea.sceneProperty().addListener((obs, oldScene, newScene) -> {
            if (newScene != null) {
                newScene.widthProperty().addListener((widthObs, oldWidth, newWidth) -> {
                    adjustLayoutForWidth(newWidth.doubleValue());
                });
                
                // Initial adjustment
                adjustLayoutForWidth(newScene.getWidth());
            }
        });
    }
    
    private void adjustLayoutForWidth(double width) {
        if (sidebar == null) return;
        
        // Adjust sidebar width based on total window width
        if (width < 900) {
            // Compact mode for smaller screens
            sidebar.setPrefWidth(180);
            sidebar.setMaxWidth(200);
            updateContentAreaAnchor(180);
        } else if (width < 1200) {
            // Normal mode
            sidebar.setPrefWidth(220);
            sidebar.setMaxWidth(250);
            updateContentAreaAnchor(220);
        } else {
            // Wide mode
            sidebar.setPrefWidth(250);
            sidebar.setMaxWidth(300);
            updateContentAreaAnchor(250);
        }
    }
    
    private void updateContentAreaAnchor(double sidebarWidth) {
        AnchorPane.setLeftAnchor(contentArea, sidebarWidth);
    }

    @FXML
    public void showDashboard() {
        setActive(btnDashboard);
        try {
            FXMLLoader loader = new FXMLLoader(
                getClass().getResource("/fxml/DashboardView.fxml")
            );
            contentArea.getChildren().setAll((javafx.scene.Node)loader.load());
        } catch (Exception e) {
            contentArea.getChildren().setAll(buildPlaceholder("📊 Dashboard", "Error cargando vista: " + e.getMessage()));
        }
    }

    @FXML
    public void showScanner() {
        setActive(btnScanner);
        try {
            FXMLLoader loader = new FXMLLoader(
                getClass().getResource("/fxml/ScannerView.fxml")
            );
            contentArea.getChildren().setAll((javafx.scene.Node)loader.load());
        } catch (Exception e) {
            contentArea.getChildren().setAll(buildPlaceholder("🔍 Escanear", "Error cargando vista: " + e.getMessage()));
        }
    }

    @FXML
    public void showDuplicates() {
        setActive(btnDuplicates);
        try {
            FXMLLoader loader = new FXMLLoader(
                getClass().getResource("/fxml/DuplicatesView.fxml")
            );
            contentArea.getChildren().setAll((javafx.scene.Node)loader.load());
        } catch (Exception e) {
            contentArea.getChildren().setAll(buildPlaceholder("📁 Duplicados", "Error cargando vista: " + e.getMessage()));
        }
    }

    @FXML
    public void showStats() {
        setActive(btnStats);
        try {
            FXMLLoader loader = new FXMLLoader(
                getClass().getResource("/fxml/StatsView.fxml")
            );
            contentArea.getChildren().setAll((javafx.scene.Node)loader.load());
        } catch (Exception e) {
            contentArea.getChildren().setAll(buildPlaceholder("📈 Estadísticas", "Error cargando vista: " + e.getMessage()));
        }
    }

    private void setActive(Button button) {
        if (activeButton != null) {
            activeButton.getStyleClass().remove("nav-btn-active");
        }
        button.getStyleClass().add("nav-btn-active");
        activeButton = button;
    }

    private VBox buildPlaceholder(String title, String subtitle) {
        Label titleLabel = new Label(title);
        titleLabel.setStyle("-fx-font-size: 24; -fx-font-weight: bold; -fx-text-fill: #1E293B;");

        Label subtitleLabel = new Label(subtitle);
        subtitleLabel.setStyle("-fx-font-size: 14; -fx-text-fill: #64748B;");

        VBox box = new VBox(10, titleLabel, subtitleLabel);
        box.setStyle("-fx-alignment: CENTER;");
        return box;
    }
}