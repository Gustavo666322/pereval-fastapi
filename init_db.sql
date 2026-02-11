CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(20),
    fam VARCHAR(50) NOT NULL,
    name VARCHAR(50) NOT NULL,
    otc VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mountain_passes (
    id SERIAL PRIMARY KEY,
    beauty_title VARCHAR(255),
    title VARCHAR(255) NOT NULL,
    other_titles VARCHAR(255),
    connect TEXT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    height INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'new' CHECK (status IN ('new', 'pending', 'accepted', 'rejected')),
    add_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_status ON mountain_passes(status);
CREATE INDEX idx_user_id ON mountain_passes(user_id);

CREATE TABLE IF NOT EXISTS difficulty_levels (
    id SERIAL PRIMARY KEY,
    pass_id INTEGER NOT NULL REFERENCES mountain_passes(id) ON DELETE CASCADE,
    season VARCHAR(10) NOT NULL CHECK (season IN ('summer', 'autumn', 'winter', 'spring')),
    level VARCHAR(10) CHECK (level IN ('1A', '1B', '2A', '2B', '3A', '3B')),
    UNIQUE(pass_id, season)
);

CREATE TABLE IF NOT EXISTS images (
    id SERIAL PRIMARY KEY,
    pass_id INTEGER NOT NULL REFERENCES mountain_passes(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    img_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pass_id ON images(pass_id);