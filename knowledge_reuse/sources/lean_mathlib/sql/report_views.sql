CREATE OR REPLACE VIEW top_reuse AS
SELECT * FROM node_metrics ORDER BY in_degree_all DESC, name LIMIT 100;

