-- GA4 Partition Maintenance Functions
-- Automated partition creation and cleanup for archon_ga4_events table

SET search_path TO app, public;

-- ============================================================
-- Function: Create New Monthly Partition
-- ============================================================

CREATE OR REPLACE FUNCTION create_ga4_events_partition(
    partition_date DATE
)
RETURNS TEXT AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
    create_sql TEXT;
    index_sql TEXT;
BEGIN
    -- Calculate partition boundaries (first day of month to first day of next month)
    start_date := DATE_TRUNC('month', partition_date)::DATE;
    end_date := (DATE_TRUNC('month', partition_date) + INTERVAL '1 month')::DATE;
    
    -- Generate partition name (e.g., archon_ga4_events_2026_01)
    partition_name := 'archon_ga4_events_' || TO_CHAR(start_date, 'YYYY_MM');
    
    -- Check if partition already exists
    IF EXISTS (
        SELECT 1 FROM pg_class 
        WHERE relname = partition_name
    ) THEN
        RETURN 'Partition ' || partition_name || ' already exists';
    END IF;
    
    -- Create partition
    create_sql := FORMAT(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF archon_ga4_events FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        start_date,
        end_date
    );
    
    EXECUTE create_sql;
    
    -- Create vector index on the new partition
    index_sql := FORMAT(
        'CREATE INDEX IF NOT EXISTS %I ON %I USING ivfflat (embedding_768 vector_cosine_ops) WITH (lists = 100)',
        'idx_' || partition_name || '_embedding',
        partition_name
    );
    
    EXECUTE index_sql;
    
    RETURN 'Successfully created partition ' || partition_name || ' for date range ' || start_date || ' to ' || end_date;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_ga4_events_partition IS 'Creates a new monthly partition for archon_ga4_events table with vector index';

-- ============================================================
-- Function: Auto-Create Future Partitions
-- ============================================================

CREATE OR REPLACE FUNCTION ensure_ga4_partitions_exist(
    months_ahead INT DEFAULT 3
)
RETURNS TABLE(partition_name TEXT, status TEXT) AS $$
DECLARE
    current_month DATE;
    i INT;
    result_msg TEXT;
BEGIN
    current_month := DATE_TRUNC('month', CURRENT_DATE)::DATE;
    
    FOR i IN 0..months_ahead LOOP
        result_msg := create_ga4_events_partition(current_month + (i || ' months')::INTERVAL);
        
        partition_name := 'archon_ga4_events_' || TO_CHAR(current_month + (i || ' months')::INTERVAL, 'YYYY_MM');
        status := result_msg;
        
        RETURN NEXT;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION ensure_ga4_partitions_exist IS 'Ensures partitions exist for current month + N months ahead. Call monthly via cron job.';

-- ============================================================
-- Function: Drop Old Partitions (Data Retention Policy)
-- ============================================================

CREATE OR REPLACE FUNCTION drop_old_ga4_partitions(
    retention_months INT DEFAULT 24
)
RETURNS TABLE(partition_name TEXT, status TEXT) AS $$
DECLARE
    cutoff_date DATE;
    partition_record RECORD;
    drop_sql TEXT;
