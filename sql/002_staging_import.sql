-- Copyright 2026 Archdiocese of Seattle
-- Author: Kevin F Benz
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

CREATE TABLE IF NOT EXISTS staging_contacts (
    account_number VARCHAR(50) NULL,
    advertiser VARCHAR(255) NULL,
    contact_name VARCHAR(255) NULL,
    address1 VARCHAR(255) NULL,
    address2 VARCHAR(255) NULL,
    city VARCHAR(255) NULL,
    prospect_raw VARCHAR(50) NULL,
    state_code VARCHAR(50) NULL,
    postal_code VARCHAR(50) NULL,
    phone VARCHAR(100) NULL,
    fax VARCHAR(100) NULL,
    email VARCHAR(255) NULL,
    website VARCHAR(255) NULL,
    category VARCHAR(255) NULL,
    ad_ops VARCHAR(255) NULL,
    directory_years VARCHAR(255) NULL,
    contact_notes TEXT NULL,
    current_advertiser_raw VARCHAR(50) NULL,
    past_advertiser_raw VARCHAR(50) NULL,
    email_list_raw VARCHAR(50) NULL
);

CREATE TABLE IF NOT EXISTS staging_ads (
    account_number VARCHAR(50) NULL,
    commission_percent_raw VARCHAR(50) NULL,
    date_sold_raw VARCHAR(64) NULL,
    date_run_raw VARCHAR(64) NULL,
    description VARCHAR(255) NULL,
    authorized_by VARCHAR(100) NULL,
    sales_rep_raw VARCHAR(100) NULL,
    amount_raw VARCHAR(50) NULL,
    size_raw VARCHAR(100) NULL,
    section_raw VARCHAR(100) NULL,
    ad_page VARCHAR(100) NULL,
    run_code VARCHAR(255) NULL,
    bill_number VARCHAR(100) NULL,
    billed_raw VARCHAR(100) NULL,
    ad_notes TEXT NULL
);

TRUNCATE TABLE staging_contacts;
TRUNCATE TABLE staging_ads;

-- Replace both file paths before running.
LOAD DATA LOCAL INFILE 'REPLACE_WITH_CONTACTS_CSV_PATH'
INTO TABLE staging_contacts
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(account_number, advertiser, contact_name, address1, address2, city, prospect_raw, state_code, postal_code, phone, fax, email, website, category, ad_ops, directory_years, contact_notes, current_advertiser_raw, past_advertiser_raw, email_list_raw);

LOAD DATA LOCAL INFILE 'REPLACE_WITH_ADS_CSV_PATH'
INTO TABLE staging_ads
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ',' ENCLOSED BY '"' ESCAPED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(account_number, commission_percent_raw, date_sold_raw, date_run_raw, description, authorized_by, sales_rep_raw, amount_raw, size_raw, section_raw, ad_page, run_code, bill_number, billed_raw, ad_notes);

INSERT INTO accounts (
    account_number,
    advertiser,
    contact_name,
    address1,
    address2,
    city,
    state_code,
    postal_code,
    phone,
    fax,
    email,
    website,
    category,
    ad_ops,
    directory_years,
    contact_notes,
    is_prospect,
    is_current_advertiser,
    is_past_advertiser,
    is_email_list
)
SELECT
    LEFT(TRIM(account_number), 6) AS account_number,
    NULLIF(TRIM(advertiser), ''),
    NULLIF(TRIM(contact_name), ''),
    NULLIF(TRIM(address1), ''),
    NULLIF(TRIM(address2), ''),
    NULLIF(TRIM(city), ''),
    NULLIF(TRIM(state_code), ''),
    NULLIF(TRIM(postal_code), ''),
    NULLIF(TRIM(phone), ''),
    NULLIF(TRIM(fax), ''),
    NULLIF(TRIM(email), ''),
    NULLIF(TRIM(website), ''),
    NULLIF(TRIM(category), ''),
    NULLIF(TRIM(ad_ops), ''),
    NULLIF(TRIM(directory_years), ''),
    NULLIF(TRIM(contact_notes), ''),
    CASE WHEN UPPER(TRIM(COALESCE(prospect_raw, ''))) IN ('TRUE', 'YES', 'Y', '1', '-1') THEN TRUE ELSE FALSE END,
    CASE WHEN UPPER(TRIM(COALESCE(current_advertiser_raw, ''))) IN ('TRUE', 'YES', 'Y', '1', '-1') THEN TRUE ELSE FALSE END,
    CASE WHEN UPPER(TRIM(COALESCE(past_advertiser_raw, ''))) IN ('TRUE', 'YES', 'Y', '1', '-1') THEN TRUE ELSE FALSE END,
    CASE WHEN UPPER(TRIM(COALESCE(email_list_raw, ''))) IN ('TRUE', 'YES', 'Y', '1', '-1') THEN TRUE ELSE FALSE END
