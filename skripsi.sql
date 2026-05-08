SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

CREATE DATABASE IF NOT EXISTS skripsi
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE skripsi;

/* =========================
   TABLE: event_logs
========================= */
CREATE TABLE `event_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `event_type` varchar(100) DEFAULT NULL,
  `deskripsi` text,
  `status` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

/* =========================
   TABLE: monitoring_logs
========================= */
CREATE TABLE `monitoring_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `suhu` float DEFAULT NULL,
  `kelembapan` float DEFAULT NULL,
  `arus_listrik` float DEFAULT NULL,
  `daya_watt` float DEFAULT NULL,
  `status_pintu` varchar(20) DEFAULT NULL,
  `power_status` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

/* =========================
   TABLE: users
========================= */
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `nama` varchar(100) NOT NULL,
  `email` varchar(100) NOT NULL,
  `password` varchar(255) NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

/* =========================
   DATA USER
========================= */
INSERT INTO `users` (`nama`, `email`, `password`, `created_at`) VALUES
(
  'Nikko Adrian',
  'nikko@skripsi.com',
  'scrypt:32768:8:1$5VhI1VCWHu50lsfo$0f8af2efafc9e3e65fb5c5c24fc9020d4d3cabdfbb79d3952472a563ddb555d47672870f5d9ff8f8f4f6854a33ac3f3c47964fa6213f7b5d18949cc7ab130495',
  '2026-05-07 09:18:04'
);

COMMIT;