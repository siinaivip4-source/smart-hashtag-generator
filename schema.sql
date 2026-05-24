-- Run this in Supabase SQL Editor to create the core_hashtags table

CREATE TABLE IF NOT EXISTS core_hashtags (
    hashtag TEXT PRIMARY KEY,
    parent_hashtag TEXT,
    category TEXT NOT NULL,
    w1 BOOLEAN DEFAULT FALSE,
    d3d1 BOOLEAN DEFAULT FALSE,
    d3d2 BOOLEAN DEFAULT FALSE,
    d3d3 BOOLEAN DEFAULT FALSE,
    zipper BOOLEAN DEFAULT FALSE,
    charging BOOLEAN DEFAULT FALSE,
    CONSTRAINT valid_category CHECK (category IN ('object', 'style', 'color'))
);

-- Indexes for fast app-filtered queries
CREATE INDEX IF NOT EXISTS idx_w1 ON core_hashtags (w1) WHERE w1 = TRUE;
CREATE INDEX IF NOT EXISTS idx_d3d1 ON core_hashtags (d3d1) WHERE d3d1 = TRUE;
CREATE INDEX IF NOT EXISTS idx_d3d2 ON core_hashtags (d3d2) WHERE d3d2 = TRUE;
CREATE INDEX IF NOT EXISTS idx_d3d3 ON core_hashtags (d3d3) WHERE d3d3 = TRUE;
CREATE INDEX IF NOT EXISTS idx_zipper ON core_hashtags (zipper) WHERE zipper = TRUE;
CREATE INDEX IF NOT EXISTS idx_charging ON core_hashtags (charging) WHERE charging = TRUE;

-- Indexes for recursive pruning queries
CREATE INDEX IF NOT EXISTS idx_parent ON core_hashtags (parent_hashtag);
CREATE INDEX IF NOT EXISTS idx_category ON core_hashtags (category);
