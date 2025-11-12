import psutil
import cpuinfo
import platform
import threading
import subprocess
import os
from tkinter import Tk, Label, Button, Menu, messagebox, StringVar, ttk, filedialog
from tkinter import N, S, E, W

try:
    import wmi
except Exception:
    wmi = None

# ---------- Helper functions to gather CPU information ----------

def get_cpu_brand_name(raw_name: str) -> str:
    _cpu_name = str(raw_name)
    if "Intel" in _cpu_name:
        return "Intel"
    if "AMD" in _cpu_name:
        return "AMD"
    return "Unknown"


def get_core_numbers():
    physical = psutil.cpu_count(logical=False)
    logical = psutil.cpu_count(logical=True)
    return {"physical_cores": physical, "logical_cores": logical}


def get_cpu_freq():
    f = psutil.cpu_freq()
    if not f:
        return {"current_mhz": None, "min_mhz": None, "max_mhz": None}
    return {
        "current_mhz": round(f.current, 2),
        "min_mhz": round(f.min, 2) if f.min else None,
        "max_mhz": round(f.max, 2) if f.max else None,
        "current_ghz": round(f.current / 1000.0, 3) if f.current else None,
    }


def get_cpu_percentages(sample_interval=0.5):
    per_core = psutil.cpu_percent(percpu=True, interval=sample_interval)
    overall = psutil.cpu_percent(interval=None)
    return per_core, overall


def get_l3_cache_size_mb() -> (int or None):
    try:
        system = platform.system()
        if system == "Windows" and wmi:
            try:
                c = wmi.WMI()
                for cpu in c.Win32_Processor():
                    size_kb = getattr(cpu, "L3CacheSize", None)
                    if size_kb:
                        try:
                            return int(size_kb) // 1024
                        except Exception:
                            return None
            except Exception:
                pass
        elif system == "Linux":
            try:
                out = subprocess.check_output(["lscpu"], universal_newlines=True)
                for line in out.splitlines():
                    if "L3 cache" in line:
                        parts = line.split(":", 1)
                        if len(parts) > 1:
                            val = parts[1].strip()
                            if val.endswith("K"):
                                return int(val[:-1]) // 1024
                            if val.endswith("M"):
                                return int(val[:-1])
            except Exception:
                try:
                    p = "/sys/devices/system/cpu/cpu0/cache"
                    if os.path.isdir(p):
                        for d in os.listdir(p):
                            path = os.path.join(p, d, "level")
                            try:
                                with open(path, "r") as f:
                                    level = f.read().strip()
                                if level == "3":
                                    size_path = os.path.join(p, d, "size")
                                    with open(size_path, "r") as f:
                                        size = f.read().strip()
                                    if size.endswith("K"):
                                        return int(size[:-1]) // 1024
                                    if size.endswith("M"):
                                        return int(size[:-1])
                            except Exception:
                                continue
                except Exception:
                    pass
    except Exception:
        pass
    return None

# ---------- UI / application logic ----------

class CPUInfoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CPU Information")
        self.root.geometry("700x550")
        self.root.minsize(840, 420)

        # CPU static info
        self.cpu_info = cpuinfo.get_cpu_info()
        self.raw_name = self.cpu_info.get("brand_raw", "Unknown CPU")
        self.brand = get_cpu_brand_name(self.raw_name)
        self.cores = get_core_numbers()
        self.l3_cache_mb = get_l3_cache_size_mb()
        self.freq = get_cpu_freq()

        # UI variables
        self.overall_var = StringVar(value="-- %")
        self.freq_var = StringVar(value=self._format_freq())

        # Build UI
        self._build_menu()
        self._build_header()
        self._build_core_table()
        self._build_footer()

        # Info label (added back)
        self.info_label = Label(self.root, text="Press 'Refresh' to update CPU usage.", fg="blue")
        self.info_label.pack(pady=5)

        # First refresh
        self.refresh_stats()

    def _build_menu(self):
        menubar = Menu(self.root)
        filemenu = Menu(menubar, tearoff=0)
        filemenu.add_command(label="Save report...", command=self.save_report)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=filemenu)

        helpmenu = Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)

        self.root.config(menu=menubar)

    def _build_header(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="x")

        lbl_name = ttk.Label(frame, text=f"CPU: {self.raw_name}")
        lbl_name.grid(row=0, column=0, sticky=W)

        lbl_brand = ttk.Label(frame, text=f"Brand: {self.brand}")
        lbl_brand.grid(row=1, column=0, sticky=W, pady=(4,0))

        lbl_cores = ttk.Label(frame, text=f"Cores: {self.cores['physical_cores']} physical / {self.cores['logical_cores']} logical")
        lbl_cores.grid(row=0, column=1, sticky=W, padx=(20,0))

        lbl_freq = ttk.Label(frame, textvariable=self.freq_var)
        lbl_freq.grid(row=1, column=1, sticky=W, padx=(20,0))

        lbl_cache = ttk.Label(frame, text=f"L3 Cache: {self.l3_cache_mb if self.l3_cache_mb is not None else 'Unknown'} MB")
        lbl_cache.grid(row=0, column=2, sticky=W, padx=(20,0))

        overall_frame = ttk.Frame(frame)
        overall_frame.grid(row=0, column=3, rowspan=2, sticky=E)
        ttk.Label(overall_frame, text="Overall CPU:").pack(anchor="e")
        self.overall_progress = ttk.Progressbar(overall_frame, orient="horizontal", length=180, mode="determinate")
        self.overall_progress.pack()
        ttk.Label(overall_frame, textvariable=self.overall_var).pack(anchor="e")

    def _build_core_table(self):
        container = ttk.Frame(self.root, padding=10)
        container.pack(fill="both", expand=True)

        self.core_canvas = ttk.Frame(container)
        self.core_canvas.pack(fill="both", expand=True)

        header = ttk.Frame(self.core_canvas)
        header.pack(fill="x")
        ttk.Label(header, text="Core", width=10).grid(row=0, column=0, sticky=W)
        ttk.Label(header, text="Usage").grid(row=0, column=1, sticky=W)

        self.core_rows = []
        for i in range(self.cores['logical_cores']):
            row = ttk.Frame(self.core_canvas)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=f"Core {i}", width=10).grid(row=0, column=0, sticky=W)
            p = ttk.Progressbar(row, orient="horizontal", length=420, mode="determinate")
            p.grid(row=0, column=1, sticky=W)
            lbl = ttk.Label(row, text="-- %", width=8)
            lbl.grid(row=0, column=2, sticky=W, padx=(6,0))
            self.core_rows.append((p, lbl))

    def _build_footer(self):
        frame = ttk.Frame(self.root, padding=10)
        frame.pack(fill="x")

        refresh_btn = Button(frame, text="Refresh", command=self.refresh_stats, bg="#4CAF50", fg="white", relief="raised", width=10)
        refresh_btn.pack(side="left", padx=(5,0))

        auto_btn = Button(frame, text="Auto-refresh (5s)", command=self.toggle_auto_refresh, bg="#2196F3", fg="white", relief="raised", width=15)
        auto_btn.pack(side="left", padx=(6,0))

        save_btn = Button(frame, text="Save report...", command=self.save_report, bg="#9C27B0", fg="white", relief="raised", width=12)
        save_btn.pack(side="left", padx=(6,0))

        quit_btn = Button(frame, text="Quit", command=self.root.quit, bg="#f44336", fg="white", relief="raised", width=8)
        quit_btn.pack(side="right", padx=(5,0))

        self._auto_refresh = False
        self._auto_thread = None

    def _show_about(self):
        txt = (
            "CPU Information App\n"
            "Shows CPU brand, cores, frequency, per-core and overall usage, and L3 cache when available.\n\n"
            "Built with psutil, py-cpuinfo and tkinter."
        )
        messagebox.showinfo("About", txt)

    def _format_freq(self):
        if not self.freq or not self.freq.get('current_mhz'):
            return "Frequency: Unknown"
        return f"Frequency: {self.freq['current_mhz']} MHz ({self.freq['current_ghz']} GHz)"

    def refresh_stats(self):
        self.info_label.config(text="Updating CPU information...", fg="orange")
        t = threading.Thread(target=self._sample_and_update, daemon=True)
        t.start()

    def _sample_and_update(self):
        per_core, overall = get_cpu_percentages(sample_interval=0.5)
        self.root.after(0, lambda: self._update_ui(per_core, overall))

    def _update_ui(self, per_core, overall):
        self.overall_var.set(f"{overall:.1f} %")
        try:
            self.overall_progress['value'] = overall
        except Exception:
            pass
        for i, (bar, lbl) in enumerate(self.core_rows):
            try:
                val = per_core[i]
            except IndexError:
                val = 0.0
            bar['value'] = val
            lbl.config(text=f"{val:.1f} %")
        self.info_label.config(text="CPU information updated successfully!", fg="green")

    def toggle_auto_refresh(self):
        self._auto_refresh = not self._auto_refresh
        if self._auto_refresh:
            self._auto_thread = threading.Thread(target=self._auto_loop, daemon=True)
            self._auto_thread.start()
            self.info_label.config(text="Auto-refresh enabled.", fg="blue")
        else:
            self._auto_thread = None
            self.info_label.config(text="Auto-refresh stopped.", fg="red")

    def _auto_loop(self):
        while self._auto_refresh:
            self.refresh_stats()
            for _ in range(50):
                if not self._auto_refresh:
                    break
                threading.Event().wait(0.1)

    def save_report(self):
        per_core, overall = get_cpu_percentages(sample_interval=0.1)
        lines = []
        lines.append(f"CPU: {self.raw_name}")
        lines.append(f"Brand: {self.brand}")
        lines.append(f"Cores: {self.cores['physical_cores']} physical / {self.cores['logical_cores']} logical")
        lines.append(self._format_freq())
        lines.append(f"L3 Cache: {self.l3_cache_mb if self.l3_cache_mb is not None else 'Unknown'} MB")
        lines.append("")
        lines.append(f"Overall CPU Usage: {overall:.1f} %")
        lines.append("Per-core usage:")
        for i, val in enumerate(per_core):
            lines.append(f"  Core {i}: {val:.1f} %")

        default_name = "cpu_report.txt"
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=default_name, filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            messagebox.showinfo("Saved", f"Report saved to: {path}")
            self.info_label.config(text=f"Report saved successfully to {path}", fg="green")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save report: {e}")
            self.info_label.config(text=f"Error saving report: {e}", fg="red")

if __name__ == "__main__":
    root = Tk()
    try:
        style = ttk.Style()
        style.theme_use('default')
    except Exception:
        pass
    app = CPUInfoApp(root)
    root.mainloop()