FROM staging_contacts
WHERE NULLIF(TRIM(account_number), '') IS NOT NULL
ON DUPLICATE KEY UPDATE
    advertiser = VALUES(advertiser),
    contact_name = VALUES(contact_name),
    address1 = VALUES(address1),
    address2 = VALUES(address2),
    city = VALUES(city),
    state_code = VALUES(state_code),
    postal_code = VALUES(postal_code),
    phone = VALUES(phone),
    fax = VALUES(fax),
    email = VALUES(email),
    website = VALUES(website),
    category = VALUES(category),
    ad_ops = VALUES(ad_ops),
    directory_years = VALUES(directory_years),
    contact_notes = VALUES(contact_notes),
    is_prospect = VALUES(is_prospect),
    is_current_advertiser = VALUES(is_current_advertiser),
    is_past_advertiser = VALUES(is_past_advertiser),
    is_email_list = VALUES(is_email_list);

INSERT INTO ad_placements (
    legacy_account_number,
    account_number,
    commission_percent,
    date_sold,
    date_run,
    description,
    authorized_by,
    sales_rep_raw,
    amount,
    size_raw,
    section_raw,
    ad_page,
    run_code,
    bill_number,
    billed_raw,
    ad_notes,
    source_row_hash
)
SELECT
    NULLIF(LEFT(TRIM(a.account_number), 6), '') AS legacy_account_number,
    CASE
        WHEN c.account_number IS NOT NULL THEN c.account_number
        ELSE NULL
    END AS account_number,
    CAST(NULLIF(TRIM(a.commission_percent_raw), '') AS DECIMAL(7,4)) AS commission_percent,
    CASE
        WHEN STR_TO_DATE(NULLIF(TRIM(a.date_sold_raw), ''), '%m/%d/%Y %r') IS NOT NULL
            THEN STR_TO_DATE(NULLIF(TRIM(a.date_sold_raw), ''), '%m/%d/%Y %r')
        WHEN STR_TO_DATE(NULLIF(TRIM(a.date_sold_raw), ''), '%m/%d/%Y') IS NOT NULL
            THEN STR_TO_DATE(NULLIF(TRIM(a.date_sold_raw), ''), '%m/%d/%Y')
        ELSE NULL
    END AS date_sold,
    CASE
        WHEN STR_TO_DATE(NULLIF(TRIM(a.date_run_raw), ''), '%m/%d/%Y %r') IS NOT NULL
            THEN STR_TO_DATE(NULLIF(TRIM(a.date_run_raw), ''), '%m/%d/%Y %r')
        WHEN STR_TO_DATE(NULLIF(TRIM(a.date_run_raw), ''), '%m/%d/%Y') IS NOT NULL
            THEN STR_TO_DATE(NULLIF(TRIM(a.date_run_raw), ''), '%m/%d/%Y')
        ELSE NULL
    END AS date_run,
    NULLIF(TRIM(a.description), ''),
    NULLIF(TRIM(a.authorized_by), ''),
    NULLIF(TRIM(a.sales_rep_raw), ''),
    CAST(NULLIF(TRIM(a.amount_raw), '') AS DECIMAL(12,2)) AS amount,
    NULLIF(TRIM(a.size_raw), ''),
    NULLIF(TRIM(a.section_raw), ''),
    NULLIF(TRIM(a.ad_page), ''),
    NULLIF(TRIM(a.run_code), ''),
    NULLIF(TRIM(a.bill_number), ''),
    NULLIF(TRIM(a.billed_raw), ''),
    NULLIF(TRIM(a.ad_notes), ''),
    SHA2(
        CONCAT_WS('|',
            COALESCE(TRIM(a.account_number), ''),
            COALESCE(TRIM(a.date_sold_raw), ''),
            COALESCE(TRIM(a.date_run_raw), ''),
            COALESCE(TRIM(a.description), ''),
            COALESCE(TRIM(a.amount_raw), ''),
            COALESCE(TRIM(a.run_code), ''),
            COALESCE(TRIM(a.bill_number), ''),
            COALESCE(TRIM(a.size_raw), '')
        ),
        256
    ) AS source_row_hash
FROM staging_ads a
LEFT JOIN accounts c
    ON LEFT(TRIM(a.account_number), 6) = c.account_number;
