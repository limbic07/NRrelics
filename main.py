# --- START OF FILE main.py ---
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import threading
import time
import json
import os
import keyboard
from tkinter import simpledialog, filedialog, messagebox
import utils
import bot_merchant
import bot_inventory


class AttributeSelector(tb.Frame):
    def __init__(self, master, all_items, title_left, title_right, bootstyle="primary", callback=None, **kwargs):
        super().__init__(master, **kwargs)
        self.all_items = all_items if all_items else []
        self.current_selection_ref = []
        self.callback = callback
        container = tb.Frame(self)
        container.pack(fill=BOTH, expand=True, padx=5, pady=5)
        frame_left = tb.Labelframe(container, text=title_left, bootstyle="secondary")
        frame_left.pack(side=LEFT, fill=BOTH, expand=True, padx=5)
        self.search_var = tb.StringVar()
        self.search_var.trace("w", self.filter_left)
        tb.Entry(frame_left, textvariable=self.search_var).pack(fill=X, padx=5, pady=5)
        self.tree_left = tb.Treeview(frame_left, show="tree", selectmode="extended")
        self.tree_left.pack(side=LEFT, fill=BOTH, expand=True)
        sb_left = tb.Scrollbar(frame_left, orient="vertical", command=self.tree_left.yview)
        sb_left.pack(side=RIGHT, fill=Y)
        self.tree_left.configure(yscrollcommand=sb_left.set)
        frame_mid = tb.Frame(container)
        frame_mid.pack(side=LEFT, fill=Y, padx=5, pady=50)
        tb.Button(frame_mid, text="添加 >>", command=self.add_item, bootstyle=bootstyle).pack(pady=10)
        tb.Button(frame_mid, text="<< 移除", command=self.remove_item, bootstyle="secondary").pack(pady=10)
        frame_right = tb.Labelframe(container, text=title_right, bootstyle=bootstyle)
        frame_right.pack(side=LEFT, fill=BOTH, expand=True, padx=5)
        self.tree_right = tb.Treeview(frame_right, show="tree", selectmode="extended")
        self.tree_right.pack(side=LEFT, fill=BOTH, expand=True)
        sb_right = tb.Scrollbar(frame_right, orient="vertical", command=self.tree_right.yview)
        sb_right.pack(side=RIGHT, fill=Y)
        self.tree_right.configure(yscrollcommand=sb_right.set)
        self.tree_left.bind("<Control-a>", lambda e: self.select_all(self.tree_left))
        self.tree_right.bind("<Control-a>", lambda e: self.select_all(self.tree_right))
        self.refresh()

    def select_all(self, tree):
        tree.selection_set(tree.get_children())
        return "break"

    def load_selection(self, selection_list_ref):
        self.current_selection_ref = selection_list_ref
        self.refresh()

    def update_source(self, new_items):
        self.all_items = new_items
        self.refresh()

    def filter_left(self, *args):
        self.refresh(self.search_var.get().lower())

    def refresh(self, search=""):
        for t in [self.tree_left, self.tree_right]:
            for x in t.get_children(): t.delete(x)
        for item in self.all_items:
            if item not in self.current_selection_ref and search in item.lower():
                self.tree_left.insert("", END, text=item)
        for item in self.current_selection_ref:
            self.tree_right.insert("", END, text=item)

    def add_item(self):
        for item in self.tree_left.selection():
            txt = self.tree_left.item(item, "text")
            if txt not in self.current_selection_ref: self.current_selection_ref.append(txt)
        self.refresh(self.search_var.get())
        if self.callback: self.callback()

    def remove_item(self):
        for item in self.tree_right.selection():
            txt = self.tree_right.item(item, "text")
            if txt in self.current_selection_ref: self.current_selection_ref.remove(txt)
        self.refresh(self.search_var.get())
        if self.callback: self.callback()

    def get_list(self):
        return self.current_selection_ref

    def set_list(self, lst):
        valid_items = [utils.normalize_text(i) for i in lst]
        self.current_selection_ref = [i for i in valid_items if i in self.all_items]
        self.refresh()


