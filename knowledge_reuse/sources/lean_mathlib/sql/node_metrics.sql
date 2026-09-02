CREATE OR REPLACE TABLE node_metrics AS
SELECT
  n.node_id,
  n.name,
  n.kind,
  n.domain,
  n.is_generated,
  count(DISTINCT e.src_id) FILTER (WHERE e.dst_id = n.node_id AND e.src_id <> e.dst_id) AS in_degree_all,
  count(DISTINCT e.src_id) FILTER (WHERE e.dst_id = n.node_id AND e.src_id <> e.dst_id AND e.edge_type = 'TYPE') AS in_degree_type,
  count(DISTINCT e.src_id) FILTER (WHERE e.dst_id = n.node_id AND e.src_id <> e.dst_id AND e.edge_type = 'VALUE') AS in_degree_value,
  count(DISTINCT e.dst_id) FILTER (WHERE e.src_id = n.node_id) AS out_degree_all
FROM nodes n
LEFT JOIN edges e ON e.src_id = n.node_id OR e.dst_id = n.node_id
GROUP BY ALL;
