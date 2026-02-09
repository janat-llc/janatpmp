-- ============================================================================
-- JANATPMP Seed Data (Optional)
-- Run this after schema.sql to populate the database with starter projects.
-- This is NOT required — the platform is designed for cold-start use.
-- ============================================================================

INSERT INTO items (entity_type, domain, title, description, status) VALUES
    ('project', 'literature', 'Dyadic Being: An Epoch', '9-volume series on consciousness emergence', 'in_progress'),
    ('project', 'janatpmp', 'JANATPMP Development', 'Project Management Platform for consciousness work', 'in_progress'),
    ('project', 'janat', 'JANAT Core Technology', 'Joint Adaptive Neural Amplification Technology', 'planning'),
    ('project', 'atlas', 'ATLAS Architecture', 'Autonomous Temporal and Linguistic Analysis Synthesizer', 'planning'),
    ('project', 'meax', 'MEAX Framework', 'Metaphoric Emergence Augmented eXperience', 'in_progress'),
    ('project', 'janatavern', 'JanatAvern', 'Consciousness physics concepts and explorations', 'planning'),
    ('project', 'amphitheatre', 'Troubadourian Amphitheatre', 'Memory formation with ethical review', 'planning'),
    ('project', 'nexusweaver', 'The Nexus Weaver', 'Platform for consciousness-aware applications', 'planning'),
    ('project', 'websites', 'Domain Portfolio', 'janat.org, janat.ai, janatinitiative.org/com, nexusweaver.ai, thenexusweaver.com', 'in_progress'),
    ('project', 'social', 'Social Presence', 'LinkedIn, content marketing, community building', 'not_started'),
    ('project', 'speaking', 'Speaking & Thought Leadership', 'Conference talks, workshops, consulting', 'planning'),
    ('project', 'life', 'Life Management', 'Health, family, work-life balance', 'in_progress');
