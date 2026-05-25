SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

/* =========================
   DATABASE
========================= */
CREATE DATABASE IF NOT EXISTS skripsi
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE skripsi;

/* =========================
   TABLE: users
========================= */
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

/* =========================
   TABLE: monitoring_logs
========================= */
CREATE TABLE `monitoring_logs` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,

  `suhu` DECIMAL(4,1) DEFAULT NULL,
  `kelembapan` DECIMAL(4,1) DEFAULT NULL,
  `arus_listrik` DECIMAL(5,2) DEFAULT NULL,
  `daya_watt` SMALLINT UNSIGNED DEFAULT NULL,

  `status_pintu` TINYINT(1) DEFAULT NULL COMMENT '0=Tertutup, 1=Terbuka',
  `power_status` TINYINT(1) DEFAULT NULL COMMENT '0=OFF, 1=ON',

  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

  PRIMARY KEY (`id`),
  INDEX `idx_monitoring_created_at` (`created_at`)
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;

/* =========================
   TABLE: event_logs
========================= */
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

/* =========================
   DATA USER DEFAULT
========================= */
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

/* =====================================================
   TRIGGER: LIMIT monitoring_logs MAX 500 DATA
===================================================== */

DELIMITER //

DROP TRIGGER IF EXISTS limit_monitoring_logs//

CREATE TRIGGER limit_monitoring_logs
AFTER INSERT ON monitoring_logs
FOR EACH ROW
BEGIN
    IF (
        SELECT COUNT(*)
        FROM monitoring_logs
    ) > 500 THEN

        DELETE FROM monitoring_logs
        ORDER BY id ASC
        LIMIT 100;

    END IF;
END//

DELIMITER ;

/* =====================================================
   TRIGGER: LIMIT event_logs MAX 300 DATA
===================================================== */

DELIMITER //

DROP TRIGGER IF EXISTS limit_event_logs//

CREATE TRIGGER limit_event_logs
AFTER INSERT ON event_logs
FOR EACH ROW
BEGIN
    IF (
        SELECT COUNT(*)
        FROM event_logs
    ) > 300 THEN

        DELETE FROM event_logs
        ORDER BY id ASC
        LIMIT 100;

    END IF;
END//

DELIMITER ;