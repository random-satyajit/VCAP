# Gemma
Core Architecture
The system uses a modular design with these key components:

Network Layer (network.py): Handles communication between your development PC (ARL) and the system under test (SUT) via HTTP.
Vision Detection (multiple options):

gemma_client.py: Uses Gemma LLM to identify UI elements in screenshots
omniparser_client.py: Alternative using Omniparser for more accurate detection
qwen_client.py: Another option using Qwen VL model


Decision Engine (decision_engine.py):

Implements a finite state machine for navigation
Uses context tracking to differentiate between identical-looking states
Handles timeouts and recovery strategies
Makes decisions based on detected UI elements


Configuration (YAML files):

cs2_benchmark.yaml: CS2-specific workflow definition
ui_flow.yaml: Generic UI navigation template
Defines states, required elements, transitions, and actions


User Interface:

gui_app.py: Tkinter GUI with live logging and control options
main.py: Command-line interface



Key Features

State Disambiguation: Uses context variables to differentiate between visually identical screens
Multiple Vision Options: Can switch between Gemma, Qwen VL, and Omniparser
Hardcoded Fallbacks: Can use hardcoded coordinates when vision detection is inaccurate
Timeout Handling: Detects when stuck in a state and implements recovery actions
Annotated Screenshots: Visualizes detected UI elements for debugging

The tool is specifically configured for benchmarking CS2, navigating through the main menu to workshop maps, running the FPS benchmark, and then exiting.