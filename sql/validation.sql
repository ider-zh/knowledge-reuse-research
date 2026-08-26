-- Parameters are supplied by scripts/verify_run.py through temporary views.
SELECT 'duplicate_node_names' AS check_name, count(*) AS failures
FROM (SELECT snapshot_id, name FROM nodes GROUP BY ALL HAVING count(*) > 1)
UNION ALL
SELECT 'duplicate_typed_edges', count(*)
FROM (
  SELECT snapshot_id, src_id, dst_id, edge_type
  FROM edges GROUP BY ALL HAVING count(*) > 1
)
UNION ALL
SELECT 'dangling_sources', count(*)
FROM edges e LEFT JOIN nodes n ON e.src_id = n.node_id WHERE n.node_id IS NULL
UNION ALL
SELECT 'dangling_targets', count(*)
FROM edges e
LEFT JOIN nodes n ON e.dst_id = n.node_id
LEFT JOIN external_nodes x ON e.dst_id = x.node_id
WHERE n.node_id IS NULL AND x.node_id IS NULL
UNION ALL
SELECT 'missing_domains', count(*) FROM nodes WHERE domain IS NULL;

