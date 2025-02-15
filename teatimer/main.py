import sys, ctypes, winsound
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QTimer
from pynput import keyboard
import threading
from pygame import mixer
import os

GetWindowLong = ctypes.windll.user32.GetWindowLongW
SetWindowLong = ctypes.windll.user32.SetWindowLongW
SetWindowPos = ctypes.windll.user32.SetWindowPos

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1

class TransparentWindow(QtWidgets.QMainWindow):
    def __init__(self, duration):
        super().__init__()
        self.duration = duration
        self.time_left = duration
        self.is_alarming = False
        self.flash_colors = ['#FFB6C1', '#98FB98']
        self.current_flash = 0
        self.initUI()
        
        self.altAlreadyPressed = False
        self.default_opacity = 0.2
        
        self.countdown_timer = QTimer()
        self.countdown_timer.timeout.connect(self.update_timer)
        self.countdown_timer.start(1000)
        
        self.flash_timer = QTimer()
        self.flash_timer.timeout.connect(self.flash_background)
        
        mixer.init()
        
        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint | 
            QtCore.Qt.FramelessWindowHint | 
            QtCore.Qt.Tool |
            QtCore.Qt.NoFocus
        )
        self.setWindowOpacity(self.default_opacity)
        self.make_click_through(True)
        
        self.keyboard_listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.keyboard_listener.start()

    def initUI(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)
        
        self.time_label = QtWidgets.QLabel()
        self.time_label.setStyleSheet('font-size: 24px; font-weight: bold;')
        self.update_time_display()
        
        self.close_button = QtWidgets.QPushButton('Cancel')
        self.close_button.clicked.connect(self.exit)
        
        layout.addWidget(self.time_label)
        layout.addWidget(self.close_button)
        
        self.resize(200, 150)
        self.move(-600, 300)
    
    def exit(self):
        self.countdown_timer.stop()
        self.flash_timer.stop()
        
        self.keyboard_listener.stop()
        
        mixer.music.stop()
        mixer.quit()
        
        self.close()
        
        sys.exit()

    def update_time_display(self):
        minutes = self.time_left // 60
        seconds = self.time_left % 60
        self.time_label.setText(f"{minutes:02d}:{seconds:02d}")

    def update_timer(self):
        if self.time_left > 0:
            self.time_left -= 1
            self.update_time_display()
        elif self.time_left == 0:
            self.time_left = -1  # Prevent multiple triggers
            self.timer_finished()

    def timer_finished(self):
        self.countdown_timer.stop()
        self.close_button.setText('Close')
        self.is_alarming = True
        self.make_click_through(False)
        self.setWindowOpacity(1)
        self.flash_timer.start(500)
        self.play_alarm()

    def play_alarm(self, audio_file="alarm.mp3"):
        if audio_file and os.path.exists(audio_file):
            mixer.music.load(audio_file)
            mixer.music.play()

            # Stop the alarm after 3 seconds
            timer = threading.Timer(3.0, mixer.music.stop)
            timer.start()
        else:
            for _ in range(3):
                winsound.Beep(1000, 500)

    def flash_background(self):
        if self.is_alarming:
            color = self.flash_colors[self.current_flash]
            self.setStyleSheet(f'background-color: {color};')
            self.current_flash = (self.current_flash + 1) % 2

    def make_click_through(self, click_through):
        hwnd = self.winId().__int__()
        style = GetWindowLong(hwnd, GWL_EXSTYLE)
        
        if click_through:
            style |= WS_EX_TRANSPARENT
        else:
            style &= ~WS_EX_TRANSPARENT
            
        SetWindowLong(hwnd, GWL_EXSTYLE, style)
        SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, 
                    SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

    def on_press(self, key):
        if key == keyboard.Key.alt_l and not self.altAlreadyPressed:
            self.altAlreadyPressed = True
            self.make_click_through(False)
            self.setWindowOpacity(1)

    def on_release(self, key):
        if key == keyboard.Key.alt_l and not self.is_alarming:
            self.altAlreadyPressed = False
            self.make_click_through(True)
            self.setWindowOpacity(self.default_opacity)

    def closeEvent(self, event):
        self.keyboard_listener.stop()
        event.accept()

def main():
    app = QtWidgets.QApplication(sys.argv)
    
    duration = 300
    if len(sys.argv) > 1:
        try:
            duration = int(sys.argv[1])
        except ValueError:
            print("Invalid duration. Using default 5 minutes.")
    
    window = TransparentWindow(duration)
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()