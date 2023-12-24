SELECT
    t.table_schema,
    t.table_name,
    (
        SELECT
            reltuples
        FROM
            pg_class
        WHERE
            relname = t.table_name
    ) AS rows,
    pg_size_pretty(
        pg_total_relation_size(t.table_schema || '.' || t.table_name)
    ) AS size,
    pg_total_relation_size(t.table_schema || '.' || t.table_name) AS size_bytes
FROM
    (
        SELECT
            *
        FROM
            information_schema.tables
        WHERE
            table_schema NOT IN ('information_schema', 'pg_catalog')
    ) AS t
ORDER BY
    size_bytes DESC