import sqlite3
import os
import sys
from datetime import datetime

_APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
           else os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(_APP_DIR, "old_warehouse.db")
APP_NAME = "OldWarehouseApp"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db():
    with get_conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS Users (
                UserID   INTEGER PRIMARY KEY AUTOINCREMENT,
                FullName TEXT    NOT NULL UNIQUE,
                IsActive INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS Settings (
                SettingKey   TEXT PRIMARY KEY,
                SettingValue TEXT
            );
            CREATE TABLE IF NOT EXISTS LogEntries (
                LogID           INTEGER PRIMARY KEY AUTOINCREMENT,
                Timestamp       TEXT NOT NULL,
                UserName        TEXT,
                ApplicationName TEXT,
                ActionType      TEXT,
                Details         TEXT
            );
            CREATE TABLE IF NOT EXISTS InventoryOld (
                InventoryID   INTEGER PRIMARY KEY AUTOINCREMENT,
                Cat           TEXT,
                Pn            TEXT NOT NULL,
                UnitOfMeasure TEXT NOT NULL DEFAULT '',
                Batch         TEXT NOT NULL DEFAULT '',
                WBS           TEXT NOT NULL DEFAULT '',
                Storage       TEXT NOT NULL DEFAULT '',
                Area          TEXT NOT NULL DEFAULT '',
                Bin           TEXT NOT NULL DEFAULT '',
                DestArea      TEXT,
                Qty           REAL,
                MultiLocation TEXT NOT NULL DEFAULT '',
                IsInStock     INTEGER NOT NULL DEFAULT 0,
                UNIQUE (Pn, Batch, WBS, Storage, Area, Bin)
            );
            CREATE TABLE IF NOT EXISTS Pallets (
                PalletID   TEXT PRIMARY KEY,
                CreateDate TEXT,
                CreateUser TEXT,
                Status     TEXT DEFAULT 'הוקם'
            );
            CREATE TABLE IF NOT EXISTS PALLET_Assignment (
                AssignmentID INTEGER PRIMARY KEY AUTOINCREMENT,
                InventoryID  INTEGER NOT NULL,
                PalletID     TEXT NOT NULL,
                IsInStock    INTEGER DEFAULT 0,
                TargetBin    TEXT,
                AssignDate   TEXT,
                FOREIGN KEY (InventoryID) REFERENCES InventoryOld(InventoryID),
                FOREIGN KEY (PalletID)   REFERENCES Pallets(PalletID),
                UNIQUE (InventoryID)
            );
        """)
        _seed_settings(c)
        # Migrations for existing databases
        for col, defn in [
            ("UnitOfMeasure", "TEXT NOT NULL DEFAULT ''"),
            ("MultiLocation",  "TEXT NOT NULL DEFAULT ''"),
            ("IsInStock",      "INTEGER NOT NULL DEFAULT 0"),
            ("UpdatedQty",     "REAL"),
            ("Notes",          "TEXT"),
        ]:
            try:
                c.execute(f"ALTER TABLE InventoryOld ADD COLUMN {col} {defn}")
            except Exception:
                pass
        c.commit()
    _migrate_pallet_id_to_text()


def _migrate_pallet_id_to_text():
    """Rebuild Pallets and PALLET_Assignment to use TEXT PalletID (no-op if already TEXT)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        pal_info = {r["name"]: r["type"] for r in conn.execute("PRAGMA table_info(Pallets)")}
        if pal_info.get("PalletID", "TEXT") != "TEXT":
            conn.executescript("""
                PRAGMA foreign_keys = OFF;
                CREATE TABLE _Pallets_new (
                    PalletID   TEXT PRIMARY KEY,
                    CreateDate TEXT,
                    CreateUser TEXT,
                    Status     TEXT DEFAULT 'הוקם'
                );
                INSERT OR IGNORE INTO _Pallets_new
                    SELECT CAST(PalletID AS TEXT), CreateDate, CreateUser, Status
                    FROM Pallets;
                DROP TABLE Pallets;
                ALTER TABLE _Pallets_new RENAME TO Pallets;
            """)
        pa_info = {r["name"]: r["type"] for r in conn.execute("PRAGMA table_info(PALLET_Assignment)")}
        if pa_info.get("PalletID", "TEXT") != "TEXT":
            conn.executescript("""
                PRAGMA foreign_keys = OFF;
                CREATE TABLE _PA_new (
                    AssignmentID INTEGER PRIMARY KEY AUTOINCREMENT,
                    InventoryID  INTEGER NOT NULL,
                    PalletID     TEXT NOT NULL,
                    IsInStock    INTEGER DEFAULT 0,
                    TargetBin    TEXT,
                    AssignDate   TEXT,
                    FOREIGN KEY (InventoryID) REFERENCES InventoryOld(InventoryID),
                    FOREIGN KEY (PalletID)    REFERENCES Pallets(PalletID),
                    UNIQUE (InventoryID)
                );
                INSERT OR IGNORE INTO _PA_new
                    SELECT AssignmentID, InventoryID, CAST(PalletID AS TEXT),
                           IsInStock, TargetBin, AssignDate
                    FROM PALLET_Assignment;
                DROP TABLE PALLET_Assignment;
                ALTER TABLE _PA_new RENAME TO PALLET_Assignment;
            """)
    finally:
        conn.close()


# Columns 1-12 map to the 12 content columns (col 0 = checkbox, no header needed)
DEFAULT_COL_HEADERS = {
    "inv_col_1":  "מס' קטלוגי",
    "inv_col_2":  "PN",
    "inv_col_3":  "סדרה",
    "inv_col_4":  "WBS",
    "inv_col_5":  "כמות",
    "inv_col_6":  "איתור",
    "inv_col_7":  "אזור יעד",
    "inv_col_8":  "ממוקם",
    "inv_col_9":  "משטח משויך",
    "inv_col_10": "חיווי",
    "inv_col_11": "כמות מעודכנת",
    "inv_col_12": "הערות",
}


def _seed_settings(c):
    defaults = [
        ("warehouse_name", "XXX"),
        ("theme", "light"),
        ("export_path",  r"C:\Temp\Old_WH_EXP"),
        ("archive_path", r"C:\Temp\Old_WH_Archive"),
        ("last_load_date", ""),
    ]
    for k, v in defaults:
        c.execute("INSERT OR IGNORE INTO Settings VALUES (?,?)", (k, v))
    # Migrate old Desktop / local-archive paths that were seeded in earlier versions
    _old_export  = os.path.expanduser("~/Desktop")
    _old_archive = os.path.join(os.path.dirname(DB_PATH), "archive")
    c.execute("UPDATE Settings SET SettingValue=? WHERE SettingKey='export_path'  AND SettingValue=?",
              (r"C:\Temp\Old_WH_EXP",     _old_export))
    c.execute("UPDATE Settings SET SettingValue=? WHERE SettingKey='archive_path' AND SettingValue=?",
              (r"C:\Temp\Old_WH_Archive",  _old_archive))
    for k, v in DEFAULT_COL_HEADERS.items():
        c.execute("INSERT OR IGNORE INTO Settings VALUES (?,?)", (k, v))
    for i in range(1, 13):
        c.execute("INSERT OR IGNORE INTO Settings VALUES (?,?)", (f"inv_col_{i}_hidden", "0"))


def get_column_headers() -> list[str]:
    """Returns 13-element list: index 0 = '' (checkbox col), 1-12 = custom/default labels."""
    result = [""]
    for i in range(1, 13):
        result.append(get_setting(f"inv_col_{i}", DEFAULT_COL_HEADERS.get(f"inv_col_{i}", "")))
    return result


def set_column_header(col_index: int, label: str):
    set_setting(f"inv_col_{col_index}", label)


def get_col_hidden(col_index: int) -> bool:
    return get_setting(f"inv_col_{col_index}_hidden", "0") == "1"


def set_col_hidden(col_index: int, hidden: bool):
    set_setting(f"inv_col_{col_index}_hidden", "1" if hidden else "0")


# ── Settings ─────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    with get_conn() as c:
        row = c.execute("SELECT SettingValue FROM Settings WHERE SettingKey=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str):
    with get_conn() as c:
        c.execute("INSERT OR REPLACE INTO Settings VALUES (?,?)", (key, value))
        c.commit()


# ── Log ───────────────────────────────────────────────────────────────────────

def log(user: str, action: str, details: str = ""):
    with get_conn() as c:
        c.execute(
            "INSERT INTO LogEntries (Timestamp,UserName,ApplicationName,ActionType,Details) VALUES (?,?,?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, APP_NAME, action, details),
        )
        c.commit()


def get_logs(from_date="", to_date="", user="", action="", search=""):
    sql = "SELECT * FROM LogEntries WHERE 1=1"
    params = []
    if from_date:
        sql += " AND Timestamp >= ?"; params.append(from_date + " 00:00:00")
    if to_date:
        sql += " AND Timestamp <= ?"; params.append(to_date + " 23:59:59")
    if user:
        sql += " AND UserName LIKE ?"; params.append(f"%{user}%")
    if action:
        sql += " AND ActionType = ?"; params.append(action)
    if search:
        sql += " AND Details LIKE ?"; params.append(f"%{search}%")
    sql += " ORDER BY LogID DESC LIMIT 500"
    with get_conn() as c:
        return c.execute(sql, params).fetchall()


# ── Users ─────────────────────────────────────────────────────────────────────

def get_active_users():
    with get_conn() as c:
        return c.execute("SELECT * FROM Users WHERE IsActive=1 ORDER BY FullName").fetchall()


def get_all_users():
    with get_conn() as c:
        return c.execute("SELECT * FROM Users ORDER BY FullName").fetchall()


def add_user(name: str):
    with get_conn() as c:
        c.execute("INSERT INTO Users (FullName) VALUES (?)", (name,))
        c.commit()


def set_user_active(user_id: int, active: bool, changed_by: str = ""):
    with get_conn() as c:
        c.execute("UPDATE Users SET IsActive=? WHERE UserID=?", (1 if active else 0, user_id))
        c.commit()
    action = "ACTIVATE_USER" if active else "DEACTIVATE_USER"
    log(changed_by or "system", action, f"UserID={user_id}")


# ── Inventory ─────────────────────────────────────────────────────────────────

def get_inventory_with_assignments(pn="", storage="", area="", bin_="",
                                    limit=0, unassigned_only=False,
                                    cat="", dest_area=""):
    sql = """
        SELECT i.InventoryID, i.Cat, i.Pn, i.UnitOfMeasure, i.Batch, i.WBS,
               i.Storage, i.Area, i.Bin, i.DestArea, i.Qty, i.MultiLocation,
               i.IsInStock, i.UpdatedQty, i.Notes,
               pa.PalletID, pa.AssignDate
        FROM InventoryOld i
        LEFT JOIN PALLET_Assignment pa ON i.InventoryID = pa.InventoryID
        WHERE 1=1
    """
    params: list = []
    if pn:
        sql += " AND i.Pn LIKE ?";          params.append(f"%{pn}%")
    if cat:
        sql += " AND i.Cat LIKE ?";         params.append(f"%{cat}%")
    if storage:
        sql += " AND i.Storage = ?";        params.append(storage)
    if area:
        sql += " AND i.Area = ?";           params.append(area)
    if bin_:
        sql += " AND i.Bin = ?";            params.append(bin_)
    if dest_area:
        sql += " AND i.DestArea LIKE ?";    params.append(f"%{dest_area}%")
    if unassigned_only:
        sql += " AND pa.PalletID IS NULL"
    sql += " ORDER BY i.Pn, i.Batch"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_conn() as c:
        return c.execute(sql, params).fetchall()


def get_inventory(pn="", storage="", area="", bin_=""):
    return get_inventory_with_assignments(pn, storage, area, bin_, limit=500)


def set_updated_qty(inv_id: int, qty, user: str):
    with get_conn() as c:
        c.execute("UPDATE InventoryOld SET UpdatedQty=? WHERE InventoryID=?", (qty, inv_id))
        c.commit()
    log(user, "UPDATE_QTY", f"InventoryID={inv_id} UpdatedQty={qty}")


def set_item_notes(inv_id: int, notes: str, user: str):
    notes_val = notes.strip() if notes else None
    with get_conn() as c:
        c.execute("UPDATE InventoryOld SET Notes=? WHERE InventoryID=?", (notes_val, inv_id))
        c.commit()
    log(user, "UPDATE_NOTES", f"InventoryID={inv_id}")


def get_distinct_values(col: str):
    allowed = {"Storage", "Area", "Bin", "Pn", "DestArea"}
    if col not in allowed:
        return []
    with get_conn() as c:
        rows = c.execute(
            f"SELECT DISTINCT {col} FROM InventoryOld "
            f"WHERE {col} IS NOT NULL AND {col}!='' ORDER BY {col}"
        ).fetchall()
    return [r[0] for r in rows]


def set_is_in_stock(inv_id: int, value: bool, user: str):
    with get_conn() as c:
        c.execute("UPDATE InventoryOld SET IsInStock=? WHERE InventoryID=?",
                  (1 if value else 0, inv_id))
        c.commit()
    log(user, "UPDATE_ISINSTOCK", f"InventoryID={inv_id} IsInStock={value}")


def upsert_is_in_stock(inv_id: int, value: bool, user: str):
    set_is_in_stock(inv_id, value, user)


# ── Pallets ───────────────────────────────────────────────────────────────────

def pallet_exists(pallet_id: str) -> bool:
    with get_conn() as c:
        return bool(c.execute("SELECT 1 FROM Pallets WHERE PalletID=?", (pallet_id,)).fetchone())


def create_pallet(pallet_id: str, user: str):
    if pallet_exists(pallet_id):
        raise ValueError(f"משטח {pallet_id} כבר קיים במערכת")
    with get_conn() as c:
        c.execute(
            "INSERT INTO Pallets (PalletID, CreateDate, CreateUser) VALUES (?,?,?)",
            (pallet_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user),
        )
        c.commit()
    log(user, "CREATE_PALLET", f"PalletID={pallet_id}")


def get_pallets():
    with get_conn() as c:
        return c.execute("SELECT * FROM Pallets ORDER BY PalletID").fetchall()


def import_pallets_from_rows(rows: list[dict], user: str) -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assigned = 0   # pallets created AND linked to an inventory item
    created  = 0   # pallets created from a simple code list (no inventory match needed)
    cleared  = 0   # orphan pallets removed before a simple-list import
    not_found = []

    # Detect simple code-list import: none of the rows carry inventory details (PN)
    is_simple_list = all(
        not str(r.get("PN", r.get("Pn", "")) or "").strip() for r in rows if r
    )

    with get_conn() as c:
        if is_simple_list:
            # Remove pallets that have no assignments so the new list replaces them cleanly
            cur = c.execute(
                "DELETE FROM Pallets "
                "WHERE PalletID NOT IN (SELECT DISTINCT PalletID FROM PALLET_Assignment)"
            )
            cleared = cur.rowcount

        for r in rows:
            pid = str(r.get("PalletID", "") or "").strip()
            if not pid:
                continue
            pn      = str(r.get("PN",      r.get("Pn", "")) or "").strip()
            batch   = str(r.get("Batch",   "") or "").strip()
            wbs     = str(r.get("WBS",     "") or "").strip()
            storage = str(r.get("Storage", "") or "").strip()
            area    = str(r.get("Area",    "") or "").strip()
            bin_    = str(r.get("Bin",     "") or "").strip()

            # Simple pallet-code list (no inventory details) → just register the pallet
            if not pn:
                c.execute(
                    """INSERT OR IGNORE INTO Pallets (PalletID, CreateDate, CreateUser, Status)
                       VALUES (?, ?, ?, ?)""",
                    (pid,
                     r.get("CreateDate", now) or now,
                     r.get("CreateUser", user) or user,
                     r.get("Status", "הוקם") or "הוקם"),
                )
                created += 1
                continue

            # Full format: locate the inventory row and create assignment
            inv_row = c.execute(
                """SELECT InventoryID FROM InventoryOld
                   WHERE Pn=? AND Batch=? AND WBS=? AND Storage=? AND Area=? AND Bin=?""",
                (pn, batch, wbs, storage, area, bin_),
            ).fetchone()
            if not inv_row:
                not_found.append(f"PN={pn}  Batch={batch}  Storage={storage}/{area}/{bin_}")
                continue
            inv_id = inv_row[0]
            c.execute(
                """INSERT OR IGNORE INTO Pallets (PalletID, CreateDate, CreateUser, Status)
                   VALUES (?, ?, ?, ?)""",
                (pid,
                 r.get("CreateDate", now) or now,
                 r.get("CreateUser", user) or user,
                 r.get("Status", "הוקם") or "הוקם"),
            )
            c.execute(
                """INSERT OR IGNORE INTO PALLET_Assignment
                   (InventoryID, PalletID, AssignDate)
                   VALUES (?, ?, ?)""",
                (inv_id, pid, now),
            )
            assigned += 1
        c.commit()
    log(user, "IMPORT_PALLETS",
        f"נוצרו: {created} | שויכו: {assigned} | הוסרו ישנים: {cleared} | לא נמצאו: {len(not_found)}")
    return {"assigned": assigned, "created": created, "cleared": cleared, "not_found": not_found}


def detach_item_from_pallet(inv_id: int, user: str):
    with get_conn() as c:
        c.execute("DELETE FROM PALLET_Assignment WHERE InventoryID=?", (inv_id,))
        c.execute("UPDATE InventoryOld SET IsInStock=0 WHERE InventoryID=?", (inv_id,))
        c.commit()
    log(user, "DETACH_FROM_PALLET", f"InventoryID={inv_id}")


def assign_items_to_pallet(inv_ids: list, pallet_id: str, user: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as c:
        for inv_id in inv_ids:
            row = c.execute("SELECT IsInStock FROM InventoryOld WHERE InventoryID=?", (inv_id,)).fetchone()
            is_in = row["IsInStock"] if row else 0
            existing = c.execute("SELECT AssignmentID FROM PALLET_Assignment WHERE InventoryID=?", (inv_id,)).fetchone()
            if existing:
                c.execute(
                    "UPDATE PALLET_Assignment SET PalletID=?, IsInStock=?, AssignDate=? WHERE InventoryID=?",
                    (pallet_id, is_in, now, inv_id),
                )
            else:
                c.execute(
                    "INSERT INTO PALLET_Assignment (InventoryID,PalletID,IsInStock,AssignDate) VALUES (?,?,?,?)",
                    (inv_id, pallet_id, is_in, now),
                )
        c.commit()
    log(user, "ASSIGN_PALLET", f"PalletID={pallet_id} items={inv_ids}")


def get_pallet_items(pallet_id: str):
    with get_conn() as c:
        return c.execute(
            """SELECT i.*, pa.IsInStock, pa.AssignDate
               FROM PALLET_Assignment pa
               JOIN InventoryOld i ON pa.InventoryID = i.InventoryID
               WHERE pa.PalletID=?
               ORDER BY i.Pn""",
            (pallet_id,),
        ).fetchall()


# ── Inventory load / export ────────────────────────────────────────────────────

def clear_inventory():
    with get_conn() as c:
        c.execute("DELETE FROM PALLET_Assignment")
        c.execute("DELETE FROM InventoryOld")
        c.commit()


def reset_all_data():
    """Delete all inventory, pallet assignments and pallets."""
    with get_conn() as c:
        c.execute("DELETE FROM PALLET_Assignment")
        c.execute("DELETE FROM InventoryOld")
        c.execute("DELETE FROM Pallets")
        c.commit()


def bulk_insert_inventory(rows: list[dict]):
    with get_conn() as c:
        for r in rows:
            c.execute(
                """INSERT OR IGNORE INTO InventoryOld
                   (Cat,Pn,UnitOfMeasure,Batch,WBS,Storage,Area,Bin,DestArea,Qty,MultiLocation)
                   VALUES (:Cat,:Pn,:UnitOfMeasure,:Batch,:WBS,:Storage,:Area,:Bin,:DestArea,:Qty,:MultiLocation)""",
                r,
            )
        c.commit()


def get_all_inventory_with_assignments():
    with get_conn() as c:
        return c.execute(
            """SELECT i.*, pa.PalletID, pa.IsInStock, pa.AssignDate, pa.TargetBin
               FROM InventoryOld i
               LEFT JOIN PALLET_Assignment pa ON i.InventoryID = pa.InventoryID
               ORDER BY i.Pn, i.Batch"""
        ).fetchall()


def get_inventory_by_pallet(pallet_id: str):
    with get_conn() as c:
        return c.execute(
            """SELECT i.InventoryID, i.Cat, i.Pn, i.Batch, i.WBS, i.Bin,
                      i.DestArea, i.Qty, i.UpdatedQty, i.Notes,
                      i.IsInStock, pa.PalletID, pa.AssignDate
               FROM PALLET_Assignment pa
               JOIN InventoryOld i ON pa.InventoryID = i.InventoryID
               WHERE pa.PalletID = ?
               ORDER BY i.Pn""",
            (pallet_id,),
        ).fetchall()


def update_last_load_date():
    set_setting("last_load_date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
