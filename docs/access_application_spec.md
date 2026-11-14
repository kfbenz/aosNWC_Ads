# Display Advertising Database - Functional Specification (from Access exports)

Source: `access_objects/` SaveAsText exports (11 forms, 15 reports, 1 module, 80 saved queries).
Tables referenced below: `C` = `tbl_ProgressContacts_01` (accounts), `A` = `tbl_ProgressAds_01` (ad placements).
Items marked **(inferred)** are not stated directly in the exports.

Important gaps in the export set:
- **Macros were not exported.** `mac_Excel_Amount`, `mac_Excel_CommEarned` and `mac_Excel_SearchResults` are called from VBA, but their contents are unknown. Their behavior below is inferred from query names and dependencies.
- Two Access-only working tables are used by the search feature and were **not** migrated: `tbl_ProgressSearches_01` (one row per search, holding the criteria) and `tbl_ProgressSearchResults_01` (a make-table output). A third, `tbl_ProgressContactsWAds_XDateRun_02`, is a make-table output used by the Excel exports. The web app does not need to keep any of them.
- The startup form setting is not part of the export. The Dashboard is assumed to be the startup form **(inferred)**: it has no Close button and quits Access from its "Goodbye" button.

---

## 1. Reachable vs. dead objects

The table below traces everything reachable from `Dashboard` through OnClick VBA (`DoCmd.OpenForm`, `DoCmd.OpenReport`, `DoCmd.RunMacro`), subform `SourceObject`, `RecordSource`, `RowSource`, and query-to-query dependencies.

### Forms

| Object | Status | Reached from / evidence |
|---|---|---|
| `Dashboard` | ACTIVE (entry point) | Startup form (inferred) |
| `frm_ProgressContacts_Info_01` | ACTIVE | Dashboard `cmdFrmContactsInfo`; Search `cmdExitSearch`; Results `cmdInfo` |
| `frm_ProgressAds_02_subfrm` | ACTIVE | Subform on Contacts_Info and SearchResults_01 |
| `frm_ProgressSearch_01` | ACTIVE | Contacts_Info `cmdOpenSearch`; Results `cmdSearchAgain`; read by `mod_Progress_Search_01` |
| `frm_ProgressSearchResults_01` | ACTIVE | Search_01 `cmdSearch` |
| `Dashboardold` | DEAD | Referenced by no object. It is an older menu with separate 2005/2006/2007 label buttons. |
| `frm_ProgressSearch_old`, `frm_ProgressSearch_old2`, `frm_ProgressSearch_1` | DEAD | Referenced by no object |
| `frm_ProgressSearchResults_old` | DEAD | Referenced by no object |
| `tbl_ProgressContacts_01` (form) | DEAD | Auto-generated form, referenced by no object. It uses older field names `Current Advertiser` and `Old Advertisers`. |

### Reports

| Object | Status | Evidence |
|---|---|---|
| `rpt_ProgressContactsWAds_Comm_01` | ACTIVE | Dashboard `cmdRptComm` |
| `rpt_ProgressContactsWAds_Pub_01` | ACTIVE | Dashboard `cmdRptPub` |
| `rpt_LabelsDirectoryXParameter_01` | ACTIVE | Dashboard `cmd_openMailingLabels` |
| `rpt_LabelsDirectory2005_01`, `_2006_01`, `_2007_01` | DEAD | Dashboard VBA still contains `cmdRptLabels2005/2006/2007_Click` handlers, but no such buttons exist on the Dashboard (they were on `Dashboardold`). The handlers are orphaned. |
| `Labels_2007_name_and_contact_only`, `lables_Directory2006_name_and_contact_only`, `Labels_qry_Directory2007_01/_02/_03`, `Labels_qry_Directory2008_01`, `Labels_Christmas_Advertisers` | DEAD | Referenced by no object. They were probably opened by hand from the navigation pane (inferred). |
| `Dashboard` (report) | DEAD | Print image of the form: date, time and page number only |
| `frm_ProgressSearch_1` (report) | DEAD | Print of the search-criteria table |

### Module / macros

| Object | Status | Notes |
|---|---|---|
| `mod_Progress_Search_01` | ACTIVE | Called by Search `cmdSearch` |
| `mac_Excel_Amount` | ACTIVE (not exported) | Dashboard `cmdMacAmount` |
| `mac_Excel_CommEarned` | ACTIVE (not exported) | Dashboard `cmdMacCommEarned` |
| `mac_Excel_SearchResults` | ACTIVE (not exported) | Results `cmdExportXL` |

### Queries (80 total)

The following 14 queries are reachable from active objects:

- `qry_ProgressContactsWAds_01`: the base join. It is used by the search, the Comm, Pub and XDateRun queries, and the Comm report chain.
- `qry_ProgressContactsWAds_Comm_01`, `_Comm_02`, `_Comm_03`: the Commission report.
- `qry_ProgressContactsWAds_Pub_01`: the Publication report.
- `qry_DirectoryYearXParameter_01`: the mailing labels.
- `qry_ProgressSearchResults_01` and `_02`: the search results form.
- `qry_ProgressContactsWAds_XDateRun_01`, `_XDateRun_02_MkTbl`, `_XDateRun_03`, `Amount`, `CommEarned`: used by the Excel export macros **(inferred)**. `Amount` and `CommEarned` read `_XDateRun_03`, which reads the table made by `_XDateRun_02_MkTbl`. The macro names match these queries.
- `SearchResultsAddresses`: used by `mac_Excel_SearchResults` **(inferred)**. It is the only query that matches the button caption "Export Addresses to Excel", and no other object references it.

