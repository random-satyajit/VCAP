#!/usr/bin/env python3
"""
Main orchestration script for Game UI Navigation using Gemma visual model.
This script coordinates the entire testing flow between ARL development PC and SUT.
"""

import os
import time
import logging
import argparse
from pathlib import Path

from modules.network import NetworkManager
from modules.screenshot import ScreenshotManager
from modules.gemma_client import GemmaClient
from modules.qwen_client import QwenClient
from modules.annotator import Annotator
from modules.decision_engine import DecisionEngine
from modules.game_launcher import GameLauncher
from modules.config_parser import ConfigParser
from modules.coordinate_scaler import CoordinateScaler

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/run_{time.strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def create_directory_structure():
    """Create the necessary directory structure if it doesn't exist."""
    os.makedirs("logs", exist_ok=True)
    os.makedirs("logs/screenshots", exist_ok=True)
    os.makedirs("logs/annotated", exist_ok=True)

def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description='Game UI Navigation Automation Tool')
    parser.add_argument('--sut-ip', type=str, required=True, help='IP address of the SUT')
    parser.add_argument('--sut-port', type=int, default=8080, help='Port for communication with SUT')
    parser.add_argument('--gemma-url', type=str, default='http://127.0.0.1:1234', 
                      help='URL for the LMStudio API (default: http://127.0.0.1:1234)')
    parser.add_argument('--vision-model', type=str, choices=['gemma', 'qwen'], default='gemma',
                      help='Vision model to use for UI detection (default: gemma)')
    parser.add_argument('--config', type=str, default='config/ui_flow.yaml',
                      help='Path to the UI flow YAML configuration')
    parser.add_argument('--game-path', type=str, required=True,
                      help='Path to the game executable on the SUT')
    parser.add_argument('--max-iterations', type=int, default=50,
                      help='Maximum number of iterations before terminating')
    return parser.parse_args()

def main():
    """Main execution function."""
    # Setup
    create_directory_structure()
    args = parse_arguments()
    
    logger.info("Starting Game UI Navigation Automation Tool")
    logger.info(f"SUT: {args.sut_ip}:{args.sut_port}")
    logger.info(f"Gemma API: {args.gemma_url}")
    logger.info(f"Config: {args.config}")
    
    # Initialize components
    network = NetworkManager(args.sut_ip, args.sut_port)
    screenshot_mgr = ScreenshotManager(network)
    
    # Initialize the vision model based on user selection
    if args.vision_model == 'gemma':
        logger.info("Using Gemma for UI detection")
        vision_model = GemmaClient(args.gemma_url)
    elif args.vision_model == 'qwen':
        logger.info("Using Qwen VL for UI detection")
        vision_model = QwenClient(args.gemma_url)  # Using the same URL parameter
    
    annotator = Annotator()
    config_parser = ConfigParser(args.config)
    decision_engine = DecisionEngine(config_parser.get_config())
    game_launcher = GameLauncher(network)
    coordinate_scaler = CoordinateScaler()  # Initialize the coordinate scaler
    
    # Main execution loop
    iteration = 0
    current_state = "initial"
    target_state = decision_engine.get_target_state()
    
    try:
        # Launch the game
        logger.info(f"Launching game from: {args.game_path}")
        game_launcher.launch(args.game_path)
        logger.info(f"Waiting 30 seconds for game to fully initialize...")
        time.sleep(30)  # Allow game to initialize
        
        while current_state != target_state and iteration < args.max_iterations:
            iteration += 1
            logger.info(f"Iteration {iteration}: Current state: {current_state}")
            
            # Capture screenshot
            screenshot_path = f"logs/screenshots/screenshot_{iteration}.png"
            screenshot_mgr.capture(screenshot_path)
            logger.info(f"Screenshot captured: {screenshot_path}")
            
            # Process with vision model
            bounding_boxes = vision_model.detect_ui_elements(screenshot_path)
            logger.info(f"Detected {len(bounding_boxes)} UI elements")
            
            # Calibrate and scale coordinates
            coordinate_scaler.calibrate_from_screenshot(screenshot_path, bounding_boxes)
            scaled_boxes = coordinate_scaler.scale_bounding_boxes(bounding_boxes)
            logger.info(f"Scaled coordinates with factors: X={coordinate_scaler.scale_x:.2f}, Y={coordinate_scaler.scale_y:.2f}")
            
            # Annotate screenshot with the original bounding boxes
            annotated_path = f"logs/annotated/annotated_{iteration}.png"
            annotator.draw_bounding_boxes(screenshot_path, bounding_boxes, annotated_path)
            logger.info(f"Annotated screenshot saved: {annotated_path}")
            
            # Create a separate annotated image with scaled bounding boxes
            scaled_annotated_path = f"logs/annotated/scaled_{iteration}.png"
            annotator.draw_bounding_boxes(screenshot_path, scaled_boxes, scaled_annotated_path)
            logger.info(f"Scaled annotated screenshot saved: {scaled_annotated_path}")
            
            # Determine next action using the scaled bounding boxes
            next_action, new_state = decision_engine.determine_next_action(
                current_state, scaled_boxes
            )
            logger.info(f"Next action: {next_action}, transitioning to state: {new_state}")
            
            # Execute action
            if next_action:
                network.send_action(next_action)
                logger.info(f"Action sent: {next_action}")
            
            # Update state
            current_state = new_state
            time.sleep(1)  # Small delay between iterations
        
        # Check if we reached the target state
        if current_state == target_state:
            logger.info(f"Successfully reached target state: {target_state}")
        else:
            logger.warning(f"Failed to reach target state. Stopped at: {current_state}")
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}", exc_info=True)
    finally:
        # Cleanup
        logger.info("Cleaning up resources")
        network.close()
        logger.info("Execution completed")

if __name__ == "__main__":
    main()