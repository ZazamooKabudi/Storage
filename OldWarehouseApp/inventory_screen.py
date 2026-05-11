from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QFrame, QHeaderView, QAbstractItemView, QCompleter, QMessageBox, QCheckBox,
    QDialog, QTextEdit, QDialogButtonBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush, QPainter, QPainterPath
from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PyQt6.QtGui import QDoubleValidator
from collections import Counter  # noqa: F401 (kept for potential future use)
import database as db

PAGE_SIZE = 300

# ── Column indices (RTL: col 0 = rightmost on screen) ────────────────────────
COL_CHK     = 0   # ✓ בחירה
COL_PN      = 1   # PN / מספר חלק
COL_CAT     = 2   # מס' קטלוגי (חומר)
COL_BATCH   = 3   # סדרה (Batch)
COL_WBS     = 4   # WBS
COL_QTY     = 5   # כמות (Qty)
COL_BIN     = 6   # איתור (Bin)
COL_DEST    = 7   # אזור יעד (DestArea)
COL_STOCK   = 8   # ממוקם – toggle switch
COL_PAL     = 9   # משטח משויך
COL_IND     = 10  # חיווי – ❗ indicator
COL_UPD_QTY = 11  # כמות מעודכנת (עריכה)
COL_NOTES   = 12  # הערות – 📝 indicator
NUM_COLS    = 13

COLOR_IND = QColor("#D32F2F")

# Maps column index → row dict key for sorting (widget columns excluded)
_SORT_KEY = {
    COL_PN:      lambda r: str(r["Pn"]      or "").lower(),
    COL_CAT:     lambda r: str(r["Cat"]     or "").lower(),
    COL_BATCH:   lambda r: str(r["Batch"]   or "").lower(),
    COL_WBS:     lambda r: str(r["WBS"]     or "").lower(),
    COL_QTY:     lambda r: float(r["Qty"]   or 0),
    COL_BIN:     lambda r: str(r["Bin"]     or "").lower(),
    COL_DEST:    lambda r: str(r["DestArea"]or "").lower(),
    COL_STOCK:   lambda r: int(r["IsInStock"] or 0),
    COL_PAL:     lambda r: (str(r["PalletID"]) if r["PalletID"] is not None else ""),
    COL_UPD_QTY: lambda r: float(r["UpdatedQty"] if r["UpdatedQty"] is not None else (r["Qty"] or 0)),
}


# ── Toggle switch widget ──────────────────────────────────────────────────────

class ToggleSwitch(QWidget):
    """Green/red sliding toggle – emits toggled(bool) on click."""
    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = True, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(90, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, value: bool):
        if self._checked != value:
            self._checked = value
            self.update()

    def mousePressEvent(self, event):
        self._checked = not self._checked
        self.toggled.emit(self._checked)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        radius = h / 2

        bg = QColor("#2E7D32") if self._checked else QColor("#C62828")
        p.setBrush(QBrush(bg))
        p.setPen(Qt.PenStyle.NoPen)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, radius, radius)
        p.drawPath(path)

        knob_d = h - 4
        knob_x = w - knob_d - 2 if self._checked else 2
        p.setBrush(QBrush(QColor("white")))
        p.drawEllipse(int(knob_x), 2, knob_d, knob_d)

        p.setPen(QColor("white"))
        font = p.font()
        font.setPointSize(8)
        font.setBold(True)
        p.setFont(font)
        text = "ממוקם" if self._checked else "לא ממוקם"
        text_rect = QRect(2, 0, w - knob_d - 6, h) if self._checked else QRect(knob_d + 6, 0, w - knob_d - 6, h)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)
        p.end()


# ── Inventory Screen ──────────────────────────────────────────────────────────