The other 66 queries are ad hoc or historical. See Section 6.

---

## 2. Menu (Dashboard)

Form caption: "Dashboard". Header label: **"Display Advertising Database"**. The order below is top to bottom by the `Top` position. Each helper label sits directly beneath its button.

| # | Control | Button caption | Helper text shown | Action |
|---|---|---|---|---|
| 1 | `cmdFrmContactsInfo` | View and Edit Advertisers and Ads | (none) | `DoCmd.OpenForm "frm_ProgressContacts_Info_01"` |
| 2 | `cmdRptComm` | Commission Report by Sell Date | Asks for starting and ending dates | `DoCmd.OpenReport "rpt_ProgressContactsWAds_Comm_01", acPreview` |
| 3 | `cmdRptPub` | Publication Report by Run Date | Asks for date | `DoCmd.OpenReport "rpt_ProgressContactsWAds_Pub_01", acPreview` |
| 4 | `cmd_openMailingLabels` | Mailing Labels by Directory Year | Asks for time period from "Directory Years" | `DoCmd.OpenReport "rpt_LabelsDirectoryXParameter_01", acPreview` |
| 5 | `cmdMacAmount` | Export Amounts by Run Date | Asks for starting and ending dates | `DoCmd.RunMacro "mac_Excel_Amount"` |
| 6 | `cmdMacCommEarned` | Export Commission Earned by Run Date | Asks for starting and ending dates | `DoCmd.RunMacro "mac_Excel_CommEarned"` |
| footer | `cmdGoodbye` | Goodbye | | `DoCmd.Quit` (not needed on the web; becomes Logout) |

The form has the Close button and Control Box disabled. All handlers use the standard `On Error -> MsgBox Err.Description` wizard pattern.

Proposed web menu: Advertisers (list/edit) | Search | Commission Report | Publication Report | Mailing Labels | Export: Amounts by Run Date | Export: Commission Earned by Run Date.

---

## 3. Active forms

### 3.1 `frm_ProgressContacts_Info_01` - "View and Edit Advertisers and Ads"

- **Purpose:** This is the main record browser and editor for one account at a time (single-form view). It shows the account's ad history in an editable datasheet subform.
- **RecordSource:** `tbl_ProgressContacts_01`. **OrderBy:** `AccountNumber DESC` (OrderByOn), so the newest or highest account appears first. All edits, additions and deletions are allowed (defaults). Navigation is by the standard Access record navigator, so the web app needs list, next/previous and new-record functions.
- **Header label:** "View and Edit Advertisers and Ads".
- **Defaults / validation / input masks:** none are defined on the form. No `DefaultValue`, `ValidationRule` or `InputMask` exists on any control. Table-level rules are not visible in the export.

Layout, left column, top to bottom (all are bound textboxes):

| Label | Control name | Bound field |
|---|---|---|
| Account | `Number` | AccountNumber |
| Advertiser | `Name` | Advertiser |
| Contact | `Contact` | Contact |
| Address | `Address` | Address |
| Address 2 | `Address 2` | Address2 |
| City | `City` | City |
| State | `State` | State |
| Zip | `Zip` | Zip |
| Phone | `Phone` | Phone |
| Fax | `Fax` | Fax |
| E-mail | `E-mail` | Email |
| Web site | `Web site` | Website |
| Directory Years | `DirectoryYears` | DirectoryYears (free text, for example a list of years) |

Section label "Client Information" sits above the right column. The right column, top to bottom:

| Label | Control name | Type | Bound field |
|---|---|---|---|
| Category | `Category` | textbox (free text, **not** a combo) | Category |
| Special Advertising Opportunities | `AdOps` | multi-line textbox | AdOps |
| Notes | `Notes` | multi-line textbox | ConNotes |
| Current Advertiser | `Current Advertiser_Label` | checkbox | CurrentAdvertiser |
| Old Avertiser (sic) | `Not Current` | checkbox | PastAdvertiser |
| E-mail List | `Email` | checkbox | EmailList |
| Prospect | `Prospect` | checkbox | Prospect |
| E-mail List | `Check108` | checkbox | EmailList (duplicate). It is positioned at Top=4860, inside the subform area (Top=4680), so it is probably hidden behind the subform **(inferred)**. Omit it. |

- **Subform** (`frm_ProgressAds_02_subfrm`), label "Advertising History": SourceObject `Form.frm_ProgressAds_02_subfrm`, **LinkMasterFields = AccountNumber, LinkChildFields = AccountNumber**. It spans the full width at the bottom.
- **Footer buttons:**
  - `cmdExit` "Exit": `DoCmd.Close`, which returns to the Dashboard.
  - `cmdOpenSearch` "Search": closes this form, then opens `frm_ProgressSearch_01`.
