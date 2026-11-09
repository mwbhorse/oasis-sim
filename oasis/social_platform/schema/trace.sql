-- This is the schema definition for the trace table
CREATE TABLE trace (
    user_id INTEGER,
    created_at DATETIME,
    action TEXT,
    info TEXT,
    FOREIGN KEY(user_id) REFERENCES user(user_id)
);
