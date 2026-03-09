"""V6: 키워드 검색 분석 테이블 추가."""

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS amz_keyword_search_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,
    product_count INT DEFAULT 0,
    snapshot_id VARCHAR(100) DEFAULT '',
    status ENUM('collecting', 'completed', 'failed') NOT NULL DEFAULT 'collecting',
    searched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_keyword_searched (keyword, searched_at DESC)
);

CREATE TABLE IF NOT EXISTS amz_keyword_products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,
    asin VARCHAR(20) NOT NULL,
    title VARCHAR(500) DEFAULT '',
    brand VARCHAR(200) DEFAULT '',
    manufacturer VARCHAR(200) DEFAULT '',
    price DECIMAL(10,2),
    initial_price DECIMAL(10,2),
    currency VARCHAR(10) DEFAULT 'USD',
    rating DECIMAL(3,2) DEFAULT 0,
    reviews_count INT DEFAULT 0,
    bsr INT,
    bsr_category VARCHAR(200) DEFAULT '',
    position INT DEFAULT 0,
    sponsored TINYINT(1) DEFAULT 0,
    badge VARCHAR(100) DEFAULT '',
    bought_past_month INT,
    coupon VARCHAR(200) DEFAULT '',
    customer_says TEXT,
    plus_content TINYINT(1) DEFAULT 0,
    number_of_sellers INT DEFAULT 1,
    variations_count INT DEFAULT 0,
    image_url VARCHAR(500) DEFAULT '',
    product_url VARCHAR(500) DEFAULT '',
    features TEXT,
    description TEXT,
    categories TEXT,
    searched_at DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_kp_keyword_searched (keyword, searched_at),
    INDEX idx_kp_asin (asin)
);
"""


def run_migration(environment: str = "CFO"):
    """마이그레이션 실행."""
    from lib.mysql_connector import MysqlConnector

    with MysqlConnector(environment) as conn:
        for statement in MIGRATION_SQL.strip().split(";"):
            statement = statement.strip()
            if statement:
                conn.cursor.execute(statement)
        conn.connection.commit()
