-- Platform business/control baseline. Executed only by the dedicated Flyway job.
-- Application identities must not have DDL privileges.

CREATE TABLE projects (
    id VARCHAR(256) NOT NULL,
    slug VARCHAR(256) NOT NULL,
    display_name VARCHAR(512) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_projects_slug (slug)
) ENGINE = InnoDB;

CREATE TABLE source_objects (
    id VARCHAR(256) NOT NULL,
    project_id VARCHAR(256) NOT NULL,
    source_kind VARCHAR(64) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT fk_source_objects_project
        FOREIGN KEY (project_id) REFERENCES projects (id)
) ENGINE = InnoDB;

CREATE TABLE source_revisions (
    id VARCHAR(256) NOT NULL,
    project_id VARCHAR(256) NOT NULL,
    source_object_id VARCHAR(256) NOT NULL,
    revision_number INT NOT NULL,
    filename VARCHAR(512) NOT NULL,
    source_zone_key VARCHAR(1024) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    content_type VARCHAR(256) NOT NULL,
    content_length BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(256) NOT NULL,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_source_revisions_object_revision (source_object_id, revision_number),
    UNIQUE KEY uk_source_revisions_idempotency (project_id, idempotency_key),
    CONSTRAINT fk_source_revisions_project
        FOREIGN KEY (project_id) REFERENCES projects (id),
    CONSTRAINT fk_source_revisions_object
        FOREIGN KEY (source_object_id) REFERENCES source_objects (id)
) ENGINE = InnoDB;

CREATE TABLE processing_tasks (
    id VARCHAR(256) NOT NULL,
    source_revision_id VARCHAR(256) NOT NULL,
    status VARCHAR(32) NOT NULL,
    progress SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    attempt INT UNSIGNED NOT NULL DEFAULT 0,
    failure_code VARCHAR(128) NULL,
    updated_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_processing_tasks_revision (source_revision_id),
    CONSTRAINT fk_processing_tasks_revision
        FOREIGN KEY (source_revision_id) REFERENCES source_revisions (id)
) ENGINE = InnoDB;

CREATE TABLE outbox_events (
    id VARCHAR(256) NOT NULL,
    aggregate_type VARCHAR(128) NOT NULL,
    aggregate_id VARCHAR(256) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    schema_version VARCHAR(16) NOT NULL,
    idempotency_key VARCHAR(256) NOT NULL,
    payload JSON NOT NULL,
    occurred_at TIMESTAMP(6) NOT NULL,
    published_at TIMESTAMP(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_outbox_events_idempotency (idempotency_key),
    KEY ix_outbox_events_unpublished (published_at, occurred_at)
) ENGINE = InnoDB;
