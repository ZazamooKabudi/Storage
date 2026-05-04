import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QGroupBox, QFileDialog, QMessageBox,
    QHeaderView, QAbstractItemView, QCheckBox, QFrame,
    QScrollArea, QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
import database as db
import excel_handler as xh


class SettingsScreen(QWidget):
    theme_changed = pyqtSignal(str)

    def __init__(self, username: str):
        super().__init__()
        self.username = username
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)

        title = QLabel("הגדרות מערכת")
        title.setObjectName("section_title")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(),  "כללי")
        tabs.addTab(self._build_data_tab(),      "נתונים")
        tabs.addTab(self._build_columns_tab(),   "כותרות עמודות")
        tabs.addTab(self._build_users_tab(),     "משתמשים")
        tabs.addTab(self._build_log_tab(),       "לוג פעולות")
        root.addWidget(tabs)

    # ── General tab ──────────────────────────────────────────────────────────

    def _build_general_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        grp = QGroupBox("הגדרות בסיסיות")
        g_lay = QVBoxLayout(grp)
        g_lay.setSpacing(12)

        g_lay.addWidget(QLabel("שם המחסן (XXX):"))
        self.txt_wh_name = QLineEdit()
        g_lay.addWidget(self.txt_wh_name)

        g_lay.addWidget(QLabel("נתיב יצוא / פלט:"))
        row = QHBoxLayout()
        self.txt_export = QLineEdit()
        btn_browse = QPushButton("עיון...")
        btn_browse.setObjectName("btn_secondary")
        btn_browse.clicked.connect(lambda: self._browse(self.txt_export))
        row.addWidget(btn_browse)
        row.addWidget(self.txt_export)
        g_lay.addLayout(row)

        g_lay.addWidget(QLabel("נתיב ארכיון:"))
        row2 = QHBoxLayout()
        self.txt_archive = QLineEdit()
        btn_arc = QPushButton("עיון...")
        btn_arc.setObjectName("btn_secondary")
        btn_arc.clicked.connect(lambda: self._browse(self.txt_archive))
        row2.addWidget(btn_arc)
        row2.addWidget(self.txt_archive)
        g_lay.addLayout(row2)

        g_lay.addWidget(QLabel("ערכת עיצוב:"))
        self.cmb_theme = QComboBox()
        self.cmb_theme.addItem("בהיר", "light")
        self.cmb_theme.addItem("כהה",  "dark")
        g_lay.addWidget(self.cmb_theme)

        btn_save = QPushButton("שמור הגדרות")
        btn_save.clicked.connect(self._save_general)
        g_lay.addWidget(btn_save)

        lay.addWidget(grp)
        lay.addStretch()
        return w

    # ── Data tab ─────────────────────────────────────────────────────────────

    def _build_data_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(16)

        grp = QGroupBox("ניהול קבצי מלאי")
        g_lay = QVBoxLayout(grp)
        g_lay.setSpacing(14)

        info = QLabel(
            "טעינת קובץ מלאי תבצע:\n"
            "1. ייצוא גיבוי של המלאי הקיים לארכיון\n"
            "2. מחיקת המלאי הנוכחי\n"
            "3. טעינת הקובץ החדש"
        )
        info.setStyleSheet("color: #616161; font-size: 12px;")
        g_lay.addWidget(info)

        btn_load = QPushButton("📂 טעינת קובץ מלאי (Excel)")
        btn_load.clicked.connect(self._load_inventory)
        g_lay.addWidget(btn_load)

        sep = QFrame(); sep.setObjectName("separator"); sep.setFixedHeight(1)
        g_lay.addWidget(sep)

        btn_export_inv = QPushButton("💾 יצוא מלאי + שיוכים (Excel)")
        btn_export_inv.setObjectName("btn_secondary")
        btn_export_inv.clicked.connect(self._export_inventory)
        g_lay.addWidget(btn_export_inv)

        sep2 = QFrame(); sep2.setObjectName("separator"); sep2.setFixedHeight(1)
        g_lay.addWidget(sep2)

        btn_import_pal = QPushButton("📂 קליטת רשימת משטחים (Excel)")
        btn_import_pal.clicked.connect(self._import_pallets)
        g_lay.addWidget(btn_import_pal)

        btn_sample = QPushButton("📄 צור קובץ דוגמא לקליטת משטחים")
        btn_sample.setObjectName("btn_secondary")
        btn_sample.clicked.connect(self._create_pallet_sample)
        g_lay.addWidget(btn_sample)

        lay.addWidget(grp)

        grp_reset = QGroupBox("איפוס נתונים")
        g_reset = QVBoxLayout(grp_reset); g_reset.setSpacing(10)
        lbl_warn = QLabel("פעולה זו תמחק לצמיתות את כל המלאי, השיוכים והמשטחים.")
        lbl_warn.setStyleSheet("color:#B71C1C; font-size:12px;")
        g_reset.addWidget(lbl_warn)
        btn_reset = QPushButton("🗑  איפוס כל הנתונים")
        btn_reset.setStyleSheet(
            "QPushButton { background:#C62828; color:white; font-weight:bold; border-radius:6px; padding:8px; }"
            "QPushButton:hover { background:#B71C1C; }"
        )
        btn_reset.setMinimumHeight(48)
        btn_reset.clicked.connect(self._reset_all_data)
        g_reset.addWidget(btn_reset)
        lay.addWidget(grp_reset)

        lay.addStretch()
        return w

    # ── Columns tab ───────────────────────────────────────────────────────────

    def _build_columns_tab(self):
        """Rename column headers and toggle visibility for the inventory table."""
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)

        outer.addWidget(QLabel(
            "שנה שמות כותרות ובחר אילו עמודות להציג בטבלת המלאי:"
        ))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 12, 0)

        # Header row
        for col_idx, text in enumerate(["כותרת עמודה", "הצג", "ברירת מחדל"]):
            h = QLabel(text)
            h.setStyleSheet("font-weight:bold; color:#1565C0; font-size:12px;")
            grid.addWidget(h, 0, col_idx)

        from database import DEFAULT_COL_HEADERS
        col_fields = {}   # col_index → QLineEdit
        col_checks = {}   # col_index → QCheckBox

        for i in range(1, 13):
            key     = f"inv_col_{i}"
            default = DEFAULT_COL_HEADERS.get(key, "")
            current = db.get_setting(key, default)
            hidden  = db.get_col_hidden(i)

            row_pos = i   # row 0 is the header row
            le = QLineEdit(current)
            le.setMinimumHeight(40)
            cb = QCheckBox()
            cb.setChecked(not hidden)
            cb.setToolTip("מסומן = עמודה מוצגת")
            lbl = QLabel(f'"{default}"')
            lbl.setStyleSheet("color:#757575; font-size:12px;")

            grid.addWidget(le,  row_pos, 0)
            grid.addWidget(cb,  row_pos, 1)
            grid.addWidget(lbl, row_pos, 2)
            col_fields[i] = le
            col_checks[i] = cb

        grid.setColumnStretch(0, 1)
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        btn_reset = QPushButton("אפס לברירות מחדל")
        btn_reset.setObjectName("btn_secondary")
        btn_save  = QPushButton("שמור כותרות")

        def _save():
            for idx, le in col_fields.items():
                db.set_column_header(idx, le.text().strip())
            for idx, cb in col_checks.items():
                db.set_col_hidden(idx, not cb.isChecked())
            db.log(self.username, "SAVE_COLUMN_HEADERS", "כותרות עמודות עודכנו")
            QMessageBox.information(w, "הצלחה",
                "הכותרות נשמרו ✓\nהשינויים יופיעו בפעם הבאה שהטבלה תיטען.")

        def _reset():
            for idx, le in col_fields.items():
                key = f"inv_col_{idx}"
                default = DEFAULT_COL_HEADERS.get(key, "")
                le.setText(default)
                db.set_column_header(idx, default)
            for idx, cb in col_checks.items():
                cb.setChecked(True)
                db.set_col_hidden(idx, False)
            QMessageBox.information(w, "אופס", "ברירות המחדל שוחזרו ✓")

        btn_reset.clicked.connect(_reset)
        btn_save.clicked.connect(_save)
        btn_row.addWidget(btn_reset)
        btn_row.addWidget(btn_save)
        outer.addLayout(btn_row)
        return w

    # ── Users tab ─────────────────────────────────────────────────────────────

    def _build_users_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        add_lay = QHBoxLayout()
        self.txt_new_user = QLineEdit()
        self.txt_new_user.setPlaceholderText("שם עובד חדש")
        btn_add = QPushButton("הוסף")
        btn_add.clicked.connect(self._add_user)
        add_lay.addWidget(btn_add)
        add_lay.addWidget(self.txt_new_user)
        lay.addLayout(add_lay)

        self.tbl_users = QTableWidget(0, 3)
        self.tbl_users.setHorizontalHeaderLabels(["שם עובד", "פעיל", "פעולה"])
        self.tbl_users.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_users.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        lay.addWidget(self.tbl_users)

        self._reload_users_table()
        return w

    # ── Log tab ───────────────────────────────────────────────────────────────

    def _build_log_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        filter_lay = QHBoxLayout()
        self.txt_log_search = QLineEdit(); self.txt_log_search.setPlaceholderText("חיפוש טקסט...")
        self.txt_log_from   = QLineEdit(); self.txt_log_from.setPlaceholderText("מתאריך YYYY-MM-DD")
        self.txt_log_to     = QLineEdit(); self.txt_log_to.setPlaceholderText("עד תאריך")
        self.cmb_log_action = QComboBox()
        self.cmb_log_action.addItems([
            "-- סוג פעולה --",
            "LOGIN",
            "LOAD_INVENTORY_XLSX",
            "EXPORT_INVENTORY",
            "IMPORT_PALLETS",
            "ASSIGN_PALLET",
            "DETACH_FROM_PALLET",
            "CREATE_PALLET",
            "UPDATE_ISINSTOCK",
            "SAVE_SETTINGS",
            "SAVE_COLUMN_HEADERS",
            "ADD_USER",
            "ACTIVATE_USER",
            "DEACTIVATE_USER",
        ])
        btn_filter = QPushButton("סנן")
        btn_filter.clicked.connect(self._filter_logs)

        filter_lay.addWidget(btn_filter)
        filter_lay.addWidget(self.cmb_log_action)
        filter_lay.addWidget(self.txt_log_to)
        filter_lay.addWidget(self.txt_log_from)
        filter_lay.addWidget(self.txt_log_search)
        lay.addLayout(filter_lay)

        self.tbl_log = QTableWidget(0, 5)
        self.tbl_log.setHorizontalHeaderLabels(["זמן", "משתמש", "אפליקציה", "פעולה", "פרטים"])
        self.tbl_log.horizontalHeader().setStretchLastSection(True)
        self.tbl_log.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_log.setAlternatingRowColors(True)
        lay.addWidget(self.tbl_log)

        self._filter_logs()
        return w

    # ── Settings helpers ──────────────────────────────────────────────────────

    def _load_settings(self):
        self.txt_wh_name.setText(db.get_setting("warehouse_name") or "XXX")
        self.txt_export.setText(db.get_setting("export_path")     or r"C:\Temp\Old_WH_EXP")
        self.txt_archive.setText(db.get_setting("archive_path")   or r"C:\Temp\Old_WH_Archive")
        theme = db.get_setting("theme") or "light"
        self.cmb_theme.setCurrentIndex(0 if theme == "light" else 1)

    def _save_general(self):
        db.set_setting("warehouse_name", self.txt_wh_name.text().strip() or "XXX")
        db.set_setting("export_path",    self.txt_export.text().strip())
        db.set_setting("archive_path",   self.txt_archive.text().strip())
        new_theme = self.cmb_theme.currentData()
        db.set_setting("theme", new_theme)
        self.theme_changed.emit(new_theme)
        db.log(self.username, "SAVE_SETTINGS", "הגדרות כלליות נשמרו")
        QMessageBox.information(self, "הצלחה", "ההגדרות נשמרו בהצלחה ✓")

    def _browse(self, target: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "בחר תיקייה", target.text())
        if path:
            target.setText(path)

    # ── Data helpers ──────────────────────────────────────────────────────────

    def _load_inventory(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "בחר קובץ מלאי Excel", "", "Excel Files (*.xlsx *.xls)"
        )
        if not path:
            return

        archive_dir = db.get_setting("archive_path") or r"C:\Temp\Old_WH_Archive"
        # Export existing to archive
        existing = db.get_all_inventory_with_assignments()
        if existing:
            arc_path = xh.archive_path(archive_dir, "InventoryOld_backup")
            xh.export_inventory_xlsx(existing, arc_path)

        try:
            rows = xh.load_inventory_xlsx(path)
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בטעינה", str(e))
            return

        db.clear_inventory()
        db.bulk_insert_inventory(rows)
        db.update_last_load_date()
        db.log(self.username, "LOAD_INVENTORY_XLSX", f"נטענו {len(rows)} שורות מ: {path}")

        if hasattr(self.parent(), "update_status"):
            self.parent().update_status()
        if hasattr(self.parent(), "inventory_screen"):
            self.parent().inventory_screen._refresh_filter_combos()

        QMessageBox.information(self, "הצלחה", f"נטענו {len(rows)} פריטים בהצלחה ✓")

    def _export_inventory(self):
        export_dir = db.get_setting("export_path") or r"C:\Temp\Old_WH_EXP"
        arc_path   = xh.archive_path(export_dir, "InventoryExport")
        rows = db.get_all_inventory_with_assignments()
        if not rows:
            QMessageBox.warning(self, "אזהרה", "אין נתוני מלאי לייצוא")
            return
        xh.export_inventory_xlsx(rows, arc_path)
        db.log(self.username, "EXPORT_INVENTORY", f"יוצא ל: {arc_path}")
        QMessageBox.information(self, "הצלחה", f"קובץ יוצא:\n{arc_path}")

    def _import_pallets(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "בחר קובץ קליטת משטחים", "", "Excel Files (*.xlsx *.xls)"
        )
        if not path:
            return
        try:
            rows = xh.load_pallet_import_xlsx(path)
        except Exception as e:
            QMessageBox.critical(self, "שגיאה בטעינה", str(e))
            return
        if not rows:
            QMessageBox.warning(self, "אזהרה", "הקובץ ריק או שאין שורות תקינות")
            return
        result    = db.import_pallets_from_rows(rows, self.username)
        assigned  = result["assigned"]
        created   = result["created"]
        cleared   = result["cleared"]
        not_found = result["not_found"]
        if created and not assigned:
            msg = f"נוצרו {created} משטחים בהצלחה (ללא שיוך פריטים)."
            if cleared:
                msg += f"\nהוסרו {cleared} משטחים ישנים ללא שיוך."
        else:
            msg = f"שויכו {assigned} פריטים למשטחים מתוך {len(rows)} שורות."
            if created:
                msg += f"\nנוסף לכך נוצרו {created} משטחים חדשים ללא שיוך."
        if not_found:
            sample = "\n".join(not_found[:6])
            if len(not_found) > 6:
                sample += f"\n... ועוד {len(not_found) - 6}"
            msg += f"\n\nפריטים שלא נמצאו במלאי ({len(not_found)}):\n{sample}"
        QMessageBox.information(self, "תוצאות קליטה", msg)

    def _reset_all_data(self):
        reply = QMessageBox.question(
            self, "איפוס נתונים",
            "האם בטוח שברצונך למחוק את כל הנתונים?\n\n"
            "• כל המלאי (InventoryOld)\n"
            "• כל שיוכי המשטחים\n"
            "• כל המשטחים\n\n"
            "פעולה זו אינה הפיכה.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        db.reset_all_data()
        db.log(self.username, "RESET_ALL_DATA", "כל הנתונים נמחקו")
        QMessageBox.information(self, "בוצע", "כל הנתונים נמחקו ✓")

    def _create_pallet_sample(self):
        export_dir = db.get_setting("export_path") or r"C:\Temp\Old_WH_EXP"
        path = xh.archive_path(export_dir, "PalletImport_Sample")
        xh.create_pallet_import_sample(path)
        QMessageBox.information(self, "הצלחה", f"קובץ דוגמא נוצר:\n{path}")

    # ── Users helpers ─────────────────────────────────────────────────────────

    def _reload_users_table(self):
        users = db.get_all_users()
        self.tbl_users.setRowCount(len(users))
        for r, u in enumerate(users):
            self.tbl_users.setItem(r, 0, QTableWidgetItem(u["FullName"]))
            active = QTableWidgetItem("✔ פעיל" if u["IsActive"] else "✘ מושהה")
            active.setForeground(Qt.GlobalColor.darkGreen if u["IsActive"] else Qt.GlobalColor.red)
            self.tbl_users.setItem(r, 1, active)
            btn = QPushButton("השהה" if u["IsActive"] else "הפעל")
            uid = u["UserID"]
            is_active = u["IsActive"]
            btn.clicked.connect(
                lambda _, uid=uid, ia=is_active: self._toggle_user(uid, ia)
            )
            self.tbl_users.setCellWidget(r, 2, btn)
            self.tbl_users.setRowHeight(r, 48)

    def _add_user(self):
        name = self.txt_new_user.text().strip()
        if not name:
            return
        try:
            db.add_user(name)
            self.txt_new_user.clear()
            self._reload_users_table()
            db.log(self.username, "ADD_USER", f"נוסף משתמש: {name}")
        except Exception as e:
            QMessageBox.warning(self, "שגיאה", str(e))

    def _toggle_user(self, uid: int, currently_active: bool):
        new_state = not currently_active
        db.set_user_active(uid, new_state, self.username)
        self._reload_users_table()

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _filter_logs(self):
        action = self.cmb_log_action.currentText()
        if action.startswith("--"):
            action = ""
        logs = db.get_logs(
            from_date=self.txt_log_from.text().strip(),
            to_date=self.txt_log_to.text().strip(),
            action=action,
            search=self.txt_log_search.text().strip(),
        )
        self.tbl_log.setRowCount(len(logs))
        for r, row in enumerate(logs):
            for c, key in enumerate(["Timestamp", "UserName", "ApplicationName", "ActionType", "Details"]):
                item = QTableWidgetItem(str(row[key] or ""))
                self.tbl_log.setItem(r, c, item)
            self.tbl_log.setRowHeight(r, 44)
