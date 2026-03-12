package com.smartfileorganizer.controllers;

import javafx.fxml.FXML;
import javafx.fxml.FXMLLoader;
import javafx.fxml.Initializable;
import javafx.scene.Node;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.layout.AnchorPane;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;

import java.net.URL;
import java.util.ResourceBundle;

public class MainController implements Initializable {

    @FXML private AnchorPane root;
    @FXML private StackPane  contentArea;
    @FXML private Button     btnDashboard;
    @FXML private Button     btnScanner;
    @FXML private Button     btnDuplicates;
    @FXML private Button     btnStats;
    @FXML private VBox       sidebar;

    private Button activeButton;

    @Override
    public void initialize(URL url, ResourceBundle rb) {
        // Store reference to self in contentArea so child controllers can navigate
        contentArea.getProperties().put("mainController", this);

        // Responsive sidebar on resize
        contentArea.sceneProperty().addListener((obs, oldScene, newScene) -> {
            if (newScene != null) {
                newScene.widthProperty().addListener((w, o, n) -> adjustLayout(n.doubleValue()));
                adjustLayout(newScene.getWidth());
            }
        });

        showDashboard();
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    @FXML
    public void showDashboard() {
        setActive(btnDashboard);
        loadView("/fxml/DashboardView.fxml", "📊 Dashboard");
    }

    @FXML
    public void showScanner() {
        setActive(btnScanner);
        loadView("/fxml/ScannerView.fxml", "🔍 Escanear");
    }

    @FXML
    public void showDuplicates() {
        setActive(btnDuplicates);
        loadView("/fxml/DuplicatesView.fxml", "📁 Duplicados");
    }

    @FXML
    public void showStats() {
        setActive(btnStats);
        loadView("/fxml/StatsView.fxml", "📈 Estadísticas");
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void loadView(String fxmlPath, String fallbackTitle) {
        try {
            FXMLLoader loader = new FXMLLoader(getClass().getResource(fxmlPath));
            Node view = loader.load();
            view.getProperties().put("mainController", this);
            contentArea.getChildren().setAll(view);
        } catch (Exception e) {
            // Imprime el error completo en consola
            e.printStackTrace();
            contentArea.getChildren().setAll(buildErrorPlaceholder(fallbackTitle, e.getMessage()));
        }
    }

    private void setActive(Button button) {
        if (activeButton != null) activeButton.getStyleClass().remove("nav-btn-active");
        button.getStyleClass().add("nav-btn-active");
        activeButton = button;
    }

    private void adjustLayout(double width) {
        if (sidebar == null) return;
        double sidebarWidth;
        if (width < 900) {
            sidebarWidth = 180;
        } else if (width < 1200) {
            sidebarWidth = 220;
        } else {
            sidebarWidth = 250;
        }
        sidebar.setPrefWidth(sidebarWidth);
        AnchorPane.setLeftAnchor(contentArea, sidebarWidth);
    }

    private VBox buildErrorPlaceholder(String title, String error) {
        Label titleLbl = new Label(title);
        titleLbl.setStyle("-fx-font-size: 24; -fx-font-weight: bold; -fx-text-fill: #1E293B;");
        Label errLbl = new Label("⚠️ Error cargando vista: " + error);
        errLbl.setStyle("-fx-font-size: 13; -fx-text-fill: #EF4444; -fx-wrap-text: true;");
        VBox box = new VBox(12, titleLbl, errLbl);
        box.setStyle("-fx-alignment: CENTER; -fx-padding: 40;");
        return box;
    }
}