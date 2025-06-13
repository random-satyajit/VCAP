"""
GUI Application for Game UI Navigation Automation Tool
This provides a user-friendly interface for controlling the automation tool.
"""

import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import logging
import queue
import yaml
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
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)
        
        # Variables
        self.sut_ip = tk.StringVar(value="192.168.50.231")
        self.sut_port = tk.StringVar(value="8080")
        self.game_path = tk.StringVar()
        self.lm_studio_url = tk.StringVar(value="http://127.0.0.1:1234")
        self.config_path = tk.StringVar(value="config/games/cs2_benchmark.yaml")
        self.max_iterations = tk.StringVar(value="50")
        self.vision_model = tk.StringVar(value="gemma")  # Default to Gemma
        self.omniparser_url = tk.StringVar(value="http://localhost:8000")  # Default Omniparser URL
        self.running = False
        self.process_thread = None
        self.game_name = "Unknown Game"  # Added for game-specific paths
        
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
        file_handler = logging.FileHandler(f"logs/gui_run_{time.strftime('%Y_%m_%d__%H_%M_%S')}.log")
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
        """Create all the GUI elements with logs on the right side"""
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create left and right panes for split layout
        left_pane = ttk.Frame(main_frame)
        right_pane = ttk.Frame(main_frame)
        
        # Place the panes side by side
        left_pane.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))
        right_pane.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        # ===== SETTINGS SECTION (LEFT PANE) =====
        settings_frame = ttk.LabelFrame(left_pane, text="Settings", padding="10")
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
        
        # Vision System URL
        ttk.Label(settings_frame, text="Vision System URL:").grid(row=0, column=4, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.lm_studio_url, width=25).grid(row=0, column=5, sticky=tk.W+tk.E, padx=5, pady=5)
        
        # ---- ROW 2: Game Path & Vision Model ----
        # Game Path
        ttk.Label(settings_frame, text="Game Path:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        path_frame = ttk.Frame(settings_frame)
        path_frame.grid(row=1, column=1, columnspan=3, sticky=tk.W+tk.E, padx=5, pady=5)
        ttk.Entry(path_frame, textvariable=self.game_path).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="Browse...", command=self.browse_game_path).pack(side=tk.RIGHT, padx=5)
        
        # Vision Model Selection
        ttk.Label(settings_frame, text="Vision Model:").grid(row=1, column=4, sticky=tk.W, padx=5, pady=5)
        model_frame = ttk.Frame(settings_frame)
        model_frame.grid(row=1, column=5, sticky=tk.W, padx=5, pady=5)
        
        # Force enough space between radio buttons
        gemma_rb = ttk.Radiobutton(model_frame, text="Gemma", variable=self.vision_model, value="gemma",
                                command=self.update_vision_model_ui)
        gemma_rb.pack(side=tk.LEFT)
        # Add a spacer label
        ttk.Label(model_frame, text="   ").pack(side=tk.LEFT)  
        qwen_rb = ttk.Radiobutton(model_frame, text="Qwen VL", variable=self.vision_model, value="qwen",
                                command=self.update_vision_model_ui)
        qwen_rb.pack(side=tk.LEFT)
        # Add Omniparser option
        ttk.Label(model_frame, text="   ").pack(side=tk.LEFT)
        omniparser_rb = ttk.Radiobutton(model_frame, text="Omniparser", variable=self.vision_model, value="omniparser",
                                    command=self.update_vision_model_ui)
        omniparser_rb.pack(side=tk.LEFT)
        
        # Additional settings for Omniparser
        self.omniparser_frame = ttk.Frame(settings_frame)
        self.omniparser_frame.grid(row=3, column=0, columnspan=6, sticky=tk.W+tk.E, padx=5, pady=5)
        ttk.Label(self.omniparser_frame, text="Omniparser URL:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(self.omniparser_frame, textvariable=self.omniparser_url, width=30).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.omniparser_status_label = ttk.Label(self.omniparser_frame, text="Not Connected", foreground="red")
        self.omniparser_status_label.pack(side=tk.LEFT, padx=5)
        ttk.Button(self.omniparser_frame, text="Test Connection", command=self.test_omniparser_connection).pack(side=tk.LEFT, padx=5)
        
        # Initially hide Omniparser settings
        self.omniparser_frame.grid_remove()
        
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
        
        # ---- ROW 4: Game Information ----
        # Game Info Label (new)
        self.game_info_frame = ttk.Frame(settings_frame)
        self.game_info_frame.grid(row=4, column=0, columnspan=6, sticky=tk.W+tk.E, padx=5, pady=5)
        ttk.Label(self.game_info_frame, text="Game Info:").pack(side=tk.LEFT, padx=5)
        self.game_info_label = ttk.Label(self.game_info_frame, text="No game selected", foreground="blue")
        self.game_info_label.pack(side=tk.LEFT, padx=5)
        
        # ===== ACTION BUTTONS =====
        button_frame = ttk.Frame(left_pane)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.start_button = ttk.Button(button_frame, text="Start Automation", command=self.start_automation)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_automation, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Clear Logs", command=self.clear_logs).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(button_frame, text="Open Logs Folder", command=self.open_logs_folder).pack(side=tk.LEFT, padx=5, pady=5)
        
        # Status indicators
        status_frame = ttk.Frame(left_pane)
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(status_frame, text="Status:").pack(side=tk.LEFT, padx=5)
        self.status_label = ttk.Label(status_frame, text="Ready", foreground="blue")
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        # ===== SCREENSHOT SECTION =====
        self.image_frame = ttk.LabelFrame(left_pane, text="Latest Screenshot", padding="10")
        self.image_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(self.image_frame, text="Screenshots and annotated images will be saved to the logs folder").pack(padx=5, pady=10)
        ttk.Button(self.image_frame, text="Open Latest Screenshot", command=self.open_latest_screenshot).pack(padx=5, pady=5)
        
        # ===== LOG DISPLAY (RIGHT PANE) =====
        log_frame = ttk.LabelFrame(right_pane, text="Logs", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, width=50, height=40)
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.config(state=tk.DISABLED)
        
        # Tag configuration for log levels
        self.log_area.tag_config("INFO", foreground="black")
        self.log_area.tag_config("DEBUG", foreground="gray")
        self.log_area.tag_config("WARNING", foreground="orange")
        self.log_area.tag_config("ERROR", foreground="red")
        self.log_area.tag_config("CRITICAL", foreground="red", background="yellow")
        
        # Load game info if a config file is already selected
        self.load_game_info()

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

    def update_vision_model_ui(self):
        """Update UI based on selected vision model"""
        if self.vision_model.get() == "omniparser":
            self.omniparser_frame.grid()
        else:
            self.omniparser_frame.grid_remove()
    
    def test_omniparser_connection(self):
        """Test connection to Omniparser server"""
        try:
            import requests
            response = requests.get(f"{self.omniparser_url.get()}/probe", timeout=5)
            if response.status_code == 200:
                self.omniparser_status_label.config(text="Connected", foreground="green")
                messagebox.showinfo("Success", "Successfully connected to Omniparser server!")
            else:
                self.omniparser_status_label.config(text="Connection Failed", foreground="red")
                messagebox.showerror("Error", f"Failed to connect to Omniparser server: HTTP {response.status_code}")
        except Exception as e:
            self.omniparser_status_label.config(text="Connection Failed", foreground="red")
            messagebox.showerror("Error", f"Failed to connect to Omniparser server: {str(e)}")
    
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
            # Load game info when a new config is selected
            self.load_game_info()

    def load_game_info(self):
        """Load and display game information from the selected config file"""
        config_file = self.config_path.get()
        if not config_file or not os.path.exists(config_file):
            self.game_info_label.config(text="No valid config file selected")
            return
            
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
                metadata = config.get("metadata", {})
                self.game_name = metadata.get("game_name", os.path.basename(config_file).replace('.yaml', ''))
                benchmark_duration = metadata.get("benchmark_duration", "Unknown")
                resolution = metadata.get("resolution", "Any")
                
                self.game_info_label.config(
                    text=f"{self.game_name} - Resolution: {resolution}, Benchmark: ~{benchmark_duration}s"
                )
                
                self.logger.info(f"Loaded config for game: {self.game_name}")
        except Exception as e:
            self.game_info_label.config(text=f"Error loading config: {str(e)}")
            self.logger.error(f"Failed to load game config: {str(e)}")

    def clear_logs(self):
        """Clear the log display area"""
        self.log_area.config(state=tk.NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state=tk.DISABLED)

    def open_logs_folder(self):
        """Open the logs folder for the current or most recent run"""
        if hasattr(self, 'current_run_dir') and self.current_run_dir:
            folder_path = os.path.abspath(self.current_run_dir)
        else:
            # Find most recent run folder
            game_dir = f"logs/{self.game_name}" if self.game_name else "logs"
            os.makedirs(game_dir, exist_ok=True)
            
            run_folders = [f for f in os.listdir(game_dir) if f.startswith("run_")]
            if run_folders:
                latest_run = max(run_folders)  # This works because timestamps are YYYYMMDD_HHMMSS format
                folder_path = os.path.abspath(f"{game_dir}/{latest_run}")
            else:
                folder_path = os.path.abspath(game_dir)
        
        # Platform-specific way to open folder
        if sys.platform == 'win32':
            os.startfile(folder_path)
        elif sys.platform == 'darwin':  # macOS
            import subprocess
            subprocess.Popen(['open', folder_path])
        else:  # Linux
            import subprocess
            subprocess.Popen(['xdg-open', folder_path])

    def open_latest_screenshot(self):
        """Open the latest annotated screenshot from the current or most recent run"""
        if hasattr(self, 'current_run_dir') and self.current_run_dir:
            screenshots_dir = os.path.abspath(f"{self.current_run_dir}/annotated")
        else:
            # Find most recent run folder
            game_dir = f"logs/{self.game_name}" if self.game_name else "logs"
            run_folders = [f for f in os.listdir(game_dir) if f.startswith("run_")]
            if run_folders:
                latest_run = max(run_folders)
                screenshots_dir = os.path.abspath(f"{game_dir}/{latest_run}/annotated")
            else:
                screenshots_dir = os.path.abspath(f"{game_dir}/annotated")
        
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
            
        # Load game info to ensure we have the game name
        self.load_game_info()
            
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
        self.logger.info(f"Starting automation process for {self.game_name}...")

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
            import datetime
            from modules.network import NetworkManager
            from modules.screenshot import ScreenshotManager
            from modules.gemma_client import GemmaClient
            from modules.qwen_client import QwenClient
            from modules.omniparser_client import OmniparserClient
            from modules.annotator import Annotator
            from modules.config_parser import ConfigParser
            from modules.decision_engine import DecisionEngine
            from modules.game_launcher import GameLauncher  # Fixed typo: GameLauncherr -> GameLauncher
            
            # Create timestamp for this run
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # Create game-specific directory structure
            os.makedirs("logs", exist_ok=True)
            game_dir = f"logs/{self.game_name}" if self.game_name else "logs"
            os.makedirs(game_dir, exist_ok=True)

            # Create run-specific directory
            run_dir = f"{game_dir}/run_{timestamp}"
            os.makedirs(run_dir, exist_ok=True)
            os.makedirs(f"{run_dir}/screenshots", exist_ok=True)
            os.makedirs(f"{run_dir}/annotated", exist_ok=True)
            
            # Store the current run directory for later use
            self.current_run_dir = run_dir
            
            # Set up run-specific logging
            run_log_file = f"{run_dir}/automation.log"
            run_file_handler = logging.FileHandler(run_log_file)
            run_file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            run_file_handler.setFormatter(run_file_formatter)
            logging.getLogger().addHandler(run_file_handler)
            
            self.logger.info(f"Created run directory: {run_dir}")
            self.logger.info(f"Logs will be saved to: {run_log_file}")
            
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
            elif self.vision_model.get() == 'omniparser':
                self.logger.info("Using Omniparser for UI detection")
                vision_model = OmniparserClient(self.omniparser_url.get())
                
            annotator = Annotator()
            config_parser = ConfigParser(self.config_path.get())
            decision_engine = DecisionEngine(config_parser.get_config())
            game_launcher = GameLauncher(network)
            
            # Get game metadata
            game_metadata = config_parser.get_config().get("metadata", {})  # Fixed to use get_config() directly
            self.logger.info(f"Game metadata loaded: {game_metadata}")
            benchmark_duration = game_metadata.get("benchmark_duration", 120)
            startup_wait = game_metadata.get("startup_wait", 30)
            
            # Main execution loop
            iteration = 0
            current_state = "initial"
            target_state = decision_engine.get_target_state()
            
            # Track time spent in each state to detect timeouts
            state_start_time = time.time()
            max_time_in_state = 60  # Default maximum seconds to remain in the same state
            
            try:
                # Launch the game
                self.logger.info(f"Launching game from: {self.game_path.get()}")
                game_launcher.launch(self.game_path.get())
                
                # Wait for game to initialize
                self.logger.info(f"Waiting {startup_wait} seconds for game to fully initialize...")
                wait_time = startup_wait
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
                    
                    # Get state-specific timeout
                    state_def = config_parser.get_state_definition(current_state)
                    state_timeout = state_def.get("timeout", max_time_in_state) if state_def else max_time_in_state
                    
                    # Check for timeout in current state
                    time_in_state = time.time() - state_start_time
                    if time_in_state > state_timeout:
                        self.logger.warning(f"Timeout in state {current_state} after {time_in_state:.1f} seconds (limit: {state_timeout}s)")
                        
                        # Get fallback action
                        fallback_action = decision_engine.get_fallback_action(current_state)
                        self.logger.info(f"Using fallback action for timeout: {fallback_action}")
                        
                        # Execute fallback action
                        network.send_action(fallback_action)
                        self.logger.info("Executed timeout recovery action")
                        time.sleep(2)
                        
                        # Reset timeout timer
                        state_start_time = time.time()
                        continue
                    
                    # Capture screenshot - USE RUN-SPECIFIC DIRECTORY
                    screenshot_path = f"{run_dir}/screenshots/screenshot_{iteration}.png"
                    screenshot_mgr.capture(screenshot_path)
                    self.logger.info(f"Screenshot captured: {screenshot_path}")
                    
                    # Process with vision model
                    bounding_boxes = vision_model.detect_ui_elements(screenshot_path)
                    self.logger.info(f"Detected {len(bounding_boxes)} UI elements")
                    
                    # Annotate screenshot - USE RUN-SPECIFIC DIRECTORY
                    annotated_path = f"{run_dir}/annotated/annotated_{iteration}.png"
                    annotator.draw_bounding_boxes(screenshot_path, bounding_boxes, annotated_path)
                    self.logger.info(f"Annotated screenshot saved: {annotated_path}")
                    
                    # Determine next action
                    previous_state = current_state
                    next_action, new_state = decision_engine.determine_next_action(
                        current_state, bounding_boxes
                    )
                    
                    # Format the action for better logging
                    action_str = ""
                    if next_action:
                        if next_action.get("type") == "click":
                            action_str = f"Click at ({next_action.get('x')}, {next_action.get('y')})"
                        elif next_action.get("type") == "key":
                            action_str = f"Press key {next_action.get('key')}"
                        elif next_action.get("type") == "wait":
                            action_str = f"Wait for {next_action.get('duration')} seconds"
                        else:
                            action_str = str(next_action)
                            
                    self.logger.info(f"Next action: {action_str}, transitioning to state: {new_state}")
                    
                    # Execute action
                    if next_action and not self.stop_event.is_set():
                        self.logger.info(f"Executing action: {action_str}")
                        
                        # Handle "wait" actions locally instead of sending to SUT
                        if next_action.get("type") == "wait":
                            duration = next_action.get("duration", 1)
                            self.logger.info(f"Waiting for {duration} seconds...")
                            
                            # Wait in small increments so we can check for stop events
                            for i in range(duration):
                                if self.stop_event.is_set():
                                    self.logger.info("Wait interrupted by stop event")
                                    break
                                time.sleep(1)
                                if i % 10 == 0 and i > 0:  # Log every 10 seconds for long waits
                                    self.logger.info(f"Still waiting... {i}/{duration} seconds elapsed")
                                    
                            self.logger.info(f"Wait completed")
                        else:
                            # Send other action types to SUT
                            network.send_action(next_action)
                            
                        self.logger.info(f"Action completed: {action_str}")
                    
                    # Update state
                    current_state = new_state
                    if previous_state != current_state:
                        # Reset timeout timer when state changes
                        state_start_time = time.time()
                        self.logger.info(f"State changed from {previous_state} to {current_state}")
                    
                    # Get delay from transition if specified
                    transition_key = f"{previous_state}->{current_state}"
                    transition = config_parser.get_config().get("transitions", {}).get(transition_key, {})
                    delay = transition.get("expected_delay", 1)
                    
                    time.sleep(delay)  # Wait before next iteration
                
                # Check if we reached the target state
                if current_state == target_state:
                    self.logger.info(f"Successfully reached target state: {target_state}")
                    
                    # Report benchmark results if available
                    if hasattr(decision_engine, "state_context") and "benchmark_duration" in decision_engine.state_context:
                        benchmark_duration = decision_engine.state_context["benchmark_duration"]
                        self.logger.info(f"Benchmark completed in {benchmark_duration:.2f} seconds")
                        
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
            if 'vision_model' in locals() and hasattr(vision_model, 'close'):
                vision_model.close()
            
            # Remove the run-specific log handler
            if 'run_file_handler' in locals():
                logging.getLogger().removeHandler(run_file_handler)
            
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