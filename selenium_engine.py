import time
import json
import logging
import re
import os 
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementClickInterceptedException, ElementNotInteractableException, UnexpectedTagNameException, StaleElementReferenceException, TimeoutException, UnexpectedAlertPresentException, NoAlertPresentException

# --- V2.3 GHOST INSPECTOR ---
JS_INSPECTOR_SCRIPT = r"""
(function() {
    let dataDiv = document.getElementById('py-inspector-data');
    if (!dataDiv) {
        dataDiv = document.createElement('div');
        dataDiv.id = 'py-inspector-data';
        dataDiv.style.display = 'none';
        document.body.appendChild(dataDiv);
    }
    window.isInspecting = true;

    let overlay = document.getElementById('py-inspector-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'py-inspector-overlay';
        overlay.style.position = 'fixed';
        overlay.style.pointerEvents = 'none'; 
        overlay.style.zIndex = '999999';
        overlay.style.border = '3px solid #ff00ff'; 
        overlay.style.backgroundColor = 'rgba(255, 0, 255, 0.1)';
        overlay.style.boxSizing = 'border-box';
        overlay.style.transition = 'all 0.1s ease';
        overlay.style.display = 'none';
        document.body.appendChild(overlay);
    }

    function getDeepTarget(event) {
        const path = event.composedPath ? event.composedPath() : [];
        return path.length > 0 ? path[0] : event.target;
    }

    function isDynamicId(id) {
        if (!id) return false;
        if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) return true;
        if (/\d{6,}/.test(id)) return true; 
        return false;
    }

    function getCSSPath(el) {
        if (!(el instanceof Element)) return;
        var path = [];
        while (el.nodeType === Node.ELEMENT_NODE) {
            var selector = el.nodeName.toLowerCase();
            
            if (el.id && !isDynamicId(el.id)) {
                selector += '#' + el.id.split(/\s+/).join('#'); 
                path.unshift(selector);
                break;
            } else {
                var sib = el, nth = 1;
                while (sib = sib.previousElementSibling) {
                    if (sib.nodeName.toLowerCase() == selector) nth++;
                }
                if (nth != 1) selector += ":nth-of-type("+nth+")";
                
                if (el.classList.length > 0) {
                     const validClasses = Array.from(el.classList).filter(c => 
                        !/\d/.test(c) && 
                        !/active|hover|focus|visited|target|disabled|checked|selected|empty|ng-|is-|has-|ui-|show|hide|open/i.test(c)
                     );
                     if (validClasses.length > 0) selector += "." + validClasses.join('.');
                }
            }
            path.unshift(selector);
            el = el.parentNode;
        }
        return path.join(" > ");
    }

    function getXPath(element) {
        if (element.id !== '' && !isDynamicId(element.id)) return 'id("' + element.id + '")';
        if (element === document.body) return element.tagName;
        let ix = 0;
        let siblings = element.parentNode.childNodes;
        for (let i = 0; i < siblings.length; i++) {
            let sibling = siblings[i];
            if (sibling === element)
                return getXPath(element.parentNode) + '/' + element.tagName + '[' + (ix + 1) + ']';
            if (sibling.nodeType === 1 && sibling.tagName === element.tagName)
                ix++;
        }
    }

    function mouseOverHandler(event) {
        const target = getDeepTarget(event);
        if (!target || target === document.body || target === document.documentElement || target === overlay) return;
        const rect = target.getBoundingClientRect();
        overlay.style.display = 'block';
        overlay.style.top = rect.top + 'px';
        overlay.style.left = rect.left + 'px';
        overlay.style.width = rect.width + 'px';
        overlay.style.height = rect.height + 'px';
    }

    function mouseOutHandler(event) {
        overlay.style.display = 'none';
    }
    
    function clickHandler(event) {
        if (!window.isInspecting) return;
        event.preventDefault(); 
        event.stopPropagation(); 
        const target = getDeepTarget(event);
        const css = getCSSPath(target);
        const xpath = getXPath(target);
        const type = target.tagName.toLowerCase();
        dataDiv.innerText = JSON.stringify({ css: css, xpath: xpath.toLowerCase(), tag: type });
        cleanup();
    }

    function cleanup() {
        window.isInspecting = false;
        document.removeEventListener('mouseover', mouseOverHandler);
        document.removeEventListener('mouseout', mouseOutHandler);
        document.removeEventListener('click', clickHandler, true);
        if (overlay) overlay.remove();
        setTimeout(() => {
            const div = document.getElementById('py-inspector-data');
            if (div) div.innerText = '';
        }, 1000); 
    }

    document.addEventListener('mouseover', mouseOverHandler);
    document.addEventListener('mouseout', mouseOutHandler);
    document.addEventListener('click', clickHandler, true); 
})();
"""

