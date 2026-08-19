SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

-- ======================================================
-- 1. Buat database jika belum ada
-- ======================================================
CREATE DATABASE IF NOT EXISTS skripsi
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE skripsi;

-- ======================================================
-- 2. Tabel users (pengguna aplikasi)
-- ======================================================
CREATE TABLE `users` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `nama` VARCHAR(100) NOT NULL,
  `email` VARCHAR(100) NOT NULL,
  `password` VARCHAR(255) NOT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ======================================================
-- 3. Tabel devices (perangkat ESP32 yang terdaftar)
-- ======================================================
CREATE TABLE `devices` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(50) NOT NULL UNIQUE,
  `status` ENUM('online','offline') NOT NULL DEFAULT 'offline',
  `last_seen` TIMESTAMP NULL DEFAULT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  INDEX `idx_device_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ======================================================
-- 4. Tabel monitoring_logs (data sensor)
-- ======================================================
CREATE TABLE `monitoring_logs` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `device_id` INT UNSIGNED NULL COMMENT 'Referensi ke devices.id',
  `suhu` DECIMAL(4,1) DEFAULT NULL,
  `kelembapan` DECIMAL(4,1) DEFAULT NULL,
  `arus_listrik` DECIMAL(5,2) DEFAULT NULL,
  `daya_watt` DECIMAL(7,1) DEFAULT NULL,
  `status_pintu` TINYINT(1) DEFAULT NULL COMMENT '0=Tertutup, 1=Terbuka',
  `power_status` TINYINT(1) DEFAULT NULL COMMENT '0=OFF, 1=ON',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  INDEX `idx_monitoring_created_at` (`created_at`),
  INDEX `idx_monitoring_device_id` (`device_id`),
  CONSTRAINT `fk_monitoring_device`
    FOREIGN KEY (`device_id`)
    REFERENCES `devices`(`id`)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ======================================================
-- 5. Tabel event_logs (log kejadian/peringatan)
-- ======================================================
CREATE TABLE `event_logs` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `device_id` INT UNSIGNED NULL COMMENT 'Referensi ke devices.id',
  `event_type` VARCHAR(50) DEFAULT NULL,
  `deskripsi` VARCHAR(255) DEFAULT NULL,
  `status` TINYINT(1) DEFAULT NULL COMMENT '0=Aman, 1=Warning, 2=Bahaya',
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  INDEX `idx_event_created_at` (`created_at`),
  INDEX `idx_event_type` (`event_type`),
  INDEX `idx_event_device_id` (`device_id`),
  CONSTRAINT `fk_event_device`
    FOREIGN KEY (`device_id`)
    REFERENCES `devices`(`id`)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ======================================================
-- 6. Tabel app_settings (konfigurasi sistem)
-- ======================================================
CREATE TABLE `app_settings` (
  `id` INT(11) NOT NULL AUTO_INCREMENT,
  `suhu_atas` DECIMAL(4,1) NOT NULL DEFAULT 35.0 COMMENT 'Batas atas suhu normal (°C)',
  `suhu_kritis` DECIMAL(4,1) NOT NULL DEFAULT 40.0 COMMENT 'Suhu kritis auto-shutdown (°C)',
  `suhu_bawah` DECIMAL(4,1) NOT NULL DEFAULT 18.0 COMMENT 'Batas bawah suhu normal (°C)',
  `lembab_atas` DECIMAL(4,1) NOT NULL DEFAULT 70.0 COMMENT 'Batas atas kelembapan normal (%)',
  `lembab_bawah` DECIMAL(4,1) NOT NULL DEFAULT 30.0 COMMENT 'Batas bawah kelembapan normal (%)',
  `watt_atas` DECIMAL(7,1) NOT NULL DEFAULT 3500.0 COMMENT 'Batas daya maksimum (Watt)',
  `amper_bawah` DECIMAL(6,3) NOT NULL DEFAULT 0.190 COMMENT 'Arus minimum deteksi listrik mati (A)',
  `durasi_maks_pintu` INT(11) NOT NULL DEFAULT 300 COMMENT 'Durasi pintu terbuka (detik)',
  `durasi_maks_arus_mati` INT(11) NOT NULL DEFAULT 300 COMMENT 'Durasi listrik padam sebelum shutdown (detik)',
  `durasi_maks_overheat` INT(11) NOT NULL DEFAULT 300 COMMENT 'Durasi suhu kritis sebelum shutdown (detik)',
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ======================================================
-- 7. Data awal (seed)
-- ======================================================

-- 7a. Konfigurasi default (satu baris)
INSERT INTO `app_settings` (
  `id`, `suhu_atas`, `suhu_kritis`, `suhu_bawah`,
  `lembab_atas`, `lembab_bawah`, `watt_atas`, `amper_bawah`,
  `durasi_maks_pintu`, `durasi_maks_arus_mati`, `durasi_maks_overheat`
) VALUES (
  1, 35.0, 40.0, 18.0,
  70.0, 30.0, 3500.0, 0.190,
  300, 300, 300
);

-- 7b. User admin
INSERT INTO `users`
(`nama`, `email`, `password`, `created_at`)
VALUES (
  'Nikko Adrian',
  'nikko@skripsi.com',
  'scrypt:32768:8:1$5VhI1VCWHu50lsfo$0f8af2efafc9e3e65fb5c5c24fc9020d4d3cabdfbb79d3952472a563ddb555d47672870f5d9ff8f8f4f6854a33ac3f3c47964fa6213f7b5d18949cc7ab130495',
  CURRENT_TIMESTAMP
);

INSERT INTO `devices`
(`name`, `status`, `last_seen`, `created_at`)
VALUES (
  'Alat 1',
  'online',
  NOW(),
  CURRENT_TIMESTAMP
);

COMMIT;