class PresetEditor(tb.Frame):
    def __init__(self, master, all_possible_items, **kwargs):
        super().__init__(master, **kwargs)
        self.presets = []
        self.current_preset_index = -1
        self.all_possible_items = all_possible_items
        left_panel = tb.Frame(self, width=220)
        left_panel.pack(side=LEFT, fill=Y, padx=5, pady=5)
        toolbar1 = tb.Frame(left_panel)
        toolbar1.pack(fill=X, pady=2)
        tb.Button(toolbar1, text="+", width=3, command=self.add_preset, bootstyle="success-outline").pack(side=LEFT,
                                                                                                          padx=1)
        tb.Button(toolbar1, text="-", width=3, command=self.del_preset, bootstyle="danger-outline").pack(side=LEFT,
                                                                                                         padx=1)
        tb.Button(toolbar1, text="改名", width=5, command=self.rename_preset, bootstyle="info-outline").pack(side=LEFT,
                                                                                                             padx=1)
        self.lb_presets = tb.Treeview(left_panel, show="tree", selectmode="browse")
        self.lb_presets.pack(fill=BOTH, expand=True)
        self.lb_presets.bind("<<TreeviewSelect>>", self.on_preset_select)
        self.selector = AttributeSelector(self, self.all_possible_items, "词条库", "当前预设词条 (>=2生效)", "success")
        self.selector.pack(side=RIGHT, fill=BOTH, expand=True)

    def load_presets(self, presets_data):
        self.presets = presets_data
        if not self.presets: self.presets.append({"name": "默认预设", "items": []})
        self.refresh_list()
        if self.presets:
            try:
                self.lb_presets.selection_set(self.lb_presets.get_children()[0])
            except:
                pass

    def refresh_list(self):
        selected = self.lb_presets.selection()
        selected_idx = self.lb_presets.index(selected[0]) if selected else 0
        for item in self.lb_presets.get_children(): self.lb_presets.delete(item)
        for p in self.presets:
            self.lb_presets.insert("", END, text=f"{p['name']} ({len(p['items'])})")
        children = self.lb_presets.get_children()
        if children:
            if 0 <= selected_idx < len(children):
                self.lb_presets.selection_set(children[selected_idx])
            else:
                self.lb_presets.selection_set(children[0])

    def on_preset_select(self, event):
        selected = self.lb_presets.selection()
        if not selected: return
        idx = self.lb_presets.index(selected[0])
        self.current_preset_index = idx
        self.selector.load_selection(self.presets[idx]["items"])

    def add_preset(self):
        if len(self.presets) >= 10: return
        self.presets.append({"name": f"预设 {len(self.presets) + 1}", "items": []})
        self.refresh_list()
        children = self.lb_presets.get_children()
        if children: self.lb_presets.selection_set(children[-1])

    def del_preset(self):
        if len(self.presets) <= 1: return
        if self.current_preset_index >= 0:
            del self.presets[self.current_preset_index]
            self.refresh_list()

    def rename_preset(self):
        if self.current_preset_index < 0: return
        old_name = self.presets[self.current_preset_index]["name"]
        new_name = simpledialog.askstring("重命名", "请输入预设名称:", initialvalue=old_name)
        if new_name:
            self.presets[self.current_preset_index]["name"] = new_name
            self.refresh_list()

    def update_source_library(self, new_library):
        self.all_possible_items = new_library
        self.selector.update_source(new_library)

    def get_presets(self):
        return self.presets


