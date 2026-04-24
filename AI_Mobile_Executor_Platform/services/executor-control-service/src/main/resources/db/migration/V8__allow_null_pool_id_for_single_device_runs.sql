ALTER TABLE experiment_runs
    MODIFY COLUMN pool_id varchar(64) DEFAULT NULL;
