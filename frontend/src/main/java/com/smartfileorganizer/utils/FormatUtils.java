package com.smartfileorganizer.utils;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public class FormatUtils {
    
    private static final DateTimeFormatter DATE_FORMATTER = 
        DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm");
    
    public static String formatFileSize(long bytes) {
        if (bytes == 0) return "0 B";
        
        String[] units = {"B", "KB", "MB", "GB", "TB"};
        int digitGroups = (int) (Math.log10(bytes) / Math.log10(1024));
        
        return String.format("%.1f %s", 
            bytes / Math.pow(1024, digitGroups), 
            units[digitGroups]);
    }
    
    public static String formatDate(LocalDateTime dateTime) {
        return dateTime.format(DATE_FORMATTER);
    }
    
    public static String formatNumber(int number) {
        return String.format("%,d", number);
    }
}