class App(tb.Window):
    def __init__(self):
        super().__init__(themename="superhero")
        self.title("NRrelic_bot V1.3")
        self.geometry("1100x850")
        try:
            self.iconbitmap(utils.get_resource_path("icon.ico"))
        except:
            pass
        self.norm_pos, self.deep_pos, self.deep_neg = utils.DataLoader.get_data()
        self.logic = None
        self.presets_norm = []
        self.presets_deep = []
        self.setup_ui()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        top = tb.Frame(self)
        top.pack(fill=X, padx=10, pady=10)
        tb.Label(top, text="遗物类型:", font=("bold", 11)).pack(side=LEFT)
        self.mode_var = tb.StringVar(value="deepnight")
        tb.Radiobutton(top, text="普通", variable=self.mode_var, value="normal", command=self.on_mode_change).pack(
            side=LEFT, padx=5)
        tb.Radiobutton(top, text="深夜", variable=self.mode_var, value="deepnight", command=self.on_mode_change).pack(
            side=LEFT, padx=5)
        func_frame = tb.Labelframe(top, text="工作模式", bootstyle="info")
        func_frame.pack(side=LEFT, padx=20)
        self.func_var = tb.StringVar(value="merchant")
        tb.Radiobutton(func_frame, text="自动购买", variable=self.func_var, value="merchant",
                       command=self.update_ui_state).pack(side=LEFT, padx=5)
        tb.Radiobutton(func_frame, text="仓库清理", variable=self.func_var, value="inventory",
                       command=self.update_ui_state).pack(side=LEFT, padx=5)
        tb.Button(top, text="导出配置", width=8, command=self.export_full_config, bootstyle="secondary-outline").pack(
            side=RIGHT, padx=5)
        tb.Button(top, text="导入配置", width=8, command=self.import_full_config, bootstyle="warning-outline").pack(
            side=RIGHT, padx=5)
        self.nb = tb.Notebook(self)
        self.nb.pack(fill=BOTH, expand=True, padx=10)
        self.tab1 = tb.Frame(self.nb)
        self.nb.add(self.tab1, text="1. 策略预设")
        self.ui_presets = PresetEditor(self.tab1, [])
        self.ui_presets.pack(fill=BOTH, expand=True)
        self.tab2 = tb.Frame(self.nb)
        self.nb.add(self.tab2, text="2. 全局黑名单")
        self.ui_neg = AttributeSelector(self.tab2, self.deep_neg, "负面词条", "黑名单(出现即卖)", "danger")
        self.ui_neg.pack(fill=BOTH, expand=True)
        self.tab3 = tb.Frame(self.nb)
        self.nb.add(self.tab3, text="3. 仓库设置")
        grp_strat = tb.Labelframe(self.tab3, text="清理策略", bootstyle="warning")
        grp_strat.pack(fill=X, padx=10, pady=10)
        self.inv_strat_var = tb.StringVar(value="lock_only")
        tb.Radiobutton(grp_strat, text="[收藏模式] 只收藏好遗物 (不出售)", variable=self.inv_strat_var,
                       value="lock_only").pack(anchor=W, padx=10, pady=5)
        tb.Radiobutton(grp_strat, text="[出售模式] 批量选中坏遗物 (一次性卖出)", variable=self.inv_strat_var,
                       value="batch_sell").pack(anchor=W, padx=10, pady=5)
        grp_opt = tb.Labelframe(self.tab3, text="附加选项", bootstyle="danger")
        grp_opt.pack(fill=X, padx=10, pady=10)
        self.chk_unfav = tb.BooleanVar(value=False)
        tb.Checkbutton(grp_opt, text="允许对【不合格且已收藏】的遗物进行操作 (取消收藏/解锁卖出)",
                       variable=self.chk_unfav, bootstyle="danger-round-toggle").pack(anchor=W, padx=10, pady=10)
        ctrl = tb.Frame(self)
        ctrl.pack(fill=X, padx=20, pady=20)
        self.btn_start = tb.Button(ctrl, text="开始运行", command=self.start, bootstyle="success")
        self.btn_start.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.btn_stop = tb.Button(ctrl, text="停止 (F11)", command=self.stop, bootstyle="danger", state="disabled")
        self.btn_stop.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.log_text = tb.Text(self, height=8)
        self.log_text.pack(fill=X, padx=20, pady=10)

    def on_mode_change(self):
        if self.mode_var.get() == "normal":
            self.ui_presets.update_source_library(self.norm_pos)
            self.ui_presets.load_presets(self.presets_norm)
            self.nb.tab(1, state="disabled")
        else:
            self.ui_presets.update_source_library(self.deep_pos)
            self.ui_presets.load_presets(self.presets_deep)
            self.nb.tab(1, state="normal")

    def update_ui_state(self):
        if self.func_var.get() == "merchant":
            self.nb.tab(2, state="disabled")
        else:
            self.nb.tab(2, state="normal")

    def start(self):
        self.save_all()
        config = {
            'mode': self.mode_var.get(),
            'presets': self.ui_presets.get_presets(),
            'bad_neg': self.ui_neg.get_list(),
            'inv_strategy': self.inv_strat_var.get(),
            'unfav_invalid': self.chk_unfav.get()
        }
        if self.func_var.get() == "merchant":
            self.logic = bot_merchant.MerchantBot(self.log)
        else:
            if not messagebox.askokcancel("确认", f"请确认游戏内仓库已筛选为【{config['mode']}】！"): return
            self.logic = bot_inventory.InventoryBot(self.log)

        t = threading.Thread(target=self.logic.run, args=(config,))
        t.daemon = True
        t.start()
        threading.Thread(target=self.monitor_keys, daemon=True).start()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.log(f"🚀 任务启动: {self.func_var.get()} 模式")

    def monitor_keys(self):
        while self.logic and not self.logic.should_stop:
            if keyboard.is_pressed('f11'): self.stop(); break
            time.sleep(0.1)

    def stop(self):
        if self.logic: self.logic.should_stop = True
        self.log("🛑 正在停止...")
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    def save_all(self):
        mode = self.mode_var.get()
        current = self.ui_presets.get_presets()
        if mode == "normal":
            self.presets_norm = current
        else:
            self.presets_deep = current
        data = {'last_mode': mode, 'presets_norm': self.presets_norm, 'presets_deep': self.presets_deep,
                'bad_neg': self.ui_neg.get_list()}
        try:
            with open(utils.get_app_config_path(), "w", encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except:
            pass
        settings = {'last_func': self.func_var.get(), 'inv_strategy': self.inv_strat_var.get(),
                    'unfav_invalid': self.chk_unfav.get()}
        try:
            with open(utils.get_user_settings_path(), "w", encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        except:
            pass

    def load_config(self):
        try:
            with open(utils.get_app_config_path(), "r", encoding='utf-8') as f:
                c = json.load(f)
                self.presets_norm = c.get('presets_norm', [])
                self.presets_deep = c.get('presets_deep', [])
                self.ui_neg.set_list(c.get('bad_neg', []))
                self.mode_var.set(c.get('last_mode', 'deepnight'))
        except:
            pass
        if not self.presets_norm: self.presets_norm = [{"name": "默认", "items": []}]
        if not self.presets_deep: self.presets_deep = [{"name": "默认", "items": []}]
        try:
            with open(utils.get_user_settings_path(), "r", encoding='utf-8') as f:
                s = json.load(f)
                self.func_var.set(s.get('last_func', 'merchant'))
                self.inv_strat_var.set(s.get('inv_strategy', 'lock_only'))
                self.chk_unfav.set(s.get('unfav_invalid', False))
        except:
            pass
        self.on_mode_change()
        self.update_ui_state()

    def export_full_config(self):
        self.save_all()
        data = {'last_mode': self.mode_var.get(), 'presets_norm': self.presets_norm, 'presets_deep': self.presets_deep,
                'bad_neg': self.ui_neg.get_list()}
        filename = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Config", "*.json")])
        if filename:
            with open(filename, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("成功", "导出成功")

    def import_full_config(self):
        filename = filedialog.askopenfilename(filetypes=[("JSON Config", "*.json")])
        if not filename: return
        with open(filename, "r", encoding="utf-8") as f: c = json.load(f)
        self.presets_norm = c.get('presets_norm', [])
        self.presets_deep = c.get('presets_deep', [])
        self.ui_neg.set_list(c.get('bad_neg', []))
        self.mode_var.set(c.get('last_mode', 'deepnight'))
        self.on_mode_change()
        messagebox.showinfo("成功", "导入成功")

    def on_close(self):
        self.stop()
        self.save_all()
        self.destroy()

    def log(self, msg):
        timestamp = time.strftime("[%H:%M:%S] ", time.localtime())
        self.log_text.insert(END, timestamp + msg + "\n")
        self.log_text.see(END)
        print(timestamp + msg)


if __name__ == "__main__":
    App().mainloop()