# Game Launcher

A minimalist game launcher focused on functionality and performance, and totally not piracy.

## Features

- Clean and efficient game management
- Accurate playtime tracking
- Custom categorization system
- Steam image integration
- Automatic game detection
- Built-in tea timer (because good games require good tea)
- Windows startup integration
- Seamless SendTo menu integration

## Why This Launcher?

Designed with a few core principles:
- Privacy-focused: No account required, no telemetry
- Resource-efficient: Minimal memory footprint
- Distraction-free: No ads, no stores, no notifications
- Just launches your games and tracks your playtime

## Setup

1. Clone this repository:
    ```bash
    git clone https://github.com/AdrianNO1/GameLauncher
    ```
2. Install dependencies (maybe I forgot some):
   ```bash
   pip install PyQt6 pynput pygame
   ```
3. Run `launcher.pyw`
4. 

## Usage

- Add games to the launcher by right-clicking the game executable in windows explorer and selecting `Send to > AGame Launcher`
- Right-click games for additional options:
  - Set category tags
  - Edit game name
  - Remove from launcher
- Use the search bar to quickly find games
- Create and manage custom categories
- Open the launcher by clicking the system tray icon
- Right click the system tray icon for additional options, such as:
  - Open launcher
  - Exit launcher
  - Restart launcher
  - Tea

## Technical Details

- Written in Python with PyQt6
- Supports executable files and shortcuts
- Utilizes Steam API for game banner image (no API key required)
- Local JSON storage for game data
- Multi-process monitoring system to track playtime

## Screenshots
