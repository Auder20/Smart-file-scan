package com.smartfileorganizer.controllers;

import javafx.fxml.FXML;
import javafx.fxml.Initializable;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;

import java.net.URL;
import java.util.ResourceBundle;

public class MainController implements Initializable {

    @FXML private StackPane contentArea;
    @FXML private Button btnDashboard;
    @FXML private Button btnScanner;
    @FXML private Button btnDuplicates;
    @FXML private Button btnStats;

    private Button activeButton;

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        // Mostrar dashboard al iniciar
        showDashboard();
    }

    @FXML
    public void showDashboard() {
        setActive(btnDashboard);
        contentArea.getChildren().setAll(buildPlaceholder("📊 Dashboard", "Escanea una carpeta para ver estadísticas"));
    }

    @FXML
    public void showScanner() {
        setActive(btnScanner);
        contentArea.getChildren().setAll(buildPlaceholder("🔍 Escanear", "Selecciona una carpeta para analizar"));
    }

    @FXML
    public void showDuplicates() {
        setActive(btnDuplicates);
        contentArea.getChildren().setAll(buildPlaceholder("📁 Duplicados", "Primero realiza un escaneo"));
    }

    @FXML
    public void showStats() {
        setActive(btnStats);
        contentArea.getChildren().setAll(buildPlaceholder("📈 Estadísticas", "Primero realiza un escaneo"));
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