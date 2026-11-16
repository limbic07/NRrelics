"""Virtual result table; full solutions and replacement variants live on disk."""
import hashlib
import json
import sqlite3
import tempfile
import weakref
import time
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QTimer, Signal, QPointF, QSize, QEvent
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QTextDocument, QPalette
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTableView, QHeaderView, QDoubleSpinBox, QSlider, QWidget, QStyledItemDelegate,
    QStyleOptionButton, QStyle, QApplication, QSpinBox, QScrollArea, QMenu,
    QListWidget, QListWidgetItem, QDialogButtonBox, QTextBrowser, QTableWidget,
    QTableWidgetItem, QMessageBox, QStyleOptionViewItem)
from qfluentwidgets import PushButton, PrimaryPushButton, isDarkTheme
from core.loadout_metrics import equivalence_key, dominates, pareto_rows, SURVIVAL_SCENARIOS


RICH_TEXT_ROLE = Qt.UserRole + 1


def change_html(text, beneficial):
    """Keep the sign/wording as well as color; a negative term addition is bad."""
    if isDarkTheme():
        foreground, background = ('#85e6b3', '#183b2c') if beneficial else ('#ffada8', '#492828')
    else:
        foreground, background = ('#12613b', '#e2f4e9') if beneficial else ('#a32020', '#fde9e7')
    return f'<span style="color:{foreground};background-color:{background};font-weight:600">{escape(text)}</span>'


def result_dialog_layout(dialog):
    # Match the existing preset editor, using the application's live palette.
    dialog.setStyleSheet('''
        QDialog { background: palette(window); }
        QListWidget, QTextBrowser, QTableView {
            background: palette(base); color: palette(text);
            border: 1px solid palette(mid); border-radius: 9px; padding: 6px;
        }
        QListWidget::item { min-height: 32px; padding: 8px; }
        QListWidget::item:selected { background: palette(highlight); color: palette(highlighted-text); }
        QHeaderView::section { padding: 8px; }
    ''')
    layout=QVBoxLayout(dialog);layout.setContentsMargins(24,20,24,20);layout.setSpacing(12)
    return layout


def close_footer(layout, dialog):
    footer=QHBoxLayout();footer.addStretch()
    close=PushButton('关闭');close.setMinimumWidth(100);close.clicked.connect(dialog.accept)
    footer.addWidget(close);layout.addLayout(footer)


class DifferenceDelegate(QStyledItemDelegate):
    """Paint per-line differences without allocating widgets for result rows."""
    def document(self, option, index, width):
        document=QTextDocument();document.setDefaultFont(option.font);document.setDocumentMargin(0)
        color=option.palette.color(QPalette.Text).name()
        document.setDefaultStyleSheet(f'body {{color:{color};}} p {{margin-top:4px;margin-bottom:4px;}}')
        document.setHtml(index.data(RICH_TEXT_ROLE));document.setTextWidth(max(30,width-20))
        return document

    def paint(self,painter,option,index):
        if not index.data(RICH_TEXT_ROLE):return super().paint(painter,option,index)
        styled=QStyleOptionViewItem(option);self.initStyleOption(styled,index);styled.text=''
        style=option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem,styled,painter,option.widget)
        document=self.document(option,index,option.rect.width())
        painter.save();painter.setClipRect(option.rect)
        painter.translate(option.rect.left()+10,option.rect.top()+6)
        document.drawContents(painter);painter.restore()

    def sizeHint(self,option,index):
        if not index.data(RICH_TEXT_ROLE):return super().sizeHint(option,index)
        width=self.parent().columnWidth(index.column())
        document=self.document(option,index,width)
        return QSize(width,max(40,int(document.size().height()+13)))


class ReferenceHeader(QHeaderView):
    """A handful of real buttons, confined to the comparison table header."""
    referenceClicked = Signal(int)

    def __init__(self, parent, labels):
        super().__init__(Qt.Horizontal, parent)
        self.buttons=[]
        for column, label in enumerate(labels, 1):
            button=PushButton(label,self.viewport());button.setCheckable(True)
            button.setToolTip('将这套方案设为本窗口的参照')
            button.clicked.connect(lambda checked=False,c=column:self.referenceClicked.emit(c))
            color='#244c54' if isDarkTheme() else '#dff3f5'
            button.setStyleSheet(f'QPushButton:checked {{background:{color};color:palette(text);font-weight:600;}}')
            self.buttons.append(button)
        self.setMinimumHeight(max(48,self.fontMetrics().height()+24))
        self.sectionResized.connect(self._place_buttons)
        self.geometriesChanged.connect(self._place_buttons)

    def _place_buttons(self,*_):
        for column,button in enumerate(self.buttons,1):
            button.setGeometry(self.sectionViewportPosition(column)+4,4,max(0,self.sectionSize(column)-8),self.height()-8)

    def scrollContentsBy(self,dx,dy):
        super().scrollContentsBy(dx,dy);self._place_buttons()