- No other VBA.

### 3.2 `frm_ProgressAds_02_subfrm` - "Ads" (datasheet)

- **RecordSource:** `tbl_ProgressAds_01`. **OrderBy:** `DateRun DESC`. DefaultView = Datasheet. The datasheet is editable and accepts new rows. New rows get AccountNumber automatically through the link field.
- Columns in datasheet order (ColumnOrder):

| # | Header (control name) | Field | Format |
|---|---|---|---|
| 0 | Comm % | CommissionPercent | General Number, 2 decimals (stored as a fraction; see rules) |
| 1 | Date Sold | DateSold | |
| 2 | Date Run | DateRun | |
| 3 | Desc | Description | (widest column) |
| 4 | Auth By | AuthorizedBy | |
| 5 | Sales | Sales | |
| 6 | Size | Size | |
| 7 | Category | **Section** (the header says "Category", but the field is `Section`) | |
| 8 | Page | AdPage | |
| 9 | Notes | AdNotes | |
| 10 | Run # | `Run #` | |
| 11 | Bill # | BillNumber | |
| 12 | Amount | Amount | General Number, 2 decimals |

- **`Billed` is not shown** on this subform or on any active form or report.
- No VBA.

### 3.3 `frm_ProgressSearch_01` - "Search Contacts and Ads"

- **Purpose:** This is a query-by-form screen. The user types patterns into fields that mirror the contact and ad fields, chooses OR/AND, and clicks Go. Section 4 describes the logic.
- **RecordSource:** `tbl_ProgressSearches_01` (an Access-local table). **Each search is saved as a record** in this table: `cmdSearch` first runs `DoCmd.DoMenuItem ... acSaveRecord`. The form has a saved Filter `AccountNumber Is Null OR AccountNumber=""` with FilterOn set, but FilterOnLoad=0, so the filter is probably not applied when the form opens **(inferred)**. OrderBy `DateRun`. Datasheet view is disabled.
- **Header text:**
  - "Search"
  - "Use the asterix ( * ) as a wildcard to find unknown characters or numbers"
  - "\"OR\" will search for records containg any of the entries:" with the example `City = Seattle  OR  Advertiser = *Mary*`
  - "\"AND\" will search for records containing all of the entries:" with the example `City = Seattle  AND  Advertiser = *Mary*`
- **Header list box** `lstBoolean`, bound to `Boolean`: value list `"OR";"AND"`, **default "OR"**.
- Visible criterion inputs, top to bottom, left column first:

Left column:

| Label | Control | Type | Field |
|---|---|---|---|
| Number | AccountNumber | textbox | AccountNumber |
| Advertiser | `cmbAdvertiser` | **combo**. RowSource is `SELECT Advertiser FROM tbl_ProgressContacts_01 GROUP BY Advertiser` (a distinct, sorted list of advertisers). Free entry is allowed (LimitToList is not set). | Advertiser |
| Contact | Contact | textbox | Contact |
| Address | Address | textbox | Address |
| Address 2 | Address2 | textbox | Address2 |
| City | City | textbox | City |
| State | State | textbox | State |
| Zip | Zip | textbox | Zip |
| Phone | Phone | textbox | Phone |
| Fax | Fax | textbox | Fax |
| E-mail | Email | textbox | Email |
| Web site | Website | textbox | Website |
| Directory Years | DirectoryYears | textbox | DirectoryYears |

Right column ("Client Information"):

| Label | Control | Type | Field |
|---|---|---|---|
| Category | Category | textbox | Category |
| Special Advertising Opportunities | AdOps | textbox | AdOps |
| Notes | ConNotes | textbox | ConNotes |
| Current Advertiser | `Current Advertiser` | checkbox | CurrentAdvertiser (**has no effect**; see Section 4) |

"Ad Information" block, lower area:

| Label | Control | Type | Field |
|---|---|---|---|
| Description | Description | textbox | Description |
| Authorized By | AuthorizedBy | textbox | AuthorizedBy |
| Sales | Sales | textbox | Sales |
| Size | Size | textbox | Size |
| Page | AdPage | textbox | AdPage |
| Bill Number | BillNumber | textbox | BillNumber |
| Publication | Publication | textbox | Publication (**no such column exists**; see Section 4) |
| Date Sold | DateSold | textbox | DateSold |
| Date Run | DateRun | textbox | DateRun |
| Amount | Amount | textbox (format `$#,##0.00`) | Amount |
| Commision % (sic) | CommissionPercent | textbox | CommissionPercent |
| Notes | AdNotes | textbox | AdNotes |

- **Footer:**
  - `Text165`, labeled "Save As" and bound to `SearchName`, names the saved search.
  - `cmdSearch` "Go": saves the record, calls `Progress_Search_01`, then opens `frm_ProgressSearchResults_01`. The Search form stays open.
  - `cmdExitSearch` "Exit Search": closes the form and opens `frm_ProgressContacts_Info_01`.
- Hidden computed controls (`txt*`, `txtBoolean`, `txtDummy`, `txtBuildSQL`, labeled "<--- SQL Build Area") build the SQL. See Section 4.

