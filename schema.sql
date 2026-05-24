# Supabase SQL: Run this in Supabase SQL Editor to create the core_hashtags table

CREATE TABLE IF NOT EXISTS core_hashtags (
    hashtag TEXT PRIMARY KEY,
    parent_hashtag TEXT,
    category TEXT NOT NULL CHECK (category IN ('object', 'style', 'color')),
    w1 BOOLEAN DEFAULT FALSE,
    "3d1" BOOLEAN DEFAULT FALSE,
    "3d2" BOOLEAN DEFAULT FALSE,
    "3d3" BOOLEAN DEFAULT FALSE,
    zipper BOOLEAN DEFAULT FALSE,
    charging BOOLEAN DEFAULT FALSE
);

-- Index for fast app-filtered queries
CREATE INDEX IF NOT EXISTS idx_w1 ON core_hashtags (w1) WHERE w1 = TRUE;
CREATE INDEX IF NOT EXISTS idx_3d1 ON core_hashtags ("3d1") WHERE "3d1" = TRUE;
CREATE INDEX IF NOT EXISTS idx_3d2 ON core_hashtags ("3d2") WHERE "3d2" = TRUE;
CREATE INDEX IF NOT EXISTS idx_3d3 ON core_hashtags ("3d3") WHERE "3d3" = TRUE;
CREATE INDEX IF NOT EXISTS idx_zipper ON core_hashtags (zipper) WHERE zipper = TRUE;
CREATE INDEX IF NOT EXISTS idx_charging ON core_hashtags (charging) WHERE charging = TRUE;

-- Index for recursive pruning queries
CREATE INDEX IF NOT EXISTS idx_parent ON core_hashtags (parent_hashtag);
CREATE INDEX IF NOT EXISTS idx_category ON core_hashtags (category);
