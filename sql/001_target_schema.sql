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

CREATE TABLE IF NOT EXISTS accounts (
    account_number VARCHAR(6) NOT NULL,
    advertiser VARCHAR(255) NULL,
    contact_name VARCHAR(255) NULL,
    address1 VARCHAR(255) NULL,
    address2 VARCHAR(50) NULL,
    city VARCHAR(50) NULL,
    state_code VARCHAR(8) NULL,
    postal_code VARCHAR(12) NULL,
    phone VARCHAR(50) NULL,
    fax VARCHAR(50) NULL,
    email VARCHAR(255) NULL,
    website VARCHAR(255) NULL,
    category VARCHAR(255) NULL,
    ad_ops VARCHAR(255) NULL,
    directory_years VARCHAR(255) NULL,
    contact_notes TEXT NULL,
    is_prospect BOOLEAN NOT NULL DEFAULT FALSE,
    is_current_advertiser BOOLEAN NOT NULL DEFAULT FALSE,
    is_past_advertiser BOOLEAN NOT NULL DEFAULT FALSE,
    is_email_list BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (account_number)
);

CREATE TABLE IF NOT EXISTS ad_placements (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    legacy_account_number VARCHAR(6) NULL,
    account_number VARCHAR(6) NULL,
    commission_percent DECIMAL(7,4) NULL,
    date_sold DATE NULL,
    date_run DATE NULL,
    description VARCHAR(255) NULL,
    authorized_by VARCHAR(50) NULL,
    sales_rep_raw VARCHAR(50) NULL,
    amount DECIMAL(12,2) NULL,
    size_raw VARCHAR(50) NULL,
    section_raw VARCHAR(50) NULL,
    ad_page VARCHAR(50) NULL,
    run_code VARCHAR(255) NULL,
    bill_number VARCHAR(50) NULL,
    billed_raw VARCHAR(50) NULL,
    ad_notes TEXT NULL,
    source_row_hash CHAR(64) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_ad_placements_date_run (date_run),
    KEY idx_ad_placements_date_sold (date_sold),
    KEY idx_ad_placements_legacy_account (legacy_account_number),
    KEY idx_ad_placements_account (account_number),
    CONSTRAINT fk_ad_placements_account
        FOREIGN KEY (account_number) REFERENCES accounts (account_number)
        ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sales_reps (
    id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (id),
    UNIQUE KEY uq_sales_reps_code (code)
);

CREATE TABLE IF NOT EXISTS ad_sizes (
    id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL,
    normalized_label VARCHAR(100) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ad_sizes_code (code)
);

CREATE TABLE IF NOT EXISTS ad_sections (
    id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL,
    normalized_label VARCHAR(100) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ad_sections_code (code)
);

CREATE TABLE IF NOT EXISTS billing_statuses (
    id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(50) NOT NULL,
    normalized_label VARCHAR(100) NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (id),
    UNIQUE KEY uq_billing_statuses_code (code)
);

CREATE TABLE IF NOT EXISTS ad_normalization_map (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    domain ENUM('size', 'section', 'sales', 'billed') NOT NULL,
    raw_value VARCHAR(255) NOT NULL,
    normalized_value VARCHAR(255) NOT NULL,
    notes VARCHAR(255) NULL,
    approved_by VARCHAR(100) NULL,
    approved_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_ad_normalization_map_domain_raw (domain, raw_value)
);