class SeleniumEngine:
    def __init__(self, log_callback, poll_callback):
        self.driver = None
        self.log_callback = log_callback
        self.poll_callback = poll_callback
        self.inspection_mode = False
        self.auto_close = False 

    def launch_browser(self, url):
        if self.driver: return
        try:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--start-maximized")
            chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.get(url)
            self.log_callback(f"Browser launched: {url}")
        except Exception as e:
            self.log_callback(f"Error launching: {e}", level="ERROR")
            self.driver = None

    def close_browser(self):
        if self.driver:
            self.driver.quit()
            self.driver = None
            self.inspection_mode = False
            self.log_callback("Browser closed.")
    
    def start_inspector(self):
        if not self.driver: return
        self.inspection_mode = True
        try:
            self.driver.execute_script(JS_INSPECTOR_SCRIPT)
            self.poll_callback() 
        except Exception as e:
            self.log_callback(f"Error starting inspector: {e}", level="ERROR")
            self.inspection_mode = False
            
    def check_inspector_result(self):
        if not self.inspection_mode or not self.driver: return None
        try:
            result_json = self.driver.execute_script("return document.getElementById('py-inspector-data').innerText;")
            if result_json:
                data = json.loads(result_json)
                self.inspection_mode = False
                self.log_callback(f"Captured! CSS: {data['css']}")
                return data
            return None
        except:
            self.inspection_mode = False
            return None

    def get_input_type(self, selector, by_type):
        if not self.driver: return 'text'
        try:
            by = By.CSS_SELECTOR if by_type == 'CSS' else By.XPATH
            element = self.driver.find_element(by, selector)
            return element.get_attribute('type') or element.tag_name.lower()
        except:
            return 'text'

    def _safe_click(self, element):
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.1) 
            element.click()
        except (ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException):
            self.log_callback(f"     [Action Blocked] Forcing click via JS...", level="WARNING")
            self.driver.execute_script("arguments[0].click();", element)

    def _safe_check_checkbox(self, element, data_value):
        is_true = str(data_value).lower() in ("true", "yes", "1", "t", "y")
        if is_true and not element.is_selected():
            self._safe_click(element)
        elif not is_true and element.is_selected():
            self._safe_click(element)

    def _check_status_200(self):
        try:
            logs = self.driver.get_log('performance')
            for entry in reversed(logs): 
                message = json.loads(entry['message'])['message']
                if message['method'] == 'Network.responseReceived':
                    response = message['params']['response']
                    if response['status'] == 200:
                        return True
                    if response['status'] >= 400:
                        return False 
            return True 
        except Exception:
            return True 
            
    def _auto_handle_tabs(self, old_handles):
        for _ in range(10): 
            current_handles = self.driver.window_handles
            if len(current_handles) > len(old_handles):
                new_handle = [h for h in current_handles if h not in old_handles][0]
                if self.auto_close:
                    for handle in old_handles:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                    self.driver.switch_to.window(new_handle)
                    self.log_callback(f"     [Auto-Tab] Switched to new tab. Closed old.")
                else:
                    self.driver.switch_to.window(new_handle)
                    self.log_callback(f"     [Auto-Tab] Focused new tab (Old tabs kept open).")
                return 
            time.sleep(0.2) 

    def _sanitize_selector(self, selector):
        if not selector: return selector
        clean_sel = re.sub(r'\.(ng-|is-|has-|ui-)[a-zA-Z0-9_\-]+', '', selector, flags=re.IGNORECASE)
        if clean_sel != selector:
            self.log_callback(f"     [Sanitizer] Auto-cleaned selector: {clean_sel}")
        return clean_sel

    def _check_for_alert(self):
        try:
            WebDriverWait(self.driver, 0.5).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            text = alert.text
            self.log_callback(f"     [ALERT DETECTED] Site says: '{text}'", level="WARNING")
            alert.accept() 
            return text
        except (TimeoutException, NoAlertPresentException):
            return None

    def execute_step(self, step, data_value, step_index):
        action = step['action']
        raw_selector = step.get('selector_value', '')
        selector = self._sanitize_selector(raw_selector)
        selector_type = step.get('selector_type', 'CSS')

        self.log_callback(f"   - Step {step_index+1}: {action}")

        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            try:
                alert_text = self._check_for_alert()
                if alert_text: pass

                old_handles = self.driver.window_handles
                wait = WebDriverWait(self.driver, 15)

                # --- LOGIC STEPS ---
                if action == "Wait (seconds)":
                    time.sleep(float(data_value))
                    return
                if action == "Go to URL":
                    self.driver.get(str(data_value))
                    return
                if action == "Execute JS":
                    self.driver.execute_script(str(data_value))
                    return
                if action == "Wait for Page Load":
                    wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                    return
                if action == "Wait for Text":
                    wait.until(EC.text_to_be_present_in_element((By.TAG_NAME, "body"), str(data_value)))
                    return
                if action == "Wait for Status 200":
                    time.sleep(1)
                    if self._check_status_200():
                        self.log_callback(f"     [Status] Confirmed 200 OK signal.")
                        return
                    else:
                        raise Exception("Network logs indicate a non-200 (4xx/5xx) error.")
                if action == "Switch to New Tab":
                    self.auto_close = True 
                    self._auto_handle_tabs(old_handles)
                    return
                if action == "Take Screenshot":
                    timestamp = time.strftime("%Y%m%d-%H%M%S")
                    suffix = f"_{str(data_value)}" if data_value and str(data_value).strip() else ""
                    filename = f"Logic_Screenshot_{timestamp}{suffix}.png"
                    path = os.path.join("error_screenshots", filename)
                    self.driver.save_screenshot(path)
                    self.log_callback(f"     [Screenshot] Saved to {filename}")
                    return

                # --- SELECTOR STEPS ---
                by_strategy = By.CSS_SELECTOR if selector_type == "CSS" else By.XPATH
                
                element = wait.until(EC.presence_of_element_located((by_strategy, selector)))
                
                if action in ["Click", "Select Dropdown", "Check Radio/Box", "Set Date (JS)"]:
                    try:
                        WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable((by_strategy, selector)))
                    except TimeoutException:
                        self.log_callback(f"     [Visibility] Element not visible/clickable. Attempting JS Force...", level="WARNING")

                if action == "Type":
                    el_type = element.get_attribute('type')
                    if el_type in ['checkbox', 'radio']:
                        self._safe_check_checkbox(element, data_value)
                    else:
                        element.clear()
                        element.send_keys(str(data_value))

                elif action == "Click":
                    # --- NEW STRICT VALIDATION ---
                    # 1. Check if physically disabled
                    if not element.is_enabled():
                        raise Exception("Validation Failed: Button is disabled.")
                    
                    # 2. Check for "disabled" class (common in Bootstrap/Tailwind)
                    classes = element.get_attribute("class")
                    if classes and ("disabled" in classes or "inactive" in classes):
                        raise Exception("Validation Failed: Button has 'disabled' class.")
                    
                    self._safe_click(element)
                    self._check_for_alert() 
                    self._auto_handle_tabs(old_handles)

                elif action == "Select Dropdown":
                    try:
                        select = Select(element)
                        try:
                            select.select_by_visible_text(str(data_value))
                        except:
                            select.select_by_value(str(data_value))
                    except UnexpectedTagNameException:
                        self.log_callback(f"     [Smart-Drop] Not a <select>. Using click interaction...", level="WARNING")
                        self._safe_click(element) 
                        time.sleep(0.5) 
                        try:
                            option_xpath = f"//*[text()='{str(data_value)}']"
                            option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
                            self._safe_click(option)
                        except Exception:
                            option_xpath = f"//*[contains(text(), '{str(data_value)}')]"
                            option = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
                            self._safe_click(option)

                elif action == "Check Radio/Box":
                    self._safe_check_checkbox(element, data_value)

                elif action == "Set Date (JS)":
                    self.driver.execute_script("""
                        arguments[0].value = arguments[1];
                        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    """, element, str(data_value))
                
                self.log_callback(f"   - Step {step_index+1}: Success.")
                return 

            except StaleElementReferenceException:
                self.log_callback(f"     [Stale] Element refreshed. Retrying attempt {attempt+2}...", level="WARNING")
                time.sleep(1) 
                continue
            
            except UnexpectedAlertPresentException:
                self.log_callback(f"     [ALERT CRASH] Unexpected alert blocked action.", level="ERROR")
                self._check_for_alert() 
                continue 
            
            except Exception as e:
                raise Exception(f"Failed {action}: {e}")
        
        raise Exception(f"Failed {action} after {MAX_RETRIES} attempts")