class InventoryScreen(QWidget):
    def __init__(self, username: str):
        super().__init__()
        self.username        = username
        self._rows: list         = []
        self._filtered_rows: list = []
        self._page               = 0
        self._sort_col           = -1
        self._sort_asc           = True
        self._build_ui()
        self._refresh_filter_combos()
        self.lbl_count.setText("טוען נתונים...")
        QTimer.singleShot(0, self._search)   # defer so the window appears before the table is built

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        self.lbl_title = QLabel("שלב 1: בחירת איתור להעברה")
        self.lbl_title.setObjectName("section_title")
        self.lbl_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.lbl_title)

        # ── Filter row ────────────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        def _filter_card(label_text, widget):
            card = QFrame(); card.setObjectName("card")
            lay  = QVBoxLayout(card)
            lay.setContentsMargins(12, 8, 12, 8); lay.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            lay.addWidget(lbl); lay.addWidget(widget)
            return card

        self.txt_pn = QLineEdit()
        self.txt_pn.setMinimumHeight(36)
        self.txt_pn.textChanged.connect(self._search)

        self.txt_cat = QLineEdit()
        self.txt_cat.setMinimumHeight(36)
        self.txt_cat.textChanged.connect(self._search)

        self.cmb_bin = QComboBox(); self.cmb_bin.setMinimumHeight(36)
        self.cmb_bin.setEditable(True)
        self.cmb_bin.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        _cb = QCompleter(self.cmb_bin.model(), self.cmb_bin)
        _cb.setFilterMode(Qt.MatchFlag.MatchContains)
        _cb.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        _cb.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.cmb_bin.setCompleter(_cb)
        self.cmb_bin.currentIndexChanged.connect(self._search)

        self.cmb_dest = QComboBox(); self.cmb_dest.setMinimumHeight(36)
        self.cmb_dest.setEditable(True)
        self.cmb_dest.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        _cd = QCompleter(self.cmb_dest.model(), self.cmb_dest)
        _cd.setFilterMode(Qt.MatchFlag.MatchContains)
        _cd.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        _cd.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.cmb_dest.setCompleter(_cd)
        self.cmb_dest.currentIndexChanged.connect(self._search)

        self.cmb_filter_pallet = QComboBox(); self.cmb_filter_pallet.setMinimumHeight(36)
        self.cmb_filter_pallet.setEditable(True)
        self.cmb_filter_pallet.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        _cp = QCompleter(self.cmb_filter_pallet.model(), self.cmb_filter_pallet)
        _cp.setFilterMode(Qt.MatchFlag.MatchContains)
        _cp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        _cp.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.cmb_filter_pallet.setCompleter(_cp)
        self.cmb_filter_pallet.currentIndexChanged.connect(self._search)

        filter_row.addWidget(_filter_card("🔍  מס' קטלוגי", self.txt_pn))
        filter_row.addWidget(_filter_card("🏷  PN",          self.txt_cat))
        filter_row.addWidget(_filter_card("📍  איתור",       self.cmb_bin))
        filter_row.addWidget(_filter_card("🎯  אזור יעד",    self.cmb_dest))
        filter_row.addWidget(_filter_card("📦  משטח",        self.cmb_filter_pallet))

        btn_clear = QPushButton("נקה")
        btn_clear.setObjectName("btn_secondary")
        btn_clear.setMinimumHeight(36)
        btn_clear.setFixedWidth(70)
        btn_clear.clicked.connect(self._clear_filter)
        filter_row.addWidget(btn_clear)

        self.chk_no_pallet = QCheckBox("ללא משטח")
        self.chk_no_pallet.setFont(QFont("Segoe UI", 11))
        self.chk_no_pallet.toggled.connect(self._search)
        filter_row.addWidget(self.chk_no_pallet)

        root.addLayout(filter_row)

        tbl_title = QLabel("תוצאות חיפוש איתורים ופריטים")
        tbl_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        tbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(tbl_title)

        # ── Table ─────────────────────────────────────────────────────────────
        self.table = QTableWidget(0, NUM_COLS)
        self.table.setHorizontalHeaderLabels([
            "✓", "מס' קטלוגי", "PN", "סדרה", "WBS", "כמות",
            "איתור", "אזור\nיעד", "ממוקם", "משטח\nמשויך", "חיווי",
            "כמות\nמעודכנת", "הערות",
        ])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(COL_CHK,     QHeaderView.ResizeMode.Fixed);        hh.resizeSection(COL_CHK,     36)
        hh.setSectionResizeMode(COL_PN,      QHeaderView.ResizeMode.Interactive);  hh.resizeSection(COL_PN,      95)
        hh.setSectionResizeMode(COL_CAT,     QHeaderView.ResizeMode.Interactive);  hh.resizeSection(COL_CAT,     110)
        hh.setSectionResizeMode(COL_BATCH,   QHeaderView.ResizeMode.Interactive);  hh.resizeSection(COL_BATCH,   90)
        hh.setSectionResizeMode(COL_WBS,     QHeaderView.ResizeMode.Interactive);  hh.resizeSection(COL_WBS,     90)
        hh.setSectionResizeMode(COL_QTY,     QHeaderView.ResizeMode.Interactive);  hh.resizeSection(COL_QTY,     65)
        hh.setSectionResizeMode(COL_BIN,     QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(COL_DEST,    QHeaderView.ResizeMode.Interactive);  hh.resizeSection(COL_DEST,    80)
        hh.setSectionResizeMode(COL_STOCK,   QHeaderView.ResizeMode.Interactive);  hh.resizeSection(COL_STOCK,   100)
        hh.setSectionResizeMode(COL_PAL,     QHeaderView.ResizeMode.Interactive);  hh.resizeSection(COL_PAL,     90)
        hh.setSectionResizeMode(COL_IND,     QHeaderView.ResizeMode.Fixed);        hh.resizeSection(COL_IND,     52)
        hh.setSectionResizeMode(COL_UPD_QTY, QHeaderView.ResizeMode.Interactive); hh.resizeSection(COL_UPD_QTY, 80)
        hh.setSectionResizeMode(COL_NOTES,   QHeaderView.ResizeMode.Fixed);        hh.resizeSection(COL_NOTES,   52)
        hh.setMinimumSectionSize(36)
        hh.setSortIndicatorShown(True)
        hh.sectionClicked.connect(self._on_header_clicked)

        self.table.horizontalHeader().setDefaultSectionSize(90)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemClicked.connect(self._on_item_clicked)
        root.addWidget(self.table, 1)

        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("font-size: 12px; color: #757575;")
        root.addWidget(self.lbl_count)

        # ── Paging bar ────────────────────────────────────────────────────────
        paging_row = QHBoxLayout()
        paging_row.setSpacing(10)
        self.btn_prev = QPushButton("הקודם  ◄")
        self.btn_prev.setObjectName("btn_secondary")
        self.btn_prev.setMinimumHeight(30)
        self.btn_prev.setFixedWidth(110)
        self.btn_prev.clicked.connect(self._prev_page)
        self.lbl_page = QLabel("")
        self.lbl_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_page.setStyleSheet("font-size: 12px; color: #424242; font-weight: bold;")
        self.btn_next = QPushButton("►  הבא")
        self.btn_next.setObjectName("btn_secondary")
        self.btn_next.setMinimumHeight(30)
        self.btn_next.setFixedWidth(110)
        self.btn_next.clicked.connect(self._next_page)
        paging_row.addWidget(self.btn_prev)
        paging_row.addStretch()
        paging_row.addWidget(self.lbl_page)
        paging_row.addStretch()
        paging_row.addWidget(self.btn_next)
        root.addLayout(paging_row)

        # ── Pallet assignment bar ─────────────────────────────────────────────
        assign_frame = QFrame(); assign_frame.setObjectName("card")
        assign_lay = QHBoxLayout(assign_frame)
        assign_lay.setContentsMargins(14, 10, 14, 10); assign_lay.setSpacing(12)

        lbl_pal = QLabel("מס' משטח:")
        lbl_pal.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        self.cmb_pallet = QComboBox()
        self.cmb_pallet.setEditable(True)
        self.cmb_pallet.setMinimumHeight(36)
        self.cmb_pallet.setFixedWidth(160)

        self.btn_assign = QPushButton("שייך פריטים נבחרים")
        self.btn_assign.setMinimumHeight(36)
        self.btn_assign.setEnabled(False)
        self.btn_assign.clicked.connect(self._assign_selected)

        self.btn_detach = QPushButton("נתק שיוך")
        self.btn_detach.setObjectName("btn_secondary")
        self.btn_detach.setMinimumHeight(36)
        self.btn_detach.setEnabled(False)
        self.btn_detach.clicked.connect(self._detach_selected)

        self.lbl_selected = QLabel("לא נבחרו פריטים")
        self.lbl_selected.setStyleSheet("font-size: 12px; color: #757575;")

        assign_lay.addWidget(lbl_pal)
        assign_lay.addWidget(self.cmb_pallet)
        assign_lay.addWidget(self.btn_assign)
        assign_lay.addWidget(self.btn_detach)
        assign_lay.addStretch()
        assign_lay.addWidget(self.lbl_selected)

        btn_print = QPushButton("🖨   הדפסה")
        btn_print.setMinimumHeight(42)
        btn_print.setMinimumWidth(140)
        btn_print.setObjectName("btn_secondary")
        btn_print.setFont(QFont("Segoe UI", 11))
        btn_print.clicked.connect(self._print_data)
        assign_lay.addWidget(btn_print)

        root.addWidget(assign_frame)

        legend = QLabel("** מקרא חיוויים **\n❗ = PN קיים במספר איתורים שונים")
        legend.setObjectName("status_label")
        legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(legend)

    # ── Data helpers ──────────────────────────────────────────────────────────

    def _refresh_filter_combos(self):
        prev = self.cmb_bin.currentText()
        self.cmb_bin.blockSignals(True)
        self.cmb_bin.clear()
        self.cmb_bin.addItem("")
        for v in db.get_distinct_values("Bin"):
            self.cmb_bin.addItem(v)
        idx = self.cmb_bin.findText(prev)
        self.cmb_bin.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_bin.blockSignals(False)

        prev_d = self.cmb_dest.currentText()
        self.cmb_dest.blockSignals(True)
        self.cmb_dest.clear()
        self.cmb_dest.addItem("")
        for v in db.get_distinct_values("DestArea"):
            self.cmb_dest.addItem(v)
        idx_d = self.cmb_dest.findText(prev_d)
        self.cmb_dest.setCurrentIndex(idx_d if idx_d >= 0 else 0)
        self.cmb_dest.blockSignals(False)

        prev_p = self.cmb_filter_pallet.currentText()
        self.cmb_filter_pallet.blockSignals(True)
        self.cmb_filter_pallet.clear()
        self.cmb_filter_pallet.addItem("", None)
        for p in db.get_pallets():
            self.cmb_filter_pallet.addItem(str(p["PalletID"]), p["PalletID"])
        idx_p = self.cmb_filter_pallet.findText(prev_p)
        self.cmb_filter_pallet.setCurrentIndex(idx_p if idx_p >= 0 else 0)
        self.cmb_filter_pallet.blockSignals(False)

    def _refresh_pallet_combo(self):
        pallets = db.get_pallets()
        labels  = [""] + [str(p["PalletID"]) for p in pallets]
        prev    = self.cmb_pallet.currentText()
        self.cmb_pallet.blockSignals(True)
        self.cmb_pallet.clear()
        self.cmb_pallet.addItem("", None)
        for p in pallets:
            self.cmb_pallet.addItem(str(p["PalletID"]), p["PalletID"])
        completer = QCompleter(labels, self.cmb_pallet)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.cmb_pallet.setCompleter(completer)
        idx = self.cmb_pallet.findText(prev)
        if idx >= 0:
            self.cmb_pallet.setCurrentIndex(idx)
        self.cmb_pallet.blockSignals(False)
        # keep filter pallet combo in sync
        self._refresh_filter_pallet(pallets)

    def _refresh_filter_pallet(self, pallets=None):
        if pallets is None:
            pallets = db.get_pallets()
        prev = self.cmb_filter_pallet.currentData()
        self.cmb_filter_pallet.blockSignals(True)
        self.cmb_filter_pallet.clear()
        self.cmb_filter_pallet.addItem("", None)
        for p in pallets:
            self.cmb_filter_pallet.addItem(str(p["PalletID"]), p["PalletID"])
        idx = self.cmb_filter_pallet.findData(prev)
        self.cmb_filter_pallet.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_filter_pallet.blockSignals(False)

    def _search(self):
        pn       = self.txt_pn.text().strip()
        cat      = self.txt_cat.text().strip()
        bin_     = self.cmb_bin.currentText() if self.cmb_bin.currentIndex() > 0 else ""
        dest     = self.cmb_dest.currentText() if self.cmb_dest.currentIndex() > 0 else ""
        pallet_f = self.cmb_filter_pallet.currentData()

        self.lbl_title.setText(
            f"שלב 1: בחירת איתור להעברה ({bin_})" if bin_
            else "שלב 1: בחירת איתור להעברה"
        )

        all_rows = db.get_inventory_with_assignments(pn, bin_=bin_, cat=cat, dest_area=dest)
        if pallet_f is not None:
            all_rows = [r for r in all_rows if r["PalletID"] == pallet_f]
        if self.chk_no_pallet.isChecked():
            all_rows = [r for r in all_rows if r["PalletID"] is None]

        self._filtered_rows = [{k: r[k] for k in r.keys()} for r in all_rows]
        self._page = 0
        self._apply_sort()
        self._refresh_pallet_combo()
        self._show_page()

    def _clear_filter(self):
        self.txt_pn.clear()
        self.txt_cat.clear()
        for cmb in (self.cmb_bin, self.cmb_dest, self.cmb_filter_pallet):
            cmb.blockSignals(True); cmb.setCurrentIndex(0); cmb.blockSignals(False)
        self.chk_no_pallet.blockSignals(True)
        self.chk_no_pallet.setChecked(False)
        self.chk_no_pallet.blockSignals(False)
        self._search()

    # ── Paging ────────────────────────────────────────────────────────────────

    def _show_page(self):
        total  = len(self._filtered_rows)
        pages  = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        start  = self._page * PAGE_SIZE
        end    = min(start + PAGE_SIZE, total)
        self._rows = self._filtered_rows[start:end]

        if total == 0:
            self.lbl_page.setText("")
        else:
            self.lbl_page.setText(f"עמוד {self._page + 1} מתוך {pages}  |  שורות {start + 1}–{end} מתוך {total}")
        self.btn_prev.setEnabled(self._page > 0)
        self.btn_next.setEnabled(end < total)
        self._populate_table()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._show_page()

    def _next_page(self):
        if (self._page + 1) * PAGE_SIZE < len(self._filtered_rows):
            self._page += 1
            self._show_page()

    # ── Sorting ───────────────────────────────────────────────────────────────

    def _on_header_clicked(self, col: int):
        if col not in _SORT_KEY:
            return
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        order = Qt.SortOrder.AscendingOrder if self._sort_asc else Qt.SortOrder.DescendingOrder
        self.table.horizontalHeader().setSortIndicator(col, order)
        self._apply_sort()
        self._page = 0
        self._show_page()

    def _apply_sort(self):
        if self._sort_col in _SORT_KEY:
            key_fn = _SORT_KEY[self._sort_col]
            self._filtered_rows.sort(key=key_fn, reverse=not self._sort_asc)

    # ── Table population ──────────────────────────────────────────────────────

    def _populate_table(self):
        rows  = self._rows
        n     = len(rows)
        total = len(self._filtered_rows)

        self.lbl_count.setText(f"נמצאו: {total} שורות")

        pn_to_bins = {}
        for row in rows:
            pn_to_bins.setdefault(row["Pn"], set()).add(row["Bin"])
        multi_loc_pns = {pn for pn, bins in pn_to_bins.items() if len(bins) > 1}

        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(n)

        for r, row in enumerate(rows):
            inv_id    = row["InventoryID"]
            pallet_id = row["PalletID"]
            is_stock  = bool(row["IsInStock"])

            def mk(text, bold=False):
                item = QTableWidgetItem(str(text) if text is not None else "")
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                if bold:
                    f = item.font(); f.setBold(True); item.setFont(f)
                return item

            # ── Checkbox: only checkable when ממוקם ──────────────────────────
            chk_item = QTableWidgetItem()
            chk_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            if is_stock:
                chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            else:
                chk_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, COL_CHK, chk_item)

            qty_val = row["Qty"]
            qty_str = (str(int(qty_val)) if qty_val == int(qty_val) else str(qty_val)) if qty_val is not None else ""

            self.table.setItem(r, COL_PN,    mk(row["Pn"],  bold=True))
            self.table.setItem(r, COL_CAT,   mk(row["Cat"]))
            self.table.setItem(r, COL_BATCH, mk(row["Batch"]))
            self.table.setItem(r, COL_WBS,   mk(row["WBS"]))
            self.table.setItem(r, COL_QTY,   mk(qty_str))
            self.table.setItem(r, COL_BIN,   mk(row["Bin"]))
            self.table.setItem(r, COL_DEST,  mk(row["DestArea"]))

            # ── Toggle switch ─────────────────────────────────────────────────
            toggle = ToggleSwitch(is_stock)
            toggle.toggled.connect(
                lambda val, iid=inv_id, row_r=r: self._on_toggle(iid, row_r, val)
            )
            self.table.setCellWidget(r, COL_STOCK, toggle)

            # ── Assigned pallet ───────────────────────────────────────────────
            self.table.setItem(r, COL_PAL, mk(str(pallet_id) if pallet_id is not None else "–"))

            # ── Indicator ❗ ───────────────────────────────────────────────────
            is_dup = row["Pn"] in multi_loc_pns
            if is_dup:
                ind = mk("❗")
                ind.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                ind.setForeground(QBrush(COLOR_IND))
            else:
                ind = mk("")
            self.table.setItem(r, COL_IND, ind)

            # ── Updated qty (click to edit) ────────────────────────────────────
            upd_qty = row["UpdatedQty"]
            upd_str = ""
            if upd_qty is not None:
                upd_str = str(int(upd_qty)) if upd_qty == int(upd_qty) else str(upd_qty)
            upd_item = QTableWidgetItem(upd_str)
            upd_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            upd_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if upd_qty is not None:
                upd_item.setBackground(QBrush(QColor("#FFF9C4")))
                upd_item.setFont(QFont("Segoe UI", -1, QFont.Weight.Bold))
            else:
                upd_item.setToolTip("לחץ לעדכון כמות")
            self.table.setItem(r, COL_UPD_QTY, upd_item)

            # ── Notes indicator ────────────────────────────────────────────────
            notes_val = row["Notes"] or ""
            notes_item = QTableWidgetItem("📝" if notes_val else "")
            notes_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            notes_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if notes_val:
                notes_item.setToolTip(notes_val[:120] + ("…" if len(notes_val) > 120 else ""))
            self.table.setItem(r, COL_NOTES, notes_item)

            self.table.setRowHeight(r, 46)

        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self._update_selection_label()

    # ── Toggle ↔ Checkbox sync ────────────────────────────────────────────────

    def _on_toggle(self, inv_id: int, row: int, val: bool):
        db.set_is_in_stock(inv_id, val, self.username)
        chk = self.table.item(row, COL_CHK)
        if chk:
            self.table.blockSignals(True)
            if val:
                chk.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                chk.setCheckState(Qt.CheckState.Checked)
            else:
                chk.setCheckState(Qt.CheckState.Unchecked)
                chk.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.blockSignals(False)
        self._update_selection_label()

    # ── Item change (checkbox guard) ──────────────────────────────────────────

    def _on_item_changed(self, item: QTableWidgetItem):
        if item.column() != COL_CHK:
            return
        if item.checkState() == Qt.CheckState.Checked:
            toggle = self.table.cellWidget(item.row(), COL_STOCK)
            if toggle and not toggle.isChecked():
                self.table.blockSignals(True)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.table.blockSignals(False)
                return
        self._update_selection_label()

    def _on_item_clicked(self, item: QTableWidgetItem):
        col = item.column()
        if col == COL_IND and item.text() == "❗":
            self._show_dup_popup(item.row())
        elif col == COL_NOTES:
            self._edit_notes(item.row())
        elif col == COL_UPD_QTY:
            self._edit_updated_qty(item.row())

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _update_selection_label(self):
        count = self._checked_count()
        if count == 0:
            self.lbl_selected.setText("לא נבחרו פריטים")
            self.btn_assign.setEnabled(False)
            self.btn_detach.setEnabled(False)
        else:
            self.lbl_selected.setText(f"נבחרו: {count} פריטים")
            self.btn_assign.setEnabled(True)
            self.btn_detach.setEnabled(True)

    def _checked_count(self) -> int:
        return sum(1 for r in range(self.table.rowCount()) if self._is_checked(r))

    def _is_checked(self, row: int) -> bool:
        item = self.table.item(row, COL_CHK)
        return item is not None and item.checkState() == Qt.CheckState.Checked

    def _selected_inv_ids(self) -> list[int]:
        return [
            self._rows[r]["InventoryID"]
            for r in range(self.table.rowCount())
            if r < len(self._rows) and self._is_checked(r)
        ]

    # ── Pallet assignment ─────────────────────────────────────────────────────

    def _assign_selected(self):
        inv_ids = self._selected_inv_ids()
        if not inv_ids:
            return
        pallet_id = self.cmb_pallet.currentData()
        if pallet_id is None:
            QMessageBox.warning(self, "שגיאה", "יש לבחור מספר משטח לפני השיוך.")
            return

        # Collect DestArea of selected items
        selected_rows = [self._rows[r] for r in range(self.table.rowCount())
                         if r < len(self._rows) and self._is_checked(r)]
        new_areas = {str(r["DestArea"]).strip() for r in selected_rows if r.get("DestArea")}

        # Collect DestArea of items already on this pallet
        existing_areas = {str(it["DestArea"]).strip()
                          for it in db.get_pallet_items(pallet_id) if it["DestArea"]}

        all_areas = new_areas | existing_areas
        if len(all_areas) > 1:
            areas_list = "\n".join(f"• {a}" for a in sorted(all_areas))
            reply = QMessageBox.question(
                self, "⚠  אזהרה – אזורי יעד שונים",
                f"על המשטח {pallet_id} יהיו פריטים עם אזורי יעד שונים:\n\n"
                f"{areas_list}\n\n"
                "האם להמשיך בשיוך?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        db.assign_items_to_pallet(inv_ids, pallet_id, self.username)
        self._search()

    def _detach_selected(self):
        inv_ids = self._selected_inv_ids()
        if not inv_ids:
            return
        for iid in inv_ids:
            db.detach_item_from_pallet(iid, self.username)
        self._search()

    # ── Duplicate popup ───────────────────────────────────────────────────────

    def _show_dup_popup(self, r: int):
        if r >= len(self._rows):
            return
        row  = self._rows[r]
        pn   = row["Pn"]
        bins = sorted({rd["Bin"] for rd in self._rows if rd["Pn"] == pn and rd["Bin"]})
        lines = [f"פריט: {pn}", f"קיים ב-{len(bins)} איתורים שונים:"]
        for b in bins:
            lines.append(f"  • {b}")
        QMessageBox.information(self, "חיווי מספר איתורים", "\n".join(lines))

    # ── Updated qty dialog ────────────────────────────────────────────────────

    def _edit_updated_qty(self, r: int):
        if r >= len(self._rows):
            return
        row    = self._rows[r]
        inv_id = row["InventoryID"]
        pn     = row["Pn"] or ""
        cur    = row["UpdatedQty"]
        cur_str = (str(int(cur)) if cur is not None and cur == int(cur) else str(cur)) if cur is not None else ""

        dlg = QDialog(self)
        dlg.setWindowTitle(f"כמות מעודכנת – {pn}")
        dlg.setMinimumWidth(320)
        dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        lay = QVBoxLayout(dlg)
        lbl = QLabel(f"מק\"ט: {row['Cat'] or ''}  |  PN: {pn}  |  כמות מקורית: {row['Qty'] or ''}")
        lbl.setStyleSheet("font-size:12px; color:#616161;")
        lay.addWidget(lbl)
        txt = QLineEdit(cur_str)
        txt.setMinimumHeight(38)
        txt.setPlaceholderText("הכנס כמות (ריק = נקה עדכון)")
        txt.selectAll()
        validator = QDoubleValidator(0, 999999999, 4, txt)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        txt.setValidator(validator)
        lay.addWidget(txt)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Save).setText("שמור")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        txt.returnPressed.connect(dlg.accept)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        raw = txt.text().strip()
        cell = self.table.item(r, COL_UPD_QTY)
        if raw == "":
            db.set_updated_qty(inv_id, None, self.username)
            self._rows[r]["UpdatedQty"] = None
            if cell:
                self.table.blockSignals(True)
                cell.setText("")
                cell.setBackground(QBrush(QColor("transparent")))
                f = cell.font(); f.setBold(False); cell.setFont(f)
                cell.setToolTip("לחץ לעדכון כמות")
                self.table.blockSignals(False)
        else:
            try:
                qty = float(raw.replace(",", "."))
            except ValueError:
                QMessageBox.warning(self, "שגיאה", f"ערך לא חוקי: {raw}")
                return
            db.set_updated_qty(inv_id, qty, self.username)
            self._rows[r]["UpdatedQty"] = qty
            disp = str(int(qty)) if qty == int(qty) else str(qty)
            if cell:
                self.table.blockSignals(True)
                cell.setText(disp)
                cell.setBackground(QBrush(QColor("#FFF9C4")))
                f = cell.font(); f.setBold(True); cell.setFont(f)
                cell.setToolTip("")
                self.table.blockSignals(False)

    # ── Notes dialog ─────────────────────────────────────────────────────────

    def _edit_notes(self, r: int):
        if r >= len(self._rows):
            return
        row    = self._rows[r]
        inv_id = row["InventoryID"]
        pn     = row["Pn"] or ""
        dlg    = QDialog(self)
        dlg.setWindowTitle(f"הערה – {pn}")
        dlg.setMinimumSize(420, 220)
        dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        lay = QVBoxLayout(dlg)
        lbl = QLabel(f"מק\"ט: {row['Cat'] or ''}  |  PN: {pn}  |  Bin: {row['Bin'] or ''}")
        lbl.setStyleSheet("font-size:12px; color:#616161;")
        lay.addWidget(lbl)
        txt = QTextEdit()
        txt.setPlainText(row["Notes"] or "")
        txt.setMinimumHeight(100)
        lay.addWidget(txt)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Save).setText("שמור")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_note = txt.toPlainText().strip()
        db.set_item_notes(inv_id, new_note, self.username)
        self._rows[r]["Notes"] = new_note or None
        notes_item = self.table.item(r, COL_NOTES)
        if notes_item:
            self.table.blockSignals(True)
            notes_item.setText("📝" if new_note else "")
            notes_item.setToolTip(new_note[:120] + ("…" if len(new_note) > 120 else "") if new_note else "")
            self.table.blockSignals(False)

    # ── Print ─────────────────────────────────────────────────────────────────

    def _print_data(self):
        pallets = db.get_pallets()
        dlg = QDialog(self)
        dlg.setWindowTitle("בחר משטח להדפסה")
        dlg.setMinimumWidth(320)
        dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("בחר משטח:"))
        cmb = QComboBox(); cmb.setMinimumHeight(36)
        cmb.addItem("הכל (כל השורות המוצגות)", "__all__")
        for p in pallets:
            cmb.addItem(str(p["PalletID"]), p["PalletID"])
        lay.addWidget(cmb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("הדפס")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        sel = cmb.currentData()
        if sel == "__all__":
            rows_to_print = self._rows
        else:
            rows_to_print = db.get_inventory_by_pallet(sel)
            rows_to_print = [dict(r) for r in rows_to_print]

        if not rows_to_print:
            QMessageBox.information(self, "הדפסה", "אין נתונים להדפסה")
            return

        def safe_get(row, key):
            try:
                return row[key]
            except (KeyError, IndexError):
                return ""

        fixed_cols = [
            ("מס' קטלוגי", "Cat"), ("PN", "Pn"), ("סדרה", "Batch"),
            ("WBS", "WBS"), ("כמות", "Qty"), ("איתור", "Bin"),
            ("אזור יעד", "DestArea"), ("משטח", "PalletID"),
            ("כמות מעודכנת", "UpdatedQty"), ("הערות", "Notes"),
        ]

        html  = """<html><head><meta charset="utf-8">
        <style>
          body { font-family: Arial, sans-serif; direction: rtl; font-size: 14pt; }
          h2   { text-align: center; font-size: 17pt; margin-bottom: 6px; }
          table { border-collapse: collapse; width: 100%; }
          th { background: #1976D2; color: white; padding: 4px 6px; border: 1px solid #90A4AE; }
          td { padding: 3px 6px; border: 1px solid #CFD8DC; }
          tr:nth-child(even) { background: #F5F9FF; }
          .upd { background: #FFF9C4; font-weight: bold; }
        </style></head><body>"""
        title = f"משטח: {sel}" if sel != "__all__" else "כל השורות המוצגות"
        html += f"<h2>דוח מלאי – {title}</h2>"
        html += "<table><tr>"
        for hdr, _ in fixed_cols:
            html += f"<th>{hdr}</th>"
        html += "</tr>"
        for row in rows_to_print:
            upd_qty = safe_get(row, "UpdatedQty")
            html += "<tr>"
            for _, key in fixed_cols:
                val = safe_get(row, key)
                val = "" if val is None else str(val)
                css = ' class="upd"' if key == "UpdatedQty" and upd_qty is not None else ""
                html += f"<td{css}>{val}</td>"
            html += "</tr>"
        html += "</table></body></html>"

        from PyQt6.QtGui import QTextDocument, QPageLayout
        printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)

        def render(p):
            doc = QTextDocument()
            doc.setHtml(html)
            doc.print(p)

        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle("תצוגה לפני הדפסה")
        preview.paintRequested.connect(render)
        preview.resize(1100, 700)
        preview.exec()

    # ── Public refresh ────────────────────────────────────────────────────────

    def refresh(self):
        self._refresh_filter_combos()
        self._search()
