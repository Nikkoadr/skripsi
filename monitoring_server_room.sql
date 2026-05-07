-- phpMyAdmin SQL Dump
-- version 5.2.3
-- https://www.phpmyadmin.net/
--
-- Host: localhost:3306
-- Waktu pembuatan: 07 Bulan Mei 2026 pada 13.01
-- Versi server: 8.4.3
-- Versi PHP: 8.5.5

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Basis data: `monitoring_server_room`
--

-- --------------------------------------------------------

--
-- Struktur dari tabel `event_logs`
--

CREATE TABLE `event_logs` (
  `id` int NOT NULL,
  `user_id` int DEFAULT NULL,
  `event_type` varchar(100) DEFAULT NULL,
  `deskripsi` text,
  `nilai` float DEFAULT NULL,
  `status` varchar(50) DEFAULT NULL,
  `waktu_mulai` datetime DEFAULT NULL,
  `waktu_selesai` datetime DEFAULT NULL,
  `durasi` int DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data untuk tabel `event_logs`
--

INSERT INTO `event_logs` (`id`, `user_id`, `event_type`, `deskripsi`, `nilai`, `status`, `waktu_mulai`, `waktu_selesai`, `durasi`, `created_at`) VALUES
(1, 1, 'SUHU_TINGGI', 'Suhu ruang server melebihi batas normal', 35, 'warning', '2026-05-07 09:05:00', '2026-05-07 09:12:00', 420, '2026-05-07 09:05:00'),
(2, 1, 'LISTRIK_MATI', 'Listrik utama terputus', 0, 'critical', '2026-05-07 09:15:00', '2026-05-07 09:30:00', 900, '2026-05-07 09:15:00'),
(3, 1, 'PINTU_TERBUKA', 'Pintu ruang server terbuka lebih dari 5 menit', 1, 'warning', '2026-05-07 09:40:00', '2026-05-07 09:50:00', 600, '2026-05-07 09:40:00'),
(4, 1, 'OVERLOAD_DAYA', 'Penggunaan daya melebihi ambang batas', 3520, 'critical', '2026-05-07 10:35:00', '2026-05-07 10:38:00', 180, '2026-05-07 10:35:00'),
(5, 1, 'SUHU_RENDAH', 'Suhu ruang server di bawah batas minimum', 17, 'warning', '2026-05-07 11:15:00', '2026-05-07 11:18:00', 180, '2026-05-07 11:15:00'),
(6, 1, 'KELEMBAPAN_RENDAH', 'Kelembapan ruang server terlalu rendah', 24, 'warning', '2026-05-07 11:35:00', '2026-05-07 11:40:00', 300, '2026-05-07 11:35:00'),
(7, 1, 'SHUTDOWN_SERVER', 'Server dimatikan otomatis melalui SSH', 0, 'critical', '2026-05-07 09:20:00', '2026-05-07 09:21:00', 60, '2026-05-07 09:20:00'),
(8, 1, 'LISTRIK_NORMAL', 'Tegangan listrik kembali normal', 220, 'normal', '2026-05-07 09:30:00', '2026-05-07 09:31:00', 60, '2026-05-07 09:30:00');

-- --------------------------------------------------------

--
-- Struktur dari tabel `monitoring_logs`
--

CREATE TABLE `monitoring_logs` (
  `id` int NOT NULL,
  `suhu` float DEFAULT NULL,
  `kelembapan` float DEFAULT NULL,
  `arus_listrik` float DEFAULT NULL,
  `daya_watt` float DEFAULT NULL,
  `status_pintu` varchar(20) DEFAULT NULL,
  `power_status` varchar(20) DEFAULT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data untuk tabel `monitoring_logs`
--

INSERT INTO `monitoring_logs` (`id`, `suhu`, `kelembapan`, `arus_listrik`, `daya_watt`, `status_pintu`, `power_status`, `created_at`) VALUES
(1, 27.1, 60.2, 1.5, 330, 'tertutup', 'on', '2026-05-07 08:00:00'),
(2, 27.3, 60.5, 1.6, 352, 'tertutup', 'on', '2026-05-07 08:05:00'),
(3, 27.5, 61, 1.7, 374, 'tertutup', 'on', '2026-05-07 08:10:00'),
(4, 27.8, 61.5, 1.8, 396, 'tertutup', 'on', '2026-05-07 08:15:00'),
(5, 28, 62, 1.9, 418, 'tertutup', 'on', '2026-05-07 08:20:00'),
(6, 28.2, 62.5, 2, 440, 'tertutup', 'on', '2026-05-07 08:25:00'),
(7, 28.5, 63, 2.1, 462, 'tertutup', 'on', '2026-05-07 08:30:00'),
(8, 29, 64, 2.2, 484, 'tertutup', 'on', '2026-05-07 08:35:00'),
(9, 29.5, 65, 2.3, 506, 'tertutup', 'on', '2026-05-07 08:40:00'),
(10, 30.2, 66, 2.5, 550, 'tertutup', 'on', '2026-05-07 08:45:00'),
(11, 31, 67, 2.8, 616, 'tertutup', 'on', '2026-05-07 08:50:00'),
(12, 32, 68, 3, 660, 'tertutup', 'on', '2026-05-07 08:55:00'),
(13, 33, 69, 3.2, 704, 'tertutup', 'on', '2026-05-07 09:00:00'),
(14, 34, 70, 3.5, 770, 'tertutup', 'on', '2026-05-07 09:05:00'),
(15, 35, 72, 3.8, 836, 'tertutup', 'on', '2026-05-07 09:10:00'),
(16, 29, 65, 0, 0, 'tertutup', 'off', '2026-05-07 09:15:00'),
(17, 28.5, 64, 0, 0, 'tertutup', 'off', '2026-05-07 09:20:00'),
(18, 28, 63, 0, 0, 'tertutup', 'off', '2026-05-07 09:25:00'),
(19, 27.8, 62, 1.5, 330, 'tertutup', 'on', '2026-05-07 09:30:00'),
(20, 27.5, 61.5, 1.6, 352, 'tertutup', 'on', '2026-05-07 09:35:00'),
(21, 27.2, 61, 1.7, 374, 'terbuka', 'on', '2026-05-07 09:40:00'),
(22, 27, 60.5, 1.7, 374, 'terbuka', 'on', '2026-05-07 09:45:00'),
(23, 27, 60.5, 1.7, 374, 'terbuka', 'on', '2026-05-07 09:50:00'),
(24, 27.5, 61, 1.8, 396, 'tertutup', 'on', '2026-05-07 09:55:00'),
(25, 28, 62, 1.9, 418, 'tertutup', 'on', '2026-05-07 10:00:00'),
(26, 28.5, 63, 2, 440, 'tertutup', 'on', '2026-05-07 10:05:00'),
(27, 29, 64, 2.1, 462, 'tertutup', 'on', '2026-05-07 10:10:00'),
(28, 29.5, 65, 2.2, 484, 'tertutup', 'on', '2026-05-07 10:15:00'),
(29, 30, 66, 2.4, 528, 'tertutup', 'on', '2026-05-07 10:20:00'),
(30, 31, 67, 2.6, 572, 'tertutup', 'on', '2026-05-07 10:25:00'),
(31, 32, 68, 15.5, 3410, 'tertutup', 'on', '2026-05-07 10:30:00'),
(32, 33, 69, 16, 3520, 'tertutup', 'on', '2026-05-07 10:35:00'),
(33, 31, 67, 2.5, 550, 'tertutup', 'on', '2026-05-07 10:40:00'),
(34, 30, 66, 2.4, 528, 'tertutup', 'on', '2026-05-07 10:45:00'),
(35, 29, 65, 2.2, 484, 'tertutup', 'on', '2026-05-07 10:50:00'),
(36, 28, 64, 1.9, 418, 'tertutup', 'on', '2026-05-07 10:55:00'),
(37, 27.5, 63, 1.8, 396, 'tertutup', 'on', '2026-05-07 11:00:00'),
(38, 27, 62, 1.7, 374, 'tertutup', 'on', '2026-05-07 11:05:00'),
(39, 18, 40, 1.5, 330, 'tertutup', 'on', '2026-05-07 11:10:00'),
(40, 17, 39, 1.5, 330, 'tertutup', 'on', '2026-05-07 11:15:00'),
(41, 19, 41, 1.6, 352, 'tertutup', 'on', '2026-05-07 11:20:00'),
(42, 20, 42, 1.7, 374, 'tertutup', 'on', '2026-05-07 11:25:00'),
(43, 26, 25, 1.8, 396, 'tertutup', 'on', '2026-05-07 11:30:00'),
(44, 27, 24, 1.9, 418, 'tertutup', 'on', '2026-05-07 11:35:00'),
(45, 28, 30, 2, 440, 'tertutup', 'on', '2026-05-07 11:40:00'),
(46, 29, 35, 2.1, 462, 'tertutup', 'on', '2026-05-07 11:45:00'),
(47, 30, 50, 2.2, 484, 'tertutup', 'on', '2026-05-07 11:50:00'),
(48, 31, 55, 2.3, 506, 'tertutup', 'on', '2026-05-07 11:55:00'),
(49, 29, 52, 2, 440, 'tertutup', 'on', '2026-05-07 12:00:00'),
(50, 28, 50, 1.8, 396, 'tertutup', 'on', '2026-05-07 12:05:00');

-- --------------------------------------------------------

--
-- Struktur dari tabel `users`
--

CREATE TABLE `users` (
  `id` int NOT NULL,
  `nama` varchar(100) NOT NULL,
  `email` varchar(100) NOT NULL,
  `password` varchar(255) NOT NULL,
  `role` varchar(50) NOT NULL,
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

--
-- Dumping data untuk tabel `users`
--

INSERT INTO `users` (`id`, `nama`, `email`, `password`, `role`, `created_at`) VALUES
(1, 'Administrator', 'nikko@skripsi.com', 'admin123', 'admin', '2026-05-07 09:18:04');

--
-- Indeks untuk tabel yang dibuang
--

--
-- Indeks untuk tabel `event_logs`
--
ALTER TABLE `event_logs`
  ADD PRIMARY KEY (`id`),
  ADD KEY `fk_event_user` (`user_id`);

--
-- Indeks untuk tabel `monitoring_logs`
--
ALTER TABLE `monitoring_logs`
  ADD PRIMARY KEY (`id`);

--
-- Indeks untuk tabel `users`
--
ALTER TABLE `users`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `email` (`email`);

--
-- AUTO_INCREMENT untuk tabel yang dibuang
--

--
-- AUTO_INCREMENT untuk tabel `event_logs`
--
ALTER TABLE `event_logs`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=9;

--
-- AUTO_INCREMENT untuk tabel `monitoring_logs`
--
ALTER TABLE `monitoring_logs`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=51;

--
-- AUTO_INCREMENT untuk tabel `users`
--
ALTER TABLE `users`
  MODIFY `id` int NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=2;

--
-- Ketidakleluasaan untuk tabel pelimpahan (Dumped Tables)
--

--
-- Ketidakleluasaan untuk tabel `event_logs`
--
ALTER TABLE `event_logs`
  ADD CONSTRAINT `fk_event_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