class ResultModel(QAbstractTableModel):

    def __init__(self, metrics, parent=None):
        super().__init__(parent)
        self.metrics = metrics
        self.rows = []
        self.damage_index = 0
        self.columns = ['score'] + list(range(min(3, len(metrics.scenarios)))) + list(metrics.survival_scenarios) + ['functions','negatives','detail']
        self.baseline = None
        self.checked = set()
        self.temp = tempfile.TemporaryDirectory(prefix='nrrelic-results-')
        self.db = sqlite3.connect(str(Path(self.temp.name) / 'results.sqlite'))
        self.cleanup = weakref.finalize(self, self._cleanup, self.db, self.temp)
        self.db.execute('CREATE TABLE results (id INTEGER PRIMARY KEY, signature TEXT, payload TEXT)')
        self.db.execute('CREATE INDEX signatures ON results(signature)')
        self.signatures = {}

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self, parent=QModelIndex()): return len(self.columns)
    def title(self, key):
        if isinstance(key, int): return self.metrics.scenarios[key][0].replace('／','\n').replace('无指定目标状态','无指定\n目标状态') + ('\n差值 / 百分点' if self.baseline is not None else '\n增幅 %')
        if key in SURVIVAL_SCENARIOS:
            return self.metrics.survival_scenarios[key][0].replace('／','\n') + ('\n差值 / 百分点' if self.baseline is not None else '\n增幅 %')
        return {'score':'综合评分\n勾选对比',
                'functions':'功能词条差异' if self.baseline is not None else '功能性词条',
                'negatives':'负面词条差异' if self.baseline is not None else '有效负面词条','detail':'查看详情'}[key]

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole: return self.title(self.columns[section])

    def number(self, row, key):
        item=self.rows[row]; m=item['metrics']
        value=item['score'] if key=='score' else m['damage'][key] if isinstance(key,int) else m['survival'][key] if key in SURVIVAL_SCENARIOS else m.get(key,0)
        if self.baseline is not None and key not in ('score','detail'):
            base=self.rows[self.baseline]['metrics']
            value-=base['damage'][key] if isinstance(key,int) else base['survival'][key] if key in SURVIVAL_SCENARIOS else base[key]
        return value

    def terms(self,row,key):
        return self.rows[row]['metrics'].get('functional_terms' if key=='functions' else 'negative_terms',{})

    def changes(self,row,key):
        current=self.terms(row,key); base=self.terms(self.baseline,key)
        lines=[]
        for sign in (1,-1):
            for name in sorted(current.keys()|base.keys()):
                delta=current.get(name,0)-base.get(name,0)
                if delta*sign>0:
                    text=('＋' if delta>0 else '－')+name+(f' ×{abs(delta)}' if abs(delta)>1 else '')
                    lines.append((text, (delta>0) if key=='functions' else (delta<0)))
        return lines

    def difference(self,row,key):
        return '\n'.join(text for text,_ in self.changes(row,key)) or '无差异'

    def set_baseline(self,row):
        self.baseline=row
        if self.rows: self.dataChanged.emit(self.index(0,0),self.index(len(self.rows)-1,self.columnCount()-1))
        self.headerDataChanged.emit(Qt.Horizontal,0,self.columnCount()-1)

    def set_scenarios(self,indices):
        self.beginResetModel()
        self.columns=['score']+list(indices)+['functions','negatives','detail']
        self.endResetModel()

    def flags(self,index):
        flags=super().flags(index)
        return flags|Qt.ItemIsUserCheckable if index.column()==0 else flags

    def setData(self,index,value,role=Qt.EditRole):
        if role==Qt.CheckStateRole and index.column()==0:
            if value==Qt.Checked or value==Qt.Checked.value:self.checked.add(index.row())
            else:self.checked.discard(index.row())
            self.dataChanged.emit(index,index,[Qt.CheckStateRole]);return True
        return False

    def values(self, row):
        return [self.number(row,key) for key in ('score',self.damage_index,'survival_physical','functions','negatives')] + [self.rows[row]['count']]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        key=self.columns[index.column()]; row=index.row()
        if role==Qt.CheckStateRole and index.column()==0:return Qt.Checked if row in self.checked else Qt.Unchecked
        if role==Qt.TextAlignmentRole and (isinstance(key,int) or key in SURVIVAL_SCENARIOS or key=='score'):
            return Qt.AlignCenter
        if role==Qt.BackgroundRole and row==self.baseline:return QBrush(QColor('#244c54' if isDarkTheme() else '#dff3f5'))
        if role == Qt.ToolTipRole:
            if key=='negatives':return '按负面等级判定，包含“几乎无负面”的词条；改为正面等级后才不计入。差异按具体词条和数量比较。'
            if key in SURVIVAL_SCENARIOS:return '按实际装备的生命上限和对应减伤计算；蓝泪仅在流派有效时生成场景和计算。不扣除负面词条造成的抗伤损失。'
            pending = self.rows[index.row()]['metrics']['pending']
            return ('未计入数值（换算规则待确认）：\n' + '\n'.join(pending)) if pending else '按有效词条计算；不代表游戏中的实际伤害。'
        if role == Qt.UserRole: return self.number(row,key)
        if role == RICH_TEXT_ROLE and key in ('functions','negatives') and self.baseline is not None:
            return ''.join('<p>'+change_html(text,good)+'</p>' for text,good in self.changes(row,key)) or '<p>无差异</p>'
        if role == Qt.DisplayRole:
            if key=='detail': return '查看详情 ›'
            if key in ('functions','negatives') and self.baseline is not None:return self.difference(row,key)
            value=self.number(row,key)
            if isinstance(key,int) or key in SURVIVAL_SCENARIOS:return f'{value:+.1f}' if self.baseline is not None else f'{value:.1f}%'
            return str(value)+('　基准' if key=='score' and row==self.baseline else '')

    def append(self, solutions):
        for solution in solutions:
            key = hashlib.sha256(repr(equivalence_key(solution)).encode()).hexdigest()
            cursor = self.db.execute('INSERT INTO results(signature,payload) VALUES (?,?)',
                                     (key, json.dumps(solution, ensure_ascii=False)))
            if key in self.signatures:
                row = self.signatures[key]
                self.rows[row]['count'] += 1
                self.dataChanged.emit(self.index(row, self.columnCount()-1), self.index(row, self.columnCount()-1))
            else:
                row = len(self.rows)
                self.beginInsertRows(QModelIndex(), row, row)
                self.rows.append(dict(id=cursor.lastrowid, signature=key, score=solution['score'], count=1,
                                      metrics=self.metrics.evaluate(solution)))
                self.signatures[key] = row
                self.endInsertRows()
        self.db.commit()

    def solution(self, row, variant=0):
        value = self.db.execute('SELECT payload FROM results WHERE signature=? ORDER BY id LIMIT 1 OFFSET ?',
                                (self.rows[row]['signature'], variant)).fetchone()
        return json.loads(value[0])

    def retain(self, indices):
        keep = set(indices)
        removed = [r['signature'] for i, r in enumerate(self.rows) if i not in keep]
        if not removed:
            return 0
        # Delete payloads before resetting the model; failed disk writes leave UI intact.
        with self.db:
            self.db.executemany('DELETE FROM results WHERE signature=?', ((s,) for s in removed))
        self.beginResetModel()
        remap = {old: new for new, old in enumerate(indices)}
        self.rows = [self.rows[i] for i in indices]
        self.signatures = {r['signature']: i for i, r in enumerate(self.rows)}
        self.checked = {remap[i] for i in self.checked if i in remap}
        self.baseline = remap.get(self.baseline)
        self.endResetModel()
        return len(removed)

    def close(self):
        if self.db is not None:
            self.beginResetModel()
            self.cleanup(); self.db = None
            self.rows.clear(); self.signatures.clear()
            self.endResetModel()

    @staticmethod
    def _cleanup(db, temp):
        db.close()
        temp.cleanup()


class ResultFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bounds = [(float('-inf'), float('inf'))] * 4
        self.column_bounds = {}
        self.setSortRole(Qt.UserRole)

    def filterAcceptsRow(self, row, parent):
        values = self.sourceModel().values(row)[1:5]
        return (all(lo <= round(value, 1) <= hi for value, (lo, hi) in zip(values, self.bounds)) and
                all(lo<=round(self.sourceModel().number(row,key),1)<=hi for key,(lo,hi) in self.column_bounds.items()))


class DetailButtonDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(option.fontMetrics.horizontalAdvance('查看详情')+32,
                     max(36, option.fontMetrics.height()+16))

    def paint(self, painter, option, index):
        button = QStyleOptionButton()
        button.rect = option.rect.adjusted(6, 4, -6, -4)
        height = max(28, option.fontMetrics.height()+8)
        if button.rect.height() > height:
            button.rect.setTop(option.rect.center().y()-height//2)
            button.rect.setHeight(height)
        button.text = '查看详情'
        button.palette = option.palette
        button.fontMetrics = option.fontMetrics
        button.state = QStyle.State_Enabled
        painter.save();painter.setFont(option.font)
        QApplication.style().drawControl(QStyle.CE_PushButton, button, painter)
        painter.restore()


class RangeBar(QWidget):
    changed = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(28)
        self.maximum = 0; self.low = 0; self.high = 0; self.handle = None
        self.setAccessibleName('范围筛选；可使用上方数字输入精确调整')

    def x(self, value):
        return 10 + (self.width()-20) * value / max(1, self.maximum)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        y = self.height()/2
        p.setPen(QPen(self.palette().mid().color(), 3))
        p.drawLine(QPointF(10, y), QPointF(self.width()-10, y))
        p.setPen(QPen(self.palette().highlight().color(), 4))
        p.drawLine(QPointF(self.x(self.low), y), QPointF(self.x(self.high), y))
        p.setBrush(self.palette().highlight()); p.setPen(Qt.NoPen)
        for value in (self.low, self.high): p.drawEllipse(QPointF(self.x(value), y), 6, 9)

    def mousePressEvent(self, event):
        x = event.position().x()
        self.handle = 0 if abs(x-self.x(self.low)) < abs(x-self.x(self.high)) else 1
        self.mouseMoveEvent(event)

    def mouseMoveEvent(self, event):
        if self.handle is None: return
        value = max(0, min(self.maximum, round((event.position().x()-10)/max(1, self.width()-20)*self.maximum)))
        if self.handle == 0: self.low = min(value, self.high)
        else: self.high = max(value, self.low)
        self.update(); self.changed.emit(self.handle, self.low if self.handle == 0 else self.high)

    def mouseReleaseEvent(self, event): self.handle = None


class RangeControl(QWidget):
    """Two handles with exact numerical inputs; sliders use observed-value ranks."""
    def __init__(self, title, changed, parent=None):
        super().__init__(parent)
        self.values = [0.0]
        self.touched = False
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(title))
        line = QHBoxLayout(); self.spins = []; self.sliders = []
        for caption in ('最低', '最高'):
            box = QDoubleSpinBox(); box.setRange(-100000, 1000000); box.setDecimals(1)
            line.addWidget(QLabel(caption)); line.addWidget(box); self.spins.append(box)
        layout.addLayout(line)
        self.bar = RangeBar()
        self.bar.changed.connect(lambda index, value: self.spins[index].setValue(self.values[value]))
        layout.addWidget(self.bar)
        self.spins[0].setValue(-100000); self.spins[1].setValue(1000000)
        for box in self.spins: box.valueChanged.connect(self._edited)
        self.changed = changed

    def _edited(self):
        import bisect
        self.touched = True
        self.bar.low = min(len(self.values)-1, bisect.bisect_left(self.values, self.spins[0].value()))
        self.bar.high = max(0, bisect.bisect_right(self.values, self.spins[1].value())-1)
        self.bar.update()
        self.changed()

    def update_values(self, values, reset=False):
        import math
        self.values = sorted(set(round(v, 1) for v in values)) or [0.0]
        self.bar.maximum = len(self.values)-1
        if reset or not self.touched:
            for i, spin in enumerate(self.spins):
                spin.blockSignals(True)
                spin.setValue(math.floor(min(values, default=0)*10)/10 if i == 0 else math.ceil(max(values, default=0)*10)/10)
                spin.blockSignals(False)
            self.touched = False
        import bisect
        self.bar.low = min(len(self.values)-1, bisect.bisect_left(self.values, self.spins[0].value()))
        self.bar.high = max(0, bisect.bisect_right(self.values, self.spins[1].value())-1)
        self.bar.update()


