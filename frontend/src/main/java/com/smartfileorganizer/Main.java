package com.smartfileorganizer;

import javafx.application.Application;
import javafx.fxml.FXMLLoader;
import javafx.scene.Scene;
import javafx.stage.Stage;

public class Main extends Application {

    @Override
    public void start(Stage stage) throws Exception {
        FXMLLoader loader = new FXMLLoader(
            getClass().getResource("/fxml/MainLayout.fxml")
        );

        Scene scene = new Scene(loader.load());
        scene.getStylesheets().add(
            getClass().getResource("/css/styles.css").toExternalForm()
        );

        stage.setTitle("Smart File Organizer");
        stage.setScene(scene);
        stage.setMinWidth(900);
        stage.setMinHeight(600);
        stage.show();
    }

    public static void main(String[] args) {
        launch(args);
    }
}