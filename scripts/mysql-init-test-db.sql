CREATE DATABASE IF NOT EXISTS test_job_tracker
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON test_job_tracker.* TO 'job_tracker'@'%';
FLUSH PRIVILEGES;
