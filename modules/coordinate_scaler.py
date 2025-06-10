"""
Coordinate scaling module to handle scaling issues between Gemma's detected coordinates 
and the actual screenshot dimensions.
"""

import os
import logging
from typing import List, Dict, Tuple
from PIL import Image

from modules.gemma_client import BoundingBox

logger = logging.getLogger(__name__)

class CoordinateScaler:
    """
    Handles coordinate scaling between Gemma's detected coordinates and actual screenshot dimensions.
    """
    
    def __init__(self):
        """Initialize the coordinate scaler."""
        self.screen_width = 1920  # Default assumption about game resolution
        self.screen_height = 1080
        self.gemma_assumed_width = 800  # Default assumption about Gemma's internal scaling
        self.gemma_assumed_height = 600
        self.scale_x = 1.0
        self.scale_y = 1.0
        self.calibrated = False
        self.calibration_count = 0
        self.max_calibration_samples = 3
        self.sum_scale_x = 0
        self.sum_scale_y = 0
        self.reference_elements = {
            "PLAY": (0.5, 0.05),  # Play button is typically near the top center
            "INVENTORY": (0.4, 0.05),  # Inventory usually near top left-center
            "STORE": (0.6, 0.05),  # Store usually near top right-center
            "NEWS": (0.7, 0.05),  # News usually near top right
            "LOADOUT": (0.45, 0.05)  # Loadout usually near top center-left
        }
        
        logger.info("CoordinateScaler initialized")
    
    def get_image_dimensions(self, image_path: str) -> Tuple[int, int]:
        """
        Get the dimensions of an image.
        
        Args:
            image_path: Path to the image
            
        Returns:
            Tuple of (width, height)
        """
        try:
            with Image.open(image_path) as img:
                return img.size
        except Exception as e:
            logger.error(f"Error getting image dimensions: {str(e)}")
            return (self.screen_width, self.screen_height)
    
    def calibrate_from_screenshot(self, image_path: str, bounding_boxes: List[BoundingBox]) -> None:
        """
        Calibrate the scaler based on the actual screenshot dimensions and detected elements.
        
        Args:
            image_path: Path to the screenshot
            bounding_boxes: List of detected UI elements
        """
        try:
            # Get actual image dimensions
            actual_width, actual_height = self.get_image_dimensions(image_path)
            
            # Check if we have any reference elements
            found_reference = False
            suggested_scale_x = 0
            suggested_scale_y = 0
            total_elements = 0
            
            # Look for known UI elements (like menu buttons) in standard locations
            for bbox in bounding_boxes:
                if bbox.element_text and bbox.element_text.upper() in self.reference_elements:
                    ref_element = bbox.element_text.upper()
                    expected_rel_x, expected_rel_y = self.reference_elements[ref_element]
                    
                    # Calculate expected absolute position
                    expected_x = int(expected_rel_x * actual_width)
                    expected_y = int(expected_rel_y * actual_height)
                    
                    # Calculate center of detected element
                    detected_x = bbox.x + (bbox.width // 2)
                    detected_y = bbox.y + (bbox.height // 2)
                    
                    # If the element is too far from expected position, it might be a false positive
                    # Only use it if it's somewhat in the expected area
                    if abs(detected_x - expected_x) < actual_width / 3 and abs(detected_y - expected_y) < actual_height / 3:
                        # Calculate scale factor for this element
                        if detected_x > 0:  # Avoid division by zero
                            suggested_scale_x += expected_x / detected_x
                        if detected_y > 0:  # Avoid division by zero
                            suggested_scale_y += expected_y / detected_y
                        
                        total_elements += 1
                        found_reference = True
                        logger.info(f"Reference element '{ref_element}' found at ({detected_x},{detected_y}), expected at ({expected_x},{expected_y})")
            
            # If we found reference elements, update scaling factors
            if found_reference and total_elements > 0:
                # Average the suggested scales
                new_scale_x = suggested_scale_x / total_elements
                new_scale_y = suggested_scale_y / total_elements
                
                # Update running average
                self.sum_scale_x += new_scale_x
                self.sum_scale_y += new_scale_y
                self.calibration_count += 1
                
                # Calculate the running average
                if self.calibration_count >= self.max_calibration_samples:
                    self.scale_x = self.sum_scale_x / self.calibration_count
                    self.scale_y = self.sum_scale_y / self.calibration_count
                    self.calibrated = True
                    logger.info(f"Calibration complete! Scale factors: X={self.scale_x:.2f}, Y={self.scale_y:.2f}")
                else:
                    # Use new scale factors immediately but keep collecting samples
                    self.scale_x = self.sum_scale_x / self.calibration_count
                    self.scale_y = self.sum_scale_y / self.calibration_count
                    logger.info(f"Calibration in progress ({self.calibration_count}/{self.max_calibration_samples}). Current scale factors: X={self.scale_x:.2f}, Y={self.scale_y:.2f}")
            else:
                # If no reference elements, use a simple heuristic based on image dimensions
                self.screen_width = actual_width
                self.screen_height = actual_height
                logger.info(f"No reference elements found. Using image dimensions for scaling: {actual_width}x{actual_height}")
        
        except Exception as e:
            logger.error(f"Error during calibration: {str(e)}")
    
    def scale_bounding_boxes(self, bounding_boxes: List[BoundingBox]) -> List[BoundingBox]:
        """
        Scale the bounding boxes to match the actual screen coordinates.
        
        Args:
            bounding_boxes: List of BoundingBox objects with Gemma's coordinates
            
        Returns:
            List of scaled BoundingBox objects
        """
        if not self.calibrated and len(bounding_boxes) > 0:
            logger.warning("Scaling without calibration. Results may be inaccurate.")
        
        scaled_boxes = []
        for bbox in bounding_boxes:
            # Create a new BoundingBox with scaled coordinates
            scaled_box = BoundingBox(
                x=int(bbox.x * self.scale_x),
                y=int(bbox.y * self.scale_y),
                width=int(bbox.width * self.scale_x),
                height=int(bbox.height * self.scale_y),
                confidence=bbox.confidence,
                element_type=bbox.element_type,
                element_text=bbox.element_text
            )
            scaled_boxes.append(scaled_box)
            
            # Log the scaling for debugging
            if bbox.element_text:
                logger.debug(f"Scaled '{bbox.element_text}' from ({bbox.x},{bbox.y}) to ({scaled_box.x},{scaled_box.y})")
        
        return scaled_boxes