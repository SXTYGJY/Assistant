
CREATE DATABASE doris_document_db;

USE doris_document_db;

CREATE TABLE `doris_vector_table` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `document_name` text NULL,
  `content` text NULL,
  `embedding` array<float> NOT NULL,
  INDEX idx_embedding (`embedding`) USING ANN PROPERTIES(
    "dim" = "512",
    "index_type" = "hnsw",
    "metric_type" = "l2_distance"
  )
) ENGINE=OLAP
DUPLICATE KEY(`id`)
DISTRIBUTED BY HASH(`id`) BUCKETS 1
PROPERTIES (
"replication_allocation" = "tag.location.default: 1"
);
