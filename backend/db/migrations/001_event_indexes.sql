-- 001_event_indexes.sql
-- Indexes for fast event-log queries.

CREATE INDEX IF NOT EXISTS ix_events_timestamp_desc
    ON events (timestamp DESC);

CREATE INDEX IF NOT EXISTS ix_events_severity
    ON events (severity);

CREATE INDEX IF NOT EXISTS ix_events_src_ip
    ON events (src_ip);

CREATE INDEX IF NOT EXISTS ix_events_dst_ip
    ON events (dst_ip);

CREATE INDEX IF NOT EXISTS ix_events_event_type
    ON events (event_type);

CREATE INDEX IF NOT EXISTS ix_events_source
    ON events (source);

-- Composite index for the most common filter pattern:
-- "recent events of severity > X"
CREATE INDEX IF NOT EXISTS ix_events_timestamp_severity
    ON events (timestamp DESC, severity);