import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, simpledialog
import pandas as pd
import time
import json
import logging
import threading
import os
import glob
import ctypes 
import traceback
import math 
import socket 
from selenium_engine import SeleniumEngine
from audit_logger import AuditLogger 

logging.basicConfig(
    filename='automation.log', 
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

class AutofillerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Petrolea - Browser Automation Tool")
        self.geometry("1400x850") 
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # Ensure directories exist
        for folder in ["saved_configs", "error_screenshots", "logs", "logs/success", "logs/failures"]:
            if not os.path.exists(folder):
                os.makedirs(folder)

        self.engine = SeleniumEngine(self._update_log, self._start_polling)
        self.audit = AuditLogger() 
        
        self.excel_data = None
        self.excel_headers = []
        self.steps = [] 
        self.is_running = False
        self.stop_signal = False

        self.start_url = ctk.StringVar(value="https://example.com/form")
        self.webhook_url = ctk.StringVar(value="") 
        self.excel_filepath = ctk.StringVar(value="No file selected")
        self.reset_session = ctk.BooleanVar(value=True)
        self.auto_close_tabs = ctk.BooleanVar(value=False)
        self.thread_count = ctk.StringVar(value="1") 
        
        self.selected_config = ctk.StringVar(value="")

        self._create_widgets()
        self._refresh_config_list()
        self._update_log(f"App started on {socket.gethostname()}.")

    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=0) 
        self.grid_columnconfigure(1, weight=1) 
        self.grid_rowconfigure(1, weight=1)

        # --- Top Control Panel ---
        top_panel = ctk.CTkFrame(self)
        top_panel.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="ew")
        
        r1 = ctk.CTkFrame(top_panel, fg_color="transparent")
        r1.pack(fill="x", padx=5, pady=5)
        
        ctk.CTkLabel(r1, text="Saved Configs:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=5)
        self.config_dropdown = ctk.CTkComboBox(r1, variable=self.selected_config, width=200)
        self.config_dropdown.pack(side="left", padx=5)
        
        ctk.CTkButton(r1, text="Load", width=60, command=self._load_selected_config).pack(side="left", padx=2)
        ctk.CTkButton(r1, text="Save New...", width=80, fg_color="#E07A5F", command=self._save_config_as).pack(side="left", padx=2)
        
        ctk.CTkLabel(r1, text="| Target URL:").pack(side="left", padx=(15, 5))
        ctk.CTkEntry(r1, textvariable=self.start_url, width=300).pack(side="left", padx=5, fill="x", expand=True)

        # Webhook Input
        r_webhook = ctk.CTkFrame(top_panel, fg_color="transparent")
        r_webhook.pack(fill="x", padx=5, pady=0)
        ctk.CTkLabel(r_webhook, text="Audit Webhook (Optional):", text_color="gray", font=("Arial", 10)).pack(side="left", padx=5)
        ctk.CTkEntry(r_webhook, textvariable=self.webhook_url, placeholder_text="https://webhook.site/...", height=20, border_width=0, fg_color="transparent").pack(side="left", padx=5, fill="x", expand=True)

        r2 = ctk.CTkFrame(top_panel, fg_color="transparent")
        r2.pack(fill="x", padx=5, pady=5)

        ctk.CTkButton(r2, text="Open Setup Browser", command=self._open_browser_thread, width=140, fg_color="#555555").pack(side="left", padx=5)
        ctk.CTkButton(r2, text="Close Setup", command=self.engine.close_browser, width=100, fg_color="#333333").pack(side="left", padx=5)
        
        ctk.CTkLabel(r2, text="| Excel File:").pack(side="left", padx=(15, 5))
        ctk.CTkLabel(r2, textvariable=self.excel_filepath, text_color="gray", width=300, anchor="w").pack(side="left", padx=5)
        ctk.CTkButton(r2, text="Browse...", command=self._load_excel_file, width=80).pack(side="left", padx=5)

        # --- Left Panel (Data) ---
        self.data_frame = ctk.CTkFrame(self, width=250)
        self.data_frame.grid(row=1, column=0, padx=(20, 10), pady=10, sticky="nsew")
        ctk.CTkLabel(self.data_frame, text="Data Preview", font=ctk.CTkFont(weight="bold")).pack(pady=5)
        self.data_preview = tk.Text(self.data_frame, wrap="none", width=30, height=20, bg="#2b2b2b", fg="#dce4ee", relief="flat")
        self.data_preview.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Right Panel (Steps) ---
        self.mapping_frame = ctk.CTkFrame(self)
        self.mapping_frame.grid(row=1, column=1, padx=(10, 20), pady=10, sticky="nsew")
        self.mapping_frame.grid_rowconfigure(2, weight=1)
        self.mapping_frame.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(self.mapping_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(header_frame, text="Automation Steps", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        
        ctk.CTkButton(header_frame, text="+ Logic Step", command=self._add_logic_step, fg_color="#5F9EA0", width=100).pack(side="right", padx=5)
        ctk.CTkButton(header_frame, text="+ Inspector Step", command=self.engine.start_inspector, fg_color="green", width=120).pack(side="right", padx=5)

        # Column Labels
        labels_frame = ctk.CTkFrame(self.mapping_frame, height=30)
        labels_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5,0))
        ctk.CTkLabel(labels_frame, text="#", width=30).pack(side="left", padx=2)
        ctk.CTkLabel(labels_frame, text="Action", width=140).pack(side="left", padx=2)
        ctk.CTkLabel(labels_frame, text="Type", width=70).pack(side="left", padx=2)
        ctk.CTkLabel(labels_frame, text="Target Element (Selector)", width=300).pack(side="left", padx=2)
        ctk.CTkLabel(labels_frame, text="Value Source", width=130).pack(side="left", padx=2)
        ctk.CTkLabel(labels_frame, text="Value / Column", width=130).pack(side="left", padx=2)
        ctk.CTkLabel(labels_frame, text="Controls", width=100).pack(side="right", padx=10)

        self.steps_scroll_frame = ctk.CTkScrollableFrame(self.mapping_frame, fg_color="transparent")
        self.steps_scroll_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

        # --- Bottom Bar ---
        bottom_frame = ctk.CTkFrame(self, height=150)
        bottom_frame.grid(row=2, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        
        controls_row = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        controls_row.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(controls_row, text="Browsers (Threads):", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(15, 5))
        ctk.CTkComboBox(controls_row, variable=self.thread_count, values=["1", "2", "3", "4", "5"], width=60, state="readonly").pack(side="left", padx=2)

        ctk.CTkCheckBox(controls_row, text="Reset Session", variable=self.reset_session).pack(side="left", padx=15)
        ctk.CTkCheckBox(controls_row, text="Auto-Close Old Tabs", variable=self.auto_close_tabs).pack(side="left", padx=5)
        
        ctk.CTkButton(controls_row, text="RUN AUTOMATION", fg_color="#006400", width=150, font=ctk.CTkFont(size=14, weight="bold"), command=self._run_automation_thread).pack(side="right", padx=5)
        ctk.CTkButton(controls_row, text="STOP", fg_color="#8B0000", width=100, font=ctk.CTkFont(size=14, weight="bold"), command=self._stop_automation).pack(side="right", padx=5)

        self.log_output = tk.Text(bottom_frame, height=5, wrap="word", bg="#1f1f1f", fg="#AAAAAA", relief="flat")
        self.log_output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # --- EXECUTION LOGIC ---
    def _run_automation_thread(self):
        if self.is_running: return
        if not self.steps:
            self._update_log("No steps defined.", level="ERROR")
            return
        if self.excel_data is None or self.excel_data.empty:
            self._update_log("No Excel data.", level="ERROR")
            return
        
        cookies = []
        if self.engine.driver:
            try:
                cookies = self.engine.driver.get_cookies()
                self._update_log(f"Harvested {len(cookies)} cookies from Setup Browser.")
            except: pass

        threading.Thread(target=self._orchestrate_automation, args=(cookies,), daemon=True).start()

    def _stop_automation(self):
        if self.is_running:
            self.stop_signal = True
            self._update_log("Stopping automation...", level="WARNING")

    def _orchestrate_automation(self, shared_cookies):
        self.is_running = True
        self.stop_signal = False
        
        num_threads = int(self.thread_count.get())
        total_rows = len(self.excel_data)
        
        self._update_log(f"Starting {total_rows} rows using {num_threads} simultaneous browser(s).")
        
        self.success_rows = []
        self.failed_rows = []
        
        chunks = []
        chunk_size = math.ceil(total_rows / num_threads)
        for i in range(0, total_rows, chunk_size):
            chunks.append(self.excel_data.iloc[i:i+chunk_size])
            
        def worker_task(worker_id, dataframe_chunk):
            def worker_log(msg, level="INFO"):
                self._update_log(f"[W{worker_id}] {msg}", level)
            
            local_engine = SeleniumEngine(worker_log, lambda: None)
            local_engine.auto_close = self.auto_close_tabs.get()
            
            try:
                worker_log("Launching browser...")
                local_engine.launch_browser(self.start_url.get())
                
                if shared_cookies:
                    try:
                        for cookie in shared_cookies:
                            cookie_dict = {k: v for k, v in cookie.items() if k in ['name', 'value', 'domain', 'path', 'expiry', 'secure', 'httpOnly']}
                            local_engine.driver.add_cookie(cookie_dict)
                        local_engine.driver.refresh()
                    except: pass

                for idx, row in dataframe_chunk.iterrows():
                    if self.stop_signal: break
                        
                    if self.reset_session.get():
                        try: local_engine.driver.get(self.start_url.get())
                        except: pass
                    
                    row_success = True
                    error_message = ""
                    try:
                        for step_idx, step in enumerate(self.steps):
                            if self.stop_signal: break
                            val = step['value']
                            if step['value_source'] in self.excel_headers:
                                val = row[step['value_source']]
                            local_engine.execute_step(step, val, step_idx)
                        
                    except Exception as e:
                        row_success = False
                        error_message = str(e)
                        worker_log(f"Row {idx+1} Failed: {e}", "ERROR")
                        try:
                            ts = time.strftime("%H%M%S")
                            sc_path = os.path.join("error_screenshots", f"W{worker_id}_Row{idx+1}_{ts}.png")
                            local_engine.driver.save_screenshot(sc_path)
                        except: pass

                    # --- AUDIT, REPORTING & GRANULAR FILE LOGGING ---
                    status = "SUCCESS" if row_success else "FAILED"
                    if self.stop_signal: status = "STOPPED"
                    
                    self.audit.send_log(self.webhook_url.get(), idx+1, status, error_message, self.selected_config.get())

                    # Prepare Row Data
                    row_data = row.to_dict()
                    row_data["_ProcessStatus"] = status
                    row_data["_ErrorMessage"] = error_message
                    row_data["_Timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

                    # SAVE PER-ROW JSON FILE
                    try:
                        filename = f"Row_{idx+1}_{status}.json"
                        folder = "logs/success" if row_success else "logs/failures"
                        filepath = os.path.join(folder, filename)
                        
                        with open(filepath, "w", encoding='utf-8') as f:
                            json.dump(row_data, f, indent=4, default=str)
                    except Exception as e:
                        print(f"Failed to save log file: {e}")

                    # Add to summary lists
                    if row_success:
                        self.success_rows.append(row_data)
                        if not self.stop_signal:
                            worker_log(f"Row {idx+1} Done.", "SUCCESS")
                    else:
                        self.failed_rows.append(row_data)
                    # ------------------------------------------------

            except Exception as e:
                worker_log(f"Critical Error: {e}", "ERROR")
            finally:
                local_engine.close_browser()

        threads = []
        for i, chunk in enumerate(chunks):
            if chunk.empty: continue
            t = threading.Thread(target=worker_task, args=(i+1, chunk))
            t.start()
            threads.append(t)
            
        for t in threads:
            t.join()
            
        # --- GENERATE SUMMARY REPORTS ---
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        if self.success_rows:
            success_df = pd.DataFrame(self.success_rows)
            success_path = f"logs/success_summary_{timestamp}.csv"
            success_df.to_csv(success_path, index=False)
            self._update_log(f"Success Summary saved: {success_path}", "SUCCESS")
            
        if self.failed_rows:
            fail_df = pd.DataFrame(self.failed_rows)
            fail_path = f"logs/failure_summary_{timestamp}.csv"
            fail_df.to_csv(fail_path, index=False)
            self._update_log(f"Failure Summary saved: {fail_path}", "ERROR")

        self.is_running = False
        self._update_log("All workers finished.")

    # --- CONFIG MANAGEMENT ---
    def _refresh_config_list(self):
        files = glob.glob("saved_configs/*.json")
        config_names = [os.path.basename(f).replace(".json", "") for f in files]
        if config_names:
            self.config_dropdown.configure(values=config_names)
            if not self.selected_config.get(): self.selected_config.set(config_names[0])
        else:
            self.config_dropdown.configure(values=["No Configs"])
            self.selected_config.set("No Configs")

    def _save_config_as(self):
        name = ctk.CTkInputDialog(text="Name:", title="Save").get_input()
        if not name: return
        config = {
            "start_url": self.start_url.get(), 
            "webhook_url": self.webhook_url.get(),
            "excel_filepath": self.excel_filepath.get(),
            "reset_session": self.reset_session.get(), "auto_close_tabs": self.auto_close_tabs.get(),
            "steps": self.steps
        }
        with open(f"saved_configs/{name.strip()}.json", "w") as f: json.dump(config, f, indent=4)
        self._refresh_config_list()
        self.selected_config.set(name)

    def _load_selected_config(self):
        name = self.selected_config.get()
        if not name or name == "No Configs": return
        try:
            with open(f"saved_configs/{name}.json", "r") as f: config = json.load(f)
            self.start_url.set(config.get("start_url", ""))
            self.webhook_url.set(config.get("webhook_url", ""))
            self.excel_filepath.set(config.get("excel_filepath", "No file"))
            self.reset_session.set(config.get("reset_session", True))
            self.auto_close_tabs.set(config.get("auto_close_tabs", False))
            self.steps = config.get("steps", [])
            self._render_steps()
            if self.excel_filepath.get() != "No file": self._load_excel_internal(config.get("excel_filepath"))
            self._update_log(f"Loaded '{name}'")
        except Exception as e: self._update_log(f"Load Error: {e}", "ERROR")

    # --- ROW RENDERING ---
    def _render_steps(self):
        for widget in self.steps_scroll_frame.winfo_children(): widget.destroy()
        for index, step in enumerate(self.steps): self._create_step_row(index, step)

    def _create_step_row(self, index, step):
        row_frame = ctk.CTkFrame(self.steps_scroll_frame)
        row_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(row_frame, text=str(index + 1), width=30).pack(side="left", padx=2)
        
        actions = ["Type", "Click", "Select Dropdown", "Check Radio/Box", "Set Date (JS)", 
                   "Wait (seconds)", "Go to URL", "Wait for Page Load", "Wait for Text", "Execute JS", "Wait for Status 200", "Switch to New Tab", "Take Screenshot"]
        action_var = ctk.StringVar(value=step.get("action", "Type"))
        ctk.CTkOptionMenu(row_frame, variable=action_var, values=actions, width=140, dynamic_resizing=False,
            command=lambda val, idx=index: self._update_step_data(idx, "action", val)).pack(side="left", padx=2)

        type_var = ctk.StringVar(value=step.get("selector_type", "CSS"))
        ctk.CTkOptionMenu(row_frame, variable=type_var, values=["CSS", "XPath"], width=70, dynamic_resizing=False,
            command=lambda val, idx=index: self._update_selector_type(idx, val)).pack(side="left", padx=2)

        selector_entry = ctk.CTkEntry(row_frame, width=300)
        selector_entry.insert(0, step.get("selector_value", ""))
        selector_entry.bind("<KeyRelease>", lambda event, idx=index: self._update_step_data(idx, "selector_value", event.widget.get()))
        if step.get("action") in ["Wait (seconds)", "Go to URL", "Wait for Page Load", "Wait for Text", "Execute JS", "Wait for Status 200", "Switch to New Tab", "Take Screenshot"]:
            selector_entry.configure(state="disabled", fg_color="gray25")
        selector_entry.pack(side="left", padx=2)

        source_options = ["Static Value"] + self.excel_headers
        source_var = ctk.StringVar(value=step.get("value_source", "Static Value"))
        value_entry = ctk.CTkEntry(row_frame, width=130)
        def on_source_change(val, idx=index, entry=value_entry):
            self._update_step_data(idx, "value_source", val)
            entry.configure(state="normal" if val == "Static Value" else "disabled", 
                            fg_color=["#F9F9FA", "#343638"] if val == "Static Value" else "gray25")
        ctk.CTkOptionMenu(row_frame, variable=source_var, values=source_options, width=130, dynamic_resizing=False,
            command=on_source_change).pack(side="left", padx=2)

        value_entry.insert(0, step.get("value", ""))
        value_entry.bind("<KeyRelease>", lambda event, idx=index: self._update_step_data(idx, "value", event.widget.get()))
        if step.get("value_source") != "Static Value": value_entry.configure(state="disabled", fg_color="gray25")
        value_entry.pack(side="left", padx=2)

        ctk.CTkButton(row_frame, text="✕", width=30, fg_color="darkred", command=lambda idx=index: self._delete_step(idx)).pack(side="right", padx=2)
        ctk.CTkButton(row_frame, text="↓", width=30, fg_color="gray", command=lambda idx=index: self._move_step(idx, 1)).pack(side="right", padx=2)
        ctk.CTkButton(row_frame, text="↑", width=30, fg_color="gray", command=lambda idx=index: self._move_step(idx, -1)).pack(side="right", padx=2)
        ctk.CTkButton(row_frame, text="▶", width=30, fg_color="#3B8ED0", command=lambda idx=index: self._test_single_step(idx)).pack(side="right", padx=5)

    def _add_logic_step(self):
        self.steps.append({"action": "Wait (seconds)", "selector_type": "CSS", "selector_value": "N/A", "value_source": "Static Value", "value": "1.0", "tag": "logic"})
        self._render_steps()
    def _update_step_data(self, index, key, value):
        if 0 <= index < len(self.steps): 
            self.steps[index][key] = value
            if key == "action": self._render_steps()
    def _update_selector_type(self, index, new_type):
        if 0 <= index < len(self.steps):
            self.steps[index]["selector_type"] = new_type
            if new_type == "CSS" and "captured_css" in self.steps[index]: self.steps[index]["selector_value"] = self.steps[index]["captured_css"]
            elif new_type == "XPath" and "captured_xpath" in self.steps[index]: self.steps[index]["selector_value"] = self.steps[index]["captured_xpath"]
            self._render_steps()
    def _move_step(self, index, direction):
        new_index = index + direction
        if 0 <= new_index < len(self.steps):
            self.steps[index], self.steps[new_index] = self.steps[new_index], self.steps[index]
            self._render_steps()
    def _delete_step(self, index):
        if 0 <= index < len(self.steps):
            del self.steps[index]
            self._render_steps()

    # --- ENGINE GLUE ---
    def _open_browser_thread(self):
        if self.engine.driver: return
        threading.Thread(target=lambda: self.engine.launch_browser(self.start_url.get()), daemon=True).start()
    def _start_polling(self): self.after(500, self._poll_inspector_result)
    def _poll_inspector_result(self):
        if not self.engine.inspection_mode: return
        data = self.engine.check_inspector_result()
        if data: self._add_new_step(data)
        else: self.after(500, self._poll_inspector_result)
    def _add_new_step(self, data):
        input_type = self.engine.get_input_type(data['css'], 'CSS')
        tag = data['tag']
        default_action = "Click"
        if tag == 'select': default_action = "Select Dropdown"
        elif input_type in ('checkbox', 'radio'): default_action = "Check Radio/Box"
        elif input_type in ('date', 'datetime-local', 'month', 'week', 'time'): default_action = "Set Date (JS)"
        elif input_type in ('submit', 'button', 'image', 'reset'): default_action = "Click"
        elif tag in ('input', 'textarea'): default_action = "Type"
        self.steps.append({"action": default_action, "selector_type": "CSS", "selector_value": data['css'], "captured_css": data['css'], "captured_xpath": data['xpath'], "value_source": "Static Value", "value": "", "tag": tag})
        self._render_steps()

    # --- EXCEL ---
    def _load_excel_file(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if not path: return
        self._load_excel_internal(path)
    def _load_excel_internal(self, path):
        try:
            self.excel_data = pd.read_excel(path).fillna("")
            self.excel_filepath.set(path)
            self.excel_headers = self.excel_data.columns.tolist()
            self._update_excel_preview()
            self._render_steps() 
            self._update_log(f"Excel loaded: {len(self.excel_data)} rows.")
        except Exception as e: self._update_log(f"Error loading Excel: {e}", level="ERROR")
    def _update_excel_preview(self):
        self.data_preview.delete('1.0', tk.END)
        self.data_preview.insert(tk.END, "COLUMNS:\n" + ", ".join(self.excel_headers) + "\n\n")
        self.data_preview.insert(tk.END, "FIRST 5 ROWS:\n")
        for i in range(min(5, len(self.excel_data))):
            row_data = [str(self.excel_data.iloc[i][header]) for header in self.excel_headers]
            self.data_preview.insert(tk.END, f"Row {i+1}: " + ", ".join(row_data) + "\n")

    def _test_single_step(self, index):
        step = self.steps[index]
        self._update_log(f"Testing Step {index + 1}...")
        threading.Thread(target=lambda: self._run_test(step, index), daemon=True).start()
    def _run_test(self, step, index):
        try:
            self.engine.execute_step(step, step['value'], index)
            self._update_log(f"Step {index + 1} Passed.", level="SUCCESS")
        except Exception as e: self._update_log(f"Step {index + 1} Failed: {e}", level="ERROR")

    # --- LOGGING ---
    def _update_log(self, message, level="INFO"):
        log_level = getattr(logging, level.upper(), logging.INFO)
        logging.log(log_level, message)
        color = {"INFO":"white", "WARNING":"orange", "ERROR":"red", "SUCCESS":"green"}.get(level, "white")
        self.after(0, lambda: self._do_log(message, level.lower(), color))
    def _do_log(self, message, tag, color):
        self.log_output.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {message}\n", tag)
        self.log_output.tag_config(tag, foreground=color)
        self.log_output.see(tk.END)

if __name__ == "__main__":
    app = AutofillerApp()
    app.mainloop()