### 3.4 `frm_ProgressSearchResults_01` - "Search Results"

- **Purpose:** This form browses the accounts that matched the search, one account per page, using the same layout as Contacts_Info and the same ad-history subform.
- **RecordSource:** `qry_ProgressSearchResults_01`. **OrderBy:** Advertiser. The fields are editable (the default), so edits write through to `tbl_ProgressContacts_01`.
- Fields: Number (AccountNumber), Advertiser, Contact, Address, Address 2, City, State, Zip, Phone, Fax, E-mail, Web site, Directory Years. On the right: Category, Special Advertising Opportunities (AdOps), Notes (ConNotes). Checkboxes: "Current Advertiser", "Past  Advertiser" and "Email List".
  - **Caution:** these three checkboxes are bound to `Current Advertiser`, `Past Advertiser` and `Email List`, which contain spaces. The migrated columns are `CurrentAdvertiser`, `PastAdvertiser` and `EmailList`. These controls were probably broken or showing #Name? in Access after a column rename **(inferred)**. Bind them to the migrated columns in the web app.
- **Subform:** `frm_ProgressAds_02_subfrm`, linked on AccountNumber. It shows **all** ads for the account, not only the ads that matched.
- **Footer buttons:**
  - `cmdInfo` "Exit Search": closes the Results and Search forms and opens Contacts_Info.
  - `cmdExportXL` "Export Addresses to Excel": runs `mac_Excel_SearchResults`. This probably exports `SearchResultsAddresses` **(inferred)**, which has the columns Advertiser, Contact, Address, Address2, City, State, Zip, Category, AdOps and ConNotes.
  - `cmdSearchAgain` "Search Again": closes Results and opens Search.

---

## 4. Search criteria and SQL generation

### Mechanism

1. Each criterion field X has a hidden textbox `txtX` with this formula:

   ```
   =IIf(IsNull([X]),"","((qry_ProgressContactsWAds_01.X) Like """ & [X] & """)" & " " & [txtBoolean])
   ```

   An empty field contributes nothing. A filled field contributes `((col) Like "value") OR ` or `... AND `.
2. `txtDummy` holds `=IIf([lstBoolean]="AND"," (1=1)"," (1=2)")` and closes the trailing operator.
3. `txtBuildSQL` concatenates the parts:

   ```
   SELECT qry_ProgressContactsWAds_01.AccountNumber INTO tbl_ProgressSearchResults_01
   FROM qry_ProgressContactsWAds_01
   WHERE ( <txtAccountNumber><txtAdvertiser><txtContact><txtAddress><txtAddress2><txtCity>
           <txtState><txtZip><txtPhone><txtFax><txtEmail><txtWebsite><txtCategory><txtAdOps>
           <txtDirectoryYears><txtConNotes><txtCommissionPercent><txtDateSold><txtDateRun>
           <txtDescription><txtAuthorizedBy><txtSales><txtAmount><txtSize><txtAdPage>
           <txtBillNumber><txtPublication><txtAdNotes><txtDummy> );
   ```

4. `Module_mod_Progress_Search_01.Progress_Search_01` reads `Forms!frm_ProgressSearch_01!txtBuildSQL`, turns warnings off (`DoCmd.SetWarnings 0`), and runs `DoCmd.RunSQL`. This is a make-table operation that replaces `tbl_ProgressSearchResults_01`.
5. The results form shows `qry_ProgressSearchResults_01`:

   ```sql
   -- qry_ProgressSearchResults_02
   SELECT AccountNumber FROM tbl_ProgressSearchResults_01 GROUP BY AccountNumber;
   -- qry_ProgressSearchResults_01
   SELECT tbl_ProgressContacts_01.* FROM tbl_ProgressContacts_01
   RIGHT JOIN qry_ProgressSearchResults_02 ON tbl_ProgressContacts_01.AccountNumber = qry_ProgressSearchResults_02.AccountNumber;
   ```

   The results are **distinct accounts**. The search runs against the contact-LEFT-JOIN-ads view, so an account matches if its contact fields match or **any** of its ads matches. Accounts with no ads can still match on contact fields.

### Base view `qry_ProgressContactsWAds_01`

```sql
SELECT C.*, A.CommissionPercent, A.DateSold, A.DateRun, A.Description, A.AuthorizedBy, A.Sales, A.Amount,
       A.Size, A.AdPage, A.BillNumber, A.[Run #], A.Billed, A.AdNotes, A.Section
FROM C LEFT JOIN A ON C.AccountNumber = A.AccountNumber;
```

### Criteria offered

All criteria use Access `LIKE` with the text exactly as typed. The user must supply `*` wildcards; none are added automatically.