class DeepResultsDialog(QDialog):
    stop_requested = Signal()
    resume_requested = Signal()

    def __init__(self, metrics, rows_by_id, detail_factory, parent=None):
        super().__init__(parent)
        self.setWindowTitle('深度优化 · 配装比较')
        self.resize(1200, 760)
        self.rows_by_id = rows_by_id; self.detail_factory = detail_factory
        self.detail = None
        self.releasing = False
        self.pruning = None; self.prune_pending = False
        self.prune_reason = None
        self.column_prune = None
        self.prune_prefix = 0; self.prune_size = 0; self.pruned_count = 0
        self.live_timer = QTimer(self); self.live_timer.setSingleShot(True); self.live_timer.setInterval(250)
        self.live_timer.timeout.connect(lambda:self.prune_dominated(None))
        self.prune_timer = QTimer(self); self.prune_timer.setInterval(10)
        self.prune_timer.timeout.connect(self._prune_step)
        self.model = ResultModel(metrics, self)
        self.proxy = ResultFilter(self); self.proxy.setSourceModel(self.model)
        layout = QVBoxLayout(self)
        self.status = QLabel('后台搜索中；可以先筛选、排序和查看已有结果。')
        layout.addWidget(self.status)
        toolbar=QHBoxLayout()
        scenes=PushButton('选择伤害/抗伤列'); scenes.clicked.connect(self._choose_scenarios)
        compare=PushButton('对比勾选方案');compare.clicked.connect(self._compare)
        self.baseline_button=PushButton('设为基准');self.baseline_button.clicked.connect(self._set_selected_baseline)
        self.clear_checked=PushButton('取消所有勾选');self.clear_checked.clicked.connect(self._clear_checked)
        for button in (scenes,compare,self.baseline_button,self.clear_checked):toolbar.addWidget(button)
        layout.addLayout(toolbar)
        self.hint=QLabel('右键列名筛选；点击表头排序；勾选2～4套对比；双击单元格查看具体词条。')
        self.hint.setWordWrap(True);layout.addWidget(self.hint)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(120)
        self.timer.timeout.connect(self._filter)
        self.refresh_timer = QTimer(self); self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(250)
        self.refresh_timer.timeout.connect(self._refresh_results)
        self.ranges=[]
        self.table = QTableView(); self.table.setModel(self.proxy)
        self.table.setProperty('rightClickCheckColumn', 0)
        self.table.viewport().installEventFilter(self)
        self.table.setSortingEnabled(True); self.table.sortByColumn(0, Qt.DescendingOrder)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setAlternatingRowColors(True); self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self._column_filter)
        self.table.setContextMenuPolicy(Qt.NoContextMenu)
        self.table.clicked.connect(lambda index: self._details(index.row()) if self.model.columns[index.column()]=='detail' else None)
        self.table.doubleClicked.connect(self._cell_details)
        self.table.verticalScrollBar().valueChanged.connect(self._resize_visible_rows)
        self.table.horizontalScrollBar().valueChanged.connect(self._resize_visible_rows)
        self.table.verticalHeader().setResizeContentsPrecision(-1)
        self.table.verticalHeader().setMinimumSectionSize(max(36,self.table.fontMetrics().height()+16))
        self.table.horizontalHeader().sectionResized.connect(self._resize_visible_rows)
        self._configure_columns()
        layout.addWidget(self.table, 1)
        footer = QHBoxLayout()
        self.stop = PushButton('停止搜索，保留结果')
        self.can_resume=False
        self.stop.clicked.connect(lambda:self.resume_requested.emit() if self.can_resume else self.stop_requested.emit())
        footer.addWidget(self.stop)
        self.prune_selected=PushButton('按当前显示列清理')
        self.prune_selected.setToolTip('按勾选显示的伤害/抗伤列，以及综合评分、具体功能和负面词条，清理已加载的严格占优方案。忽略隐藏列，不受行筛选或基准影响；不改变续搜进度。')
        self.prune_selected.clicked.connect(self._prune_visible_columns)
        footer.addWidget(self.prune_selected)
        reset = PushButton('重置筛选'); reset.clicked.connect(self.reset_filters)
        self.back = PushButton('返回（继续后台搜索）'); self.back.clicked.connect(self.hide)
        footer.addWidget(reset); footer.addStretch(); footer.addWidget(self.back); layout.addLayout(footer)

    def set_search_state(self,running,can_resume=False):
        self.can_resume=can_resume
        self.stop.setText('继续搜索至上限' if can_resume else '停止搜索，保留结果' if running else '搜索已结束')
        self.stop.setEnabled(running or can_resume)
        self.back.setText('返回（继续后台搜索）' if running else '返回')

    def showEvent(self, event):
        super().showEvent(event)
        self.setStyleSheet('QDialog {background: '+('#202020' if isDarkTheme() else '#f5f5f5')+';} '
                           'QTableView {background: palette(base); color: palette(text); border: 1px solid palette(mid);}')

    def _configure_columns(self):
        fm=self.table.fontMetrics()
        numeric=max(104,fm.horizontalAdvance('差值 / 百分点')+16)
        score=max(104,fm.horizontalAdvance('100　基准')+40)
        detail=max(110,fm.horizontalAdvance('查看详情')+32)
        fixed=score+detail+numeric*sum(isinstance(k,int) or k in SURVIVAL_SCENARIOS for k in self.model.columns)
        text_width=max(145,(self.table.viewport().width()-fixed)//2)
        if not hasattr(self,'difference_delegate'):self.difference_delegate=DifferenceDelegate(self.table)
        for col,key in enumerate(self.model.columns):
            self.table.setItemDelegateForColumn(col,None)
            if key in ('functions','negatives'):self.table.setItemDelegateForColumn(col,self.difference_delegate)
            width=(text_width if key in ('functions','negatives') else detail if key=='detail' else score if key=='score' else numeric)
            self.table.setColumnWidth(col,width)
        if not hasattr(self,'detail_delegate'):self.detail_delegate=DetailButtonDelegate(self.table)
        self.table.setItemDelegateForColumn(self.model.columnCount()-1,self.detail_delegate)
        lines=max(self.model.title(k).count('\n')+1 for k in self.model.columns)
        self.table.horizontalHeader().setMinimumHeight(lines*fm.lineSpacing()+14)

    def eventFilter(self, watched, event):
        if watched is self.table.viewport():
            if event.type()==QEvent.Resize:
                QTimer.singleShot(0,self._fit_columns)
            elif event.type() in (QEvent.MouseButtonPress,QEvent.MouseButtonRelease) and event.button()==Qt.RightButton:
                if event.type()==QEvent.MouseButtonRelease:
                    index=self.table.indexAt(event.position().toPoint())
                    if index.isValid():
                        first=self.proxy.mapToSource(index).siblingAtColumn(0)
                        state=Qt.Unchecked if first.row() in self.model.checked else Qt.Checked
                        self.model.setData(first,state,Qt.CheckStateRole)
                return True
        return super().eventFilter(watched,event)

    def _fit_columns(self):
        if self.model.db is not None:
            self._configure_columns();self._resize_visible_rows()

    def _choose_scenarios(self):
        dialog=QDialog(self);dialog.setWindowTitle('选择伤害/抗伤列');dialog.resize(820,620)
        layout=result_dialog_layout(dialog)
        layout.addWidget(QLabel('勾选要显示的伤害与抗伤场景，可同时选择多项。蓝泪仅在流派有效时提供。'))
        choices=QListWidget();choices.setWordWrap(True)
        scenes=[(i,label) for i,(label,_) in enumerate(self.model.metrics.scenarios)] + [(k,label) for k,(label,_) in self.model.metrics.survival_scenarios.items()]
        for key,label in scenes:
            item=QListWidgetItem(label);item.setFlags(item.flags()|Qt.ItemIsUserCheckable)
            item.setData(Qt.UserRole,key)
            item.setCheckState(Qt.Checked if key in self.model.columns else Qt.Unchecked);choices.addItem(item)
        layout.addWidget(choices)
        footer=QHBoxLayout();footer.addStretch()
        cancel=PushButton('取消');apply=PrimaryPushButton('应用')
        for button in (cancel,apply):button.setMinimumWidth(100);footer.addWidget(button)
        cancel.clicked.connect(dialog.reject);apply.clicked.connect(dialog.accept);layout.addLayout(footer)
        try:
            if dialog.exec():
                indices=[choices.item(i).data(Qt.UserRole) for i in range(choices.count()) if choices.item(i).checkState()==Qt.Checked]
                self.model.set_scenarios(indices)
                self.proxy.column_bounds={k:v for k,v in self.proxy.column_bounds.items() if k in self.model.columns}
                self._configure_columns();self._filter()
        finally:dialog.deleteLater()

    def _column_filter(self,position):
        col=self.table.horizontalHeader().logicalIndexAt(position)
        if col<0:return
        key=self.model.columns[col]
        if key=='detail':return
        dialog=QDialog(self);dialog.setWindowTitle('列筛选');dialog.resize(530,180)
        layout=QVBoxLayout(dialog)
        title=self.model.title(key).replace('\n','／')
        if key in ('functions','negatives'):
            title+='（数量差：负数比基准少，正数比基准多）' if self.model.baseline is not None else '（按当前方案词条总数量筛选）'
        control=RangeControl(title,lambda:None)
        control.update_values([self.model.number(i,key) for i in range(len(self.model.rows))])
        if key in self.proxy.column_bounds:
            for spin,value in zip(control.spins,self.proxy.column_bounds[key]):spin.setValue(value)
        layout.addWidget(control)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel);layout.addWidget(buttons)
        clear=buttons.addButton('清除此列筛选',QDialogButtonBox.ResetRole)
        def reset():self.proxy.column_bounds.pop(key,None);dialog.reject();self._filter()
        clear.clicked.connect(reset);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject)
        try:
            if dialog.exec():
                lo,hi=(s.value() for s in control.spins)
                if lo>hi:QMessageBox.information(self,'筛选范围','最低值不能大于最高值。');return
                self.proxy.column_bounds[key]=(lo,hi);self._filter()
        finally:dialog.deleteLater()

    def refresh_ranges(self):
        self._filter()

    def reset_filters(self):
        self.proxy.column_bounds.clear();self._filter()

    def _filter(self):
        self.proxy.invalidateFilter()
        self._resize_visible_rows()
        base=f'基准：方案 {self.model.baseline+1}；伤害/抗伤显示百分点差值，＋新增、－缺少。绿色：增加功能／减少负面；红色：减少功能／增加负面。' if self.model.baseline is not None else '未设置基准，显示绝对增幅与词条数量。'
        filters='；'.join(self.model.title(k).replace('\n','／')+f' [{lo:g}, {hi:g}]' for k,(lo,hi) in self.proxy.column_bounds.items())
        self.hint.setText(base+' 右键单元格勾选整行；右键列名筛选，双击单元格看明细。'+(' 筛选：'+filters if filters else ''))

    def _resize_visible_rows(self,*_):
        if getattr(self,'_resizing',False):return
        self._resizing=True
        try:
            first=max(0,self.table.rowAt(0));last=self.table.rowAt(self.table.viewport().height()-1)
            if last<0:last=min(self.proxy.rowCount()-1,first+40)
            for row in range(first,last+1):
                self.table.resizeRowToContents(row)
                self.table.setRowHeight(row,max(self.table.rowHeight(row),self.table.fontMetrics().height()+16,36))
        finally:self._resizing=False

    def _set_selected_baseline(self):
        if self.model.baseline is not None:
            self._baseline_changed(None);return
        if len(self.model.checked)!=1:
            QMessageBox.information(self,'设置基准','请只勾选一套方案作为基准。可右键单元格勾选整行。');return
        self._baseline_changed(next(iter(self.model.checked)))

    def _clear_checked(self):
        self.model.checked.clear()
        if self.model.rowCount():
            self.model.dataChanged.emit(self.model.index(0,0),self.model.index(self.model.rowCount()-1,0),[Qt.CheckStateRole])

    def _baseline_changed(self,row):
        self.model.set_baseline(row)
        self.baseline_button.setText('取消基准' if row is not None else '设为基准')
        # Absolute ranges and percentage-point ranges are not interchangeable.
        self.proxy.column_bounds={k:v for k,v in self.proxy.column_bounds.items() if k=='score'}
        self.proxy.bounds=[(float('-inf'),float('inf'))]*4
        self._configure_columns();self._filter()

    def _cell_details(self,index):
        if not index.isValid():return
        row=self.proxy.mapToSource(index).row();key=self.model.columns[index.column()]
        if key=='detail':self._details(index.row());return
        solution=self.model.solution(row);m=self.model.rows[row]['metrics']
        lines=[]
        if key=='score':
            for relic in solution['relics']:
                lines.extend(f'{name}：{points:+d} 分' for name,points in relic.get('affix_points',{}).items() if points)
                if relic.get('official_adjustment'):lines.append(f"官方遗物整体修正：{relic['official_adjustment']:+d} 分")
        elif key in ('functions','negatives'):
            lines=[name+(f' ×{count}' if count>1 else '') for name,count in self.model.terms(row,key).items()]
        else:
            scopes=self.model.metrics.scenarios[key][1] if isinstance(key,int) else SURVIVAL_SCENARIOS[key][1]
            lines=[f'{name}：{value*100:g}%' for name,tag,value in m['active_effects'] if tag in scopes]
        if not lines:lines=['没有对应的有效词条。']
        sections=[('当前方案 · 有效词条',[escape(line) for line in lines])]
        if self.model.baseline is not None and key!='score':
            if key in ('functions','negatives'):
                differences=[change_html(text,good) for text,good in self.model.changes(row,key)] or ['无差异']
            else:
                delta=self.model.number(row,key)
                caption=f'{delta:+.1f} 个百分点'
                differences=[change_html(caption,delta>0) if abs(delta)>1e-8 else '与基准相同（0.0 个百分点）']
            sections.append((f'相对基准 · 方案 {self.model.baseline+1}',differences))
            if isinstance(key,int) or key in SURVIVAL_SCENARIOS:
                base=self.model.rows[self.model.baseline]['metrics']
                sections.append(('基准方案对应词条',[escape(f'{name}：{value*100:g}%') for name,tag,value in base['active_effects'] if tag in scopes] or ['没有对应的有效词条。']))
        if m['pending']:sections.append(('尚未计入数值',[escape(name) for name in m['pending']]))
        dialog=QDialog(self);dialog.setWindowTitle(f'方案 {row+1} · '+self.model.title(key).replace('\n','／'));dialog.resize(860,620)
        layout=result_dialog_layout(dialog)
        heading=QLabel(self.model.title(key).replace('\n','／'));heading.setWordWrap(True);layout.addWidget(heading)
        text=QTextBrowser();text.setFont(dialog.font())
        document=text.document();document.setDefaultFont(dialog.font());document.setDocumentMargin(12)
        html=''.join('<h3>'+escape(title)+'</h3><table width="100%" cellpadding="10" cellspacing="0">'+
            ''.join('<tr><td>'+line+'</td></tr>' for line in content)+'</table>' for title,content in sections)
        text.setHtml(html);layout.addWidget(text)
        close_footer(layout,dialog)
        dialog.setAttribute(Qt.WA_DeleteOnClose);dialog.open()
        return dialog

    def _compare(self):
        selected=sorted(self.model.checked)
        if not 2<=len(selected)<=4:
            QMessageBox.information(self,'选择对比方案','请在综合评分列勾选2～4套配装。');return
        dialog=QDialog(self);dialog.setWindowTitle('配装对比');dialog.resize(1150,750)
        reference=self.model.baseline if self.model.baseline in selected else selected[0]
        layout=result_dialog_layout(dialog)
        hint=QLabel()
        hint.setWordWrap(True);layout.addWidget(hint)
        table=QTableWidget(0,len(selected)+1);table.setHorizontalHeaderLabels(['对比项目']+[f'方案 {i+1}'+('（参照）' if i==reference else '') for i in selected])
        header=ReferenceHeader(table,[f'方案 {i+1}' for i in selected]);table.setHorizontalHeader(header)
        table.setEditTriggers(QTableView.NoEditTriggers);table.setWordWrap(True);table.setShowGrid(False);table.setAlternatingRowColors(True)
        table.setTextElideMode(Qt.ElideNone);table.verticalHeader().hide()
        table.setItemDelegate(DifferenceDelegate(table));table.verticalHeader().setMinimumSectionSize(44)
        entries=[]
        for key in self.model.columns:
            if key in ('functions','negatives','detail'):continue
            values=[]
            for row in selected:
                r=self.model.rows[row];v=r['score'] if key=='score' else r['metrics']['damage'][key] if isinstance(key,int) else r['metrics']['survival'][key]
                values.append(v)
            entries.append((self.model.metrics.scenarios[key][0] if isinstance(key,int) else '综合评分' if key=='score' else self.model.metrics.survival_scenarios[key][0],values,key))
        for key,label in (('functions','功能'),('negatives','负面')):
            names=sorted(set().union(*(self.model.terms(r,key) for r in selected)))
            for name in names:entries.append((label+'｜'+name,[self.model.terms(r,key).get(name,0) for r in selected],key))
        table.setRowCount(len(entries))
        # Keep this popup's values independent of ongoing pruning in the owner.
        def set_reference(column):
            reference=selected[column-1]
            hint.setText(f'以方案 {reference+1} 为对比参照；点击顶部方案按钮可切换。显示绝对值及差值；绿色表示增益更多／负面更少，红色表示相反。')
            for j,button in enumerate(header.buttons,1):
                label=f'方案 {selected[j-1]+1}'+('（参照）' if j==column else '')
                button.setChecked(j==column);button.setText(label)
                table.horizontalHeaderItem(j).setText(label)
            table.setUpdatesEnabled(False)
            try:
                for i,(label,values,key) in enumerate(entries):
                    table.setItem(i,0,QTableWidgetItem(label))
                    base=values[column-1]
                    for j,value in enumerate(values,1):
                        numeric=isinstance(key,int) or key in SURVIVAL_SCENARIOS
                        caption=f'{value:.1f}%' if numeric else str(value)
                        delta=value-base
                        description=(f'{delta:+.1f} 个百分点' if numeric else f'{delta:+g}'+(' 项' if key in ('functions','negatives') else ' 分'))
                        html='<p>'+escape(caption)+'</p>'
                        if abs(delta)>1e-8:
                            html+='<p>'+change_html(description,delta<0 if key=='negatives' else delta>0)+'</p>'
                            caption+='\n'+description
                        item=QTableWidgetItem(caption);item.setData(RICH_TEXT_ROLE,html)
                        table.setItem(i,j,item)
                table.resizeRowsToContents()
            finally:table.setUpdatesEnabled(True)
        header.referenceClicked.connect(set_reference)
        set_reference(selected.index(reference)+1)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Interactive);table.setColumnWidth(0,390)
        table.resizeRowsToContents();layout.addWidget(table)
        table.horizontalHeader().sectionResized.connect(table.resizeRowsToContents)
        close_footer(layout,dialog)
        dialog.setAttribute(Qt.WA_DeleteOnClose);dialog.open()
        return dialog

    def append(self, result):
        self.proxy.setDynamicSortFilter(False)
        self.model.append(result['solutions'])
        if self.prune_prefix < len(self.model.rows) and self.pruning is None and not self.live_timer.isActive():
            self.live_timer.start()
        if self.detail is None and not self.refresh_timer.isActive():
            self.refresh_timer.start()

    def _refresh_results(self):
        if self.detail is not None: return
        self.proxy.setDynamicSortFilter(True)
        self.refresh_ranges()

    def _details(self, position):
        if self.detail is not None:
            self.detail.raise_(); self.detail.activateWindow()
            return
        if position < 0 or position >= self.proxy.rowCount(): return
        # Snapshot visible ordering, so a new batch cannot move the user's next/previous target.
        order = [self.proxy.mapToSource(self.proxy.index(i, 0)).row() for i in range(self.proxy.rowCount())]
        self.timer.stop(); self.refresh_timer.stop()
        self.prune_timer.stop(); self.live_timer.stop()
        self.proxy.setDynamicSortFilter(False)
        self.detail = SingleResultDialog(self, order, position)
        self.detail.finished.connect(self._detail_closed)
        self.detail.open()

    def _detail_closed(self):
        detail = self.detail; self.detail = None
        if detail is not None: detail.deleteLater()
        if self.releasing:return
        self._refresh_results()
        if self.pruning is not None:self.prune_timer.start()
        elif self.prune_pending or self.prune_prefix<len(self.model.rows):self.prune_dominated(self.prune_reason)

    def _prune_visible_columns(self):
        # Restart comparison over all retained rows; an all-scene frontier is
        # not necessarily a frontier for a smaller set of displayed scenes.
        self.prune_timer.stop()
        if self.pruning is not None:self.pruning.close()
        self.pruning=None
        self.column_prune=tuple(self.model.columns)
        self.prune_selected.setEnabled(False)
        self.prune_dominated(None)

    def prune_dominated(self, reason='搜索已停止'):
        if reason is not None:self.prune_reason=reason
        if self.pruning is not None:return
        self.live_timer.stop()
        if self.detail is not None:
            self.prune_pending=True
            if self.prune_reason:
                self.status.setText(f'{self.prune_reason}；关闭当前详情后自动清理严格占优方案。')
            return
        self.prune_pending=False
        self.refresh_timer.stop();self.timer.stop()
        self.prune_size=len(self.model.rows)
        # Freeze just row references: arrivals can append while this batch yields.
        self.pruning=pareto_rows(tuple(self.model.rows),0 if self.column_prune is not None else self.prune_prefix,self.column_prune)
        if self.column_prune is not None:
            self.status.setText('正在按当前显示列清理严格占优方案；搜索进度保持不变…')
        elif self.prune_reason:
            self.status.setText(f'{self.prune_reason}，正在清理严格占优方案（比较全部伤害场景及具体词条）…')
        self.prune_timer.start()

    def _prune_step(self):
        if self.detail is not None:
            self.prune_timer.stop();return
        deadline=time.monotonic()+.006
        try:
            while time.monotonic()<deadline:next(self.pruning)
        except StopIteration as done:
            self.prune_timer.stop();self.pruning=None
            by_columns=self.column_prune is not None
            self.column_prune=None;self.prune_selected.setEnabled(True)
            before=self.model.baseline
            current=self.proxy.mapToSource(self.table.currentIndex())
            signature=self.model.rows[current.row()]['signature'] if current.isValid() else None
            # New arrivals were not part of this pass; preserve them for the next.
            indices=done.value+list(range(self.prune_size,len(self.model.rows)))
            try:removed=self.model.retain(indices)
            except Exception as exc:
                self.status.setText('清理未完成，已有结果保留：'+str(exc));return
            # Equal visible metrics can still dominate in hidden metrics: the
            # next automatic pass must recheck this prefix with its own rules.
            self.prune_prefix=0 if by_columns else len(done.value)
            self.pruned_count+=removed
            if before is not None and self.model.baseline is None:
                self._baseline_changed(None)
            self._refresh_results()
            if removed and signature in self.model.signatures:
                self.table.setCurrentIndex(self.proxy.mapFromSource(self.model.index(self.model.signatures[signature],0)))
            if (len(done.value) if by_columns else self.prune_prefix)<len(self.model.rows):self.live_timer.start()
            if by_columns:
                self.status.setText(f'按当前显示列清理完成，移除 {removed} 组，保留 {len(self.model.rows)} 组；搜索及继续搜索不受影响。')
            elif self.prune_reason:
                suffix='' if self.prune_reason=='已找完达标方案' else '当前为已搜索的部分结果。'
                self.status.setText(f'{self.prune_reason}；累计移除 {self.pruned_count} 组严格占优方案，保留 {len(self.model.rows)} 组。'+suffix)
            elif removed:
                self.status.setText(f'实时清理已移除 {self.pruned_count} 组严格占优方案，当前保留 {len(self.model.rows)} 组；搜索继续。')
        except Exception as exc:
            self.prune_timer.stop();self.pruning=None
            self.column_prune=None;self.prune_selected.setEnabled(True)
            self.status.setText('实时清理未完成，已有结果保留：'+str(exc))

    def release(self):
        self.releasing=True
        self.live_timer.stop();self.prune_pending=False;self.prune_timer.stop();self.pruning=None
        if self.detail is not None: self.detail.close()
        self.timer.stop(); self.refresh_timer.stop()
        self.hide(); self.model.close(); self.deleteLater()


