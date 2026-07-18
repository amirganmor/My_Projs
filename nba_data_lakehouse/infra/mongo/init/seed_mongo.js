// MongoDB init script -- creates collections with indexes
// Actual document seeding happens via the seed DAG for deterministic control

db = db.getSiblingDB('nba_scouting');

db.createCollection('player_profiles');
db.createCollection('scouting_reports');

db.player_profiles.createIndex({ "player_name": 1 }, { unique: false });
db.player_profiles.createIndex({ "player_name": 1, "season": 1 }, { unique: true });
db.scouting_reports.createIndex({ "player_name": 1 }, { unique: false });
db.scouting_reports.createIndex({ "player_name": 1, "season": 1 }, { unique: true });

print("MongoDB collections and indexes created for nba_scouting database.");