BEGIN
    -- Calculate cutoff date
    cutoff_date := (DATE_TRUNC('month', CURRENT_DATE) - (retention_months || ' months')::INTERVAL)::DATE;
    
    -- Find partitions older than retention period
    FOR partition_record IN
        SELECT 
            c.relname AS table_name,
            pg_get_expr(c.relpartbound, c.oid) AS partition_bounds
        FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class p ON i.inhparent = p.oid
        WHERE p.relname = 'archon_ga4_events'
        AND c.relname ~ '^archon_ga4_events_[0-9]{4}_[0-9]{2}$'
    LOOP
        -- Extract year and month from partition name
        DECLARE
            year_month TEXT;
            partition_date DATE;
        BEGIN
            year_month := SUBSTRING(partition_record.table_name FROM 'archon_ga4_events_([0-9]{4}_[0-9]{2})');
            partition_date := TO_DATE(REPLACE(year_month, '_', '-'), 'YYYY-MM');
            
            IF partition_date < cutoff_date THEN
                -- Drop the partition
                drop_sql := FORMAT('DROP TABLE IF EXISTS %I', partition_record.table_name);
                EXECUTE drop_sql;
                
                partition_name := partition_record.table_name;
                status := 'Dropped partition (older than ' || retention_months || ' months)';
                
                RETURN NEXT;
            END IF;
        END;
    END LOOP;
    
    IF NOT FOUND THEN
        partition_name := 'N/A';
        status := 'No partitions older than ' || retention_months || ' months found';
        RETURN NEXT;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION drop_old_ga4_partitions IS 'Drops partitions older than specified retention period. Default: 24 months.';

-- ============================================================
-- Function: Get Partition Statistics
-- ============================================================

CREATE OR REPLACE FUNCTION get_ga4_partition_stats()
RETURNS TABLE(
    partition_name TEXT,
    row_count BIGINT,
    size_bytes BIGINT,
    size_pretty TEXT,
    date_range_start DATE,
    date_range_end DATE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.relname::TEXT AS partition_name,
        COALESCE(s.n_live_tup, 0) AS row_count,
        pg_total_relation_size(c.oid) AS size_bytes,
        pg_size_pretty(pg_total_relation_size(c.oid)) AS size_pretty,
        -- Extract date range from partition name
        TO_DATE(SUBSTRING(c.relname FROM 'archon_ga4_events_([0-9]{4}_[0-9]{2})'), 'YYYY_MM') AS date_range_start,
        (TO_DATE(SUBSTRING(c.relname FROM 'archon_ga4_events_([0-9]{4}_[0-9]{2})'), 'YYYY_MM') + INTERVAL '1 month')::DATE AS date_range_end
    FROM pg_class c
    JOIN pg_inherits i ON c.oid = i.inhrelid
    JOIN pg_class p ON i.inhparent = p.oid
    LEFT JOIN pg_stat_user_tables s ON c.oid = s.relid
    WHERE p.relname = 'archon_ga4_events'
    AND c.relname ~ '^archon_ga4_events_[0-9]{4}_[0-9]{2}$'
    ORDER BY c.relname;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_ga4_partition_stats IS 'Returns statistics for all GA4 event partitions (row count, size, date range)';

-- ============================================================
-- Trigger: Auto-Create Partition on Insert
-- ============================================================

CREATE OR REPLACE FUNCTION auto_create_ga4_partition()
RETURNS TRIGGER AS $$
DECLARE
    partition_exists BOOLEAN;
    partition_name TEXT;
BEGIN
    -- Generate expected partition name
    partition_name := 'archon_ga4_events_' || TO_CHAR(NEW.event_timestamp, 'YYYY_MM');
    
    -- Check if partition exists
    SELECT EXISTS (
        SELECT 1 FROM pg_class 
        WHERE relname = partition_name
    ) INTO partition_exists;
    
    -- Create partition if it doesn't exist
    IF NOT partition_exists THEN
        PERFORM create_ga4_events_partition(NEW.event_timestamp::DATE);
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger (but disabled by default - use ensure_ga4_partitions_exist instead)
-- Uncomment if you want automatic partition creation on insert:
-- CREATE TRIGGER trigger_auto_create_ga4_partition
--     BEFORE INSERT ON archon_ga4_events
--     FOR EACH ROW
--     EXECUTE FUNCTION auto_create_ga4_partition();

-- ============================================================
-- Initial Setup: Create Partitions for Current + Next 3 Months
-- ============================================================

SELECT * FROM ensure_ga4_partitions_exist(3);

-- ============================================================
-- Success Message
-- ============================================================

SELECT 'GA4 Partition Maintenance Functions Created Successfully' AS status;

