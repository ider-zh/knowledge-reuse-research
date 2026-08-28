CREATE OR REPLACE TABLE domain_matrix AS
SELECT src.domain AS src_domain, dst.domain AS dst_domain, e.edge_type, count(*) AS edge_count
FROM edges e
JOIN nodes src ON e.src_id = src.node_id
JOIN nodes dst ON e.dst_id = dst.node_id
GROUP BY ALL;

