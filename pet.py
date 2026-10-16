# -*- coding: utf-8 -*-
"""
小蕾米埃尔桌宠 —— 实时反映 Claude Code 的工作状态。

事件来源：Claude Code hook 把原始事件写进 status.json，
本程序轮询该文件，按 pet_config.json 的 events/states 映射表切换动作。

启动： python pet.py
"""
import json
import os
import sys
import time

from PySide6.QtCore import Qt, QTimer, QSize, QPoint, QRect
from PySide6.QtGui import QMovie, QAction, QIcon, QPixmap, QPainter, QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QMenu,
    QSystemTrayIcon, QSizePolicy,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "pet_config.json")
STATUS_PATH = os.path.join(BASE_DIR, "status.json")
LOG_PATH = os.path.join(BASE_DIR, "pet.log")

# 所有 gif 统一按高度归一化后居中在这个基础画框里，避免切换动作时窗口跳动
BOX_W, BOX_H = 320, 298


def log(msg):
    """往 pet.log 追加一行。桌宠是被 hook 后台拉起的，输出看不到，出错只能靠这个查。"""
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 256 * 1024:
            with open(LOG_PATH, "w", encoding="utf-8") as f:
                f.write("")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%m-%d %H:%M:%S')}  [pid {os.getpid()}]  {msg}\n")
    except Exception:
        pass


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# 状态机
# --------------------------------------------------------------------------
class PetBrain:
    """把「事件」翻译成「当前该播哪个动作」。规则对应 config 里的 playback 段。"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.states = cfg.get("states", {})
        self.events = {e["event"]: e for e in cfg.get("events", [])}
        self.default = cfg.get("defaultState", "idle")
        self.playback = cfg.get("playback", {})
        tb = cfg.get("turn", {})
        self.turn_start = set(tb.get("startEvents", ["UserPromptSubmit", "SessionStart"]))
        self.turn_end = set(tb.get("endEvents", ["Stop", "SessionEnd"]))

        self.current = self.default
        self.previous = self.default
        self.detail = ""

        self._one_shot_until = 0.0      # monotonic 截止时间
        self._one_shot_restore = None
        self._last_seen_ts = None       # status.json 里的时间戳，用来判重
        self._last_event_at = time.monotonic()
        self._cooldowns = {}            # event -> monotonic
        self._pending = None            # 被一次性动画挡住的事件，播完再处理
        self._quiet = set()             # 回合已结束的会话 id，不再接受"工作中"类事件

    # -- 对外 ------------------------------------------------------------
    def reload(self, cfg):
        self.cfg = cfg
        self.states = cfg.get("states", {})
        self.events = {e["event"]: e for e in cfg.get("events", [])}
        self.default = cfg.get("defaultState", "idle")
        self.playback = cfg.get("playback", {})
        tb = cfg.get("turn", {})
        self.turn_start = set(tb.get("startEvents", ["UserPromptSubmit", "SessionStart"]))
        self.turn_end = set(tb.get("endEvents", ["Stop", "SessionEnd"]))

    def force(self, state, detail=""):
        """从菜单手动切状态（调试用）。"""
        if state not in self.states:
            return None
        self._enter(state, detail)
        return state

    def feed(self, payload):
        """喂一个来自 status.json 的事件；返回新的状态名，没变化就返回 None。"""
        if not isinstance(payload, dict):
            return None
        ts = payload.get("ts")

        # 手动注入优先，不受下面的乱序过滤影响
        if payload.get("manual"):
            st = payload.get("state")
            if st in self.states:
                self._last_seen_ts = ts
                self._last_event_at = time.monotonic()
                self._enter(st, payload.get("detail") or "", reason="手动注入")
                return st

        if ts is not None:
            if ts == self._last_seen_ts:
                return None                 # 同一条事件，已经处理过
            if self._last_seen_ts is not None and ts < self._last_seen_ts:
                return None                 # 乱序到达的旧事件（async hook 可能并发）
            self._last_seen_ts = ts

        name = payload.get("event")
        detail = payload.get("detail") or ""
        if not name:
            return None

        ev = self.events.get(name)
        if ev is None:
            return None                     # 未配置的事件，忽略

        sid = payload.get("session_id") or ""

        # 回合状态的记账必须早于冷却判断 —— 冷却只是防抖，不该让某个会话的
        # Stop 被丢掉，否则它之后迟到的工作中事件就挡不住了（多开会话时容易撞上）
        if name in self.turn_start:
            if sid in self._quiet:
                log(f"回合开始 (sid={sid[:8] or '-'}) → 解除安静")
            self._quiet.discard(sid)
        elif name in self.turn_end:
            log(f"回合结束 (sid={sid[:8] or '-'}) → 标记安静　当前安静集合={sorted(x[:8] or '-' for x in self._quiet)}")
            self._quiet.add(sid)

        # 关键修复：回合已经结束的会话，不再接受"工作中"类事件（states 里标了 working 的）。
        # hook 是 async 后台执行的，写入顺序不保证 —— Stop 之后迟到的
        # PostToolUse / SubagentStop 会把已经回到待机的桌宠重新推回"思考中"，
        # 而循环状态不会自己超时，于是卡住直到睡着。
        if self.states.get(ev.get("state"), {}).get("working") and sid in self._quiet:
            log(f"忽略迟到的工作中事件 {name}（会话 {sid[:8]} 的回合已结束）")
            return None

        now = time.monotonic()
        cd = ev.get("cooldownMs", 0) or 0
        last = self._cooldowns.get(name)
        if cd and last is not None and (now - last) * 1000.0 < cd:
            return None
        self._cooldowns[name] = now
        self._last_event_at = now

        return self._request(ev.get("state"), ev.get("priority", 50), detail,
                             reason=f"事件 {name} sid={sid[:8] or '-'}")

    def tick(self):
        """处理一次性动画结束、以及长时间无事件后进入睡眠。"""
        now = time.monotonic()

        if self._one_shot_until and now >= self._one_shot_until:
            target = self._one_shot_restore or self.default
            self._one_shot_until = 0.0
            self._one_shot_restore = None
            pending, self._pending = self._pending, None
            if pending:
                st, pr, dt = pending
                return self._request(st, pr, dt, reason="补播排队的事件")
            return self._enter(target, "", reason="一次性动作播完")

        # 兜底：停在"工作中/思考中"太久且完全没有新事件 —— 多半回合其实早结束了，
        # 但 Stop 没触发（比如你按 ESC 打断了 Claude），或事件丢了。回待机。
        wt = (self.cfg.get("workingTimeoutMs", 0) or 0) / 1000.0
        if (wt and not self._one_shot_until
                and self.states.get(self.current, {}).get("working")
                and now - self._last_event_at > wt):
            return self._enter(self.default, "",
                               reason=f"工作态超过 {wt:.0f} 秒无任何事件")

        # 够久没动静就睡觉；睡着状态本身不再重复触发
        timeout = (self.cfg.get("idleTimeoutMs", 240000) or 0) / 1000.0
        if timeout and self.current not in ("sleep",) and not self._one_shot_until:
            if now - self._last_event_at > timeout:
                return self._enter("sleep", "", reason=f"空闲超过 {timeout:.0f} 秒")

        return None

    def wake(self):
        self._last_event_at = time.monotonic()

    # -- 内部 ------------------------------------------------------------
    def _request(self, state, prio, detail="", reason=""):
        if state not in self.states:
            return None

        playing_one_shot = self._one_shot_until and time.monotonic() < self._one_shot_until
        if playing_one_shot:
            cur_prio = self.states[self.current].get("priority", 0)
            if prio > cur_prio and self.playback.get("interruptHigherPriority", True):
                pass                                  # 高优先级可以打断
            else:
                self._pending = (state, prio, detail)  # 排队，等这次播完
                log(f"  排队待播 -> {state}　（{reason}）")
                return None

        return self._enter(state, detail, reason)

    def _enter(self, state, detail="", reason=""):
        if state not in self.states:
            return None

        now = time.monotonic()
        if state != self.current:
            log(f"状态 {self.current} -> {state}　　（{reason or '未说明'}）")
        self.previous = self.current
        self.current = state
        self.detail = detail
        self._pending = None

        st = self.states[state]
        if st.get("loop", True):
            self._one_shot_until = 0.0
            self._one_shot_restore = None
        else:
            dur = (st.get("durationMs", 1500) or 1500) / 1000.0
            self._one_shot_until = now + dur
            restore = st.get("restoreTo", "previous-or-idle")
            if restore == "previous-or-idle":
                self._one_shot_restore = self.previous if self.previous in self.states else self.default
            else:
                self._one_shot_restore = restore if restore in self.states else self.default

        return state


# --------------------------------------------------------------------------
# 桌宠窗口
# --------------------------------------------------------------------------
class PetWindow(QWidget):
    def __init__(self, cfg, brain):
        super().__init__()
        self.cfg = cfg
        self.brain = brain
        self._movies = {}
        self._drag_from = None
        self._cur_pixmap_size = QSize(BOX_W, BOX_H)

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool                      # 不进任务栏
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("小蕾米")

        wcfg = cfg.get("window", {})

        # --- 画面 ---
        self.pet_label = QLabel(self)
        self.pet_label.setAlignment(Qt.AlignCenter)
        self.pet_label.setAttribute(Qt.WA_TranslucentBackground, True)
        self.pet_label.setStyleSheet("background: transparent;")
        self.pet_label.setFixedSize(BOX_W, BOX_H)

        # --- 状态小标签 ---
        self.text_label = QLabel(self)
        self.text_label.setAlignment(Qt.AlignCenter)
        self._apply_label_style(wcfg.get("labelFontPt", 18))
        self.text_label.setVisible(bool(wcfg.get("showLabel", True)))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self.pet_label, 0, Qt.AlignHCenter)
        lay.addWidget(self.text_label, 0, Qt.AlignHCenter)

        self._apply_scale(wcfg.get("scale", 0.8))
        self._apply_opacity(wcfg.get("opacity", 1.0))

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

        self.switch_to(brain.current, brain.detail)

    # -- 缩放 / 透明度 ---------------------------------------------------
    def _apply_scale(self, scale):
        self.scale = max(0.35, min(2.0, float(scale)))
        self.pet_label.setFixedSize(int(BOX_W * self.scale), int(BOX_H * self.scale))
        for m in self._movies.values():
            self._rescale_movie(m)
        if self._movies:
            cur = self.pet_label.movie()
            if cur is not None:
                self._rescale_movie(cur)
        self.adjustSize()

    def _apply_opacity(self, op):
        self.setWindowOpacity(max(0.15, min(1.0, float(op))))

    def _rescale_movie(self, movie):
        size = movie.property("_nat_size")
        if not size:
            return
        nw, nh = size.width(), size.height()
        # 统一按高度归一化，宽度超框再按宽度压
        k = (BOX_H * self.scale) / nh
        if nw * k > BOX_W * self.scale:
            k = (BOX_W * self.scale) / nw
        movie.setScaledSize(QSize(max(1, int(nw * k)), max(1, int(nh * k))))

    # -- 动作切换 --------------------------------------------------------
    def _get_movie(self, state):
        st = self.brain.states.get(state)
        if not st:
            return None
        path = os.path.join(BASE_DIR, st["gif"])
        if not os.path.exists(path):
            return None

        key = (state, st["gif"])
        movie = self._movies.get(key)
        if movie is None:
            movie = QMovie(path)
            if not movie.isValid():
                return None
            movie.setCacheMode(QMovie.CacheNone)
            movie.jumpToFrame(0)
            nat = movie.currentPixmap().size()
            if nat.isValid() and nat.width() > 0:
                movie.setProperty("_nat_size", nat)
            else:
                movie.setProperty("_nat_size", QSize(300, 290))
            self._movies[key] = movie
        self._rescale_movie(movie)
        return movie

    def _resize_keeping_center(self):
        """
        调整窗口大小时保持中心不动。

        QLabel 的文字长短会撑大/缩小窗口，而 Qt 的 adjustSize() 是保持左上角的 ——
        那样每换一次状态，小蕾米就横向跳一下。这里把位移补回去。
        """
        before = self.geometry()
        self.adjustSize()
        after = self.geometry()
        dx = (after.width() - before.width()) // 2
        dy = (after.height() - before.height()) // 2
        if dx or dy:
            self.move(before.x() - dx, before.y() - dy)

    def switch_to(self, state, detail=""):
        movie = self._get_movie(state)
        if movie is None:
            return

        old = self.pet_label.movie()
        if old is movie and old.state() == QMovie.Running:
            self._update_text(state, detail)
            self._resize_keeping_center()
            return
        if old is not None and old is not movie:
            old.stop()

        movie.stop()
        self.pet_label.setMovie(movie)
        movie.jumpToFrame(0)
        movie.start()
        self._update_text(state, detail)
        self._resize_keeping_center()

    def _apply_label_style(self, pt):
        """字号决定内边距和圆角，保证放大之后比例仍然协调。"""
        pt = max(8, min(64, int(pt)))
        self._label_pt = pt
        pad_v = max(2, round(pt * 0.30))
        pad_h = max(6, round(pt * 0.72))
        radius = max(4, round(pt * 0.55))
        self.text_label.setStyleSheet(
            "background: rgba(28,24,32,0.78);"
            "color: #FFF3F7;"
            f"border-radius: {radius}px;"
            f"padding: {pad_v}px {pad_h}px;"
        )
        self.text_label.setFont(QFont("Microsoft YaHei UI", pt))

    def _update_text(self, state, detail=""):
        st = self.brain.states.get(state, {})
        txt = st.get("label", state)
        if detail:
            # 先按字数砍一刀（Notification 的 message 可能是一整句）
            limit = int(self.cfg.get("maxDetailChars", 22))
            if len(detail) > limit:
                detail = detail[: limit - 1] + "…"
            txt = f"{txt} · {detail}"

        # 再按像素宽度省略，保证字号放大后气泡不会撑出屏幕
        maxw = int(self.cfg.get("window", {}).get("labelMaxWidth", 460))
        fm = QFontMetrics(self.text_label.font())
        txt = fm.elidedText(txt, Qt.ElideRight, maxw)

        self.text_label.setText(txt)
        self.text_label.setVisible(
            bool(self.cfg.get("window", {}).get("showLabel", True))
        )

    def _restart_current(self):
        m = self.pet_label.movie()
        if m is not None:
            m.stop()
            m.jumpToFrame(0)
            m.start()

    # -- 鼠标：拖动 + 右键菜单 -------------------------------------------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_from = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_from is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_from)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._drag_from is not None:
            self._drag_from = None
            self._save_pos()
            e.accept()

    def mouseDoubleClickEvent(self, e):
        # 双击临时显隐状态文字
        v = not self.text_label.isVisible()
        self.cfg.setdefault("window", {})["showLabel"] = v
        self.text_label.setVisible(v)
        self._resize_keeping_center()

    def _save_window(self):
        """
        只把自己管的 window 段并回磁盘，保留配置文件里其它字段的手工修改。

        不能直接 save_json(self.cfg)：桌宠内存里是启动时读的那份，全量写回会把
        用户后来手工加/改的字段（比如 states 里的 working、新增的 turn 段）全部抹掉。
        顺带把磁盘上的其它改动同步回内存，这样 reload 之前也能看到。
        """
        disk = load_json(CONFIG_PATH)
        if not isinstance(disk, dict):
            disk = {}
        merged_win = dict(disk.get("window") or {})
        merged_win.update(self.cfg.get("window", {}))
        disk["window"] = merged_win
        try:
            save_json(CONFIG_PATH, disk)
        except Exception:
            return
        self.cfg = disk
        self.brain.reload(disk)

    def _save_pos(self):
        p = self.pos()
        self.cfg.setdefault("window", {})["x"] = p.x()
        self.cfg["window"]["y"] = p.y()
        self._save_window()

    def _menu(self, pos):
        m = QMenu(self)
        m.setStyleSheet(
            "QMenu{background:#2A2529;color:#F5EFF2;border:1px solid #4A4148;"
            "padding:5px;border-radius:8px;}"
            "QMenu::item{padding:5px 22px;border-radius:5px;}"
            "QMenu::item:selected{background:#C8647E;}"
            "QMenu::separator{height:1px;background:#4A4148;margin:5px 8px;}"
        )

        hdr = QAction(f"当前：{self.brain.states.get(self.brain.current,{}).get('label', self.brain.current)}", self)
        hdr.setEnabled(False)
        m.addAction(hdr)
        m.addSeparator()

        # 手动预览各动作
        sub = m.addMenu("预览动作")
        for name, st in self.brain.states.items():
            a = QAction(f"{st.get('label', name)}  ({name})", self)
            a.triggered.connect(lambda _=False, n=name: self._preview(n))
            sub.addAction(a)

        # 窗口大小
        size_sub = m.addMenu("窗口大小")
        for pct in (60, 80, 100, 120, 150):
            a = QAction(f"{pct}%", self)
            a.setCheckable(True)
            a.setChecked(abs(self.scale * 100 - pct) < 3)
            a.triggered.connect(lambda _=False, p=pct: self._set_scale(p / 100.0))
            size_sub.addAction(a)

        # 文字大小
        font_sub = m.addMenu("文字大小")
        for pt in (12, 18, 22, 28, 36, 48):
            a = QAction(f"{pt} pt", self)
            a.setCheckable(True)
            a.setChecked(getattr(self, "_label_pt", 18) == pt)
            a.triggered.connect(lambda _=False, p=pt: self._set_label_pt(p))
            font_sub.addAction(a)

        # 透明度
        op_sub = m.addMenu("透明度")
        for pct in (100, 85, 70, 55, 40):
            a = QAction(f"{pct}%", self)
            a.setCheckable(True)
            a.setChecked(abs(self.windowOpacity() * 100 - pct) < 4)
            a.triggered.connect(lambda _=False, p=pct: self._set_opacity(p / 100.0))
            op_sub.addAction(a)

        m.addSeparator()
        a_lbl = QAction("显示状态文字", self)
        a_lbl.setCheckable(True)
        a_lbl.setChecked(self.text_label.isVisible())
        a_lbl.triggered.connect(self._toggle_label)
        m.addAction(a_lbl)

        a_top = QAction("总在最前", self)
        a_top.setCheckable(True)
        a_top.setChecked(bool(self.cfg.get("window", {}).get("alwaysOnTop", True)))
        a_top.triggered.connect(self._toggle_top)
        m.addAction(a_top)

        a_restart = QAction("重播当前动作", self)
        a_restart.triggered.connect(self._restart_current)
        m.addAction(a_restart)

        a_reload = QAction("重新读取配置", self)
        a_reload.triggered.connect(self._reload_cfg)
        m.addAction(a_reload)

        m.addSeparator()
        a_quit = QAction("退出桌宠", self)
        a_quit.triggered.connect(QApplication.quit)
        m.addAction(a_quit)

        m.exec(self.mapToGlobal(pos))

    def _preview(self, name):
        self.brain.force(name)
        self.brain.wake()
        self.switch_to(name, "")

    def _set_scale(self, s):
        self.cfg.setdefault("window", {})["scale"] = s
        self._apply_scale(s)
        self._save_window()

    def _set_label_pt(self, pt):
        self.cfg.setdefault("window", {})["labelFontPt"] = pt
        self._apply_label_style(pt)
        self._update_text(self.brain.current, self.brain.detail)
        self._resize_keeping_center()
        self._save_window()

    def _set_opacity(self, o):
        self.cfg.setdefault("window", {})["opacity"] = o
        self._apply_opacity(o)
        self._save_window()

    def _toggle_label(self):
        v = not self.text_label.isVisible()
        self.cfg.setdefault("window", {})["showLabel"] = v
        self.text_label.setVisible(v)
        self._resize_keeping_center()
        self._save_window()

    def _toggle_top(self):
        cur = bool(self.cfg.get("window", {}).get("alwaysOnTop", True))
        new = not cur
        self.cfg.setdefault("window", {})["alwaysOnTop"] = new
        flags = self.windowFlags()
        if new:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        # setWindowFlags 会重建窗口，重建后 topmost 会丢 —— 必须重申一次
        enforce_topmost(self, new)
        self._save_window()

    def _reload_cfg(self):
        cfg = load_json(CONFIG_PATH)
        if not cfg:
            return
        self.cfg = cfg
        self.brain.reload(cfg)
        for m in self._movies.values():
            m.stop()
        self._movies.clear()
        self.switch_to(self.brain.current, "")
        self._apply_scale(cfg.get("window", {}).get("scale", 0.8))
        self._apply_opacity(cfg.get("window", {}).get("opacity", 1.0))


# --------------------------------------------------------------------------
# 主程序
# --------------------------------------------------------------------------
def make_tray_icon():
    for name in ("4.gif", "1.gif"):
        p = os.path.join(BASE_DIR, "assets", "gifs", name)
        if os.path.exists(p):
            m = QMovie(p)
            if m.isValid():
                m.jumpToFrame(0)
                pm = m.currentPixmap()
                if not pm.isNull():
                    return QIcon(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return QIcon()


SINGLETON_KEY = "xiaolemi-claude-pet"
PID_PATH = os.path.join(BASE_DIR, "pet.pid")
PET_EXE = ("python.exe", "pythonw.exe")


def _iter_procs():
    """遍历系统进程，产出 (pid, 小写进程名)。Toolhelp 快照，不启子进程。"""
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    k32 = ctypes.windll.kernel32

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == ctypes.c_void_p(-1).value:
        return
    try:
        e = PROCESSENTRY32()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = k32.Process32First(snap, ctypes.byref(e))
        while ok:
            yield e.th32ProcessID, e.szExeFile.decode("mbcs", "ignore").strip().lower()
            ok = k32.Process32Next(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(ctypes.c_void_p(snap))


def claude_running(names):
    """
    系统里还有没有 Claude 的进程在跑。
    names 是进程名列表（小写），桌面版主程序和它带起来的 CLI 都叫 claude.exe，一并算数。
    查不到时返回 True —— 宁可让桌宠多留一会儿，也别误杀。
    """
    if not names:
        return True
    try:
        for _pid, name in _iter_procs():
            if name in names:
                return True
    except Exception:
        return True
    return False


def _pid_is_pet(pid):
    """这个 pid 是否活着、且确实是 python 进程（防 PID 被复用后误判）。"""
    if not pid:
        return False
    try:
        for p, name in _iter_procs():
            if p == pid:
                return name in PET_EXE
    except Exception:
        return True          # 查不到就当它活着，宁可不开第二只
    return False


def read_pid():
    try:
        with open(PID_PATH, "r", encoding="utf-8") as f:
            return int((f.read() or "0").strip())
    except Exception:
        return 0


def write_pid(pid):
    try:
        with open(PID_PATH, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception:
        pass


def clear_pid():
    """退出时清掉 pid 文件，但只清自己的，别把别人的擦了。"""
    try:
        if read_pid() == os.getpid() and os.path.exists(PID_PATH):
            os.remove(PID_PATH)
    except Exception:
        pass


def ping_pet(msg=b"show"):
    """连上桌宠的命名管道发一条指令；连得上就说明它在跑。"""
    s = QLocalSocket()
    s.connectToServer(SINGLETON_KEY)
    if not s.waitForConnected(300):
        return False
    try:
        s.write(msg)
        s.flush()
        s.waitForBytesWritten(300)
    except Exception:
        pass
    s.disconnectFromServer()
    return True


def claim_pid_file():
    """
    原子地抢占 pid 文件（O_CREAT|O_EXCL 是原子的，谁先创建成功谁赢）。
    抢到返回 True；已有活实例返回 False；文件是上次崩溃残留的就删掉重试。
    """
    for _ in range(40):
        try:
            fd = os.open(PID_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
            return True
        except FileExistsError:
            old = read_pid()
            if old and old != os.getpid() and _pid_is_pet(old):
                return False                 # 有活着的实例，认输
            try:
                os.remove(PID_PATH)          # 残留文件，清掉重抢
            except Exception:
                pass
            time.sleep(0.05)
        except Exception:
            return True                      # 出意外别卡死，当作抢到
    return False


def claim_singleton():
    """
    抢单实例锁。已经有实例在跑就唤醒它并返回 None。

    两层保护，缺一不可：
      1. **原子 pid 文件**解决「两个进程几乎同时启动」的竞态。
      2. 拿不到锁时**不再碰管道** —— 早先的写法是管道连不上就
         QLocalServer.removeServer() 清残留，而那一步会把正在运行的实例的管道
         一起删掉，于是自己重新 listen 成功，就开出了第二只小蕾米。
    """
    if not claim_pid_file():
        # 已有实例 —— 等它的管道就绪（刚启动时可能还没 listen），然后叫它显形
        for _ in range(20):
            if ping_pet(b"show"):
                return None
            time.sleep(0.15)
        log("已有实例在运行，但管道无响应；本次不启动")
        return None

    # 抢到锁了，才轮到清残留管道
    QLocalServer.removeServer(SINGLETON_KEY)
    srv = QLocalServer()
    if not srv.listen(SINGLETON_KEY):
        log("pid 锁拿到了但管道监听失败（多半有实例正占着），本次不启动")
        clear_pid()
        return None
    return srv


def enforce_topmost(win, on=True):
    """
    用 Win32 强制把窗口压到最上层（或取消）。

    为什么不能只靠 Qt 的 Qt.WindowStaysOnTopHint：那个标志在窗口重建、被全屏程序
    顶掉、或者系统调整 z-order 之后会失效，表现就是"桌宠还在，但被别的窗口盖住了"。
    定期重申一次最省心。SWP_NOACTIVATE 保证不抢焦点。
    """
    try:
        import ctypes
        hwnd = int(win.winId())
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOACTIVATE = 0x0010
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST if on else HWND_NOTOPMOST,
            0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE,
        )
    except Exception:
        pass


def rescue_onto_screen(win):
    """
    窗口如果整块落在所有显示器之外，就挪回主屏。返回 True 表示确实挪了。

    为什么会发生：窗口坐标是持久化的，但显示器布局会变 —— 拔掉副屏、换接口、
    接投影，都可能让上次的位置变成"虚空"。Windows 不会自动把窗口挪回来，
    于是进程活着、IsWindowVisible() 还是 True，可你就是看不见它。
    """
    from PySide6.QtWidgets import QApplication

    MIN_VISIBLE = 60        # 至少要有这么大一块露在某块屏上，否则拖都拖不回来
    pos, size = win.pos(), win.size()
    rect = QRect(pos.x(), pos.y(), size.width(), size.height())

    for s in QApplication.screens():
        inter = s.availableGeometry().intersected(rect)
        if inter.width() >= MIN_VISIBLE and inter.height() >= MIN_VISIBLE:
            return False

    scr = QApplication.primaryScreen().availableGeometry()
    win.move(scr.right() - size.width() - 40, scr.bottom() - size.height() - 60)
    return True


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    _srv = claim_singleton()
    if _srv is None:
        print("小蕾米已经在跑了，已把它叫到前面。")
        return 0

    cfg = load_json(CONFIG_PATH)
    if not cfg:
        print("找不到或无法解析 pet_config.json", file=sys.stderr)
        return 1

    _life = cfg.get("lifecycle", {})
    log(f"启动  动作数={len(cfg.get('states', {}))}  "
        f"自动启动={_life.get('launchWithClaude', True)}  "
        f"自动退出={_life.get('exitWithClaude', True)}  "
        f"监视={_life.get('claudeProcesses', ['claude.exe'])}")

    brain = PetBrain(cfg)
    win = PetWindow(cfg, brain)

    # 恢复上次位置。但上次那台显示器可能已经拔了 / 改了布局，
    # 那样窗口会永远待在屏幕外 —— 进程活着、Windows 也说"可见"，但你什么都看不到。
    wcfg = cfg.get("window", {})
    if wcfg.get("x") is not None and wcfg.get("y") is not None:
        win.move(int(wcfg["x"]), int(wcfg["y"]))
    else:
        scr = QApplication.primaryScreen().availableGeometry()
        win.move(scr.right() - win.width() - 40, scr.bottom() - win.height() - 60)

    if rescue_onto_screen(win):
        log(f"上次的坐标 ({wcfg.get('x')}, {wcfg.get('y')}) 已经不在任何显示器里，"
            f"挪到主屏 ({win.pos().x()}, {win.pos().y()})")

    screens = ", ".join(
        f"{s.name()} {s.geometry().x()},{s.geometry().y()} "
        f"{s.geometry().width()}x{s.geometry().height()}"
        for s in QApplication.screens())
    log(f"显示器: {screens}　窗口落点: ({win.pos().x()}, {win.pos().y()})")

    win.show()

    # 再有启动器被双击时，新进程会连上这个管道发一条指令过来
    def _bring_to_front():
        # 只调 show() 不够：窗口若被外部方式隐藏 / 最小化，Qt 不认为自己不可见，
        # show() 会变成空操作。所以要按状态分别处理。
        if win.isMinimized():
            win.showNormal()
        if not win.isVisible():
            win.setVisible(True)
        win.show()
        win.raise_()
        win.activateWindow()
        enforce_topmost(win, True)

    def _on_new_conn():
        # 必须非阻塞。早先这里用 waitForReadyRead() 会把事件循环卡住 250ms，
        # 期间别的探测连不上 → 误判「没在跑」→ 开出第二只小蕾米。
        while True:
            c = _srv.nextPendingConnection()
            if c is None:
                return

            def handle(sock=c):
                try:
                    msg = bytes(sock.readAll()).strip()
                    if msg == b"show":
                        _bring_to_front()
                    elif msg == b"hide":
                        win.setVisible(False)
                    elif msg == b"toggle":
                        win.setVisible(False) if win.isVisible() else _bring_to_front()
                    elif msg == b"reload":
                        win._reload_cfg()
                        log("收到 reload 指令，已重新读取 pet_config.json")
                except Exception:
                    pass
                finally:
                    sock.close()

            c.readyRead.connect(handle)
            c.disconnected.connect(c.deleteLater)

    _srv.newConnection.connect(_on_new_conn)

    # 退出时记一笔再清 pid 文件。
    # 有了这行，日志里"只有启动没有退出"就说明是硬崩溃（可去 Windows 事件日志查）；
    # 有退出行就说明是正常退出，原因写在上一行。
    def _on_quit():
        log("退出")
        clear_pid()

    app.aboutToQuit.connect(_on_quit)

    # --- 托盘 ---
    tray = QSystemTrayIcon(make_tray_icon(), app)
    tray.setToolTip("小蕾米 · Claude 状态")
    tmenu = QMenu()
    tmenu.setStyleSheet(win.styleSheet())
    a_show = tmenu.addAction("显示 / 隐藏")
    a_quit = tmenu.addAction("退出")
    a_show.triggered.connect(lambda: win.setVisible(not win.isVisible()))
    a_quit.triggered.connect(app.quit)
    tray.setContextMenu(tmenu)
    tray.activated.connect(
        lambda r: win.setVisible(not win.isVisible()) if r == QSystemTrayIcon.Trigger else None
    )
    tray.show()

    # --- 轮询 status.json ---
    state = {"mtime": None}

    def poll():
        try:
            mt = os.path.getmtime(STATUS_PATH)
        except OSError:
            mt = None
        if mt != state["mtime"]:
            state["mtime"] = mt
            payload = load_json(STATUS_PATH)
            if payload:
                new = brain.feed(payload)
                if new:
                    win.switch_to(new, brain.detail)
                    return
        t = brain.tick()
        if t:
            win.switch_to(t, brain.detail)

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(int(cfg.get("pollMs", 150)))

    # 心跳：每 2 分钟记一次当前状态和"还在干活"的会话，排查卡状态时全靠它
    def heartbeat():
        q = sorted(s[:8] or "-" for s in brain._quiet)
        log(f"心跳：当前状态={brain.current}　已结束回合的会话={q or '无'}")

    hb = QTimer()
    hb.timeout.connect(heartbeat)
    hb.start(120000)

    # 定期重申「总在最前」。Qt 的 WindowStaysOnTopHint 会失效（窗口重建、被全屏程序
    # 顶掉…），不重申就会出现「桌宠还在，但被别的窗口盖住了」。
    def keep_top():
        if win.cfg.get("window", {}).get("alwaysOnTop", True):
            enforce_topmost(win, True)

    kt = QTimer()
    kt.timeout.connect(keep_top)
    kt.start(4000)
    keep_top()

    # --- 跟随 Claude 生命周期：Claude 关掉了，小蕾米也下班 ---
    life = cfg.get("lifecycle", {})
    if life.get("exitWithClaude", True):
        names = {str(n).strip().lower() for n in life.get("claudeProcesses", ["claude.exe"])}
        poll_ms = max(500, int(life.get("checkEveryMs", 3000)))
        miss_limit = max(1, int(life.get("exitAfterMisses", 10)))
        miss = {"n": 0}

        def watch_claude():
            if claude_running(names):
                if miss["n"]:
                    log(f"又看到 Claude 了（之前连续漏了 {miss['n']} 次）")
                miss["n"] = 0
                return
            miss["n"] += 1
            if miss["n"] == 1:
                log(f"第 1 次没看到 Claude  监视={sorted(names)}")
            elif miss["n"] % 3 == 0:
                log(f"连续 {miss['n']} 次没看到 Claude")
            # 连续若干次都没看到，才认定它真的退出了（避免重启瞬间误杀）
            if miss["n"] >= miss_limit:
                log(f"连续 {miss_limit} 次没看到 Claude → 退出")
                app.quit()

        wd = QTimer()
        wd.timeout.connect(watch_claude)
        wd.start(poll_ms)

    print("小蕾米桌宠已启动。右键图标可调菜单，托盘可退出。")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
