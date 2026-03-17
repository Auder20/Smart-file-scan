package com.smartfileorganizer.utils;

import javafx.application.Platform;
import javafx.scene.control.*;
import javafx.scene.layout.*;
import javafx.scene.Node;
import javafx.geometry.*;
import javafx.animation.*;
import javafx.util.Duration;
import javafx.fxml.FXMLLoader;
import javafx.scene.Parent;
import javafx.scene.Scene;
import javafx.stage.*;

import java.io.IOException;
import java.util.List;
import java.util.Optional;

public class UIUtils {

    // ── CSS stylesheet URL (cargado una vez) ──────────────────────────────────
    private static String cssUrl = null;

    private static String getCssUrl() {
        if (cssUrl == null) {
            var url = UIUtils.class.getResource("/css/styles.css");
            if (url != null) cssUrl = url.toExternalForm();
        }
        return cssUrl;
    }

    /** Inyecta el CSS de la app en cualquier DialogPane para que herede el tema oscuro. */
    public static void applyTheme(DialogPane pane) {
        String css = getCssUrl();
        if (css != null) pane.getStylesheets().add(css);
        // Forzar fondo oscuro aunque el OS use modo claro
        pane.setStyle("-fx-background-color: #252526; -fx-border-color: #3E3E42; "
                    + "-fx-border-width: 1; -fx-border-radius: 8; -fx-background-radius: 8;");
    }

    // ── Loading / Empty / Error states ────────────────────────────────────────

    public static void showLoadingState(VBox container, String message) {
        Platform.runLater(() -> {
            container.getChildren().clear();
            ProgressIndicator progress = new ProgressIndicator();
            progress.setPrefSize(40, 40);
            Label loadingLabel = new Label(message);
            loadingLabel.setStyle("-fx-text-fill: #64748B; -fx-font-size: 14;");
            VBox box = new VBox(10, progress, loadingLabel);
            box.setAlignment(Pos.CENTER); box.setPadding(new Insets(20));
            container.getChildren().add(box);
            FadeTransition ft = new FadeTransition(Duration.millis(300), box);
            ft.setFromValue(0); ft.setToValue(1); ft.play();
        });
    }

    public static void hideLoadingState(VBox container) {
        Platform.runLater(() -> {
            FadeTransition ft = new FadeTransition(Duration.millis(200), container);
            ft.setFromValue(1); ft.setToValue(0);
            ft.setOnFinished(e -> container.getChildren().clear());
            ft.play();
        });
    }

    public static void showErrorState(VBox container, String errorMessage, String suggestion) {
        Platform.runLater(() -> {
            container.getChildren().clear();
            Label icon = new Label("⚠️");
            icon.setStyle("-fx-font-size: 48; -fx-opacity: 0.6;");
            Label err  = new Label(errorMessage);
            err.setStyle("-fx-text-fill: #EF4444; -fx-font-size: 16; -fx-font-weight: bold;");
            Label sug  = new Label(suggestion);
            sug.setStyle("-fx-text-fill: #64748B; -fx-font-size: 14;");
            VBox box   = new VBox(10, icon, err, sug);
            box.setAlignment(Pos.CENTER); box.setPadding(new Insets(20));
            container.getChildren().add(box);
            FadeTransition ft = new FadeTransition(Duration.millis(300), box);
            ft.setFromValue(0); ft.setToValue(1); ft.play();
        });
    }

    public static void showEmptyState(VBox container, String message, String icon) {
        Platform.runLater(() -> {
            container.getChildren().clear();
            Label ic = new Label(icon);
            ic.setStyle("-fx-font-size: 48; -fx-opacity: 0.3;");
            Label lbl = new Label(message);
            lbl.setStyle("-fx-text-fill: #64748B; -fx-font-size: 14;");
            VBox box  = new VBox(10, ic, lbl);
            box.setAlignment(Pos.CENTER); box.setPadding(new Insets(20));
            container.getChildren().add(box);
        });
    }

    // ── Alert dialogs (con CSS inyectado) ─────────────────────────────────────

    private static Alert makeAlert(Alert.AlertType type, String title, String message) {
        Alert alert = new Alert(type);
        alert.setTitle(title);
        alert.setHeaderText(null);
        alert.setContentText(message);
        applyTheme(alert.getDialogPane());
        // Estilo del texto de contenido
        Node contentLabel = alert.getDialogPane().lookup(".content.label");
            if (contentLabel != null) {
            contentLabel.setStyle("-fx-text-fill: #C0C0C5; -fx-font-size: 13px;");
}
        return alert;
    }

    public static boolean showConfirmationDialog(String title, String header, String content) {
        Alert alert = new Alert(Alert.AlertType.CONFIRMATION);
        alert.setTitle(title);
        alert.setHeaderText(header);
        alert.setContentText(content);
        applyTheme(alert.getDialogPane());
        return alert.showAndWait().orElse(ButtonType.CANCEL) == ButtonType.OK;
    }

