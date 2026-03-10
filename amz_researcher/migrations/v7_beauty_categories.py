"""V7: Beauty & Personal Care 카테고리 트리 시딩.

browsenodes.com에서 수집한 Amazon Best Sellers 카테고리 구조.
기존 is_active=TRUE 카테고리는 유지하고, 신규는 is_active=FALSE로 삽입.
"""
import logging

from app.config import settings
from lib.mysql_connector import MysqlConnector

logger = logging.getLogger(__name__)

# (node_id, name, parent_node_id, depth)
# depth: 0=root, 1=대분류, 2=중분류, 3=소분류, 4=세분류
BEAUTY_CATEGORIES = [
    # ── Root ──
    ("3760911", "Beauty & Personal Care", None, 0),

    # ── 대분류 (depth=1) ──
    ("11060451", "Skin Care", "3760911", 1),
    ("11057241", "Hair Care", "3760911", 1),
    ("11058281", "Makeup", "3760911", 1),
    ("11056591", "Fragrance", "3760911", 1),
    ("17242866011", "Foot, Hand & Nail Care", "3760911", 1),
    ("11062741", "Tools & Accessories", "3760911", 1),
    ("3778591", "Shave & Hair Removal", "3760911", 1),
    ("3777891", "Personal Care", "3760911", 1),
    ("10079992011", "Oral Care", "3760911", 1),

    # ── Skin Care (depth=2) ──
    ("11060711", "Face", "11060451", 2),
    ("11060521", "Body", "11060451", 2),
    ("11061941", "Eyes", "11060451", 2),
    ("3761351", "Lip Care", "11060451", 2),
    ("11062371", "Maternity", "11060451", 2),
    ("11062581", "Sets & Kits", "11060451", 2),
    ("11062591", "Sunscreens & Tanning Products", "11060451", 2),

    # ── Skin Care > Face (depth=3) ──
    ("11060901", "Facial Cleansers", "11060711", 3),
    ("11061301", "Creams & Moisturizers", "11060711", 3),
    ("11061091", "Polishes & Scrubs", "11060711", 3),
    ("11061931", "Facial Toners & Astringents", "11060711", 3),
    ("11062031", "Treatments & Masks", "11060711", 3),
    ("7792636011", "Face Sets & Kits", "11060711", 3),

    # ── Skin Care > Face > Cleansers (depth=4) ──
    ("7730189011", "Cleansing Bars", "11060901", 4),
    ("11060941", "Cleansing Cloths & Towelettes", "11060901", 4),
    ("11061001", "Cleansing Gels", "11060901", 4),
    ("7730193011", "Cleansing Washes", "11060901", 4),

    # ── Skin Care > Face > Creams & Moisturizers (depth=4) ──
    ("15239989011", "Face Mists", "11061301", 4),
    ("16479981011", "Face Moisturizers", "11061301", 4),
    ("7792527011", "Face Oil", "11061301", 4),
    ("7792277011", "Neck & Décolleté", "11061301", 4),
    ("7792275011", "Night Creams", "11061301", 4),
    ("7792276011", "Tinted Moisturizers", "11061301", 4),

    # ── Skin Care > Face > Treatments & Masks (depth=4) ──
    ("7792926011", "Acids & Peels", "11062031", 4),
    ("11061121", "Facial Masks", "11062031", 4),
    ("7792934011", "Microdermabrasion", "11062031", 4),
    ("7792936011", "Pore Cleansing Strips", "11062031", 4),
    ("7792528011", "Facial Serums", "11062031", 4),

    # ── Skin Care > Body (depth=3) ──
    ("11056281", "Body Cleansers", "11060521", 3),
    ("11060661", "Body Moisturizers", "11060521", 3),
    ("11056421", "Scrubs & Body Treatments", "11060521", 3),
    ("11056581", "Body Sets & Kits", "11060521", 3),

    # ── Skin Care > Eyes (depth=3) ──
    ("7730090011", "Eye Creams", "11061941", 3),
    ("7730092011", "Eye Gels", "11061941", 3),
    ("11061971", "Eye Masks", "11061941", 3),
    ("3422321", "Eye Pillows", "11061941", 3),
    ("7730095011", "Eye Rollers & Pens", "11061941", 3),
    ("7730098011", "Eye Serums", "11061941", 3),

    # ── Skin Care > Lip Care (depth=3) ──
    ("979546011", "Lip Balms & Moisturizers", "3761351", 3),
    ("18065339011", "Lip Butters", "3761351", 3),
    ("979548011", "Lip Scrubs", "3761351", 3),

    # ── Skin Care > Sunscreens & Tanning (depth=3) ──
    ("11062601", "After Sun", "11062591", 3),
    ("7792568011", "Facial Self Tanners", "11062591", 3),
    ("11062641", "Self-Tanners & Bronzers", "11062591", 3),
    ("11062651", "Sunscreens", "11062591", 3),
    ("11062731", "Tanning Oils & Lotions", "11062591", 3),

    # ── Hair Care (depth=2) ──
    ("17911764011", "Shampoo & Conditioner", "11057241", 2),
    ("13105931", "Extensions, Wigs & Accessories", "11057241", 2),
    ("11057431", "Hair & Scalp Treatments", "11057241", 2),
    ("11057971", "Hair Accessories", "11057241", 2),
    ("11057451", "Hair Coloring Products", "11057241", 2),
    ("10676449011", "Hair Cutting Tools", "11057241", 2),
    ("10898755011", "Hair Loss Products", "11057241", 2),
    ("10666437011", "Hair Masks", "11057241", 2),
    ("16236250011", "Hair Perms, Relaxers & Texturizers", "11057241", 2),
    ("10666439011", "Hair Treatment Oils", "11057241", 2),
    ("11057841", "Styling Products", "11057241", 2),
    ("11058091", "Styling Tools & Appliances", "11057241", 2),

    # ── Hair Care > Shampoo & Conditioner (depth=3) ──
    ("11057651", "Shampoos", "17911764011", 3),
    ("11057251", "Conditioners", "17911764011", 3),
    ("17911765011", "2-in-1 Shampoo & Conditioner", "17911764011", 3),
    ("17911766011", "3-in-1 Shampoo, Conditioner & Body Wash", "17911764011", 3),
    ("17911767011", "Deep Conditioners", "17911764011", 3),
    ("10656664011", "Dry Shampoos", "17911764011", 3),
    ("11057441", "Shampoo & Conditioner Sets", "17911764011", 3),

    # ── Hair Care > Styling Products (depth=3) ──
    ("10664362011", "Detanglers", "11057841", 3),
    ("11057871", "Hair Gels", "11057841", 3),
    ("11057891", "Hair Sprays", "11057841", 3),
    ("11057901", "Mousses & Foams", "11057841", 3),
    ("10664802011", "Putties & Clays", "11057841", 3),
    ("10666084011", "Styling Treatments", "11057841", 3),

    # ── Hair Care > Styling Tools & Appliances (depth=3) ──
    ("11058121", "Hair Brushes", "11058091", 3),
    ("11058131", "Hair Combs", "11058091", 3),
    ("16508037011", "Hair Dryers & Accessories", "11058091", 3),
    ("3784371", "Hair Rollers", "11058091", 3),
    ("11058221", "Hot-Air Brushes", "11058091", 3),
    ("17168139011", "Irons", "11058091", 3),

    # ── Hair Care > Hair Coloring Products (depth=3) ──
    ("10728531", "Hair Color", "11057451", 3),
    ("10676298011", "Color Additives & Fillers", "11057451", 3),
    ("3781671", "Color Correctors", "11057451", 3),
    ("10676302011", "Color Glazes", "11057451", 3),
    ("3784201", "Color Removers", "11057451", 3),
    ("3784151", "Coloring & Highlighting Tools", "11057451", 3),
    ("10676347011", "Developers", "11057451", 3),
    ("10676355011", "Hair Chalk", "11057451", 3),
    ("10676359011", "Hair Mascaras & Root Touch Ups", "11057451", 3),
    ("3781641", "Hennas", "11057451", 3),

    # ── Hair Care > Hair Loss Products (depth=3) ──
    ("16262041011", "Hair Regrowth Shampoos", "10898755011", 3),
    ("16262042011", "Hair Regrowth Conditioners", "10898755011", 3),
    ("16262043011", "Hair Building Fibers", "10898755011", 3),
    ("16262044011", "Hair Regrowth Tonics", "10898755011", 3),
    ("11057581", "Hair Regrowth Treatments", "10898755011", 3),

    # ── Makeup (depth=2) ──
    ("11058291", "Body Makeup", "11058281", 2),
    ("11058331", "Eyes", "11058281", 2),
    ("11058691", "Face", "11058281", 2),
    ("11059031", "Lips", "11058281", 2),
    ("2265896011", "Makeup Palettes", "11058281", 2),
    ("11059231", "Makeup Remover", "11058281", 2),
    ("11059301", "Makeup Sets", "11058281", 2),

    # ── Makeup > Eyes (depth=3) ──
    ("16228107011", "Eye Concealer", "11058331", 3),
    ("11058451", "Eyebrow Color", "11058331", 3),
    ("11058521", "Eyeliner", "11058331", 3),
    ("11058361", "Eyeshadow", "11058331", 3),
    ("16228108011", "Eyeshadow Bases & Primers", "11058331", 3),
    ("10312668011", "Lash Enhancers & Primers", "11058331", 3),
    ("11058381", "Liner & Shadow Combinations", "11058331", 3),
    ("11058611", "Mascara", "11058331", 3),

    # ── Makeup > Face (depth=3) ──
    ("11058701", "Blotting Paper", "11058691", 3),
    ("11058711", "Blush", "11058691", 3),
    ("11058781", "Bronzers & Highlighters", "11058691", 3),
    ("11058791", "Concealers & Neutralizers", "11058691", 3),
    ("11058871", "Foundation", "11058691", 3),
    ("388109011", "Foundation Primers", "11058691", 3),
    ("11058971", "Powder", "11058691", 3),

    # ── Makeup > Lips (depth=3) ──
    ("11059041", "Lip Glosses", "11059031", 3),
    ("11059101", "Lip Liners", "11059031", 3),
    ("14104641", "Lip Plumpers", "11059031", 3),
    ("11059051", "Lip Stains", "11059031", 3),
    ("11059111", "Lipstick", "11059031", 3),
    ("11059221", "Lipstick Primers", "11059031", 3),

    # ── Fragrance (depth=2) ──
    ("11056711", "Children's Fragrance", "11056591", 2),
    ("10292709011", "Dusting Powders", "11056591", 2),
    ("11056761", "Men's Fragrance", "11056591", 2),
    ("11056891", "Fragrance Sets", "11056591", 2),
    ("11056931", "Women's Fragrance", "11056591", 2),

    # ── Hair Care > Hair Styling Serums (기존 시드 — depth=4 from Styling Products) ──
    ("382803011", "Hair Styling Serums", "11057841", 3),
]

BASE_URL = "https://www.amazon.com/Best-Sellers/zgbs/beauty"


def run_migration(environment: str = "CFO"):
    """Beauty 카테고리 트리 시딩. 기존 active 카테고리는 유지."""
    upsert_sql = """
        INSERT INTO amz_categories (node_id, name, parent_node_id, url, depth, is_active)
        VALUES (%s, %s, %s, %s, %s, FALSE)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            parent_node_id = VALUES(parent_node_id),
            depth = VALUES(depth)
    """
    # is_active는 ON DUPLICATE KEY에서 업데이트하지 않음 → 기존 active 유지

    with MysqlConnector(environment) as conn:
        count = 0
        for node_id, name, parent_node_id, depth in BEAUTY_CATEGORIES:
            url = f"{BASE_URL}/{node_id}"
            conn.cursor.execute(upsert_sql, (node_id, name, parent_node_id, url, depth))
            count += 1
        conn.connection.commit()
        logger.info("Beauty categories seeded: %d categories", count)
    print(f"✅ {count} categories seeded (is_active=FALSE for new, existing active preserved)")


if __name__ == "__main__":
    run_migration()
