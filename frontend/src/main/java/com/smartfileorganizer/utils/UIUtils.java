package com.smartfileorganizer.utils;

import javafx.application.Platform;
import javafx.scene.control.Alert;
import javafx.scene.control.ButtonType;
import javafx.scene.control.ProgressIndicator;
import javafx.scene.layout.VBox;
import javafx.scene.control.Label;
import javafx.scene.Node;
import javafx.geometry.Insets;
import javafx.geometry.Pos;
import javafx.animation.FadeTransition;
import javafx.util.Duration;
import javafx.fxml.FXMLLoader;
import javafx.scene.Parent;
import javafx.scene.Scene;
import javafx.stage.Modality;
import javafx.stage.Stage;
import javafx.stage.StageStyle;

import java.io.IOException;

public class UIUtils {
    
    public static void showLoadingState(VBox container, String message) {
        Platform.runLater(() -> {
            container.getChildren().clear();
            
            ProgressIndicator progress = new ProgressIndicator();
            progress.setPrefSize(40, 40);
            
            Label loadingLabel = new Label(message);
            loadingLabel.setStyle("-fx-text-fill: #64748B; -fx-font-size: 14;");
            
            VBox loadingBox = new VBox(10, progress, loadingLabel);
            loadingBox.setAlignment(Pos.CENTER);
            loadingBox.setPadding(new Insets(20));
            
            container.getChildren().add(loadingBox);
            
            // Add fade-in animation
            FadeTransition fadeIn = new FadeTransition(Duration.millis(300), loadingBox);
            fadeIn.setFromValue(0.0);
            fadeIn.setToValue(1.0);
            fadeIn.play();
        });
    }
    
    public static void hideLoadingState(VBox container) {
        Platform.runLater(() -> {
            FadeTransition fadeOut = new FadeTransition(Duration.millis(200), container);
            fadeOut.setFromValue(1.0);
            fadeOut.setToValue(0.0);
            fadeOut.setOnFinished(e -> container.getChildren().clear());
            fadeOut.play();
        });
    }
    
    public static void showErrorState(VBox container, String errorMessage, String suggestion) {
        Platform.runLater(() -> {
            container.getChildren().clear();
            
            Label errorIcon = new Label("⚠️");
            errorIcon.setStyle("-fx-font-size: 48; -fx-opacity: 0.6;");
            
            Label errorLabel = new Label(errorMessage);
            errorLabel.setStyle("-fx-text-fill: #EF4444; -fx-font-size: 16; -fx-font-weight: bold;");
            
            Label suggestionLabel = new Label(suggestion);
            suggestionLabel.setStyle("-fx-text-fill: #64748B; -fx-font-size: 14;");
            
            VBox errorBox = new VBox(10, errorIcon, errorLabel, suggestionLabel);
            errorBox.setAlignment(Pos.CENTER);
            errorBox.setPadding(new Insets(20));
            
            container.getChildren().add(errorBox);
            
            FadeTransition fadeIn = new FadeTransition(Duration.millis(300), errorBox);
            fadeIn.setFromValue(0.0);
            fadeIn.setToValue(1.0);
            fadeIn.play();
        });
    }
    
    public static void showEmptyState(VBox container, String message, String icon) {
        Platform.runLater(() -> {
            container.getChildren().clear();
            
            Label emptyIcon = new Label(icon);
            emptyIcon.setStyle("-fx-font-size: 48; -fx-opacity: 0.3;");
            
            Label emptyLabel = new Label(message);
            emptyLabel.setStyle("-fx-text-fill: #64748B; -fx-font-size: 14;");
            
            VBox emptyBox = new VBox(10, emptyIcon, emptyLabel);
            emptyBox.setAlignment(Pos.CENTER);
            emptyBox.setPadding(new Insets(20));
            
            container.getChildren().add(emptyBox);
        });
    }
    
    public static boolean showConfirmationDialog(String title, String header, String content) {
        Alert alert = new Alert(Alert.AlertType.CONFIRMATION);
        alert.setTitle(title);
        alert.setHeaderText(header);
        alert.setContentText(content);
        
        return alert.showAndWait().get() == ButtonType.OK;
    }
    
    public static void showInfoDialog(String title, String message) {
        Platform.runLater(() -> {
            Alert alert = new Alert(Alert.AlertType.INFORMATION);
            alert.setTitle(title);
            alert.setHeaderText(null);
            alert.setContentText(message);
            alert.showAndWait();
        });
    }
    
    public static void showErrorDialog(String title, String message) {
        Platform.runLater(() -> {
            Alert alert = new Alert(Alert.AlertType.ERROR);
            alert.setTitle(title);
            alert.setHeaderText(null);
            alert.setContentText(message);
            alert.showAndWait();
        });
    }
    
    public static void showWarningDialog(String title, String message) {
        Platform.runLater(() -> {
            Alert alert = new Alert(Alert.AlertType.WARNING);
            alert.setTitle(title);
            alert.setHeaderText(null);
            alert.setContentText(message);
            alert.showAndWait();
        });
    }
    
    public static void setContentWithFade(VBox container, Node... content) {
        Platform.runLater(() -> {
            container.getChildren().clear();
            container.getChildren().addAll(content);
            
            FadeTransition fadeIn = new FadeTransition(Duration.millis(300), container);
            fadeIn.setFromValue(0.0);
            fadeIn.setToValue(1.0);
            fadeIn.play();
        });
    }
    
    public static void setButtonLoadingState(javafx.scene.control.Button button, boolean loading) {
        Platform.runLater(() -> {
            if (loading) {
                button.setDisable(true);
                ProgressIndicator indicator = new ProgressIndicator(10);
                indicator.setStyle("-fx-progress-color: white;");
                button.setGraphic(indicator);
                button.setText("Cargando...");
            } else {
                button.setDisable(false);
                button.setGraphic(null);
                // Restore original text (you may need to store this elsewhere)
                if (button.getText().equals("Cargando...")) {
                    // This is a simplified approach - in production, store original text
                    button.setText("Actualizar");
                }
            }
        });
    }
    
    // FEAT 1: Show files view dialog
    public static void showFilesView(String scanId, String status) {
        Platform.runLater(() -> {
            try {
                FXMLLoader loader = new FXMLLoader(
                    UIUtils.class.getResource("/fxml/files_view.fxml")
                );
                Parent root = loader.load();
                
                com.smartfileorganizer.controllers.FilesViewController controller = loader.getController();
                controller.setScanId(scanId);
                
                Stage stage = new Stage();
                stage.setTitle("Archivos del Scan: " + scanId);
                stage.setScene(new Scene(root, 1000, 700));
                stage.initModality(Modality.APPLICATION_MODAL);
                stage.setResizable(true);
                stage.showAndWait();
                
            } catch (IOException e) {
                showErrorDialog("Error", "No se pudo abrir la vista de archivos: " + e.getMessage());
            } catch (Exception e) {
                showErrorDialog("Error", "Error inesperado: " + e.getMessage());
            }
        });
    }
}
