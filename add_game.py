import sys
import socket
import json
import os
import win32com.client

def resolve_shortcut(file_path):
    if file_path.lower().endswith(".lnk"):
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(file_path)
        return shortcut.Targetpath
    return file_path

def main():
    if len(sys.argv) < 2:
        print("No file provided")
        return

    file_path = sys.argv[1]
    
    actual_path = resolve_shortcut(file_path)
    
    if not actual_path.lower().endswith(".exe"):
        print("Not an executable file")
        return

    data = {
        "action": "add_game",
        "exe_path": actual_path,
        "name": os.path.splitext(os.path.basename(actual_path))[0]
    }

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("localhost", 12345))
        sock.send(json.dumps(data).encode())
        sock.close()
    except Exception as e:
        print(f"Failed to communicate with launcher: {e}")

if __name__ == "__main__":
    main()
