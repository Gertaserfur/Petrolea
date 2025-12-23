import os
import socket
import time
import requests
import threading
import json

class AuditLogger:
    """
    Handles sending execution logs to a central remote server (Webhook).
    Runs asynchronously to avoid blocking the main automation thread.
    """
    def __init__(self):
        try:
            self.user = os.getlogin()
        except:
            self.user = "Unknown"
            
        try:
            self.hostname = socket.gethostname()
        except:
            self.hostname = "Unknown"

    def send_log(self, webhook_url, row_index, status, error_msg="", config_name=""):
        if not webhook_url or not webhook_url.startswith("http"):
            return 

        payload = {
            "app": "Petrolea",
            "version": "1.0",
            "user": self.user,
            "machine": self.hostname,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "row_index": row_index,
            "status": status,
            "error_details": error_msg,
            "config_name": config_name
        }

        thread = threading.Thread(target=self._post_request, args=(webhook_url, payload))
        thread.daemon = True
        thread.start()

    def _post_request(self, url, payload):
        try:
            headers = {'Content-Type': 'application/json'}
            requests.post(url, json=payload, headers=headers, timeout=5)
        except Exception as e:
            print(f"[Audit Error] Failed to send log: {e}")