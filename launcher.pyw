import sys
import json, socket
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
                            QPushButton, QSystemTrayIcon, QMenu, QLineEdit, QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QAction, QPixmap, QImage
from datetime import datetime
import os
import subprocess
import psutil
import time
from filelock import FileLock
import threading, win32com.client
from steam_utils import update_game_data

categories = ["favorites", "interesting", "replay", "done"]

HIDDEN_BY_DEFAULT = "-h" in sys.argv

if not os.path.exists("games.json"):
    with open("games.json", "w") as f:
        json.dump({"games": [{
            "name": "Example game",
            "exe_path": "C:\\Windows\\System32\\calc.exe",
            "categories": ["favorites"],
            "playtime": 0,
            "steam_id": None,
            "image_path": None,
            "icon_path": None,
            "last_played": None
        }]}, f, indent=4)

json_lock = FileLock("games.json.lock")
history_lock = FileLock("history.json.lock")

if not os.path.exists("history.json"):
    with open("history.json", "w") as f:
        json.dump({"sessions": []}, f, indent=4)

def ensure_startup():
    appdata = os.getenv("APPDATA")
    shortcut_path = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "GameLauncher.lnk")
    if not os.path.exists(shortcut_path):
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = sys.executable
        shortcut.Arguments = f'"{os.path.abspath("launcher.py")}" -h'
        shortcut.WorkingDirectory = os.path.dirname(os.path.abspath("launcher.py"))
        shortcut.save()
        print("Added to startup")
    
    sendto_path = os.path.join(appdata, "Microsoft", "Windows", "SendTo", "AGameLauncher.lnk")
    if not os.path.exists(sendto_path):
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(sendto_path)
        shortcut.Targetpath = sys.executable
        shortcut.Arguments = f'"{os.path.abspath("add_game.py")}"'
        shortcut.WorkingDirectory = os.path.dirname(os.path.abspath("add_game.py"))
        shortcut.save()
        print("Added to SendTo")

ensure_startup()

class GameMonitor(QThread):
    playtime_updated = pyqtSignal(str, int) # game_name, elapsed_seconds
    game_closed = pyqtSignal(str)

    def __init__(self, game_name, exe_path, initial_playtime, PID, parent=None):
        super().__init__(parent)
        self.game_name = game_name
        self.exe_path = exe_path
        self.running = True
        self.last_save = 0
        self.initial_playtime = initial_playtime
        self.PID = PID

    def run(self):
        start_time = datetime.now()
        session_id = self.log_session_start(start_time)
        
        if not self.PID:
            game_dir = os.path.dirname(self.exe_path)
            process = subprocess.Popen([self.exe_path], cwd=game_dir)
            self.PID = process.pid
        
        while self.running:
            try:
                process = psutil.Process(self.PID)
                if process.is_running():
                    current_time = datetime.now()
                    elapsed_seconds = int((current_time - start_time).total_seconds())
                    self.playtime_updated.emit(self.game_name, self.initial_playtime + elapsed_seconds)
                    
                    if elapsed_seconds - self.last_save >= 60:
                        self.save_playtime(elapsed_seconds)
                        self.last_save = elapsed_seconds
                    
                    time.sleep(5)
                else:
                    break
            except psutil.NoSuchProcess:
                break
            except Exception as e:
                print(f"Error monitoring game: {str(e)}")
                break

        final_elapsed = int((datetime.now() - start_time).total_seconds())
        self.save_playtime(final_elapsed)
        self.update_session_end(session_id, final_elapsed)
        self.game_closed.emit(self.game_name)

    def save_playtime(self, elapsed_seconds):
        with json_lock:
            try:
                with open("games.json", "r") as f:
                    data = json.load(f)
                
                for game in data["games"]:
                    if game["name"] == self.game_name:
                        game["playtime"] = game.get("playtime", 0) + (elapsed_seconds - self.last_save)
                        game["last_played"] = datetime.now().isoformat()
                
                with open("games.json", "w") as f:
                    json.dump(data, f, indent=4)
            
            except Exception as e:
                print(f"Error saving playtime: {str(e)}")

    def log_session_start(self, start_time):
        with history_lock:
            try:
                with open("history.json", "r") as f:
                    history = json.load(f)
                
                session = {
                    "id": str(time.time()),
                    "game": self.game_name,
                    "start_time": start_time.isoformat(),
                    "exe_path": self.exe_path,
                    "duration": None
                }
                
                history["sessions"].append(session)
                
                with open("history.json", "w") as f:
                    json.dump(history, f, indent=4)
                
                return session["id"]
            
            except Exception as e:
                print(f"Error logging session start: {str(e)}")
                return None

    def update_session_end(self, session_id, duration):
        if not session_id:
            return
            
        with history_lock:
            try:
                with open("history.json", "r") as f:
                    history = json.load(f)
                
                for session in history["sessions"]:
                    if session.get("id") == session_id:
                        session["duration"] = duration
                        break
                
                with open("history.json", "w") as f:
                    json.dump(history, f, indent=4)
            
            except Exception as e:
                print(f"Error updating session end: {str(e)}")

    def stop(self):
        self.running = False


