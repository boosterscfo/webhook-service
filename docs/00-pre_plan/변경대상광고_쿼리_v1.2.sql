-- ================================================================
-- 변경대상광고 식별 쿼리 v1.2
-- ================================================================
-- Python에서 3개 쿼리를 순서대로 실행 → pandas merge
-- 서브쿼리 없음. 각 쿼리가 독립적으로 가볍게 동작.
-- ================================================================


-- Step 1: Active 광고 목록 (마스터 테이블만)
SELECT 
    fia.id          AS internal_ad_id,
    fia.ad_id       AS meta_ad_id,
    fia.name        AS ad_name,
    fia.product_name,
    fia.ad_type,
    fia.author,
    fia.start_time  AS ad_start_time,
    
    fis.id          AS internal_adset_id,
    fis.adset_id    AS meta_adset_id,
    fis.name        AS adset_name,
    fis.start_time  AS adset_start_time,
    
    fic.id          AS internal_campaign_id,
    fic.campaign_id AS meta_campaign_id,
    fic.name        AS campaign_name

FROM facebook_id_ads fia
INNER JOIN facebook_id_adsets fis ON fia.adset_id = fis.id
INNER JOIN facebook_id_campaigns fic ON fis.campaign_id = fic.id

WHERE fic.name LIKE '%이퀄베리%'
  AND fia.status = 'ACTIVE'
  AND fis.status = 'ACTIVE'
  AND fic.status = 'ACTIVE'

ORDER BY fia.name;


-- Step 2: 최근 30일 성과 (internal_ad_id 목록은 Python에서 IN절로 전달)
SELECT 
    facebook_id_ad_id   AS internal_ad_id,
    SUM(spend)                      AS spend_30d,
    SUM(impressions)                AS impr_30d,
    SUM(clicks)                     AS clicks_30d,
    SUM(fb_pixel_purchase)          AS purchases_30d,
    SUM(fb_pixel_purchase_values)   AS purchase_value_30d

FROM facebook_data_ads
WHERE date_start >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
  AND facebook_id_ad_id IN (%s)

GROUP BY facebook_id_ad_id
ORDER BY spend_30d DESC;


-- Step 3: 전체 기간 성과
SELECT 
    facebook_id_ad_id   AS internal_ad_id,
    SUM(spend)                      AS spend_total,
    SUM(impressions)                AS impr_total,
    SUM(fb_pixel_purchase)          AS purchases_total,
    SUM(fb_pixel_purchase_values)   AS purchase_value_total,
    MIN(date_start)                 AS first_data_date,
    MAX(date_start)                 AS last_data_date

FROM facebook_data_ads
WHERE facebook_id_ad_id IN (%s)

GROUP BY facebook_id_ad_id
ORDER BY spend_total DESC;


-- ================================================================
-- Python merge 예시
-- ================================================================
-- df_ads   = pd.read_sql(step1, conn)
-- ids = ','.join(df_ads['internal_ad_id'].astype(str))
-- df_30d   = pd.read_sql(step2 % ids, conn)
-- df_total = pd.read_sql(step3 % ids, conn)
--
-- result = (df_ads
--     .merge(df_30d,   on='internal_ad_id', how='left')
--     .merge(df_total, on='internal_ad_id', how='left')
--     .fillna(0)
--     .sort_values('spend_30d', ascending=False)
-- )
-- ================================================================
