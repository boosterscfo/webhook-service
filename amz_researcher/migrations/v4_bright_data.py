"""V4 마이그레이션: Bright Data 전환을 위한 테이블 생성 + 카테고리 시딩.

Usage:
    python -m amz_researcher.migrations.v4_bright_data
"""
import logging
import pymysql

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


TABLES = {
    "amz_categories": """
        CREATE TABLE IF NOT EXISTS amz_categories (
            id INT AUTO_INCREMENT PRIMARY KEY,
            node_id VARCHAR(20) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            parent_node_id VARCHAR(20),
            url VARCHAR(500) NOT NULL,
            keywords VARCHAR(500) DEFAULT '',
            depth INT DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """,
    "amz_products": """
        CREATE TABLE IF NOT EXISTS amz_products (
            asin VARCHAR(20) PRIMARY KEY,
            title VARCHAR(500),
            brand VARCHAR(200),
            description TEXT,
            initial_price DECIMAL(10,2),
            final_price DECIMAL(10,2),
            currency VARCHAR(10) DEFAULT 'USD',
            rating DECIMAL(3,2),
            reviews_count INT,
            bs_rank INT,
            bs_category VARCHAR(200),
            root_bs_rank INT,
            root_bs_category VARCHAR(200),
            subcategory_ranks JSON,
            ingredients TEXT,
            features JSON,
            product_details JSON,
            manufacturer VARCHAR(200),
            department VARCHAR(200),
            image_url VARCHAR(1000),
            url VARCHAR(1000),
            badge VARCHAR(100),
            bought_past_month INT,
            is_available BOOLEAN DEFAULT TRUE,
            country_of_origin VARCHAR(100),
            item_weight VARCHAR(100),
            categories JSON,
            customer_says TEXT,
            unit_price VARCHAR(100),
            sns_price DECIMAL(10,2),
            variations_count INT DEFAULT 0,
            number_of_sellers INT DEFAULT 1,
            coupon VARCHAR(200),
            plus_content BOOLEAN DEFAULT FALSE,
            collected_at DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """,
    "amz_products_history": """
        CREATE TABLE IF NOT EXISTS amz_products_history (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            asin VARCHAR(20) NOT NULL,
            snapshot_date DATE NOT NULL,
            bs_rank INT,
            bs_category VARCHAR(200),
            final_price DECIMAL(10,2),
            rating DECIMAL(3,2),
            reviews_count INT,
            bought_past_month INT,
            badge VARCHAR(100),
            root_bs_rank INT,
            number_of_sellers INT,
            coupon VARCHAR(200),
            INDEX idx_asin_date (asin, snapshot_date),
            UNIQUE KEY uk_asin_date (asin, snapshot_date)
        )
    """,
    "amz_product_categories": """
        CREATE TABLE IF NOT EXISTS amz_product_categories (
            asin VARCHAR(20) NOT NULL,
            category_node_id VARCHAR(20) NOT NULL,
            collected_at DATE NOT NULL,
            PRIMARY KEY (asin, category_node_id),
            INDEX idx_category (category_node_id)
        )
    """,
}

SEED_CATEGORIES = [
    ("11058281", "Hair Growth Products", "11057241", "https://www.amazon.com/Best-Sellers/zgbs/beauty/11058281", "hair growth, 탈모, 발모, 육모", 3),
    ("3591081", "Hair Loss Shampoos", "11057651", "https://www.amazon.com/Best-Sellers/zgbs/beauty/3591081", "hair loss shampoo, 탈모샴푸", 3),
    ("11060451", "Skin Care", "3760911", "https://www.amazon.com/Best-Sellers/zgbs/beauty/11060451", "skin care, 스킨케어, 기초화장품", 2),
    ("11060901", "Facial Cleansing", "11060451", "https://www.amazon.com/Best-Sellers/zgbs/beauty/11060901", "facial cleansing, 클렌징, 세안", 3),
    ("3764441", "Vitamins & Supplements", "3760901", "https://www.amazon.com/Best-Sellers/zgbs/hpc/3764441", "vitamins, supplements, 비타민, 영양제", 2),
]


def run():
    conn = pymysql.connect(
        host=settings.CFO_HOST,
        port=settings.CFO_PORT,
        user=settings.CFO_USER,
        password=settings.CFO_PASSWORD,
        database=settings.CFO_DATABASE,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            # 테이블 생성
            for name, ddl in TABLES.items():
                cur.execute(ddl)
                logger.info("Table %s: OK", name)

            # 카테고리 시딩
            for node_id, name, parent, url, keywords, depth in SEED_CATEGORIES:
                cur.execute(
                    """INSERT INTO amz_categories (node_id, name, parent_node_id, url, keywords, depth, is_active)
                       VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                       ON DUPLICATE KEY UPDATE name=VALUES(name), url=VALUES(url), keywords=VALUES(keywords)""",
                    (node_id, name, parent, url, keywords, depth),
                )
            logger.info("Seeded %d categories", len(SEED_CATEGORIES))

            conn.commit()
            logger.info("Migration complete")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
