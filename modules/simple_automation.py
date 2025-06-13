"""
Simple step-by-step automation module for game UI navigation.
Uses a direct procedural approach instead of complex state machines.
"""

import os
import time
import logging
import yaml
from typing import List, Dict, Any, Optional

from modules.gemma_client import BoundingBox

logger = logging.getLogger(__name__)

class SimpleAutomation:
    """Simplified step-by-step automation for game UI workflows."""
    
    def __init__(self, config_path, network, screenshot_mgr, vision_model, stop_event=None, run_dir=None, annotator=None):
        """Initialize with all necessary components."""
        self.config_path = config_path
        self.network = network
        self.screenshot_mgr = screenshot_mgr
        self.vision_model = vision_model
        self.stop_event = stop_event
        self.annotator = annotator
        
        # Load configuration using SimpleConfigParser if available
        try:
            from modules.simple_config_parser import SimpleConfigParser
            config_parser = SimpleConfigParser(config_path)
            self.config = config_parser.get_config()
            logger.info("Using SimpleConfigParser for step-based configuration")
        except (ImportError, ValueError):
            # Fall back to direct YAML loading
            logger.info("SimpleConfigParser not available, loading YAML directly")
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        
        # Game metadata
        self.game_name = self.config.get("metadata", {}).get("game_name", "Unknown Game")
        self.run_dir = run_dir or f"logs/{self.game_name}"
        
        logger.info(f"SimpleAutomation initialized for {self.game_name}")
            
    def run(self):
        """Run the simplified step-by-step automation."""
        # Get steps from configuration
        steps = self.config.get("steps", {})
        
        # If no steps defined, try to convert from state machine format
        if not steps:
            logger.info("No steps defined in config, attempting to convert from state machine format")
            steps = self._convert_states_to_steps()
            
        if not steps:
            logger.error("No steps defined and couldn't convert from state machine format")
            return False
        
        current_step = 1
        max_retries = 3
        retries = 0
        
        logger.info(f"Starting automation with {len(steps)} steps")
        
        while current_step <= len(steps):
            step = steps[str(current_step)]
            logger.info(f"Executing step {current_step}: {step['description']}")
            
            # Check for stop event
            if self.stop_event and self.stop_event.is_set():
                logger.info("Stop event detected, ending automation")
                break
            
            # Capture screenshot
            screenshot_path = f"{self.run_dir}/screenshots/screenshot_{current_step}.png"
            self.screenshot_mgr.capture(screenshot_path)
            
            # Detect UI elements
            bounding_boxes = self.vision_model.detect_ui_elements(screenshot_path)
            
            # Annotate screenshot if annotator available
            if self.annotator:
                annotated_path = f"{self.run_dir}/annotated/annotated_{current_step}.png"
                self.annotator.draw_bounding_boxes(screenshot_path, bounding_boxes, annotated_path)
                logger.info(f"Annotated screenshot saved: {annotated_path}")
            
            # Process step based on type
            if "find_and_click" in step:
                # Find and click element
                target = step["find_and_click"]
                element = self._find_matching_element(target, bounding_boxes)
                
                if element:
                    # Calculate center point for click
                    center_x = element.x + (element.width // 2)
                    center_y = element.y + (element.height // 2)
                    
                    # Execute click
                    action = {"type": "click", "x": center_x, "y": center_y}
                    self.network.send_action(action)
                    logger.info(f"Clicked on {element.element_text} at ({center_x}, {center_y})")
                    
                    # Wait for expected delay
                    time.sleep(step.get("expected_delay", 2))
                    
                    # Verify success if specified
                    if step.get("verify_success"):
                        # Capture new screenshot for verification
                        verify_path = f"{self.run_dir}/screenshots/verify_{current_step}.png"
                        self.screenshot_mgr.capture(verify_path)
                        verify_boxes = self.vision_model.detect_ui_elements(verify_path)
                        
                        # Annotate verification screenshot if annotator available
                        if self.annotator:
                            annotated_verify_path = f"{self.run_dir}/annotated/verify_{current_step}.png"
                            self.annotator.draw_bounding_boxes(verify_path, verify_boxes, annotated_verify_path)
                        
                        # Check for verification elements
                        success = True
                        for verify_element in step["verify_success"]:
                            if not self._find_matching_element(verify_element, verify_boxes):
                                success = False
                                logger.warning(f"Verification failed: {verify_element['text']} not found")
                        
                        if success:
                            logger.info(f"Step {current_step} completed successfully")
                            current_step += 1
                            retries = 0  # Reset retry counter on success
                        else:
                            retries += 1
                            logger.warning(f"Step {current_step} verification failed, retry {retries}/{max_retries}")
                            if retries >= max_retries:
                                logger.error(f"Max retries reached for step {current_step}, failing")
                                return False
                            # Execute fallback if verification fails
                            self._execute_fallback()
                    else:
                        # No verification needed, move to next step
                        current_step += 1
                        retries = 0  # Reset retry counter on success
                else:
                    retries += 1
                    logger.warning(f"Target element {target['text']} not found, retry {retries}/{max_retries}")
                    if retries >= max_retries:
                        logger.error(f"Max retries reached for step {current_step}, failing")
                        return False
                    # Execute fallback if target not found
                    self._execute_fallback()
                    
            elif "action" in step and step["action"] == "wait":
                # Wait action
                duration = step.get("duration", 10)
                logger.info(f"Waiting for {duration} seconds")
                
                # Wait in smaller increments to allow for interruption
                for i in range(duration):
                    if self.stop_event and self.stop_event.is_set():
                        break
                    time.sleep(1)
                    if i % 10 == 0 and i > 0:  # Log progress for long waits
                        logger.info(f"Still waiting... {i}/{duration} seconds elapsed")
                
                # Move to next step after wait
                current_step += 1
                retries = 0  # Reset retry counter
                
        if current_step > len(steps):
            logger.info("All steps completed successfully!")
            return True
        else:
            logger.info("Automation stopped before completion")
            return False
    
    def _find_matching_element(self, target_def, bounding_boxes):
        """Find a UI element matching the target definition."""
        target_type = target_def.get("type", "any")
        target_text = target_def.get("text", "")
        match_type = target_def.get("text_match", "contains")
        
        for bbox in bounding_boxes:
            # Check element type
            type_match = (target_type == "any" or bbox.element_type == target_type)
            
            # Check text content with specified matching strategy
            text_match = False
            if bbox.element_text and target_text:
                if match_type == "exact":
                    text_match = target_text.lower() == bbox.element_text.lower()
                elif match_type == "contains":
                    text_match = target_text.lower() in bbox.element_text.lower()
                elif match_type == "startswith":
                    text_match = bbox.element_text.lower().startswith(target_text.lower())
                elif match_type == "endswith":
                    text_match = bbox.element_text.lower().endswith(target_text.lower())
            elif not target_text:  # If no text requirement, match any element
                text_match = True
                    
            if type_match and text_match:
                return bbox
                
        return None
        
    def _execute_fallback(self):
        """Execute fallback action if step fails."""
        fallback = self.config.get("fallbacks", {}).get("general", {})
        if fallback:
            action_type = fallback.get("action")
            if action_type == "key":
                key = fallback.get("key", "Escape")
                logger.info(f"Executing fallback: Press key {key}")
                self.network.send_action({"type": "key", "key": key})
            elif action_type == "click":
                x = fallback.get("x", 0)
                y = fallback.get("y", 0)
                logger.info(f"Executing fallback: Click at ({x}, {y})")
                self.network.send_action({"type": "click", "x": x, "y": y})
                
        # Wait after fallback
        time.sleep(fallback.get("expected_delay", 1))
        
    def _convert_states_to_steps(self):
        """
        Attempt to convert state machine format to step format.
        This allows using existing YAML files with the simple automation.
        """
        steps = {}
        states = self.config.get("states", {})
        transitions = self.config.get("transitions", {})
        initial_state = self.config.get("initial_state")
        
        if not states or not transitions or not initial_state:
            logger.warning("Missing required state machine components for conversion")
            return {}
            
        # Start with initial state
        current_state = initial_state
        step_num = 1
        visited_states = set()
        
        # Prevent infinite loops
        while current_state not in visited_states and step_num <= 10:
            visited_states.add(current_state)
            
            # Find transitions from current state
            for transition_key, transition in transitions.items():
                if transition_key.startswith(f"{current_state}->"):
                    to_state = transition_key.split("->")[1]
                    action_type = transition.get("action")
                    
                    # Create step based on transition type
                    if action_type == "click":
                        target = transition.get("target", {})
                        
                        step = {
                            "description": f"Click to go from {current_state} to {to_state}",
                            "find_and_click": {
                                "type": target.get("type", "any"),
                                "text": target.get("text", ""),
                                "text_match": target.get("text_match", "contains")
                            },
                            "expected_delay": transition.get("expected_delay", 2)
                        }
                        
                        # Add verification if target state has required elements
                        if to_state in states:
                            verify = []
                            for req in states[to_state].get("required_elements", []):
                                verify.append({
                                    "type": req.get("type", "any"),
                                    "text": req.get("text", ""),
                                    "text_match": req.get("text_match", "contains")
                                })
                            if verify:
                                step["verify_success"] = verify
                        
                        steps[str(step_num)] = step
                        step_num += 1
                        current_state = to_state
                        break
                        
                    elif action_type == "wait":
                        step = {
                            "description": f"Wait during {current_state}",
                            "action": "wait",
                            "duration": transition.get("duration", 10)
                        }
                        steps[str(step_num)] = step
                        step_num += 1
                        current_state = to_state
                        break
        
        logger.info(f"Converted state machine to {len(steps)} steps")
        return steps