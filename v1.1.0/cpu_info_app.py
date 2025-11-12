import psutil
import cpuinfo
import platform
import threading
import subprocess
import os
import requests
import urllib.parse
from tkinter import Tk, Label, Button, Menu, messagebox, StringVar, ttk, filedialog, Frame
from tkinter import N, S, E, W
from bs4 import BeautifulSoup
from tkinter import font

try:
    import wmi
except Exception:
    wmi = None

# ---------- Helper functions ----------

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
                pass
    except Exception:
        pass
    return None

def get_cpu_multithread_rating():
    cpu_name = cpuinfo.get_cpu_info().get('brand_raw', 'CPU name not available')
    encoded_cpu_name = urllib.parse.quote(cpu_name)
    base_url = "https://www.cpubenchmark.net/cpu.php?cpu="
    url = f"{base_url}{encoded_cpu_name}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36'
    }

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        rating_element = soup.find(string="Multithread Rating")
        if rating_element:
            rating_value = rating_element.find_next().text.strip()
            return rating_value
        else:
            return "Rating not found"
    else:
        return f"Failed to retrieve page (Status {response.status_code})"

# ---------- Enhanced UI Class with working core updates ----------

class CPUInfoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CPU Information")
        self.root.geometry("1150x650")
        self.root.minsize(1150, 650)
        self.root.configure(bg="#2C3E50")

        # Fonts
        self.header_font = font.Font(family="Helvetica", size=14, weight="bold")
        self.normal_font = font.Font(family="Helvetica", size=11)
        self.small_font = font.Font(family="Helvetica", size=10)

        # CPU info
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

        # Info label
        self.info_label = Label(self.root, text="Press 'Refresh' to update CPU usage.", fg="#1ABC9C",
                                bg="#2C3E50", font=self.small_font)
        self.info_label.pack(pady=5)

        # Style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#2C3E50")
        style.configure("TLabel", background="#2C3E50", foreground="white", font=self.normal_font)
        style.configure("Header.TLabel", font=self.header_font, foreground="#ECF0F1", background="#34495E")
        style.configure("Horizontal.TProgressbar", troughcolor="#34495E", background="#1ABC9C")
        style.configure("TButton", background="#1ABC9C", foreground="white", font=self.normal_font)
        style.map("TButton", background=[("active", "#16A085")])

        # Auto refresh control
        self._auto_refresh = False

        # First refresh
        psutil.cpu_percent(percpu=True)  # discard initial reading
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

        benchmarkMenu = Menu(menubar, tearoff=0)
        benchmarkMenu.add_command(label="Benchmark Rating", command=self._show_cpu_rating)
        menubar.add_cascade(label="CPU Rating", menu=benchmarkMenu)

        self.root.config(menu=menubar)

    def _build_header(self):
        frame = ttk.Frame(self.root, padding=15)
        frame.pack(fill="x")
        ttk.Label(frame, text=f"CPU: {self.raw_name}", style="Header.TLabel").grid(row=0, column=0, sticky=W, pady=(0,5))
        ttk.Label(frame, text=f"Brand: {self.brand}").grid(row=1, column=0, sticky=W, pady=(0,5))
        ttk.Label(frame, text=f"Cores: {self.cores['physical_cores']} physical / {self.cores['logical_cores']} logical").grid(row=0, column=1, sticky=W, padx=(20,0))
        ttk.Label(frame, textvariable=self.freq_var).grid(row=1, column=1, sticky=W, padx=(20,0))
        ttk.Label(frame, text=f"L3 Cache: {self.l3_cache_mb if self.l3_cache_mb else 'Unknown'} MB").grid(row=0, column=2, sticky=W, padx=(20,0))

        overall_frame = ttk.Frame(frame)
        overall_frame.grid(row=0, column=3, rowspan=2, sticky="e")
        ttk.Label(overall_frame, text="Overall CPU:").pack(anchor="e")
        self.overall_progress = ttk.Progressbar(overall_frame, orient="horizontal", length=220, mode="determinate")
        self.overall_progress.pack(pady=2)
        ttk.Label(overall_frame, textvariable=self.overall_var).pack(anchor="e")

    def _build_core_table(self):
        container = ttk.Frame(self.root, padding=15)
        container.pack(fill="both", expand=True)
        self.core_canvas = ttk.Frame(container)
        self.core_canvas.pack(fill="both", expand=True)

        header = ttk.Frame(self.core_canvas)
        header.pack(fill="x")
        ttk.Label(header, text="Core", width=10, style="Header.TLabel").grid(row=0, column=0, sticky=W)
        ttk.Label(header, text="Usage", style="Header.TLabel").grid(row=0, column=1, sticky=W)

        self.core_rows = []
        for i in range(self.cores['logical_cores']):
            row_bg = "#34495E" if i % 2 == 0 else "#3E556E"
            row = Frame(self.core_canvas, bg=row_bg)
            row.pack(fill="x", pady=2)
            Label(row, text=f"Core {i}", width=10, bg=row_bg, fg="white").grid(row=0, column=0, sticky=W, padx=5)
            p = ttk.Progressbar(row, orient="horizontal", length=500, mode="determinate")
            p.grid(row=0, column=1, sticky=W, padx=5)
            lbl_val = Label(row, text="-- %", width=8, bg=row_bg, fg="white")
            lbl_val.grid(row=0, column=2, sticky=W, padx=(6,0))
            self.core_rows.append((p, lbl_val))

    def _build_footer(self):
        frame = ttk.Frame(self.root, padding=15)
        frame.pack(fill="x")
        Button(frame, text="Refresh", command=self.refresh_stats, bg="#1ABC9C", fg="white", width=12).pack(side="left", padx=(5,0))
        Button(frame, text="Auto-refresh (5s)", command=self.toggle_auto_refresh, bg="#1ABC9C", fg="white", width=16).pack(side="left", padx=(6,0))
        Button(frame, text="Save report...", command=self.save_report, bg="#1ABC9C", fg="white", width=12).pack(side="left", padx=(6,0))
        Button(frame, text="Quit", command=self.root.quit, bg="#E74C3C", fg="white", width=8).pack(side="right", padx=(5,0))

    def _format_freq(self):
        if not self.freq or not self.freq.get('current_mhz'):
            return "Frequency: Unknown"
        return f"Frequency: {self.freq['current_mhz']} MHz ({self.freq['current_ghz']} GHz)"

    def refresh_stats(self):
        self.info_label.config(text="Updating CPU information...", fg="orange")
        threading.Thread(target=self._sample_and_update, daemon=True).start()

    def _sample_and_update(self):
        # discard first reading
        psutil.cpu_percent(percpu=True)
        per_core, overall = get_cpu_percentages(sample_interval=0.5)
        self.root.after(0, lambda: self._update_ui(per_core, overall))

    def _update_ui(self, per_core, overall):
        self.overall_var.set(f"{overall:.1f} %")
        self.overall_progress['value'] = overall
        for i, (bar, lbl) in enumerate(self.core_rows):
            val = per_core[i] if i < len(per_core) else 0
            bar['value'] = val
            lbl.config(text=f"{val:.1f} %")
        self.info_label.config(text="CPU information updated!", fg="green")

    def toggle_auto_refresh(self):
        self._auto_refresh = not self._auto_refresh
        if self._auto_refresh:
            threading.Thread(target=self._auto_loop, daemon=True).start()
            self.info_label.config(text="Auto-refresh enabled.", fg="blue")
        else:
            self.info_label.config(text="Auto-refresh stopped.", fg="red")

    def _auto_loop(self):
        while self._auto_refresh:
            self.refresh_stats()
            for _ in range(50):
                if not self._auto_refresh:
                    break
                threading.Event().wait(0.1)

    def save_report(self):
        per_core, overall = get_cpu_percentages(0.1)
        lines = [
            f"CPU: {self.raw_name}",
            f"Brand: {self.brand}",
            f"Cores: {self.cores['physical_cores']} physical / {self.cores['logical_cores']} logical",
            self._format_freq(),
            f"L3 Cache: {self.l3_cache_mb if self.l3_cache_mb else 'Unknown'} MB",
            "",
            f"Overall CPU Usage: {overall:.1f} %",
            "Per-core usage:"
        ]
        for i, val in enumerate(per_core):
            lines.append(f"  Core {i}: {val:.1f} %")

        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="cpu_report.txt",
                                            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            messagebox.showinfo("Saved", f"Report saved to: {path}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save report: {e}")

    def _show_about(self):
        messagebox.showinfo("About", "CPU Information App\nShows CPU stats with modern GUI.\nBuilt with psutil, py-cpuinfo, requests, bs4, and tkinter.")

    def _show_cpu_rating(self):
        rating = get_cpu_multithread_rating()
        messagebox.showinfo("CPU Multi-thread Rating", f"{self.raw_name}\nRating: {rating}")

# ---------- Main ----------
if __name__ == "__main__":
    root = Tk()
    app = CPUInfoApp(root)
    root.mainloop()
