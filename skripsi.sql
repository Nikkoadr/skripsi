SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

CREATE DATABASE IF NOT EXISTS skripsi
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE skripsi;

CREATE TABLE `users` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `nama` VARCHAR(100) NOT NULL,
  `email` VARCHAR(100) NOT NULL,
  `password` VARCHAR(255) NOT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_users_email` (`email`)
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `monitoring_logs` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,

  `suhu` DECIMAL(4,1) DEFAULT NULL,
  `kelembapan` DECIMAL(4,1) DEFAULT NULL,
  `arus_listrik` DECIMAL(5,2) DEFAULT NULL,
  `daya_watt` DECIMAL(7,1) DEFAULT NULL,

  `status_pintu` TINYINT(1) DEFAULT NULL COMMENT '0=Tertutup, 1=Terbuka',
  `power_status` TINYINT(1) DEFAULT NULL COMMENT '0=OFF, 1=ON',

  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  INDEX `idx_monitoring_created_at` (`created_at`)
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `event_logs` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,

  `event_type` VARCHAR(50) DEFAULT NULL,
  `deskripsi` VARCHAR(255) DEFAULT NULL,

  `status` TINYINT(1) DEFAULT NULL COMMENT '0=Aman, 1=Warning, 2=Bahaya',

  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  INDEX `idx_event_created_at` (`created_at`),
  INDEX `idx_event_type` (`event_type`)
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `app_settings` (
  `setting_key` VARCHAR(50) NOT NULL,
  `setting_value` VARCHAR(50) NOT NULL,
  `description` VARCHAR(255) DEFAULT NULL,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (`setting_key`)
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;

INSERT INTO `app_settings` (`setting_key`, `setting_value`, `description`) VALUES
('suhu_atas', '35.0', 'Batas atas suhu normal (°C)'),
('suhu_kritis', '40.0', 'Suhu kritis untuk shutdown (°C)'),
('suhu_bawah', '18.0', 'Batas bawah suhu normal (°C)'),
('lembab_atas', '70.0', 'Batas atas kelembapan normal (%)'),
('lembab_bawah', '30.0', 'Batas bawah kelembapan normal (%)'),
('watt_atas', '3500.0', 'Batas daya maksimum (Watt)'),
('amper_bawah', '0.190', 'Ambang batas arus untuk deteksi listrik mati (A)'),
('durasi_maks_pintu', '300', 'Durasi maksimum pintu terbuka sebelum alarm (detik)'),
('durasi_maks_arus_mati', '300', 'Durasi listrik padam sebelum shutdown (detik)'),
('durasi_maks_overheat', '300', 'Durasi overheat sebelum shutdown (detik)');

INSERT INTO `users`
(
  `nama`,
  `email`,
  `password`,
  `created_at`
)
VALUES
(
  'Nikko Adrian',
  'nikko@skripsi.com',
  'scrypt:32768:8:1$5VhI1VCWHu50lsfo$0f8af2efafc9e3e65fb5c5c24fc9020d4d3cabdfbb79d3952472a563ddb555d47672870f5d9ff8f8f4f6854a33ac3f3c47964fa6213f7b5d18949cc7ab130495',
  CURRENT_TIMESTAMP
);

COMMIT;