| Criterion (label) | Column | Works in Access? |
|---|---|---|
| Number | AccountNumber | Yes |
| Advertiser (combo) | Advertiser | Yes |
| Contact | Contact | Yes |
| Address | Address | Yes |
| Address 2 | Address2 | Yes |
| City | City | Yes |
| State | State | Yes |
| Zip | Zip | **Broken.** The fragment omits `& [txtBoolean]`, so no OR/AND follows it and the SQL is malformed (`...) (1=2)`) **(inferred: syntax error)** |
| Phone | Phone | **Broken** (same defect) |
| Fax | Fax | **Broken** (same defect) |
| E-mail | Email | **Broken** (same defect) |
| Web site | Website | **Broken** (same defect) |
| Directory Years | DirectoryYears | **Broken** (same defect) |
| Category | Category | Yes |
| Special Advertising Opportunities | AdOps | Yes |
| Notes | ConNotes | Yes |
| Commision % | CommissionPercent | Yes (LIKE on a number) |
| Date Sold | DateSold | Yes (LIKE on a date; the match depends on the date's text form) |
| Date Run | DateRun | Yes (same caveat) |
| Description | Description | Yes |
| Authorized By | AuthorizedBy | Yes |
| Sales | Sales | Yes |
| Amount | Amount | Yes (LIKE on a number) |
| Size | Size | Yes |
| Page | AdPage | Yes |
| Bill Number | BillNumber | Yes |
| Publication | Publication | **Broken.** No `Publication` column exists in the view, so Access would treat it as a parameter prompt or fail **(inferred)** |
| Notes (ad) | AdNotes | Yes |
| Current Advertiser (checkbox) | CurrentAdvertiser | **Ignored.** The fragment `Text175` is not concatenated into `txtBuildSQL` and has a typo (`qry_ProgressContactsWAds_01CurrentAdvertiser`) |
| OR / AND | (combiner) | Yes. The default is OR. |

Edge behavior: if no criteria are entered, OR mode produces `WHERE ( (1=2))`, which returns no results. AND mode produces `(1=1)`, which returns all accounts.

Section, Run # and Billed are in the view but have no search input.

### Recommended web equivalent

Build the query as a parameterized `SELECT DISTINCT c.* FROM contacts c LEFT JOIN ads a ON ... WHERE (cond1 OR/AND cond2 ...)`. Translate `*` to `%` and `?` to `_` for text fields. Use exact matches or ranges for dates and amounts. Include all of the fields above, add a working Current/Past/Prospect/EmailList filter, and sort the results by Advertiser. Provide a CSV/Excel export of the `SearchResultsAddresses` columns. Saving named searches is optional, because the Access feature existed but was not exposed for reuse in any active form.

---

## 5. Active reports

### 5.1 `rpt_ProgressContactsWAds_Comm_01` - Commission Report by Sell Date

- **RecordSource:** `qry_ProgressContactsWAds_Comm_03`.

  ```sql
  -- Comm_01
  SELECT qry_ProgressContactsWAds_01.*, DateSold AS DateParam, CommissionPercent AS CommNot0
  FROM qry_ProgressContactsWAds_01
  WHERE DateSold >= [Starting Date:] AND DateSold <= [Ending Date:] AND CommissionPercent > 0;
  -- Comm_02
  SELECT Min(DateSold) AS MinOfDateSold, Max(DateSold) AS MaxOfDateSold FROM qry_ProgressContactsWAds_Comm_01;
  -- Comm_03
  SELECT Comm_01.*, Comm_02.*, 1 AS GroupingDummy FROM Comm_01, Comm_02;
  ```

- **Parameters prompted:** `Starting Date:` and `Ending Date:`. They filter on **DateSold**, inclusive.
- **Filter:** only ads with `CommissionPercent > 0`.
- **Grouping and sorting:**
  1. `GroupingDummy` has a header and a footer. It is a single group that carries the grand totals.
  2. `DateSold` has a header and a footer. There is one group per distinct sell date, in ascending order.
  3. Within each date, rows are sorted by `Advertiser`.
- **Page header:** `"Commission Report for " & [MinOfDateSold] & " through " & [MaxOfDateSold]`. These are the actual first and last sell dates in the result, not the entered parameters.
- **Date group header:** column labels.
- **Detail columns:**

| Column | Field / expression | Format |
|---|---|---|
| Date Sold | DateSold | m/d/yy |
| Description | Description | |
| Amount | Amount | $#,##0.00 |
| Comm % | CommissionPercent | Percent |
| Run Date | DateRun | m/d/yy |
| Advertiser | Advertiser | |
| Comm Earned | `=[Amount]*[CommissionPercent]` | $#,##0.00 |

- **Date group footer:** Date Sold (Long Date), "Total Amount" `=Sum([Amount])`, and "Total Commissions Earned" `=Sum([Amount]*[CommissionPercent])`.
- **Grand-total footer:** the title line repeated, Total Amount and Total Commissions Earned.
- **Page footer:** "Printed" `=Date()`.
- **Layout:** portrait with 1" margins (from PrtMip).

### 5.2 `rpt_ProgressContactsWAds_Pub_01` - Publication Report by Run Date

- **RecordSource:** `qry_ProgressContactsWAds_Pub_01`.

  ```sql
  SELECT qry_ProgressContactsWAds_01.*, DateRun AS DateParam
  FROM qry_ProgressContactsWAds_01 WHERE DateRun = [Please Enter Run Date:];
  ```

- **Parameter:** `Please Enter Run Date:`. This is a single date with an **exact** match on DateRun.
- **Sorting:** by `Advertiser`, with no group header or footer.
- **Page header:** "Publication Report for " followed by DateRun (Long Date), then column headings.
- **Detail columns, left to right:**

| Column | Field / expression | Notes |
|---|---|---|
| (row #) | `txtCount` `=1` | RunningSum over the report, so it numbers the lines |
| Acct# | AccountNumber | |
| Advertiser | Advertiser | |
| Contact | Contact | |
| Description/Category | `Description ` | The ControlSource has a trailing space; it is intended as Description |
| Size | Size | |
| Page | AdPage | |
| Notes | AdNotes | |
| Run # | `Run #` | |
| Billing | BillNumber | |
| Amt | Amount | $#,##0.00 |
| (no header) | CommissionPercent | Percent, far right |

- Each cell is boxed (rectangles), giving a grid look.
- **Totals:** none. Only the running line count is shown.
- **Page footer:** "Printed" `=Date()` and `"Page " & [Page] & " of " & [Pages]`.
- **Layout:** the report is 10.33" wide with 0.2" side margins, so it prints **landscape** **(inferred)**. This is effectively the production or billing worksheet for one issue.

### 5.3 `rpt_LabelsDirectoryXParameter_01` - Mailing Labels by Directory Year

- **RecordSource:** `qry_DirectoryYearXParameter_01`.

  ```sql
  SELECT tbl_ProgressContacts_01.* FROM tbl_ProgressContacts_01
  WHERE DirectoryYears Like "*" & [Please enter year:] & "*";
  ```

- **Parameter:** `Please enter year:`. It is a substring match against the free-text `DirectoryYears` field.
- **Sorting:** by Advertiser (a BreakLevel). A saved OrderBy on DirectoryYears is overridden by the BreakLevel sort.
- **Label content:**
  - Line 1: Advertiser
  - Line 2: Address
  - Line 3: Address2
  - Line 4: `=Trim([City] & ", " & [State] & " " & [Zip])`
  - Contact is **not** printed.
- **Label layout** (decoded from PrtMip):
  - 3 labels across, each 2.3" wide by 1.0" high.
  - 0.6" horizontal spacing and 0" vertical spacing.
  - Margins: left and right 0.3", top and bottom 0.5".
  - Down-then-across layout code 1953 (default).
  - Result: 10 rows of 3, or 30 labels per letter page. This matches **Avery 5160 / 8160-class 30-up 1"x2-5/8" sheets** **(inferred)**. The Access geometry is approximate (the true 5160 is 2.625" wide with 0.125" gaps and 0.19" side margins). The web app should use true 5160 dimensions.
- Blank Address2 lines are not suppressed. Hiding them is recommended (CanShrink behavior).

### 5.4 Excel exports (macros not exported; all inferred)

The pipeline below is inferred from query dependencies:

1. `qry_ProgressContactsWAds_XDateRun_01` selects base-view rows `WHERE DateRun >= [Starting Date:] AND DateRun <= [Ending Date:]`. The Dashboard caption reads "Asks for starting and ending dates".
2. `..._XDateRun_02_MkTbl` makes the table `tbl_ProgressContactsWAds_XDateRun_02`, and `..._XDateRun_03` reads it.
3. **"Export Amounts by Run Date"** uses query `Amount`, a crosstab:

   ```sql
   TRANSFORM Sum(Amount) AS SumOfAmount
   SELECT Advertiser, Description FROM qry_ProgressContactsWAds_XDateRun_03
   GROUP BY Advertiser, Description
   PIVOT Format([DateRun],"yyyy/mm/dd");
   ```

   Rows are Advertiser + Description. There is one column per run date, and each cell holds the summed Amount.
4. **"Export Commission Earned by Run Date"** uses query `CommEarned`:

   ```sql
   TRANSFORM Sum([CommissionPercent]*[Amount]) AS CommEarned
   SELECT Advertiser, Description, Amount, CommissionPercent FROM ..._XDateRun_03
   GROUP BY Advertiser, Description, Amount, CommissionPercent
   PIVOT Format([DateRun],"yyyy/mm/dd");
   ```

   There is no `CommissionPercent > 0` filter here, unlike the Commission report.
5. The output is probably produced by `TransferSpreadsheet` or `OutputTo` Excel **(inferred)**.

The web app needs an XLSX or CSV download of a pivot: rows are Advertiser/Description, and columns are run dates within the chosen range.

---

## 6. Query categories and generalized patterns

The 80 queries fall into the following categories:

| Category | Count | Queries |
|---|---|---|
| A. Active application infrastructure | 14 | See Section 1 |
| B. Superseded versions (`_old`, `_old3`, ByRunDate) | 5 | qry_ProgressContactsWAds_Comm_old, Amount_old3, AmountByRunDate_old3, CommEarned_old3, CommEarnedByRunDate. They read a non-migrated `tbl_CrosstabByRunDate_01` or use old prompt names. |
| C. Directory label lists by directory year (`DirectoryYears LIKE *yyyy*`) | 5 | qry_Directory2005_01, 2006_01, 2007_01, 2008_01, qry_Directory2005_06_07 (2005-2008 combined) |
| D. Directory ads with billing info (`DateRun = 12/31/yyyy`) | 7 | qry_Directory2007_with_billing_info, 2008_with_billing_info, 2009-10_with_billing_info, 2009-12, 2010-11_with_billing_info, 2011-12_with_billing_info, Copy_of_qry_Directory2012-13_with_billing_info |
| E. Issue / special-section advertiser lists by specific run date(s): seasonal (Christmas, Easter), special sections (Catholic Schools Week, Graduation, Golden Jubilee, Ordination, Back to School, anniversary, special issue), current issue and monthly billing | 28 | 00_Current_NWC_Monthly_Billing, ABB-ABS_billing_12-2-10, ABB_Page_Numbers, AB_10_ANNIVERSARY_10-2007, Catholic_Schools_Week, Christmas_2006, Christmas_2007, Christmas_Advertisers, Christmas_Advertisers_2008, _2009, _2012, Copy_of_Christmas_Advertisers_08_09_10_11, Copy_of_Easter_2013_billing, Current_issue_address_labels, Easte_Advertisers, Easte_Advertisers_2012, Easte_and_Xmas_Advertisers_06, _07, Easter_2007_billing, Easter_2011-12, Final_Progress, Golden_Jubilee, Graduation, Graduation_2013, Ordination_Supplement, back_to_school, billing_special_issue, tbl_ProgressContacts_01_Query2 |
| F. Advertisers whose ads ran within a date range | 4 | Advertisers_2022-2026, Copy_of_all_advertisers_2005-2013, all_advertisers_7-13_to_12-14 (the actual range is 12/1/2021-12/1/2023), email_contacts_NWC_Monthly_Billing (the range 7/1/2017-5/1/2017 is inverted and returns nothing) |
| G. Contact-flag lists (CurrentAdvertiser / PastAdvertiser / EmailList) | 6 | current_advertisers_6_09, current_advertisers_7_10, past_advertisers_6_09, Email_list_03-2012, Copy_of_Email_list_05-2014, all_advertisers (flags plus one advertiser name) |
| H. Category-based prospect lists | 5 | Financial (legal/housing/financial), funeral_Advertisers (healthcare), vocations_08 and womans_religious (sisters/religious/outreach ministry/spiritual formation/seminary), Parish_list_9_13 (`Category Like *Parish*`) |
| I. Single-account lookups | 2 | 10-4-07_contracts (by advertiser name), Cemetery_2005-2006 (by AccountNumber) |
| J. Orphans on non-migrated objects | 4 | ABB-ABS_Billing (`[ABB-ABS Billing info]` cross-joined with contacts), tbl_ProgressContacts_01_Query (`[ABB Page Numbers]`), tbl_ProgressContacts_01_Query1 (`ABS`), Query1 (`[Christmas Advertisers 2009]`) |

Total: 80.

### Generalized patterns

Categories C through I collapse into **one "Advertiser List" report with filters**.

**Pattern 1: ads run on one or more issue dates, or within a date range** (categories D, E, F). This is the dominant pattern.

```sql
SELECT C.Advertiser, C.Contact, C.Address, C.Address2, C.City, C.State, C.Zip, C.Email,
       A.DateRun, A.Size, A.Amount, A.AdPage, A.Description, A.AdNotes, A.BillNumber
FROM C LEFT JOIN A ON C.AccountNumber = A.AccountNumber
WHERE A.DateRun = #12/11/2008# OR A.DateRun = #12/24/2009# OR A.DateRun = #12/23/2010#   -- Copy_of_Christmas_Advertisers_08_09_10_11
-- or: WHERE A.DateRun BETWEEN #12/31/2021# AND #6/2/2026#                               -- Advertisers_2022-2026
ORDER BY C.Advertiser;
```

Filters: a run-date list and/or a run-date range. The `Section` field (now in the ads table) should also be a filter, because it would replace "which special section" lookups by date **(inferred)**.

**Pattern 2: contacts by directory year** (category C, plus the active label report).

```sql
SELECT C.* FROM C WHERE C.DirectoryYears LIKE "*2007*";   -- qry_Directory2007_01
```

Filter: directory year, multi-select OR (`qry_Directory2005_06_07` ORs 2005-2008).

**Pattern 3: contacts by flag and/or category.**

```sql
SELECT C.Category, C.Advertiser, C.Contact, C.Email, C.Address, ... FROM C LEFT JOIN A ...
WHERE C.CurrentAdvertiser = Yes ORDER BY C.Advertiser;              -- current_advertisers_7_10
SELECT ... WHERE C.Category IN ("legal","housing","financial");     -- Financial
```

Filters: CurrentAdvertiser, PastAdvertiser, EmailList, Prospect, Category (multi-select or LIKE).

**Recommended unified report "Advertiser Lists":**

- Filters (combined with AND): run date (single, list or range); section; directory year(s); category (list or contains); the flags Current, Past, EmailList and Prospect; advertiser or account.
- Output options:
  - (a) one row per ad, with ad columns;
  - (b) one row per distinct advertiser (address list). Many legacy queries return duplicate rows per account because of the ad join.
- Exports: CSV/XLSX; and mailing labels (5160 layout), with an optional Contact line, because the 2007/2008/Christmas label reports print Contact.

---

## 7. Business rules

1. **Commission earned** = `Amount * CommissionPercent`, per ad.
   - The rule appears in the Comm report (`txtCommCalc`, group and grand sums) and in the `CommEarned` crosstab.
   - `CommissionPercent` is stored as a **fraction** (0.15 = 15%). The report formats it as `Percent`, and the product is formatted as currency **(inferred from formatting)**.
2. **Commission report scope:** ads with `CommissionPercent > 0` and `DateSold` between the start and end dates, inclusive. The report is grouped by DateSold, with per-day and grand totals of Amount and Commission. The commission export uses DateRun (not DateSold) and does not exclude zero-commission ads.
3. **Publication report:** all ads with `DateRun` exactly equal to one issue date, sorted by Advertiser, with line numbering. It is used as the issue manifest or billing sheet (Bill #, Amount, Page, Run #).
4. **Directory ads** are recorded as ads with `DateRun = December 31` of the directory year (for example `#12/31/2012#` for the 2012-13 directory). This is inferred from the seven "Directory ... with billing info" queries.
5. **DirectoryYears** (on the contact) is a free-text list of the years the account appeared in the directory. Label selection is a substring match (`LIKE *year*`).
6. **Monthly publication:** the newest query, `00_Current_NWC_Monthly_Billing`, filters `DateRun = #8/1/2026#`, which suggests that issues are now monthly and dated the first of the month **(inferred)**. Older queries use weekly Thursday dates.
7. **CurrentAdvertiser, PastAdvertiser, Prospect and EmailList** are manually maintained yes/no checkboxes. **No VBA, query or macro sets them automatically**, and no update queries exist. The label for PastAdvertiser reads "Old Avertiser". Older objects used the column names `Current Advertiser`, `Old Advertisers`, `Past Advertiser` and `Email List`.
8. **Billed:** no active form or report displays or edits it, and no query filters on it. It is only passed through in `SELECT` lists. **No rule for its values is discoverable.** BillNumber is the visible billing reference.
9. **Section** is shown as the "Category" column in the ads subform. It is distinct from the contact-level `Category`, which is the business type (for example parish, healthcare, legal, sisters, seminary).
10. **Account numbers** are text: the queries compare `AccountNumber = "000305"` and the search filter tests `= ""`. They may be zero-padded. Contacts_Info lists the highest or newest accounts first. No auto-numbering logic exists in the forms, so a new account number must be typed by the user **(inferred)**.
11. **Sales** and **AuthorizedBy** are free-text fields per ad, probably salesperson and customer authorizer **(inferred)**. Neither is used in any calculation or report filter.
12. Search semantics: user-supplied `*` wildcards; OR (default) or AND across all filled fields; matching on any ad of the account; results are distinct accounts.

---

## 8. Open questions and ambiguities

1. **Macro contents** (`mac_Excel_Amount`, `mac_Excel_CommEarned`, `mac_Excel_SearchResults`) were not exported. Confirm which queries they export and their file names and locations. Export them with `SaveAsText acMacro` if possible.
2. **Startup form:** confirm that the Dashboard is set as the startup form (Display Form / AutoExec), and check whether an AutoExec macro does anything else.
3. **Billed field:** clarify its meaning and allowed values (Yes/No? a date?), and whether the web app should show it or filter on it (for example an "unbilled ads" report).
4. **Section field:** confirm its allowed values. Today it is free text with no dropdown. Should it become a dropdown, along with Category, Size and Sales? No RowSources exist in Access; all are free-text textboxes. Distinct values could be derived from data.
5. **Search "Publication" field:** it refers to a column that does not exist. Did a Publication column exist once, and was it replaced by `Section`?
6. The **Zip/Phone/Fax/Email/Website/DirectoryYears** search criteria and the **Current Advertiser** search checkbox do not work in Access, as described in Section 4. Confirm whether users relied on workarounds. The web app should simply make them work.
7. **SearchResults checkbox bindings** use spaced column names that no longer exist. Confirm whether the column rename happened before or during the MariaDB migration.
8. **Label stock:** confirm the Avery product (5160 assumed). Confirm whether Contact should print. The active report omits it, while the older 2007/2008/Christmas label reports include it. Other stocks used historically: 2-up 4"x2", 2-up 4"x3.33", 1-up 4"x3.31", 2-up 4.25"x3.375", 3-up 2.5"x1.5" and 3-up 2.625"x1".
9. **Commission basis:** the report uses DateSold while the export uses DateRun. Confirm both are wanted.
10. **CommissionPercent storage:** confirm that the data holds fractions (0.15), not whole numbers (15). If it holds whole numbers, the formulas need `/100`.
11. **Saved searches** (`tbl_ProgressSearches_01`, field SearchName "Save As") were stored but never reloaded by any active form. Is this feature needed?
12. **Duplicate EmailList checkbox** on Contacts_Info (`Check108`): confirm that it is hidden behind the subform and can be dropped.
13. **Data validation:** none exists at the form level. Table-level required fields, defaults and indexes were not part of the export. Check the MariaDB schema for NOT NULL and unique constraints, especially uniqueness of AccountNumber.
