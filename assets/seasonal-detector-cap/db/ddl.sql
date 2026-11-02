-- DDL script for Seasonal Article Detector Agent — run ONCE by a DBA
-- before first deployment of the seasonal-detector-cap application.
--
-- Tables are created in the schema accessible to the HANA user behind
-- the BTP Destination 'CAR_HANA' (or CAR_HANA_WRITE_DESTINATION_NAME).
-- The user needs: SELECT, INSERT, UPDATE on both tables.
--
-- Naming convention: Z-prefix (customer namespace, avoids SAP namespace conflicts).

-- ──────────────────────────────────────────────────────────────────────────────
-- 1. Classification run header
--    One row per agent execution (a batch that processes N article/store combos).
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE "ZSEASONAL_CLASS_RUN" (
  "ID"                      NVARCHAR(36)   NOT NULL,
  "STATUS"                  NVARCHAR(20)   NOT NULL DEFAULT 'RUNNING',
  "STARTED_AT"              TIMESTAMP,
  "COMPLETED_AT"            TIMESTAMP,
  "TOTAL_PROCESSED"         INTEGER        DEFAULT 0,
  "COVERAGE_PCT"            DECIMAL(5,2)   DEFAULT 0,
  "SEASONAL_COUNT"          INTEGER        DEFAULT 0,
  "NON_SEASONAL_COUNT"      INTEGER        DEFAULT 0,
  "INSUFFICIENT_DATA_COUNT" INTEGER        DEFAULT 0,
  "LOW_CONFIDENCE_COUNT"    INTEGER        DEFAULT 0,
  "ERROR_DETAIL"            NVARCHAR(500),
  "CREATED_AT"              TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
  "MODIFIED_AT"             TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("ID")
);

COMMENT ON TABLE  "ZSEASONAL_CLASS_RUN" IS 'Seasonal Article Detector — classification run headers';
COMMENT ON COLUMN "ZSEASONAL_CLASS_RUN"."STATUS" IS 'RUNNING | COMPLETED | FAILED';

-- ──────────────────────────────────────────────────────────────────────────────
-- 2. Classification results
--    One row per article/store combination per run.
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE "ZSEASONAL_CLASS_RESULT" (
  "ID"                       NVARCHAR(36)  NOT NULL,
  "RUN_ID"                   NVARCHAR(36)  NOT NULL,
  "ARTICLE_ID"               NVARCHAR(32),
  "STORE_ID"                 NVARCHAR(32),
  "CLASSIFICATION"           NVARCHAR(30),
  "CONFIDENCE_SCORE"         DECIMAL(5,2),
  "SEASON_START_WEEK"        INTEGER,
  "SEASON_END_WEEK"          INTEGER,
  "SEASONAL_STRENGTH_INDEX"  DECIMAL(6,4),
  "ALGORITHM_USED"           NVARCHAR(20),
  "DATA_RANGE_START"         NVARCHAR(10),
  "DATA_RANGE_END"           NVARCHAR(10),
  "WORKFLOW_STATUS"          NVARCHAR(30)  DEFAULT 'NOT_APPLICABLE',
  "NOTIFICATION_STATUS"      NVARCHAR(30)  DEFAULT 'NOT_APPLICABLE',
  "CREATED_AT"               TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("ID"),
  FOREIGN KEY ("RUN_ID") REFERENCES "ZSEASONAL_CLASS_RUN"("ID") ON DELETE CASCADE
);

COMMENT ON TABLE  "ZSEASONAL_CLASS_RESULT" IS 'Seasonal Article Detector — article/store classification results';
COMMENT ON COLUMN "ZSEASONAL_CLASS_RESULT"."CLASSIFICATION"      IS 'SEASONAL | NON_SEASONAL | LOW_CONFIDENCE_SEASONAL | INSUFFICIENT_DATA';
COMMENT ON COLUMN "ZSEASONAL_CLASS_RESULT"."WORKFLOW_STATUS"     IS 'NOT_APPLICABLE | PENDING_WORKFLOW | WORKFLOW_TRIGGERED | WORKFLOW_FAILED';
COMMENT ON COLUMN "ZSEASONAL_CLASS_RESULT"."NOTIFICATION_STATUS" IS 'NOT_APPLICABLE | PENDING_NOTIFICATION | NOTIFICATION_SENT | NOTIFICATION_FAILED';

-- ──────────────────────────────────────────────────────────────────────────────
-- 3. Indexes for common query patterns
-- ──────────────────────────────────────────────────────────────────────────────
CREATE INDEX "ZSEASONAL_CLASS_RESULT_RUN"     ON "ZSEASONAL_CLASS_RESULT" ("RUN_ID");
CREATE INDEX "ZSEASONAL_CLASS_RESULT_ARTICLE" ON "ZSEASONAL_CLASS_RESULT" ("ARTICLE_ID", "STORE_ID");
CREATE INDEX "ZSEASONAL_CLASS_RESULT_CLASS"   ON "ZSEASONAL_CLASS_RESULT" ("CLASSIFICATION", "CONFIDENCE_SCORE");

-- ──────────────────────────────────────────────────────────────────────────────
-- 4. Grant permissions to the technical user
--    Replace ZSEASONAL_USER with the actual HANA user from the BTP Destination.
-- ──────────────────────────────────────────────────────────────────────────────
-- GRANT SELECT, INSERT, UPDATE ON "ZSEASONAL_CLASS_RUN"    TO ZSEASONAL_USER;
-- GRANT SELECT, INSERT         ON "ZSEASONAL_CLASS_RESULT" TO ZSEASONAL_USER;