    public static void showInfoDialog(String title, String message) {
        Platform.runLater(() -> makeAlert(Alert.AlertType.INFORMATION, title, message).showAndWait());
    }

    public static void showErrorDialog(String title, String message) {
        Platform.runLater(() -> makeAlert(Alert.AlertType.ERROR, title, message).showAndWait());
    }

    public static void showWarningDialog(String title, String message) {
        Platform.runLater(() -> makeAlert(Alert.AlertType.WARNING, title, message).showAndWait());
    }

    // ── Choice dialog con CSS ─────────────────────────────────────────────────

    /**
     * Muestra un ChoiceDialog estilizado con el tema oscuro de la app.
     * @param title      Título de la ventana
     * @param header     Texto del encabezado
     * @param defaultChoice  Opción por defecto
     * @param choices    Lista de opciones
     * @return Optional con la opción seleccionada
     */
    public static Optional<String> showStyledChoiceDialog(
            String title, String header, String defaultChoice, String... choices) {

        ChoiceDialog<String> dialog = new ChoiceDialog<>(defaultChoice, choices);
        dialog.setTitle(title);
        dialog.setHeaderText(header);
        dialog.setContentText(null);
        applyTheme(dialog.getDialogPane());

        // Estilo del ComboBox interno del ChoiceDialog
        dialog.getDialogPane().lookupAll(".combo-box").forEach(node ->
            node.setStyle(
                "-fx-background-color: #1A1A1A; -fx-border-color: #4B9EFF; "
              + "-fx-border-width: 1; -fx-border-radius: 6; -fx-background-radius: 6; "
              + "-fx-text-fill: #E8E8E8;")
        );
        // Estilo header
        Node headerNode = dialog.getDialogPane().lookup(".header-panel");
        if (headerNode != null)
            headerNode.setStyle("-fx-background-color: #1E1E1E; -fx-background-radius: 8 8 0 0;");
        Node headerLabel = dialog.getDialogPane().lookup(".header-panel .label");
        if (headerLabel != null)
            headerLabel.setStyle("-fx-text-fill: #E8E8E8; -fx-font-weight: bold; -fx-font-size: 14px;");

        // Estilo botones
        dialog.getDialogPane().getButtonTypes().forEach(bt -> {
            Node btn = dialog.getDialogPane().lookupButton(bt);
            if (btn != null) {
                if (bt.getButtonData().isDefaultButton()) {
                    btn.setStyle(
                        "-fx-background-color: linear-gradient(to bottom,#5AABFF,#3A8FEE); "
                      + "-fx-text-fill: #0A1628; -fx-font-weight: bold; "
                      + "-fx-background-radius: 6; -fx-padding: 7 16;");
                } else {
                    btn.setStyle(
                        "-fx-background-color: #3C3C3F; -fx-text-fill: #C0C0C5; "
                      + "-fx-border-color: #5A5A60; -fx-border-width: 1; "
                      + "-fx-background-radius: 6; -fx-border-radius: 6; -fx-padding: 7 16;");
                }
            }
        });

        return dialog.showAndWait();
    }

    // ── Button loading state ──────────────────────────────────────────────────

    public static void setButtonLoadingState(Button button, boolean loading) {
        Platform.runLater(() -> {
            if (loading) {
                button.setDisable(true);
                ProgressIndicator ind = new ProgressIndicator(10);
                ind.setStyle("-fx-progress-color: white;");
                button.setGraphic(ind);
                button.setText("Cargando...");
            } else {
                button.setDisable(false);
                button.setGraphic(null);
            }
        });
    }

    public static void setContentWithFade(VBox container, Node... content) {
        Platform.runLater(() -> {
            container.getChildren().clear();
            container.getChildren().addAll(content);
            FadeTransition ft = new FadeTransition(Duration.millis(300), container);
            ft.setFromValue(0); ft.setToValue(1); ft.play();
        });
    }

    // ── Files view ────────────────────────────────────────────────────────────

    public static void showFilesView(String scanId, String status) {
        Platform.runLater(() -> {
            try {
                FXMLLoader loader = new FXMLLoader(
                    UIUtils.class.getResource("/fxml/files_view.fxml"));
                Parent root = loader.load();
                com.smartfileorganizer.controllers.FilesViewController ctrl = loader.getController();
                ctrl.setScanId(scanId);

                Stage stage = new Stage();
                stage.setTitle("Archivos del Scan: " + scanId);
                Scene scene = new Scene(root, 1000, 700);
                String css  = getCssUrl();
                if (css != null) scene.getStylesheets().add(css);
                stage.setScene(scene);
                stage.initModality(Modality.APPLICATION_MODAL);
                stage.setResizable(true);
                stage.showAndWait();
            } catch (IOException e) {
                showErrorDialog("Error", "No se pudo abrir la vista de archivos: " + e.getMessage());
            }
        });
    }
}