class SingleResultDialog(QDialog):
    """One window and one scroll area, no nested event loop or result dialog."""
    def __init__(self, owner, order, position):
        super().__init__(owner)
        self.owner=owner; self.order=order; self.position=position
        self.setWindowTitle('配装详情')
        self.resize(1480, 850)
        layout=QVBoxLayout(self)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        controls=QHBoxLayout()
        self.previous=PushButton('‹ 上一套'); self.following=PushButton('下一套 ›')
        self.caption=QLabel(); self.variants=QSpinBox(); self.variants.setPrefix('同效替换 ')
        close=PushButton('关闭'); close.clicked.connect(self.accept)
        for widget in (self.previous,self.caption,self.variants,self.following,close): controls.addWidget(widget)
        layout.addLayout(controls)
        self.previous.clicked.connect(lambda:self.move(-1)); self.following.clicked.connect(lambda:self.move(1))
        self.previous.setShortcut(Qt.Key_Left); self.following.setShortcut(Qt.Key_Right)
        self.render_timer=QTimer(self); self.render_timer.setSingleShot(True); self.render_timer.setInterval(50)
        self.render_timer.timeout.connect(self.render)
        self.variants.valueChanged.connect(lambda _: self.render_timer.start())
        self.move(0); self.render_timer.stop(); self.render()

    def move(self, delta):
        self.position=max(0,min(len(self.order)-1,self.position+delta))
        self.variants.blockSignals(True)
        self.variants.setRange(1,self.owner.model.rows[self.order[self.position]]['count'])
        self.variants.setValue(1); self.variants.blockSignals(False)
        self.caption.setText(f'{self.position+1} / {len(self.order)}')
        self.previous.setEnabled(self.position>0)
        self.following.setEnabled(self.position+1<len(self.order))
        self.render_timer.start()

    def render(self):
        solution=self.owner.model.solution(self.order[self.position],self.variants.value()-1)
        content=self.owner.detail_factory.solution_widget(solution,self.owner.rows_by_id)
        # QScrollArea owns and deletes its previous widget immediately.
        self.scroll.setWidget(content)

    def done(self, result):
        self.render_timer.stop()
        super().done(result)
