package com.smartfileorganizer.utils;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Utility class for managing concurrent operations in the JavaFX application.
 * Provides optimized thread pools for background tasks.
 */
public class ConcurrencyUtils {
    
    // Dedicated thread pool for background API calls
    private static final Executor API_EXECUTOR = Executors.newFixedThreadPool(
        4,  // Limit concurrent API calls
        new ThreadFactory() {
            private final AtomicInteger threadNumber = new AtomicInteger(1);
            @Override
            public Thread newThread(Runnable r) {
                Thread t = new Thread(r, "API-Worker-" + threadNumber.getAndIncrement());
                t.setDaemon(true);
                return t;
            }
        }
    );
    
    // Separate thread pool for file system operations
    private static final Executor FS_EXECUTOR = Executors.newFixedThreadPool(
        2,  // Limit filesystem operations
        new ThreadFactory() {
            private final AtomicInteger threadNumber = new AtomicInteger(1);
            @Override
            public Thread newThread(Runnable r) {
                Thread t = new Thread(r, "FS-Worker-" + threadNumber.getAndIncrement());
                t.setDaemon(true);
                return t;
            }
        }
    );
    
    /**
     * Run a task in the API thread pool
     */
    public static CompletableFuture<Void> runAsync(Runnable task) {
        return CompletableFuture.runAsync(task, API_EXECUTOR);
    }
    
    /**
     * Run a task in the API thread pool and return a result
     */
    public static <T> CompletableFuture<T> supplyAsync(java.util.function.Supplier<T> task) {
        return CompletableFuture.supplyAsync(task, API_EXECUTOR);
    }
    
    /**
     * Run a file system operation in the dedicated FS thread pool
     */
    public static CompletableFuture<Void> runFsAsync(Runnable task) {
        return CompletableFuture.runAsync(task, FS_EXECUTOR);
    }
    
    /**
     * Run a file system operation in the dedicated FS thread pool and return a result
     */
    public static <T> CompletableFuture<T> supplyFsAsync(java.util.function.Supplier<T> task) {
        return CompletableFuture.supplyAsync(task, FS_EXECUTOR);
    }
    
    /**
     * Execute a task with a delay (useful for debouncing UI updates)
     */
    public static CompletableFuture<Void> delayedAsync(Runnable task, long delayMs) {
        return CompletableFuture.runAsync(() -> {
            try {
                Thread.sleep(delayMs);
                task.run();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, API_EXECUTOR);
    }
}