class GameLauncher(QMainWindow):
    new_game_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Game Launcher")
        self.setMinimumSize(915, 800)
        
        self.active_monitors = {}
        
        update_game_data()
        
        self.setWindowIcon(QIcon("app_icon.jpg"))
        
        self.load_games()
        
        self.load_styles()

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon("app_icon.jpg"))
        self.tray_icon.activated.connect(self.tray_icon_activated)
        
        self.tray_icon.setVisible(True)
        if hasattr(self.tray_icon, "setToolTip"):
            self.tray_icon.setToolTip("Game Launcher")
        
        tray_menu = QMenu()
        show_action = QAction("Show", self)
        restart_action = QAction("Restart", self)
        quit_action = QAction("Quit", self)
        
        tea_menu = QMenu("Tea", self)
        minute_options = [2, 3, 4, 5]
        tea_options = [{"action": QAction(f"{m} minutes", self), "minutes": m} for m in minute_options]
        
        teapath = os.path.abspath(r"teatimer\main.py")
        def create_timer(minutes):
            print(minutes)
            tea_dir = os.path.dirname(teapath)
            subprocess.Popen([sys.executable, teapath, str(minutes*60)], cwd=tea_dir)
        
        for tea_option in tea_options:
            print(tea_option["minutes"])
            tea_option["action"].triggered.connect(lambda _, minutes=tea_option["minutes"]: create_timer(minutes))
            tea_menu.addAction(tea_option["action"])
        
        show_action.triggered.connect(self.show)
        restart_action.triggered.connect(self.restart_application)
        quit_action.triggered.connect(self.clean_exit)
        
        tray_menu.addAction(show_action)
        tray_menu.addMenu(tea_menu)
        tray_menu.addAction(restart_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar.setMaximumWidth(300)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search games...")
        self.search_bar.textChanged.connect(self.filter_games)
        sidebar_layout.addWidget(self.search_bar)

        self.games_tree = QTreeWidget()
        self.games_tree.setHeaderHidden(True)
        self.games_tree.itemClicked.connect(self.show_game_details)
        self.populate_games_tree()
        sidebar_layout.addWidget(self.games_tree)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        
        self.image_label = QLabel()
        self.image_label.setFixedSize(616, 353)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background-color: #2d2d2d;")
        self.content_layout.addWidget(self.image_label)
        
        self.details_container = QWidget()
        self.details_layout = QVBoxLayout(self.details_container)
        self.content_layout.addWidget(self.details_container)
        
        self.content_layout.addStretch()
        
        layout.addWidget(sidebar)
        layout.addWidget(self.content_area)

        self.setup_context_menu()
        
        self.select_last_played_game()
        
        self.new_game_signal.connect(self.handle_new_game)

        self.start_socket_server()
    
    def check_running_games(self):
        processes = []
        for proc in psutil.process_iter(['name', 'exe', 'pid']):
            try:
                if proc.info['exe']:
                    processes.append({
                        'exe': os.path.normpath(proc.info['exe'].lower()),
                        'pid': proc.info['pid']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        for game in self.games_data["games"]:
            if game.get("deleted", False):
                continue
            if not self.active_monitors.get(game["name"]):
                game_exe = os.path.normpath(game["exe_path"].lower())
                for p in processes:
                    if p['exe'] == game_exe:
                        print("Game already running:", game["name"])
                        self.launch_game(game["name"], p['pid'])

    def start_socket_server(self):
        self.server_thread = threading.Thread(target=self.run_socket_server, daemon=True)
        self.server_thread.start()

    def run_socket_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("localhost", 12345))
        server.listen(1)

        while True:
            try:
                client, addr = server.accept()
                data = client.recv(4096).decode()
                client.close()
                
                message = json.loads(data)
                if message["action"] == "add_game":
                    self.new_game_signal.emit(message)
            except Exception as e:
                print(f"Socket server error: {e}")

    def handle_new_game(self, message):
        new_game = {
            "name": message["name"],
            "exe_path": message["exe_path"],
            "categories": [],
            "playtime": 0,
            "last_played": datetime.now().isoformat(),
            "steam_id": None,
            "image_path": None
        }

        with json_lock:
            try:
                with open("games.json", "r") as f:
                    data = json.load(f)
                
                if not any(g["exe_path"] == new_game["exe_path"] for g in data["games"]):
                    data["games"].append(new_game)
                    
                    with open("games.json", "w") as f:
                        json.dump(data, f, indent=4)
                    
                    update_game_data()
                    self.load_games()
                    self.populate_games_tree()
                    self.select_game_in_tree(new_game["name"])
                    self.show()
                    self.activateWindow()
                else:
                    print("Game already exists")

            except Exception as e:
                print(f"Error adding new game: {e}")

    def select_last_played_game(self):
        last_played_game = None
        last_played_time = None
        
        for game in self.games_data["games"]:
            if game.get("deleted", False) or not game.get("last_played"):
                continue
            game_time = datetime.fromisoformat(game["last_played"])
            if not last_played_time or game_time > last_played_time:
                last_played_time = game_time
                last_played_game = game["name"]
        
        if last_played_game:
            self.select_game_in_tree(last_played_game)

    def select_game_in_tree(self, game_name):
        for i in range(self.games_tree.topLevelItemCount()):
            category = self.games_tree.topLevelItem(i)
            for j in range(category.childCount()):
                game_item = category.child(j)
                if game_item.text(0) == game_name:
                    self.games_tree.setCurrentItem(game_item)
                    self.show_game_details(game_item)
                    return

    def clean_exit(self):
        for monitor in self.active_monitors.values():
            monitor.stop()
        app.quit()

    def launch_game(self, game_name, PID=None):
        game_data = self.find_game_by_name(game_name)
        if game_data and os.path.exists(game_data["exe_path"]):
            monitor = GameMonitor(game_name, game_data["exe_path"], game_data.get("playtime", 0), PID)
            monitor.playtime_updated.connect(lambda name, time: self.update_game_ui(name, time))
            monitor.game_closed.connect(lambda name: self.on_game_closed(name))
            monitor.start()
            
            self.active_monitors[game_name] = monitor
            self.update_game_status_in_tree(game_name, True)
            
            if game_name == self.current_game_name:
                self.show_game_details(self.games_tree.currentItem())

            self.hide()
        else:
            print(f"Game not found: {game_name}")

    def update_game_ui(self, game_name, elapsed_seconds):
        if game_name == self.current_game_name:
            for i in reversed(range(self.details_layout.count())):
                widget = self.details_layout.itemAt(i).widget()
                if isinstance(widget, QLabel) and widget.objectName() == "gameInfo":
                    if "Playtime:" in widget.text():
                        playtime_hours = round(elapsed_seconds / 3600, 1)
                        if playtime_hours.is_integer():
                            playtime_hours = int(playtime_hours)
                        widget.setText(f"Playtime: {playtime_hours} hours")
                        break

    def on_game_closed(self, game_name):
        if game_name in self.active_monitors:
            self.active_monitors[game_name].deleteLater()
            del self.active_monitors[game_name]
            
            for i in range(self.games_tree.topLevelItemCount()):
                category = self.games_tree.topLevelItem(i)
                for j in range(category.childCount()):
                    game_item = category.child(j)
                    if game_item.text(0).replace(" (Running)", "") == game_name:
                        game_item.setText(0, game_name)
                        game_item.setData(0, Qt.ItemDataRole.UserRole, "false")
                        break
            
            current_item = self.games_tree.currentItem()
            if current_item and current_item.text(0).replace(" (Running)", "") == game_name:
                self.show_game_details(current_item)

    def load_styles(self):
        with open("styles.css", "r") as f:
            self.setStyleSheet(f.read())

    def load_games(self):
        with json_lock:
            with open("games.json", "r") as f:
                self.games_data = json.load(f)

    def save_games(self):
        with json_lock:
            with open("games.json", "w") as f:
                json.dump(self.games_data, f, indent=4)

    def setup_context_menu(self):
        self.games_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.games_tree.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, position):
        item = self.games_tree.itemAt(position)
        if item and item.parent():
            context_menu = QMenu()
            
            for category in categories:
                action = QAction(category.capitalize(), self)
                action.setCheckable(True)
                game_data = self.find_game_by_name(item.text(0))
                if game_data and category in game_data["categories"]:
                    action.setChecked(True)
                action.triggered.connect(lambda checked, c=category, g=item.text(0): 
                                      self.toggle_category(g, c))
                context_menu.addAction(action)

            context_menu.addSeparator()

            edit_action = QAction("Edit Name", self)
            edit_action.triggered.connect(lambda: self.edit_game_name(item.text(0)))
            context_menu.addAction(edit_action)
            
            delete_action = QAction("Delete Game", self)
            delete_action.triggered.connect(lambda: self.delete_game(item.text(0)))
            context_menu.addAction(delete_action)
            
            
            context_menu.exec(self.games_tree.viewport().mapToGlobal(position))

    def toggle_category(self, game_name, category):
        game_data = self.find_game_by_name(game_name)
        if game_data:
            if category in game_data['categories']:
                game_data['categories'].remove(category)
            else:
                game_data['categories'].append(category)
            self.save_games()
            self.populate_games_tree()

    def edit_game_name(self, game_name):
        game_data = self.find_game_by_name(game_name)
        if game_data:
            dialog = QInputDialog(self)
            dialog.setWindowTitle("Edit Game Name")
            dialog.setLabelText("Enter new name:")
            dialog.setTextValue(game_name)
            
            if dialog.exec() == 1:
                new_name = dialog.textValue().strip()
                if new_name and new_name != game_name:
                    game_data["name"] = new_name
                    game_data["steam_id"] = None
                    game_data["image_path"] = None
                    game_data["icon_path"] = None
                    self.save_games()
                    update_game_data()
                    self.load_games()
                    self.populate_games_tree()
                    self.select_game_in_tree(new_name)

    def delete_game(self, game_name):
        game_data = self.find_game_by_name(game_name)
        if game_data:
            reply = QMessageBox.question(self, 'Delete Game', 
                                       f'Are you sure you want to delete "{game_name}"?',
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if reply == QMessageBox.StandardButton.Yes:
                game_data["deleted"] = True
                self.save_games()
                self.load_games()
                self.populate_games_tree()
                if self.current_game_name == game_name:
                    for i in reversed(range(self.details_layout.count())):
                        widget = self.details_layout.itemAt(i).widget()
                        if widget:
                            widget.deleteLater()

    def find_game_by_name(self, name):
        game = next((game for game in self.games_data["games"] 
                    if game["name"].lower() == name.lower()), None)
        if not game:
            name = name.strip(" (Running)")
            game = next((game for game in self.games_data["games"]
                        if game["name"].lower() == name.lower()), None)
        return game

    def populate_games_tree(self):
        self.games_tree.clear()
        categoriess = {c: QTreeWidgetItem([c.capitalize()]) for c in categories}
        categoriess["uncategorized"] = QTreeWidgetItem(["Uncategorized"])
        
        for category_item in categoriess.values():
            self.games_tree.addTopLevelItem(category_item)
            category_item.setExpanded(True)

        for game in self.games_data["games"]:
            if game.get("deleted", False):
                continue
                
            game_categories = game["categories"]
            
            if not game_categories:
                game_categories = ["uncategorized"]
            for category in game_categories:
                if category in categoriess:
                    if (len(game["name"]) > 0):
                        game_item = QTreeWidgetItem([game["name"]])
                    else:
                        game_item = QTreeWidgetItem(["No Game Name"])
                    if os.path.exists(game["exe_path"]):
                        icon = game.get("icon_path")
                    else:
                        icon = "deleted_icon.jpg"
                    if icon:
                        game_item.setIcon(0, QIcon(icon))
                    categoriess[category].addChild(game_item)

        self.filter_games("")

    def filter_games(self, text):
        for i in range(self.games_tree.topLevelItemCount()):
            category = self.games_tree.topLevelItem(i)
            has_visible_children = False
            
            for j in range(category.childCount()):
                game_item = category.child(j)
                should_show = text.lower() in game_item.text(0).lower()
                game_item.setHidden(not should_show)
                has_visible_children = has_visible_children or should_show
            
            category.setHidden(not has_visible_children)

    def show_game_details(self, item):
        if item.parent() is None:
            return

        for i in reversed(range(self.details_layout.count())):
            widget = self.details_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        self.load_games()
        game_data = self.find_game_by_name(item.text(0))
        if not game_data:
            return

        self.current_game_name = game_data["name"]

        if game_data.get("image_path"):
            pixmap = QPixmap(game_data["image_path"])
            scaled_pixmap = pixmap.scaled(616, 353, Qt.AspectRatioMode.KeepAspectRatio)
            self.image_label.setPixmap(scaled_pixmap)
        else:
            self.image_label.clear()
            self.image_label.setText("No image available")

        title = QLabel(game_data["name"])
        title.setObjectName("gameTitle")
        self.details_layout.addWidget(title)

        playtime_hours = round(game_data["playtime"] / 3600, 1)
        if playtime_hours.is_integer():
            playtime_hours = int(playtime_hours)
        playtime = QLabel(f"Playtime: {playtime_hours} hours")
        playtime.setObjectName("gameInfo")
        self.details_layout.addWidget(playtime)

        if game_data.get("last_played"):
            last_played_date = datetime.fromisoformat(game_data["last_played"])
            last_played_text = f"Last played: {last_played_date.strftime('%B %d, %Y at %H:%M')}"
        else:
            last_played_text = "Last played: Never"
        last_played = QLabel(last_played_text)
        last_played.setObjectName("gameInfo")
        self.details_layout.addWidget(last_played)

        is_running = game_data["name"] in self.active_monitors
        launch_button = QPushButton("Stop Game" if is_running else "Launch Game")
        launch_button.setObjectName("stopButton" if is_running else "launchButton")
        launch_button.setFixedSize(300, 75)
        if is_running:
            launch_button.clicked.connect(lambda: self.stop_game(game_data["name"]))
        else:
            launch_button.clicked.connect(lambda: self.launch_game(game_data["name"]))
        self.details_layout.addWidget(launch_button)

    def stop_game(self, game_name):
        reply = QMessageBox.question(
            self, 
            'Stop Game', 
            f'Are you sure you want to stop "{game_name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if game_name in self.active_monitors:
                monitor = self.active_monitors[game_name]
                monitor.stop()
                try:
                    for proc in psutil.process_iter(['pid', 'name']):
                        if proc.info['name'] == os.path.basename(monitor.exe_path):
                            psutil.Process(proc.info['pid']).terminate()
                except Exception as e:
                    print(f"Error stopping game: {e}")

    def update_game_status_in_tree(self, game_name, is_running=True):
        for i in range(self.games_tree.topLevelItemCount()):
            category = self.games_tree.topLevelItem(i)
            for j in range(category.childCount()):
                game_item = category.child(j)
                if game_item.text(0) == game_name:
                    if is_running:
                        game_item.setText(0, f"{game_name} (Running)")
                        game_item.setData(0, Qt.ItemDataRole.UserRole, "true")
                    else:
                        game_item.setText(0, game_name)
                        game_item.setData(0, Qt.ItemDataRole.UserRole, "false")
                    break

    def tray_icon_activated(self, reason):
        print(reason)
        if reason == QSystemTrayIcon.ActivationReason.Trigger or reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            if self.isHidden() or not self.isActiveWindow():
                print("s")
                self.show()
                self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
                self.raise_()
                self.activateWindow()
            else:
                print("h")
                self.hide()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    def restart_application(self):
        script_path = os.path.abspath(__file__)
        subprocess.Popen([sys.executable, script_path])
        self.clean_exit()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = GameLauncher()
    if not HIDDEN_BY_DEFAULT:
        window.show()
    sys.exit(app.exec())