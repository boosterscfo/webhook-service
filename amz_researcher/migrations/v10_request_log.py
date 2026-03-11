"""V10: 리포트 요청 로그 테이블 추가."""

MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS amz_report_request_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL DEFAULT '',
    channel_id VARCHAR(50) NOT NULL DEFAULT '',
    request_type ENUM('category', 'keyword', 'report_only') NOT NULL,
    query_value VARCHAR(255) NOT NULL COMMENT 'category name or keyword',
    product_count INT DEFAULT 0,
    report_id VARCHAR(64) DEFAULT '' COMMENT 'HTML report UUID',
    duration_sec DECIMAL(6,1) DEFAULT NULL,
    status ENUM('started', 'completed', 'failed') NOT NULL DEFAULT 'started',
    error_message VARCHAR(500) DEFAULT '',
    requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME DEFAULT NULL,
    INDEX idx_user (user_id, requested_at DESC),
    INDEX idx_query (query_value, requested_at DESC)
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
    print("V10 migration completed: amz_report_request_log")


if __name__ == "__main__":
    run_migration()
