"""
New GUI Application for Game UI Navigation Automation Tool
This provides a completely redesigned interface for controlling the automation tool.
"""

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import logging
import queue
from pathlib import Path

# Add logging handler for GUI
class QueueHandler(logging.Handler):
    """Send logging records to a queue"""
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)

class AutomationGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Game UI Navigation Tool")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # Variables
        self.sut_ip = tk.StringVar(value="192.168.50.231")
        self.sut_port = tk.StringVar(value="8000")
        self.game_path = tk.StringVar()
        self.lm_studio_url = tk.StringVar(value="http://127.0.0.1:1234")
        self.config_path = tk.StringVar(value="config/cs2_benchmark.yaml")
        self.max_iterations = tk.StringVar(value="50")
        self.vision_model = tk.StringVar(value="gemma")  # Default to Gemma
        self.running = False
        self.process_thread = None
        
        # Queue for logging
        self.log_queue = queue.Queue()
        self.setup_logger()
        
        # Create GUI elements
        self.create_widgets()
        
        # Configure style
        self.style = ttk.Style()
        self.style.configure("TButton", padding=6)
        self.style.configure("Green.TButton", background="green")
        self.style.configure("Red.TButton", background="red")
        
        # Start queue processing
        self.root.after(100, self.process_log_queue)
        
        # Save references to running objects
        self.automation_thread = None
        self.stop_event = threading.Event()

    def setup_logger(self):
        """Configure logging to both file and GUI"""
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        
        # Clear existing handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # File handler
        os.makedirs("logs", exist_ok=True)
        file_handler = logging.FileHandler(f"logs/gui_run_{time.strftime('%Y%m%d_%H%M%S')}.log")
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Queue handler for GUI
        queue_handler = QueueHandler(self.log_queue)
        queue_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', 
                                           datefmt='%H:%M:%S')
        queue_handler.setFormatter(queue_formatter)
        self.logger.addHandler(queue_handler)

    def create_widgets(self):
        """Create all the GUI elements"""
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ===== SETTINGS SECTION =====
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding="10")
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create a grid with 6 columns for better organization
        for i in range(6):
            settings_frame.columnconfigure(i, weight=1)
        
        # ---- ROW 1: SUT and LM Studio settings ----
        # SUT IP
        ttk.Label(settings_frame, text="SUT IP:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.sut_ip, width=15).grid(row=0, column=1, sticky=tk.W+tk.E, padx=5, pady=5)
        
        # SUT Port
        ttk.Label(settings_frame, text="Port:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.sut_port, width=6).grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        
        # LM Studio URL
        ttk.Label(settings_frame, text="LM Studio URL:").grid(row=0, column=4, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.lm_studio_url, width=25).grid(row=0, column=5, sticky=tk.W+tk.E, padx=5, pady=5)
        
        # ---- ROW 2: Game Path & Vision Model ----
        # Game Path
        ttk.Label(settings_frame, text="Game Path:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        path_frame = ttk.Frame(settings_frame)
        path_frame.grid(row=1, column=1, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)
        ttk.Entry(path_frame, textvariable=self.game_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="Browse...", command=self.browse_game_path).pack(side=tk.RIGHT, padx=5)
        
        # Vision Model - COMPLETELY REDESIGNED
        ttk.Label(settings_frame, text="Vision Model:").grid(row=1, column=4, sticky=tk.W, padx=5, pady=5)
        model_frame = ttk.Frame(settings_frame)
        model_frame.grid(row=1, column=5, sticky=tk.W, padx=5, pady=5)
        
        # Force enough space between radio buttons
        gemma_rb = ttk.Radiobutton(model_frame, text="Gemma", variable=self.vision_model, value="gemma")
        gemma_rb.pack(side=tk.LEFT)
        # Add a spacer label
        ttk.Label(model_frame, text="   ").pack(side=tk.LEFT)  
        qwen_rb = ttk.Radiobutton(model_frame, text="Qwen VL", variable=self.vision_model, value="qwen")
        qwen_rb.pack(side=tk.LEFT)
        
        # ---- ROW 3: Config & Max Iterations ----
        # Config File
        ttk.Label(settings_frame, text="Config File:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        config_frame = ttk.Frame(settings_frame)
        config_frame.grid(row=2, column=1, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)
        ttk.Entry(config_frame, textvariable=self.config_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(config_frame, text="Browse...", command=self.browse_config_path).pack(side=tk.RIGHT, padx=5)
        
        # Max Iterations
        ttk.Label(settings_frame, text="Max Iterations:").grid(row=2, column=4, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.max_iterations, width=6).grid(row=2, column=5, sticky=tk.W, padx=5, pady=5)
        
        # ===== ACTION BUTTONS =====
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.start_button = ttk.Button(button_frame, text="Start Automation", command=self.start_automation)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_automation, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Clear Logs", command=self.clear_logs).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(button_frame, text="Open Logs Folder", command=self.open_logs_folder).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Status indicators
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT, padx=5)
        self.status_label = ttk.Label(status_frame, text="Ready", foreground="blue")
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        # ===== SCREENSHOT SECTION =====
        self.image_frame = ttk.LabelFrame(main_frame, text="Latest Screenshot", padding="10")
        self.image_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(self.image_frame, text="Screenshots and annotated images will be saved to the logs folder").pack(padx=5, pady=20)
        ttk.Button(self.image_frame, text="Open Latest Screenshot", command=self.open_latest_screenshot).pack(padx=5, pady=5)
        
        # ===== LOG DISPLAY =====
        log_frame = ttk.LabelFrame(main_frame, text="Logs", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, width=80, height=20)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.config(state=tk.DISABLED)
        
        # Tag configuration for log levels
        self.log_area.tag_config("INFO", foreground="black")
        self.log_area.tag_config("DEBUG", foreground="gray")
        self.log_area.tag_config("WARNING", foreground="orange")
        self.log_area.tag_config("ERROR", foreground="red")
        self.log_area.tag_config("CRITICAL", foreground="red", background="yellow")

    def process_log_queue(self):
        """Process logs from the queue and display them in the GUI"""
        try:
            while True:
                record = self.log_queue.get_nowait()
                self.display_log(record)
        except queue.Empty:
            self.root.after(100, self.process_log_queue)

    def display_log(self, record):
        """Display a log record in the log area"""
        msg = self.format_log_record(record)
        self.log_area.config(state=tk.NORMAL)
        self.log_area.insert(tk.END, msg + "\n", record.levelname)
        self.log_area.see(tk.END)  # Scroll to the end
        self.log_area.config(state=tk.DISABLED)

    def format_log_record(self, record):
        """Format a log record for display"""
        formatter = self.logger.handlers[1].formatter
        return formatter.format(record)

    def browse_game_path(self):
        """Open file dialog to browse for game executable"""
        filepath = filedialog.askopenfilename(
            title="Select Game Executable",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if filepath:
            self.game_path.set(filepath)

    def browse_config_path(self):
        """Open file dialog to browse for config file"""
        filepath = filedialog.askopenfilename(
            title="Select Config File",
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")]
        )
        if filepath:
            self.config_path.set(filepath)

    def clear_logs(self):
        """Clear the log display area"""
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state=tk.DISABLED)

    def open_logs_folder(self):
        """Open the logs folder in file explorer"""
        logs_path = os.path.abspath("logs")
        os.makedirs(logs_path, exist_ok=True)
        
        # Platform-specific way to open folder
        if sys.platform == 'win32':
            os.startfile(logs_path)
        elif sys.platform == 'darwin':  # macOS
            import subprocess
            subprocess.Popen(['open', logs_path])
        else:  # Linux
            import subprocess
            subprocess.Popen(['xdg-open', logs_path])

    def open_latest_screenshot(self):
        """Open the latest annotated screenshot"""
        screenshots_dir = os.path.abspath("logs/annotated")
        os.makedirs(screenshots_dir, exist_ok=True)
        
        # Find the latest screenshot
        try:
            files = [os.path.join(screenshots_dir, f) for f in os.listdir(screenshots_dir) 
                     if f.startswith("annotated_") and f.endswith(".png")]
            if files:
                latest_file = max(files, key=os.path.getmtime)
                
                # Platform-specific way to open image
                if sys.platform == 'win32':
                    os.startfile(latest_file)
                elif sys.platform == 'darwin':  # macOS
                    import subprocess
                    subprocess.Popen(['open', latest_file])
                else:  # Linux
                    import subprocess
                    subprocess.Popen(['xdg-open', latest_file])
            else:
                messagebox.showinfo("No Screenshots", "No annotated screenshots found.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open screenshot: {str(e)}")

    def start_automation(self):
        """Start the automation process in a separate thread"""
        # Validate inputs
        try:
            port = int(self.sut_port.get())
            iterations = int(self.max_iterations.get())
            if port <= 0 or iterations <= 0:
                raise ValueError("Port and max iterations must be positive integers")
        except ValueError as e:
            messagebox.showerror("Invalid Input", str(e))
            return
        
        if not self.sut_ip.get():
            messagebox.showerror("Invalid Input", "SUT IP address is required")
            return
            
        if not self.game_path.get():
            messagebox.showerror("Invalid Input", "Game path is required")
            return
            
        if not self.config_path.get() or not os.path.exists(self.config_path.get()):
            messagebox.showerror("Invalid Input", "Config file does not exist")
            return
            
        # Clear stop event and update GUI state
        self.stop_event.clear()
        self.running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_label.config(text="Running", foreground="green")
        
        # Start automation in a separate thread
        self.automation_thread = threading.Thread(
            target=self.run_automation,
            daemon=True
        )
        self.automation_thread.start()
        
        # Log start
        self.logger.info("Starting automation process...")

    def stop_automation(self):
        """Stop the automation process"""
        if self.running and self.automation_thread:
            self.logger.info("Stopping automation process...")
            self.stop_event.set()
            self.running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="Stopped", foreground="red")

    def run_automation(self):
        """Run the main automation process"""
        try:
            # Import here to avoid circular imports
            import sys
            import time
            from modules.network import NetworkManager
            from modules.screenshot import ScreenshotManager
            from modules.gemma_client import GemmaClient
            from modules.qwen_client import QwenClient
            from modules.annotator import Annotator
            from modules.config_parser import ConfigParser
            from modules.decision_engine import DecisionEngine
            from modules.game_launcher import GameLauncher
            from modules.coordinate_scaler import CoordinateScaler
            
            # Create directory structure
            os.makedirs("logs", exist_ok=True)
            os.makedirs("logs/screenshots", exist_ok=True)
            os.makedirs("logs/annotated", exist_ok=True)
            
            # Initialize components
            self.logger.info(f"Connecting to SUT at {self.sut_ip.get()}:{self.sut_port.get()}")
            network = NetworkManager(self.sut_ip.get(), int(self.sut_port.get()))
            
            self.logger.info("Initializing components...")
            screenshot_mgr = ScreenshotManager(network)
            
            # Initialize the vision model based on user selection
            if self.vision_model.get() == 'gemma':
                self.logger.info("Using Gemma for UI detection")
                vision_model = GemmaClient(self.lm_studio_url.get())
            elif self.vision_model.get() == 'qwen':
                self.logger.info("Using Qwen VL for UI detection")
                vision_model = QwenClient(self.lm_studio_url.get())
                
            annotator = Annotator()
            config_parser = ConfigParser(self.config_path.get())
            decision_engine = DecisionEngine(config_parser.get_config())
            game_launcher = GameLauncher(network)
            coordinate_scaler = CoordinateScaler()
            
            # Main execution loop
            iteration = 0
            current_state = "initial"
            target_state = decision_engine.get_target_state()
            
            # Track time spent in each state to detect timeouts
            state_start_time = time.time()
            max_time_in_state = 60  # Maximum seconds to remain in the same state
            
            try:
                # Launch the game
                self.logger.info(f"Launching game from: {self.game_path.get()}")
                game_launcher.launch(self.game_path.get())
                
                # Wait for game to initialize
                self.logger.info("Waiting 30 seconds for game to fully initialize...")
                wait_time = 30
                for i in range(wait_time):
                    if self.stop_event.is_set():
                        break
                    time.sleep(1)
                    self.status_label.config(text=f"Initializing ({wait_time-i}s)")
                
                if self.stop_event.is_set():
                    self.logger.info("Automation stopped during initialization")
                    return
                    
                self.status_label.config(text="Running", foreground="green")
                
                while current_state != target_state and iteration < int(self.max_iterations.get()) and not self.stop_event.is_set():
                    iteration += 1
                    self.logger.info(f"Iteration {iteration}: Current state: {current_state}")
                    
                    # Check for timeout in current state
                    time_in_state = time.time() - state_start_time
                    if time_in_state > max_time_in_state:
                        self.logger.warning(f"Timeout in state {current_state} after {time_in_state:.1f} seconds")
                        # Attempt recovery - press escape and reset to initial state
                        network.send_action({"type": "key", "key": "escape"})
                        self.logger.info("Sending escape key as timeout recovery")
                        time.sleep(2)
                        current_state = "initial"
                        state_start_time = time.time()
                        continue
                    
                    # Capture screenshot
                    screenshot_path = f"logs/screenshots/screenshot_{iteration}.png"
                    screenshot_mgr.capture(screenshot_path)
                    self.logger.info(f"Screenshot captured: {screenshot_path}")
                    
                    # Process with vision model
                    bounding_boxes = vision_model.detect_ui_elements(screenshot_path)
                    self.logger.info(f"Detected {len(bounding_boxes)} UI elements")
                    
                    # Calibrate and scale coordinates
                    coordinate_scaler.calibrate_from_screenshot(screenshot_path, bounding_boxes)
                    scaled_boxes = coordinate_scaler.scale_bounding_boxes(bounding_boxes)
                    self.logger.info(f"Scaled coordinates with factors: X={coordinate_scaler.scale_x:.2f}, Y={coordinate_scaler.scale_y:.2f}")
                    
                    # Annotate screenshot with the original bounding boxes
                    annotated_path = f"logs/annotated/annotated_{iteration}.png"
                    annotator.draw_bounding_boxes(screenshot_path, bounding_boxes, annotated_path)
                    self.logger.info(f"Annotated screenshot saved: {annotated_path}")
                    
                    # Create a separate annotated image with scaled bounding boxes
                    scaled_annotated_path = f"logs/annotated/scaled_{iteration}.png"
                    annotator.draw_bounding_boxes(screenshot_path, scaled_boxes, scaled_annotated_path)
                    self.logger.info(f"Scaled annotated screenshot saved: {scaled_annotated_path}")
                    
                    # Determine next action using the scaled bounding boxes
                    previous_state = current_state
                    next_action, new_state = decision_engine.determine_next_action(
                        current_state, scaled_boxes
                    )
                    self.logger.info(f"Next action: {next_action}, transitioning to state: {new_state}")
                    
                    # Execute action
                    if next_action and not self.stop_event.is_set():
                        # Format the action for better logging
                        action_str = ""
                        if next_action.get("type") == "click":
                            action_str = f"Click at ({next_action.get('x')}, {next_action.get('y')})"
                        elif next_action.get("type") == "key":
                            action_str = f"Press key {next_action.get('key')}"
                        elif next_action.get("type") == "wait":
                            action_str = f"Wait for {next_action.get('duration')} seconds"
                        else:
                            action_str = str(next_action)
                            
                        self.logger.info(f"Executing action: {action_str}")
                        network.send_action(next_action)
                        self.logger.info(f"Action completed: {action_str}")
                    
                    # Update state
                    current_state = new_state
                    if previous_state != current_state:
                        # Reset timeout timer when state changes
                        state_start_time = time.time()
                        self.logger.info(f"State changed from {previous_state} to {current_state}")
                    
                    time.sleep(1)  # Small delay between iterations
                
                # Check if we reached the target state
                if current_state == target_state:
                    self.logger.info(f"Successfully reached target state: {target_state}")
                    self.status_label.config(text="Completed", foreground="green")
                elif self.stop_event.is_set():
                    self.logger.info("Automation process was manually stopped")
                    self.status_label.config(text="Stopped", foreground="red")
                else:
                    self.logger.warning(f"Failed to reach target state. Stopped at: {current_state}")
                    self.status_label.config(text="Failed", foreground="red")
                
            except Exception as e:
                self.logger.error(f"Error in main execution: {str(e)}", exc_info=True)
                self.status_label.config(text="Error", foreground="red")
            
        except Exception as e:
            self.logger.error(f"Error in automation process: {str(e)}", exc_info=True)
            self.status_label.config(text="Error", foreground="red")
        finally:
            # Cleanup
            self.logger.info("Cleaning up resources")
            if 'network' in locals():
                network.close()
            
            # Reset GUI state
            self.running = False
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_button.config(state=tk.DISABLED))
            
            self.logger.info("Automation process completed")

if __name__ == "__main__":
    # Ensure the modules can be imported
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Create and run the GUI
    root = tk.Tk()
    app = AutomationGUI(root)
    root.mainloop()